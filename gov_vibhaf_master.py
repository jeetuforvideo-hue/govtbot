import base64
import hashlib
import json
import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus, urljoin

import requests
from bs4 import BeautifulSoup

try:
    import pymupdf as fitz

    PYMUPDF_AVAILABLE = True
except ImportError:
    try:
        import fitz

        PYMUPDF_AVAILABLE = True
    except ImportError:
        PYMUPDF_AVAILABLE = False


# ==============================================================================
# 1. कॉन्फ़िगरेशन (FROM-NOW-ON CUTOFF + DRAFT + NO REPEAT + LIVE UPDATE)
# ==============================================================================
CONFIG = {
    "site_name": "GovtVibhag",
    "wp_site_url": os.getenv("WP_SITE_URL", "https://govtvibhag.com").strip().rstrip("/"),
    "wp_username": os.getenv("WP_USERNAME", "").strip(),
    "wp_app_password": os.getenv("WP_APP_PASSWORD", "").strip(),
    "wp_post_status": os.getenv("WP_POST_STATUS", "draft").strip().lower(),  # पहले चेक करने के लिए 'draft'
    "gemini_api_key": os.getenv("GEMINI_API_KEY", "").strip(),
    "gemini_model": os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip(),
    "db_path": os.getenv("DB_PATH", "scraped_data_cache/govtvibhag_from_now.db").strip(),
    "cache_dir": os.getenv("CACHE_DIR", "scraped_data_cache").strip(),
    "min_words": int(os.getenv("MIN_ARTICLE_WORDS", "1050")),
    "max_items_per_portal": int(os.getenv("MAX_ITEMS_PER_PORTAL", "6")),
    "max_new_posts_per_run": int(os.getenv("MAX_NEW_POSTS_PER_RUN", "8")),
    "max_updates_per_run": int(os.getenv("MAX_UPDATES_PER_RUN", "8")),
    "request_timeout": int(os.getenv("REQUEST_TIMEOUT", "20")),
    "enable_fallback": os.getenv("ENABLE_FALLBACK", "true").lower() == "true",
}

HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf;q=0.8,*/*;q=0.7",
    "Accept-Language": "hi-IN,hi;q=0.9,en-IN;q=0.8,en;q=0.7",
}


# ==============================================================================
# 2. आधिकारिक सरकारी पोर्टल्स (OFFICIAL GOVERNMENT PORTALS)
# ==============================================================================
GOVT_PORTALS = [
    {"url": "https://ssc.gov.in", "org": "Staff Selection Commission (SSC)", "short_org": "SSC"},
    {"url": "https://upsc.gov.in/whats-new", "org": "Union Public Service Commission (UPSC)", "short_org": "UPSC"},
    {"url": "https://indianrailways.gov.in", "org": "Ministry of Railways (Indian Railways)", "short_org": "Indian Railways"},
    {"url": "https://www.rrbcdg.gov.in", "org": "Railway Recruitment Board (RRB)", "short_org": "RRB"},
    {"url": "https://www.indiapost.gov.in", "org": "Department of Posts (India Post)", "short_org": "India Post"},
    {"url": "https://www.drdo.gov.in/drdo/whats-new", "org": "Defence Research and Development Organisation (DRDO)", "short_org": "DRDO"},
    {"url": "https://www.isro.gov.in/Careers.html", "org": "Indian Space Research Organisation (ISRO)", "short_org": "ISRO"},
    {"url": "https://nta.ac.in/NoticeBoardArchive", "org": "National Testing Agency (NTA)", "short_org": "NTA"},
    {"url": "https://ctet.nic.in", "org": "Central Board of Secondary Education (CBSE CTET)", "short_org": "CBSE CTET"},
    {"url": "https://kvsangathan.nic.in/en/announcement", "org": "Kendriya Vidyalaya Sangathan (KVS)", "short_org": "KVS"},
    {"url": "https://navodaya.gov.in", "org": "Navodaya Vidyalaya Samiti (NVS)", "short_org": "NVS"},
    {"url": "https://www.ibps.in", "org": "Institute of Banking Personnel Selection (IBPS)", "short_org": "IBPS"},
    {"url": "https://sbi.co.in/web/careers/current-openings", "org": "State Bank of India (SBI)", "short_org": "SBI"},
    {"url": "https://opportunities.rbi.org.in/Scripts/Vacancies.aspx", "org": "Reserve Bank of India (RBI)", "short_org": "RBI"},
    {"url": "https://licindia.in/Bottom-Links/Careers", "org": "Life Insurance Corporation of India (LIC)", "short_org": "LIC"},
    {"url": "https://joinindianarmy.nic.in", "org": "Indian Army", "short_org": "Indian Army"},
    {"url": "https://www.joinindiannavy.gov.in", "org": "Indian Navy", "short_org": "Indian Navy"},
    {"url": "https://agnipathvayu.cdac.in", "org": "Indian Air Force (Agniveer / CASB)", "short_org": "Indian Air Force"},
    {"url": "https://joinindiancoastguard.cdac.in", "org": "Indian Coast Guard (ICG)", "short_org": "Coast Guard"},
    {"url": "https://rect.crpf.gov.in", "org": "Central Reserve Police Force (CRPF)", "short_org": "CRPF"},
    {"url": "https://rectt.bsf.gov.in", "org": "Border Security Force (BSF)", "short_org": "BSF"},
    {"url": "https://cisfrectt.cisf.gov.in", "org": "Central Industrial Security Force (CISF)", "short_org": "CISF"},
    {"url": "https://recruitment.itbpolice.nic.in", "org": "Indo-Tibetan Border Police Force (ITBP)", "short_org": "ITBP"},
    {"url": "https://uppsc.up.nic.in", "org": "Uttar Pradesh Public Service Commission (UPPSC)", "short_org": "UPPSC"},
    {"url": "https://uppbpb.gov.in", "org": "Uttar Pradesh Police Recruitment Board (UPPRPB)", "short_org": "UP Police"},
    {"url": "https://upsssc.gov.in", "org": "Uttar Pradesh Subordinate Services Selection Commission (UPSSSC)", "short_org": "UPSSSC"},
    {"url": "https://dsssb.delhi.gov.in", "org": "Delhi Subordinate Services Selection Board (DSSSB)", "short_org": "DSSSB"},
    {"url": "https://bpsc.bih.nic.in", "org": "Bihar Public Service Commission (BPSC)", "short_org": "BPSC"},
    {"url": "https://bssc.bihar.gov.in", "org": "Bihar Staff Selection Commission (BSSC)", "short_org": "BSSC"},
    {"url": "https://csbc.bih.nic.in", "org": "Central Selection Board of Constable (CSBC Bihar)", "short_org": "CSBC Bihar"},
    {"url": "https://rpsc.rajasthan.gov.in/news", "org": "Rajasthan Public Service Commission (RPSC)", "short_org": "RPSC"},
    {"url": "https://rssb.rajasthan.gov.in/news", "org": "Rajasthan Staff Selection Board (RSSB)", "short_org": "RSSB Rajasthan"},
    {"url": "https://esb.mp.gov.in", "org": "Madhya Pradesh Employees Selection Board (MPESB)", "short_org": "MPESB"},
    {"url": "https://mppsc.mp.gov.in", "org": "Madhya Pradesh Public Service Commission (MPPSC)", "short_org": "MPPSC"},
    {"url": "https://hssc.gov.in", "org": "Haryana Staff Selection Commission (HSSC)", "short_org": "HSSC"},
    {"url": "https://gpsc.gujarat.gov.in", "org": "Gujarat Public Service Commission (GPSC)", "short_org": "GPSC"},
    {"url": "https://www.mpsc.gov.in", "org": "Maharashtra Public Service Commission (MPSC)", "short_org": "MPSC"},
    {"url": "https://tnpsc.gov.in", "org": "Tamil Nadu Public Service Commission (TNPSC)", "short_org": "TNPSC"},
]

STAGE_KEYWORDS = {
    "Result": [
        "result", "results", "merit list", "scorecard", "score card", "shortlisted",
        "selected candidates", "cut off", "cutoff", "final result", "रिजल्ट", "परिणाम", "मेरिट"
    ],
    "Answer Key": [
        "answer key", "ans key", "response sheet", "objection", "provisional key",
        "final key", "आंसर की", "उत्तर कुंजी"
    ],
    "Admit Card": [
        "admit card", "hall ticket", "call letter", "exam city", "city intimation",
        "admission certificate", "एडमिट कार्ड", "प्रवेश पत्र"
    ],
    "Jobs": [
        "recruitment", "vacancy", "vacancies", "notification", "advertisement", "advt",
        "apply online", "bharti", "employment", "opening", "भर्ती", "विज्ञप्ति", "आवेदन"
    ],
}

IGNORE_PHRASES = [
    "tender", "quotation", "auction", "deputation", "pension", "rti", "privacy policy",
    "disclaimer", "terms", "sitemap", "feedback", "accessibility", "citizen charter",
    "screen reader", "skip to main", "holiday list", "annual report", "contact us", "about us",
    "archive", "old notice", "previous year"
]

GENERIC_LABELS = {
    "click here", "download", "view", "pdf", "link", "notice", "read more",
    "more", "home", "login", "apply", "result", "admit card", "answer key"
}

MONTH_MAP = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}


# ==============================================================================
# 3. समय व डेटाबेस (IST TIME & SQLITE STATE)
# ==============================================================================
IST_TZ = timezone(timedelta(hours=5, minutes=30))


def now_ist_dt() -> datetime:
    return datetime.now(IST_TZ).replace(tzinfo=None)


def now_ist_str() -> str:
    return now_ist_dt().strftime("%d-%m-%Y %H:%M IST")


def current_year_str() -> str:
    return str(now_ist_dt().year)


def init_db() -> None:
    os.makedirs(CONFIG["cache_dir"], exist_ok=True)
    db_dir = os.path.dirname(CONFIG["db_path"])
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    conn = sqlite3.connect(CONFIG["db_path"])
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            topic_key TEXT PRIMARY KEY,
            portal_url TEXT,
            short_org TEXT,
            raw_title TEXT,
            seo_title TEXT,
            stage TEXT,
            stages_history TEXT,
            target_url TEXT,
            content_hash TEXT,
            word_count INTEGER DEFAULT 0,
            wp_post_id INTEGER DEFAULT 0,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS baseline_snapshot (
            notice_sig TEXT PRIMARY KEY,
            portal_url TEXT,
            raw_title TEXT,
            target_url TEXT,
            locked_at_iso TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS runtime_meta (
            meta_key TEXT PRIMARY KEY,
            meta_value TEXT
        )
    """)
    conn.commit()
    conn.close()


def get_or_lock_boot_time(current_boot_dt: datetime) -> tuple[datetime, bool]:
    """
    पहली बार बोट चालू करते ही समय लॉक करता है (is_first_boot = True)।
    बाद के रन्स में वही लॉक समय रहता है ताकि बोट चालू करने से पहले की चीज़ों पर नया आर्टिकल न बने।
    """
    conn = sqlite3.connect(CONFIG["db_path"])
    cur = conn.cursor()
    cur.execute("SELECT meta_value FROM runtime_meta WHERE meta_key = 'boot_started_iso'")
    row = cur.fetchone()
    if not row:
        cur.execute(
            "INSERT OR REPLACE INTO runtime_meta (meta_key, meta_value) VALUES ('boot_started_iso', ?)",
            (current_boot_dt.isoformat(),),
        )
        conn.commit()
        conn.close()
        return current_boot_dt, True
    conn.close()
    try:
        return datetime.fromisoformat(row[0]), False
    except Exception:
        return current_boot_dt, False


def is_in_baseline_snapshot(notice_sig: str) -> bool:
    conn = sqlite3.connect(CONFIG["db_path"])
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM baseline_snapshot WHERE notice_sig = ?", (notice_sig,))
    row = cur.fetchone()
    conn.close()
    return row is not None


def add_to_baseline_snapshot(notice_sig: str, portal_url: str, raw_title: str, target_url: str) -> None:
    iso_now = now_ist_dt().isoformat()
    conn = sqlite3.connect(CONFIG["db_path"])
    cur = conn.cursor()
    cur.execute(
        """INSERT OR IGNORE INTO baseline_snapshot (notice_sig, portal_url, raw_title, target_url, locked_at_iso)
           VALUES (?, ?, ?, ?, ?)""",
        (notice_sig, portal_url, raw_title[:200], target_url, iso_now),
    )
    conn.commit()
    conn.close()


def get_article_record(topic_key: str) -> dict | None:
    conn = sqlite3.connect(CONFIG["db_path"])
    cur = conn.cursor()
    cur.execute(
        """SELECT topic_key, portal_url, short_org, raw_title, seo_title, stage,
                  stages_history, target_url, content_hash, word_count, wp_post_id,
                  created_at, updated_at
           FROM articles WHERE topic_key = ?""",
        (topic_key,),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "topic_key": row[0],
        "portal_url": row[1],
        "short_org": row[2],
        "raw_title": row[3],
        "seo_title": row[4],
        "stage": row[5],
        "stages_history": json.loads(row[6] or "[]"),
        "target_url": row[7],
        "content_hash": row[8],
        "word_count": row[9],
        "wp_post_id": row[10],
        "created_at": row[11],
        "updated_at": row[12],
    }


def upsert_article_record(record: dict) -> None:
    conn = sqlite3.connect(CONFIG["db_path"])
    cur = conn.cursor()
    cur.execute(
        """INSERT OR REPLACE INTO articles
           (topic_key, portal_url, short_org, raw_title, seo_title, stage,
            stages_history, target_url, content_hash, word_count, wp_post_id,
            created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            record["topic_key"],
            record["portal_url"],
            record["short_org"],
            record["raw_title"],
            record["seo_title"],
            record["stage"],
            json.dumps(record["stages_history"], ensure_ascii=False),
            record["target_url"],
            record["content_hash"],
            record["word_count"],
            record["wp_post_id"],
            record["created_at"],
            record["updated_at"],
        ),
    )
    conn.commit()
    conn.close()


# ==============================================================================
# 4. टेक्स्ट सफ़ाई, चरण पहचान व टॉपिक की (TEXT CLEANING, STAGE & TOPIC KEY)
# ==============================================================================
def clean_text(text: str) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"[\ufffd\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", " ", text)
    cleaned = re.sub(r"\(cid:\d+\)", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def count_words_from_html(html_content: str) -> int:
    plain = BeautifulSoup(html_content or "", "html.parser").get_text(" ", strip=True)
    return len(re.findall(r"[A-Za-z0-9\u0900-\u097f]+", plain))


def detect_stage(text: str) -> str:
    low = (text or "").lower()
    for stage in ["Result", "Answer Key", "Admit Card", "Jobs"]:
        if any(kw in low for kw in STAGE_KEYWORDS[stage]):
            return stage
    return "Jobs"


def build_topic_key(short_org: str, title: str) -> str:
    stripped = re.sub(
        r"\b(admit card|hall ticket|call letter|exam city|answer key|ans key|response sheet|"
        r"result|results|merit list|scorecard|cut off|cutoff|notification|recruitment|"
        r"vacancy|vacancies|apply online|provisional|final|revised|corrigendum|2024|2025|2026|2027)\b",
        " ",
        (title or "").lower(),
        flags=re.IGNORECASE,
    )
    stripped = re.sub(r"[^a-z0-9\u0900-\u097f]+", " ", stripped)
    tokens = [t for t in stripped.split() if len(t) > 1][:6]
    core_slug = "_".join(tokens) if tokens else hashlib.md5(title.encode("utf-8")).hexdigest()[:10]
    raw_id = f"{short_org.lower().strip()}|{core_slug}"
    return hashlib.sha256(raw_id.encode("utf-8")).hexdigest()[:16]


def build_notice_signature(short_org: str, title: str, target_url: str) -> str:
    norm_t = re.sub(r"\s+", " ", (title or "").lower()).strip()
    norm_u = (target_url or "").strip().lower()
    return hashlib.sha256(f"{short_org.lower()}|{norm_t}|{norm_u}".encode("utf-8")).hexdigest()[:20]


def is_valid_notice_candidate(title: str, full_url: str) -> bool:
    low_t = (title or "").lower().strip()
    low_u = (full_url or "").lower().strip()

    if not low_t or len(low_t) < 12 or len(low_t.split()) < 3:
        return False
    if low_t in GENERIC_LABELS:
        return False
    if any(bad in low_t for bad in IGNORE_PHRASES):
        return False
    if low_u.startswith(("javascript:", "mailto:", "tel:")) or full_url.endswith("#"):
        return False

    all_stage_words = [w for words in STAGE_KEYWORDS.values() for w in words]
    return any(w in low_t or w in low_u for w in all_stage_words) or (".pdf" in low_u)


# ==============================================================================
# 5. लचीला HTTP फेचर + स्मार्ट बैकअप फ़ॉलबैक + "बोट चालू होने के बाद" जांच
# ==============================================================================
def fetch_url_flexible(url: str) -> requests.Response | None:
    try:
        resp = requests.get(
            url,
            headers=HTTP_HEADERS,
            timeout=CONFIG["request_timeout"],
            allow_redirects=True,
        )
        if 200 <= resp.status_code < 400 and (resp.content or b""):
            return resp
    except Exception:
        pass
    return None


def fetch_fallback_updates(portal_info: dict) -> list[dict]:
    results = []
    if not CONFIG["enable_fallback"]:
        return results

    short_org = portal_info["short_org"]
    portal_url = portal_info["url"]
    query = f'"{short_org}" (recruitment OR vacancy OR result OR "admit card" OR "answer key" OR notification) when:1d'
    rss_url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=hi-IN&gl=IN&ceid=IN:hi"

    resp = fetch_url_flexible(rss_url)
    if resp is None:
        return results

    try:
        soup = BeautifulSoup(resp.text, "xml")
        for entry in soup.find_all("item")[: CONFIG["max_items_per_portal"]]:
            title_el = entry.find("title")
            link_el = entry.find("link")
            pub_el = entry.find("pubDate")

            raw_title = clean_text(title_el.text if title_el else "")
            if " - " in raw_title:
                raw_title = raw_title.rsplit(" - ", 1)[0].strip()

            link_val = clean_text(link_el.text if link_el else "") or portal_url
            if not is_valid_notice_candidate(raw_title, link_val):
                continue

            pub_dt = None
            if pub_el and pub_el.text:
                try:
                    p_utc = parsedate_to_datetime(pub_el.text.strip())
                    pub_dt = (
                        p_utc.astimezone(IST_TZ).replace(tzinfo=None)
                        if p_utc.tzinfo
                        else p_utc + timedelta(hours=5, minutes=30)
                    )
                except Exception:
                    pub_dt = None

            stage = detect_stage(f"{raw_title} {link_val}")
            topic_key = build_topic_key(short_org, raw_title)
            notice_sig = build_notice_signature(short_org, raw_title, link_val)

            results.append({
                "notice_sig": notice_sig,
                "topic_key": topic_key,
                "portal_url": portal_url,
                "org": portal_info["org"],
                "short_org": short_org,
                "title": raw_title,
                "target_url": link_val,
                "stage": stage,
                "fallback_dt": pub_dt,
            })
    except Exception:
        pass

    return results


def parse_dt_safe(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime | None:
    try:
        if 2020 <= year <= 2030 and 1 <= month <= 12 and 1 <= day <= 31 and 0 <= hour <= 23 and 0 <= minute <= 59:
            return datetime(year, month, day, hour, minute)
    except Exception:
        return None
    return None


def extract_timestamp_details(
    raw_title: str,
    text_excerpt: str,
    pdf_meta_dt: datetime | None,
    http_last_mod_dt: datetime | None,
    fallback_dt: datetime | None = None,
) -> tuple[datetime | None, bool]:
    sample = f"{raw_title} {text_excerpt[:1500]}"

    m_dt_time = re.search(
        r"\b(\d{1,2})[./-](\d{1,2})[./-](202\d)\s+(\d{1,2}):(\d{2})(?:\s*(AM|PM))?\b",
        sample,
        flags=re.IGNORECASE,
    )
    if m_dt_time:
        d, mn, y = int(m_dt_time.group(1)), int(m_dt_time.group(2)), int(m_dt_time.group(3))
        hr, mins = int(m_dt_time.group(4)), int(m_dt_time.group(5))
        ampm = (m_dt_time.group(6) or "").upper()
        if ampm == "PM" and hr < 12:
            hr += 12
        elif ampm == "AM" and hr == 12:
            hr = 0
        dt = parse_dt_safe(y, mn, d, hr, mins)
        if dt:
            return dt, True

    explicit_patterns = [
        r"(?:dated|date|issued\s+on|published\s+on|दिनांक)\s*[:\-–]?\s*(\d{1,2})[./-](\d{1,2})[./-](202\d)",
        r"(?:dated|date|issued\s+on|published\s+on|दिनांक)\s*[:\-–]?\s*(\d{1,2})\s+([A-Za-z]{3,9})[,\s]+(202\d)",
    ]
    for pat in explicit_patterns:
        m = re.search(pat, sample, flags=re.IGNORECASE)
        if m:
            g1, g2, g3 = m.group(1), m.group(2), m.group(3)
            if g2.isdigit():
                dt = parse_dt_safe(int(g3), int(g2), int(g1), 0, 0)
            else:
                mon = MONTH_MAP.get(g2.lower())
                dt = parse_dt_safe(int(g3), mon, int(g1), 0, 0) if mon else None
            if dt:
                return dt, False

    if pdf_meta_dt:
        return pdf_meta_dt, True
    if http_last_mod_dt:
        return http_last_mod_dt, True
    if fallback_dt:
        return fallback_dt, True

    return None, False


def is_arrived_after_boot(details: dict, notice_sig: str, boot_cutoff_dt: datetime) -> tuple[bool, str]:
    """
    नियम:
    - बोट चालू होने के समय (boot_cutoff_dt) से पहले वेबसाइट पर जो भी था (baseline_snapshot में लॉक),
      उस पर नया आर्टिकल नहीं बनेगा।
    - यदि किसी नोटिस/PDF की स्पष्ट तारीख/समय बोट चालू होने के समय से पहले का है, तो भी नया आर्टिकल नहीं बनेगा।
    - बोट चालू होने के बाद आने वाले नए अपडेट्स पर आर्टिकल बनेगा।
    """
    if is_in_baseline_snapshot(notice_sig):
        return False, "बोट चालू करने से पहले का डाटा (Baseline में लॉक)"

    det_dt = details.get("detected_dt")
    has_exact_time = bool(details.get("has_exact_time"))

    if det_dt is not None:
        if has_exact_time and det_dt < boot_cutoff_dt:
            return False, f"बोट चालू होने ({boot_cutoff_dt.strftime('%d-%m-%Y %H:%M')}) से पहले का अपडेट"
        if not has_exact_time and det_dt.date() < boot_cutoff_dt.date():
            return False, f"बोट चालू होने की तारीख से पहले का नोटिस ({det_dt.strftime('%d-%m-%Y')})"

    return True, "बोट चालू होने के बाद आया नया अपडेट"


def extract_context_details(raw_title: str, target_url: str, fallback_dt: datetime | None = None) -> dict:
    details = {
        "doc_type": "Official Notice Link",
        "text_excerpt": "",
        "headings": [],
        "vacancy_info": "आधिकारिक नोटिफिकेशन के अनुसार",
        "qualification_info": "पद के अनुसार आधिकारिक सूचना में देखें",
        "age_info": "नोटिफिकेशन के अनुसार निर्धारित आयु सीमा",
        "fee_info": "श्रेणी व पद के अनुसार आधिकारिक नोटिस देखें",
        "dates_info": "आधिकारिक सूचना के अनुसार",
        "detected_dt": None,
        "has_exact_time": False,
    }

    resp = fetch_url_flexible(target_url)
    http_last_mod_dt = None
    extracted_text = ""
    headings = []
    pdf_meta_dt = None

    if resp is not None:
        if resp.headers.get("Last-Modified"):
            try:
                lm_utc = parsedate_to_datetime(resp.headers["Last-Modified"])
                http_last_mod_dt = (
                    lm_utc.astimezone(IST_TZ).replace(tzinfo=None)
                    if lm_utc.tzinfo
                    else lm_utc + timedelta(hours=5, minutes=30)
                )
            except Exception:
                pass

        ctype = (resp.headers.get("Content-Type") or "").lower()
        is_pdf = target_url.lower().endswith(".pdf") or "application/pdf" in ctype or (resp.content or b"").startswith(b"%PDF")

        if is_pdf and PYMUPDF_AVAILABLE and len(resp.content or b"") >= 300:
            details["doc_type"] = "Official PDF"
            pdf_tmp = os.path.join(CONFIG["cache_dir"], "inspect_notice.pdf")
            try:
                with open(pdf_tmp, "wb") as f:
                    f.write(resp.content)

                doc = fitz.open(pdf_tmp)
                meta = doc.metadata or {}
                raw_d = str(meta.get("modDate") or meta.get("creationDate") or "")
                m_d = re.search(r"D:(\d{4})(\d{2})(\d{2})(\d{2})?(\d{2})?", raw_d)
                if m_d:
                    y, mn, d = int(m_d.group(1)), int(m_d.group(2)), int(m_d.group(3))
                    hr = int(m_d.group(4)) if m_d.group(4) else 0
                    mins = int(m_d.group(5)) if m_d.group(5) else 0
                    dt_utc = parse_dt_safe(y, mn, d, hr, mins)
                    if dt_utc:
                        pdf_meta_dt = dt_utc + timedelta(hours=5, minutes=30) if (m_d.group(4) or m_d.group(5)) else dt_utc

                lines = []
                for p_idx in range(min(8, len(doc))):
                    page_txt = doc[p_idx].get_text("text") or ""
                    for ln in page_txt.splitlines():
                        cl = clean_text(ln)
                        if cl:
                            lines.append(cl)
                            if 6 <= len(cl) <= 75 and re.match(
                                r"^(?:\d+[\.\)]\s*)?(?:important\s+dates|vacanc(?:y|ies)|eligibility|qualification|age\s+limit|application\s+fee|selection|how\s+to\s+apply|cut[\s-]*off|result|admit\s+card|answer\s+key)",
                                cl,
                                flags=re.IGNORECASE,
                            ):
                                if cl not in headings:
                                    headings.append(cl)
                doc.close()
                extracted_text = " ".join(lines)
            except Exception:
                pass
        else:
            details["doc_type"] = "Official Web Notice"
            try:
                soup = BeautifulSoup(resp.text, "html.parser")
                for h in soup.find_all(["h1", "h2", "h3", "th"]):
                    ht = clean_text(h.get_text(" ", strip=True))
                    if 6 <= len(ht) <= 75 and ht not in headings:
                        headings.append(ht)
                for tag in soup(["script", "style", "nav", "footer", "header"]):
                    tag.decompose()
                extracted_text = clean_text(soup.get_text(" ", strip=True))
            except Exception:
                pass

    details["headings"] = headings[:6]
    details["text_excerpt"] = extracted_text[:4500]

    det_dt, exact_tm = extract_timestamp_details(
        raw_title=raw_title,
        text_excerpt=extracted_text,
        pdf_meta_dt=pdf_meta_dt,
        http_last_mod_dt=http_last_mod_dt,
        fallback_dt=fallback_dt,
    )
    details["detected_dt"] = det_dt
    details["has_exact_time"] = exact_tm

    vac_m = re.search(
        r"(?:total\s+vacanc(?:y|ies)|total\s+posts?|no\.?\s*of\s+posts?|कुल\s+पद)\s*[:\-–]?\s*(\d{1,6})",
        extracted_text,
        flags=re.IGNORECASE,
    )
    if vac_m:
        details["vacancy_info"] = f"{vac_m.group(1)} पद (आधिकारिक नोटिस के अनुसार)"

    age_m = re.search(
        r"(?:age\s+limit|आयु\s+सीमा)[^\n\.]{0,80}?(\d{2})\s*(?:to|\-|से)\s*(\d{2})\s*(?:years|वर्ष|yrs)",
        extracted_text,
        flags=re.IGNORECASE,
    )
    if age_m:
        details["age_info"] = f"{age_m.group(1)} से {age_m.group(2)} वर्ष (नोटिफिकेशन के नियमानुसार)"

    qual_found = []
    for pat, label in [
        (r"\b10th|matric|high\s*school\b", "10वीं"),
        (r"\b12th|intermediate|higher\s*secondary\b", "12वीं"),
        (r"\biti\b", "ITI"),
        (r"\bdiploma\b", "डिप्लोमा"),
        (r"\bgraduate|graduation|bachelor|degree|b\.tech|b\.sc|b\.a|b\.com\b", "स्नातक"),
        (r"\bpost\s*graduate|master|m\.sc|m\.a|m\.tech\b", "स्नातकोत्तर"),
        (r"\bb\.ed|ctet|tet\b", "B.Ed / TET"),
    ]:
        if re.search(pat, extracted_text, flags=re.IGNORECASE):
            qual_found.append(label)
    if qual_found:
        details["qualification_info"] = ", ".join(qual_found[:3]) + " (पदानुसार नोटिस देखें)"

    fee_m = re.search(
        r"(?:application\s+fee|fee|आवेदन\s+शुल्क)[^\n\.]{0,70}?(?:rs\.?|₹|inr)\s*(\d{1,4})",
        extracted_text,
        flags=re.IGNORECASE,
    )
    if fee_m:
        details["fee_info"] = f"₹{fee_m.group(1)} (श्रेणीवार छूट व नियम नोटिस में देखें)"

    date_list = re.findall(
        r"\b\d{1,2}[./-]\d{1,2}[./-]202[5-7]|\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+202[5-7]",
        extracted_text,
        flags=re.IGNORECASE,
    )
    if date_list:
        unique_dates = []
        for d in date_list:
            if d not in unique_dates:
                unique_dates.append(d)
        details["dates_info"] = ", ".join(unique_dates[:4])

    return details


# ==============================================================================
# 6. सर्च-फ्रेंडली SEO टाइटल व प्रोफेशनल 1000+ वर्ड आर्टिकल बिल्डर
# ==============================================================================
def build_search_friendly_title(short_org: str, raw_title: str, stage: str) -> str:
    yr = current_year_str()
    cleaned = re.sub(r"\.pdf$|\.html$|\.aspx$", "", clean_text(raw_title), flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(click here|download|view|new|latest|notice|notification)\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -–|:")

    words = []
    for w in cleaned.split():
        token = w.strip("()[]\"',.")
        if len(token) >= 2 and token.lower() not in {"the", "of", "for", "and", "in", "on", "to"}:
            words.append(token)
    topic_short = " ".join(words[:6]) if words else cleaned[:55]

    if short_org.lower() not in topic_short.lower():
        base_subject = f"{short_org} {topic_short}".strip()
    else:
        base_subject = topic_short

    deduped = []
    for w in base_subject.split():
        if not deduped or deduped[-1].lower() != w.lower():
            deduped.append(w)
    subject = " ".join(deduped)[:72].strip()

    if stage == "Result":
        return f"{subject} Result {yr}: कैसे चेक करें और मेरिट लिस्ट देखें"
    if stage == "Admit Card":
        return f"{subject} Admit Card {yr}: डाउनलोड लिंक और परीक्षा निर्देश"
    if stage == "Answer Key":
        return f"{subject} Answer Key {yr}: उत्तर मिलान और आपत्ति प्रक्रिया"
    return f"{subject} Recruitment {yr}: योग्यता, तिथियां और आवेदन विवरण"


def call_gemini_writer(prompt: str) -> str:
    api_key = CONFIG["gemini_api_key"]
    if not api_key:
        return ""
    try:
        endpoint = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{CONFIG['gemini_model']}:generateContent?key={api_key}"
        )
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        resp = requests.post(endpoint, json=payload, timeout=45)
        if resp.status_code == 200:
            raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            raw = re.sub(r"^```html\s*|\s*```$", "", raw, flags=re.IGNORECASE).strip()
            return raw
    except Exception as e:
        print(f"   [WARN] Gemini लेखन उपलब्ध नहीं हो सका: {e}")
    return ""


def build_stage_core_html(portal_info: dict, raw_title: str, target_url: str, stage: str, details: dict) -> str:
    org = portal_info["org"]
    short_org = portal_info["short_org"]
    portal_url = portal_info["url"]
    updated_now = now_ist_str()

    overview_table = f"""
<h2>मुख्य विवरण (Overview)</h2>
<p>नीचे दी गई तालिका में <strong>{short_org}</strong> से जुड़े इस <strong>{stage}</strong> अपडेट की मुख्य जानकारियां संक्षेप में दी गई हैं। किसी भी निर्णय या आवेदन से पहले आधिकारिक सूचना अवश्य जांचें।</p>
<table border="1" cellpadding="8" cellspacing="0" width="100%" style="border-collapse:collapse;">
  <tbody>
    <tr>
      <td><strong>विभाग / संस्था</strong></td>
      <td>{org}</td>
    </tr>
    <tr>
      <td><strong>अपडेट का प्रकार</strong></td>
      <td>{stage} ({details['doc_type']})</td>
    </tr>
    <tr>
      <td><strong>मूल सूचना / शीर्षक</strong></td>
      <td>{raw_title}</td>
    </tr>
    <tr>
      <td><strong>पद / वैकेंसी विवरण</strong></td>
      <td>{details['vacancy_info']}</td>
    </tr>
    <tr>
      <td><strong>पात्रता व आयु सीमा</strong></td>
      <td>{details['qualification_info']} | {details['age_info']}</td>
    </tr>
    <tr>
      <td><strong>शुल्क व तिथियां</strong></td>
      <td>{details['fee_info']} | तिथियां: {details['dates_info']}</td>
    </tr>
    <tr>
      <td><strong>Current Status</strong></td>
      <td><strong>{stage}</strong> — ताज़ा आधिकारिक अपडेट</td>
    </tr>
    <tr>
      <td><strong>Last Updated</strong></td>
      <td>{updated_now}</td>
    </tr>
  </tbody>
</table>
"""

    if stage == "Result":
        stage_body = f"""
<h2>रिजल्ट और मेरिट से जुड़ी मुख्य बातें</h2>
<p><strong>{short_org}</strong> से संबंधित यह <strong>Result</strong> अपडेट उम्मीदवारों के लिए महत्वपूर्ण है। परिणाम से जुड़े नोटिस या लिंक आने के बाद अभ्यर्थियों को अपने रोल नंबर, रजिस्ट्रेशन नंबर और जन्मतिथि के साथ आधिकारिक पोर्टल पर विवरण जांचना चाहिए।</p>
<p>परिणाम देखते समय केवल आधिकारिक स्रोत पर उपलब्ध सूची या स्कोरकार्ड को ही मान्य मानें। किसी भी अनधिकृत लिंक या अफवाह से बचें।</p>
<ul>
  <li><strong>व्यक्तिगत विवरण जांचें:</strong> स्कोरकार्ड या सूची में नाम, रोल नंबर, श्रेणी और प्राप्तांक/स्थिति का मिलान करें।</li>
  <li><strong>अगले चरण की तैयारी:</strong> चयन या शॉर्टलिस्ट होने पर दस्तावेज़ सत्यापन (DV), साक्षात्कार या अगले चरण के निर्देश पढ़ें।</li>
  <li><strong>रिकॉर्ड सुरक्षित रखें:</strong> स्कोरकार्ड या मेरिट से जुड़ी प्रति को भविष्य के संदर्भ के लिए सेव कर लें।</li>
</ul>

<h2>परिणाम कैसे चेक करें?</h2>
<p>मोबाइल या कंप्यूटर से परिणाम देखने के लिए नीचे दिए गए सरल चरणों का पालन करें:</p>
<ol>
  <li>आधिकारिक पोर्टल या इस लेख में दिए गए संबंधित लिंक पर जाएं।</li>
  <li><strong>{raw_title}</strong> से जुड़े रिजल्ट या मेरिट लिंक को खोलें।</li>
  <li>आवश्यक रोल नंबर/रजिस्ट्रेशन विवरण भरें या पीडीएफ में अपना विवरण खोजें।</li>
  <li>आगे की प्रक्रिया के लिए विवरण सुरक्षित रखें।</li>
</ol>
"""
    elif stage == "Admit Card":
        stage_body = f"""
<h2>एडमिट कार्ड और परीक्षा निर्देश</h2>
<p><strong>{short_org}</strong> के इस <strong>Admit Card</strong> अपडेट के अंतर्गत उम्मीदवारों को परीक्षा तिथि, शिफ्ट, परीक्षा केंद्र और आवश्यक निर्देशों से जुड़ी जानकारी मिलती है। एडमिट कार्ड डाउनलोड करने से पहले लॉगिन विवरण तैयार रखें।</p>
<p>परीक्षा केंद्र पर जाने से पहले प्रवेश पत्र में दर्ज विवरणों की जांच करें और निर्धारित समय से पहले केंद्र पर पहुंचने की योजना बनाएं।</p>
<ul>
  <li><strong>विवरणों का मिलान:</strong> नाम, फोटो, हस्ताक्षर, परीक्षा केंद्र और रिपोर्टिंग समय ध्यान से देखें।</li>
  <li><strong>आवश्यक सामग्री:</strong> एडमिट कार्ड का प्रिंट, वैध मूल फोटो पहचान पत्र और निर्देशानुसार दस्तावेज़ साथ रखें।</li>
  <li><strong>प्रतिबंधित वस्तुएं:</strong> परीक्षा कक्ष में निषिद्ध सामग्री ले जाने से बचें और नियमों का पालन करें।</li>
</ul>

<h2>एडमिट कार्ड कैसे डाउनलोड करें?</h2>
<p>प्रवेश पत्र डाउनलोड करने के लिए नीचे दिए गए चरण देखें:</p>
<ol>
  <li>आधिकारिक लिंक खोलें और एडमिट कार्ड / लॉगिन अनुभाग पर जाएं।</li>
  <li>अपना रजिस्ट्रेशन/आवेदन नंबर और जन्मतिथि या पासवर्ड दर्ज करें।</li>
  <li>कैप्चा कोड भरकर विवरण सबमिट करें।</li>
  <li>प्रवेश पत्र डाउनलोड करें और साफ प्रिंटआउट निकाल लें।</li>
</ol>
"""
    elif stage == "Answer Key":
        stage_body = f"""
<h2>आंसर की और उत्तर मिलान की जानकारी</h2>
<p><strong>{short_org}</strong> से जुड़े इस <strong>Answer Key</strong> अपडेट की मदद से उम्मीदवार अपनी परीक्षा के संभावित अंकों का अनुमान लगा सकते हैं। उत्तर मिलान करते समय प्रश्न सेट, शिफ्ट और मार्किंग नियमों का ध्यान रखना जरूरी है।</p>
<p>यदि संबंधित सूचना में आपत्ति (Objection) दर्ज करने का प्रावधान दिया गया है, तो निर्धारित समय-सीमा और नियमों के अनुसार ही कदम उठाएं।</p>
<ul>
  <li><strong>सही मिलान:</strong> प्रश्न संख्या या प्रश्न आईडी के अनुसार उत्तरों का मिलान करें।</li>
  <li><strong>अंक गणना:</strong> सही उत्तर और नेगेटिव मार्किंग (यदि लागू हो) के नियमों को ध्यान में रखें।</li>
  <li><strong>आपत्ति विंडो:</strong> किसी प्रश्न पर आपत्ति होने पर अंतिम तिथि से पहले आधिकारिक माध्यम से प्रक्रिया पूरी करें।</li>
</ul>

<h2>आंसर की कैसे देखें?</h2>
<p>आंसर की या उससे जुड़ी सूचना देखने के लिए नीचे दिए गए चरण अपनाएं:</p>
<ol>
  <li>आधिकारिक पोर्टल या नीचे दिए गए संबंधित लिंक पर क्लिक करें।</li>
  <li><strong>{raw_title}</strong> से जुड़ा सेक्शन या पीडीएफ खोलें।</li>
  <li>अपने उत्तरों का मिलान करें और आवश्यकता होने पर फाइल सेव कर लें।</li>
</ol>
"""
    else:
        stage_body = f"""
<h2>भर्ती और आवेदन से जुड़ी मुख्य बातें</h2>
<p><strong>{short_org}</strong> के इस <strong>Jobs</strong> अपडेट के माध्यम से उम्मीदवारों को भर्ती, पद, पात्रता और आवेदन से जुड़ी महत्वपूर्ण जानकारी मिलती है। आवेदन करने से पहले आधिकारिक अधिसूचना को पूरा पढ़ना सबसे जरूरी है।</p>
<p>अंतिम तिथि के समय वेबसाइट पर ट्रैफिक बढ़ सकता है, इसलिए पात्रता सुनिश्चित करने के बाद समय रहते आवेदन प्रक्रिया पूरी करना उचित रहता है।</p>
<ul>
  <li><strong>पात्रता की जांच:</strong> शैक्षणिक योग्यता, आयु सीमा और अनुभव (यदि लागू हो) की शर्तें मिलाएं।</li>
  <li><strong>दस्तावेज़ व फोटो:</strong> आवेदन से पहले आवश्यक प्रमाणपत्र, फोटो और हस्ताक्षर तैयार रखें।</li>
  <li><strong>फीस व सबमिशन:</strong> शुल्क भुगतान और अंतिम सबमिशन के बाद कन्फर्मेशन प्रति सुरक्षित रखें।</li>
</ul>

<h2>आवेदन कैसे करें?</h2>
<p>ऑनलाइन आवेदन प्रक्रिया को सही तरीके से पूरा करने के लिए नीचे दिए गए चरण देखें:</p>
<ol>
  <li>आधिकारिक वेबसाइट (<a href="{portal_url}" target="_blank" rel="noopener noreferrer">{portal_url}</a>) या संबंधित लिंक पर जाएं।</li>
  <li>नोटिफिकेशन में दिए गए निर्देशों के अनुसार रजिस्ट्रेशन करें।</li>
  <li>आवेदन फॉर्म में सही विवरण भरें और आवश्यक दस्तावेज़ अपलोड करें।</li>
  <li>निर्धारित शुल्क जमा करें और अंतिम फॉर्म का प्रिंट या पीडीएफ सुरक्षित रखें।</li>
</ol>
"""

    headings_section = ""
    if details.get("headings"):
        h_bullets = "".join(
            f"<li><strong>{clean_text(h)}:</strong> आधिकारिक सूचना का यह हिस्सा उम्मीदवारों के लिए महत्वपूर्ण नियम व विवरण दर्शाता है।</li>"
            for h in details["headings"][:5]
        )
        headings_section = f"""
<h2>आधिकारिक सूचना के प्रमुख खंड</h2>
<p>मूल दस्तावेज़ या पेज में पाए गए प्रमुख अनुभाग नीचे दिए गए हैं ताकि आपको विस्तृत जानकारी ढूंढने में आसानी हो:</p>
<ul>
  {h_bullets}
</ul>
"""

    links_and_faq = f"""
{headings_section}
<h2>महत्वपूर्ण लिंक्स</h2>
<table border="1" cellpadding="8" cellspacing="0" width="100%" style="border-collapse:collapse;">
  <tbody>
    <tr>
      <td><strong>संबंधित आधिकारिक लिंक / सूचना</strong></td>
      <td><a href="{target_url}" target="_blank" rel="noopener noreferrer">आधिकारिक लिंक खोलें</a></td>
    </tr>
    <tr>
      <td><strong>आधिकारिक वेबसाइट ({short_org})</strong></td>
      <td><a href="{portal_url}" target="_blank" rel="noopener noreferrer">{org}</a></td>
    </tr>
  </tbody>
</table>

<h2>अक्सर पूछे जाने वाले प्रश्न (FAQs)</h2>
<p><strong>प्रश्न 1: इस {stage} अपडेट की आधिकारिक पुष्टि कहाँ से करें?</strong><br>
उत्तर: इस अपडेट की सबसे प्रामाणिक और अंतिम पुष्टि <strong>{org}</strong> की आधिकारिक वेबसाइट (<a href="{portal_url}" target="_blank" rel="noopener noreferrer">{portal_url}</a>) और संबंधित आधिकारिक सूचना से ही करें।</p>

<p><strong>प्रश्न 2: क्या इस पोस्ट में आगे भी बदलाव किया जा सकता है?</strong><br>
उत्तर: हाँ, यदि इस भर्ती या परीक्षा से जुड़ा नया चरण, तिथि या लिंक सामने आता है, तो उसी पोस्ट को ताज़ा स्थिति और <strong>Last Updated</strong> समय के साथ अपडेट किया जाता है।</p>

<p><strong>प्रश्न 3: लिंक खुलने में देरी हो या सर्वर स्लो चले तो क्या करें?</strong><br>
उत्तर: पोर्टल पर अधिक लोड होने पर पेज खुलने में समय लग सकता है। ऐसे में कुछ समय बाद पुनः प्रयास करें और इंटरनेट कनेक्शन जांचें।</p>

<p><strong>प्रश्न 4: क्या केवल इस लेख के आधार पर अंतिम निर्णय लेना चाहिए?</strong><br>
उत्तर: यह लेख उम्मीदवारों की सुविधा के लिए तैयार किया गया है; आवेदन, परीक्षा, आपत्ति या परिणाम से जुड़ा अंतिम निर्णय हमेशा आधिकारिक अधिसूचना के अनुसार ही लें।</p>
"""

    return f"""<p><strong>{raw_title}</strong> से जुड़ा यह अपडेट <strong>{org}</strong> के आधिकारिक स्रोत से प्राप्त किया गया है। यह लेख <strong>{stage}</strong> श्रेणी के अंतर्गत तैयार किया गया है ताकि उम्मीदवारों को मुख्य बिंदु, नियम और आधिकारिक लिंक एक ही स्थान पर स्पष्ट रूप से मिल सकें।</p>
{overview_table}
{stage_body}
{links_and_faq}""".strip()


def ensure_minimum_words(html_content: str, portal_info: dict, raw_title: str, stage: str, min_words: int) -> str:
    short_org = portal_info["short_org"]
    org = portal_info["org"]

    extra_sections = [
        f"""
<h2>उम्मीदवारों के लिए व्यावहारिक तैयारी और सावधानियां</h2>
<p>सरकारी परीक्षाओं और भर्तियों की प्रक्रिया में सही समय पर सही जानकारी होना बहुत बड़ा अंतर पैदा करता है। <strong>{short_org}</strong> से जुड़े इस <strong>{stage}</strong> अपडेट के दौरान उम्मीदवारों को जल्दबाजी के बजाय व्यवस्थित तरीके से आगे बढ़ना चाहिए।</p>
<p>अक्सर अभ्यर्थी किसी एक सूचना को पढ़कर बाकी नियमों को नज़रअंदाज़ कर देते हैं, जिससे आगे चलकर फॉर्म रिजेक्शन, लॉगिन समस्या या दस्तावेज़ मिलान में कठिनाई होती है। इसलिए हर निर्देश को शांत मन से पढ़ना और समझना बेहद ज़रूरी है।</p>
<ul>
  <li><strong>सही विवरण दर्ज करें:</strong> नाम, जन्मतिथि, श्रेणी और रजिस्ट्रेशन नंबर जैसी जानकारी में अंतर न होने दें।</li>
  <li><strong>आधिकारिक स्रोतों पर भरोसा करें:</strong> अनौपचारिक समूहों या अधूरी पोस्ट्स के बजाय केवल आधिकारिक पोर्टल के निर्देश मानें।</li>
  <li><strong>दस्तावेज़ों का बैकअप रखें:</strong> महत्वपूर्ण फॉर्म, प्रवेश पत्र, स्कोरकार्ड और रसीदों की डिजिटल व प्रिंट प्रति सुरक्षित रखें।</li>
</ul>
""",
        f"""
<h2>समय प्रबंधन और आगे के चरणों की योजना</h2>
<p>चाहे आप आवेदन कर रहे हों, परीक्षा की तैयारी कर रहे हों, उत्तर कुंजी मिला रहे हों या परिणाम व अगले राउंड की प्रतीक्षा कर रहे हों—एक स्पष्ट योजना आपकी तैयारी को मजबूत बनाती है। <strong>{org}</strong> की प्रक्रिया में प्रत्येक चरण के लिए तय नियम और समय-सीमा निर्धारित होती है।</p>
<p>यदि किसी चरण में दस्तावेज़ सत्यापन, कौशल परीक्षण, शारीरिक मापदंड या साक्षात्कार शामिल है, तो उसके लिए आवश्यक प्रमाणपत्र पहले से तैयार रखना समझदारी भरा कदम है। इससे अंतिम समय की भागदौड़ से बचा जा सकता है।</p>
<ul>
  <li><strong>नियमित जांच:</strong> आधिकारिक वेबसाइट पर आने वाले नए नोटिस, संशोधनों या शेड्यूल पर नज़र रखें।</li>
  <li><strong>स्पष्ट नोट्स बनाएं:</strong> महत्वपूर्ण तिथियां, रजिस्ट्रेशन विवरण और निर्देश एक जगह नोट रखें।</li>
  <li><strong>सटीक मार्गदर्शन:</strong> किसी भी नियम को लेकर संदेह होने पर मूल अधिसूचना का संबंधित पैराग्राफ दोबारा पढ़ें।</li>
</ul>
""",
    ]

    result_html = html_content
    idx = 0
    while count_words_from_html(result_html) < min_words and idx < len(extra_sections):
        result_html = f"{result_html}\n{extra_sections[idx]}"
        idx += 1

    counter = 1
    while count_words_from_html(result_html) < min_words:
        result_html += (
            f"\n<p><strong>अतिरिक्त मार्गदर्शन ({counter}):</strong> {short_org} के इस {stage} अपडेट "
            f"({raw_title}) से संबंधित उम्मीदवारों को सलाह दी जाती है कि वे आवेदन, परीक्षा, उत्तर मिलान "
            f"या परिणाम जांचने से पूर्व आधिकारिक पोर्टल पर प्रकाशित सभी शर्तों व निर्देशों की पुष्टि "
            f"अवश्य करें तथा अपनी लॉगिन व दस्तावेज़ संबंधी जानकारी सुरक्षित रखें।</p>"
        )
        counter += 1

    return result_html.strip()


def build_complete_article(
    portal_info: dict,
    raw_title: str,
    target_url: str,
    stage: str,
    details: dict,
    is_live_update: bool = False,
    stages_history: list | None = None,
) -> tuple[str, str, int]:
    seo_title = build_search_friendly_title(portal_info["short_org"], raw_title, stage)
    base_html = build_stage_core_html(portal_info, raw_title, target_url, stage, details)

    if is_live_update and stages_history:
        flow_txt = " &rarr; ".join(stages_history)
        update_box = (
            f"<p><strong>लाइव अपडेट नोट:</strong> इस पोस्ट को उसी विषय/आर्टिकल पर नए चरण या जानकारी के अनुसार "
            f"अपडेट किया गया है (चरण इतिहास: <strong>{flow_txt}</strong>)। वर्तमान में <strong>{stage}</strong> "
            f"से जुड़ी जानकारी को प्राथमिकता दी गई है।</p>\n"
        )
        base_html = f"{update_box}{base_html}"

    if CONFIG["gemini_api_key"]:
        prompt = f"""
आप एक प्रोफेशनल हिंदी कंटेंट राइटर हैं जो सरकारी भर्ती, एडमिट कार्ड, आंसर की और रिजल्ट के लिए स्पष्ट, भरोसेमंद और पढ़ने में आसान लेख लिखते हैं।
नीचे दिए गए आधारभूत HTML कंटेंट को बेहतर और स्वाभाविक हिंदी में सुधारें/विस्तार दें ताकि यह कम से कम {CONFIG['min_words']} शब्दों का हो।

नियम:
- केवल शुद्ध HTML (`<h2>`, `<h3>`, `<p>`, `<ul>`, `<ol>`, `<table>`, `<tr>`, `<td>`, `<strong>`, `<a>`) दें, markdown ``` न लगाएं।
- पैराग्राफ छोटे और स्पष्ट रखें, साथ में बुलेट पॉइंट्स और टेबल बनाए रखें।
- बिना किसी आधार के कोई काल्पनिक तारीख, पद संख्या या दावा न जोड़ें; जो तथ्य उपलब्ध नहीं हैं, वहाँ "आधिकारिक सूचना के अनुसार" लिखें।
- {stage} चरण की जानकारी को स्पष्ट व व्यवस्थित रखें।

शीर्षक: {seo_title}
विभाग: {portal_info['org']}
चरण: {stage}

आधारभूत HTML:
{base_html[:6500]}
"""
        ai_html = call_gemini_writer(prompt)
        if ai_html and count_words_from_html(ai_html) >= 700:
            final_html = ensure_minimum_words(ai_html, portal_info, raw_title, stage, CONFIG["min_words"])
            return seo_title, final_html, count_words_from_html(final_html)

    final_html = ensure_minimum_words(base_html, portal_info, raw_title, stage, CONFIG["min_words"])
    return seo_title, final_html, count_words_from_html(final_html)


# ==============================================================================
# 7. WORDPRESS पब्लिश व लाइव अपडेट (DRAFT BY DEFAULT FOR YOUR REVIEW)
# ==============================================================================
def push_to_wordpress(title: str, html_content: str, wp_post_id: int = 0) -> tuple[bool, int, str]:
    preview_file = os.path.join(CONFIG["cache_dir"], "last_generated_article.html")
    with open(preview_file, "w", encoding="utf-8") as f:
        f.write(f"<h1>{title}</h1>\n{html_content}")

    if not (CONFIG["wp_site_url"] and CONFIG["wp_username"] and CONFIG["wp_app_password"]):
        sim_id = wp_post_id if wp_post_id > 0 else int(hashlib.md5(title.encode("utf-8")).hexdigest()[:6], 16)
        print(f"   [DRY-RUN WP] {'UPDATE' if wp_post_id > 0 else 'CREATE'} -> {title} ({count_words_from_html(html_content)} words)")
        return True, sim_id, f"{CONFIG['wp_site_url']}/?p={sim_id}"

    clean_pass = CONFIG["wp_app_password"].replace(" ", "")
    token = base64.b64encode(f"{CONFIG['wp_username']}:{clean_pass}".encode("utf-8")).decode("utf-8")
    headers = {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json",
        "User-Agent": HTTP_HEADERS["User-Agent"],
    }

    status_to_use = CONFIG["wp_post_status"] if CONFIG["wp_post_status"] in ("draft", "publish", "pending", "private") else "draft"
    payload = {
        "title": title,
        "content": html_content,
        "status": status_to_use,
    }

    base_endpoint = f"{CONFIG['wp_site_url']}/wp-json/wp/v2/posts"
    endpoint = f"{base_endpoint}/{wp_post_id}" if wp_post_id > 0 else base_endpoint

    try:
        resp = requests.post(endpoint, headers=headers, json=payload, timeout=25)
        resp.raise_for_status()
        data = resp.json()
        post_id = int(data.get("id") or wp_post_id or 0)
        post_link = str(data.get("link") or "")
        return True, post_id, post_link
    except Exception as e:
        print(f"   [WP ERROR] '{title}' पब्लिश/अपडेट करने में त्रुटि: {e}")
        return False, wp_post_id, ""


# ==============================================================================
# 8. मुख्य निष्पादन चक्र
# ==============================================================================
def fetch_portal_candidates(portal_info: dict) -> list[dict]:
    candidates = []
    portal_url = portal_info["url"]
    short_org = portal_info["short_org"]

    resp = fetch_url_flexible(portal_url)
    if resp is not None:
        try:
            soup = BeautifulSoup(resp.text, "html.parser")
            for nav_or_foot in soup.find_all(["nav", "footer"]):
                nav_or_foot.decompose()

            seen_urls = set()
            for a_tag in soup.find_all("a", href=True):
                raw_href = (a_tag.get("href") or "").strip()
                full_url = urljoin(portal_url, raw_href)
                if full_url in seen_urls:
                    continue
                seen_urls.add(full_url)

                title = clean_text(a_tag.get_text(" ", strip=True))
                if len(title) < 12 or title.lower() in GENERIC_LABELS:
                    parent = a_tag.find_parent(["tr", "li", "p"])
                    if parent:
                        p_text = clean_text(parent.get_text(" ", strip=True))
                        if 15 <= len(p_text) <= 260:
                            title = p_text

                if not is_valid_notice_candidate(title, full_url):
                    continue

                stage = detect_stage(f"{title} {full_url}")
                topic_key = build_topic_key(short_org, title)
                notice_sig = build_notice_signature(short_org, title, full_url)

                candidates.append({
                    "notice_sig": notice_sig,
                    "topic_key": topic_key,
                    "portal_url": portal_url,
                    "org": portal_info["org"],
                    "short_org": short_org,
                    "title": title,
                    "target_url": full_url,
                    "stage": stage,
                    "fallback_dt": None,
                })

                if len(candidates) >= CONFIG["max_items_per_portal"]:
                    break
        except Exception:
            pass

    if not candidates:
        fallback_items = fetch_fallback_updates(portal_info)
        if fallback_items:
            print(f"   [FALLBACK ACTIVE] {short_org}: बैकअप सोर्स से {len(fallback_items)} अपडेट मिले")
            candidates.extend(fallback_items)

    return candidates


def run_writer_pipeline() -> None:
    boot_now_dt = now_ist_dt()
    init_db()
    boot_cutoff_dt, is_first_boot = get_or_lock_boot_time(boot_now_dt)

    print("=" * 72)
    print(f"{CONFIG['site_name']} Content Writer Engine (From-Boot-Cutoff Mode)")
    print(f"रन समय (IST): {now_ist_str()} | बोट कटऑफ: {boot_cutoff_dt.strftime('%d-%m-%Y %H:%M IST')} के बाद")
    print(f"स्टेटस: {CONFIG['wp_post_status']} | न्यूनतम शब्द: {CONFIG['min_words']}")
    print("=" * 72)

    new_created = 0
    live_updated = 0
    skipped_items = 0

    for idx, portal in enumerate(GOVT_PORTALS, start=1):
        candidates = fetch_portal_candidates(portal)
        print(f"[{idx:02d}/{len(GOVT_PORTALS)}] {portal['short_org']}: {len(candidates)} संभावित अपडेट मिले")

        # पहली बार बोट चालू होते ही उस समय से पहले मौजूद सभी आइटम्स को baseline_snapshot में लॉक करें
        if is_first_boot:
            for item in candidates:
                add_to_baseline_snapshot(item["notice_sig"], item["portal_url"], item["title"], item["target_url"])
            print(f"   [BASELINE LOCKED] {portal['short_org']}: बोट चालू होने से पहले के {len(candidates)} आइटम्स लॉक किए गए")
            continue

        for item in candidates:
            notice_sig = item["notice_sig"]
            topic_key = item["topic_key"]
            existing = get_article_record(topic_key)

            details = extract_context_details(
                item["title"],
                item["target_url"],
                fallback_dt=item.get("fallback_dt"),
            )
            content_hash = hashlib.md5(
                f"{item['title']}|{item['stage']}|{item['target_url']}|{details['text_excerpt'][:600]}".encode("utf-8")
            ).hexdigest()

            if existing is None:
                eligible, reason = is_arrived_after_boot(details, notice_sig, boot_cutoff_dt)
                if not eligible:
                    print(f"   [SKIP PRE-BOOT] {item['title'][:50]}... -> {reason}")
                    skipped_items += 1
                    continue

                if new_created >= CONFIG["max_new_posts_per_run"]:
                    skipped_items += 1
                    continue

                history = [item["stage"]]
                seo_title, html_body, wc = build_complete_article(
                    portal_info=item,
                    raw_title=item["title"],
                    target_url=item["target_url"],
                    stage=item["stage"],
                    details=details,
                    is_live_update=False,
                    stages_history=history,
                )

                ok, wp_id, _ = push_to_wordpress(seo_title, html_body, wp_post_id=0)
                if ok:
                    now_str = now_ist_str()
                    upsert_article_record({
                        "topic_key": topic_key,
                        "portal_url": item["portal_url"],
                        "short_org": item["short_org"],
                        "raw_title": item["title"],
                        "seo_title": seo_title,
                        "stage": item["stage"],
                        "stages_history": history,
                        "target_url": item["target_url"],
                        "content_hash": content_hash,
                        "word_count": wc,
                        "wp_post_id": wp_id,
                        "created_at": now_str,
                        "updated_at": now_str,
                    })
                    new_created += 1
                    print(f"   [NEW ARTICLE] [{item['stage']}] ({wc} words) -> {seo_title}")

            else:
                stage_changed = existing["stage"] != item["stage"]
                url_changed = existing["target_url"] != item["target_url"]
                hash_changed = existing["content_hash"] != content_hash

                if not (stage_changed or url_changed or hash_changed):
                    skipped_items += 1
                    continue

                if live_updated >= CONFIG["max_updates_per_run"]:
                    skipped_items += 1
                    continue

                history = list(existing["stages_history"] or [existing["stage"]])
                if item["stage"] not in history:
                    history.append(item["stage"])

                seo_title, html_body, wc = build_complete_article(
                    portal_info=item,
                    raw_title=item["title"],
                    target_url=item["target_url"],
                    stage=item["stage"],
                    details=details,
                    is_live_update=True,
                    stages_history=history,
                )

                ok, wp_id, _ = push_to_wordpress(
                    seo_title,
                    html_body,
                    wp_post_id=int(existing.get("wp_post_id") or 0),
                )
                if ok:
                    now_str = now_ist_str()
                    upsert_article_record({
                        "topic_key": topic_key,
                        "portal_url": item["portal_url"],
                        "short_org": item["short_org"],
                        "raw_title": item["title"],
                        "seo_title": seo_title,
                        "stage": item["stage"],
                        "stages_history": history,
                        "target_url": item["target_url"],
                        "content_hash": content_hash,
                        "word_count": wc,
                        "wp_post_id": wp_id or existing.get("wp_post_id", 0),
                        "created_at": existing.get("created_at") or now_str,
                        "updated_at": now_str,
                    })
                    live_updated += 1
                    print(f"   [LIVE UPDATE] [{existing['stage']} -> {item['stage']}] ({wc} words) -> {seo_title}")

    print("-" * 72)
    print(f"पूरा हुआ -> नए आर्टिकल: {new_created} | लाइव अपडेट: {live_updated} | स्किप: {skipped_items}")
    print("=" * 72)


if __name__ == "__main__":
    run_writer_pipeline()
