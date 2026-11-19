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
# 1. CONFIGURATION (EXPERIENCED WRITER EDITION + STRICT NO-DUPLICATE + DRAFT)
# ==============================================================================
CONFIG = {
    "site_name": "GovtVibhag",
    "wp_site_url": os.getenv("WP_SITE_URL", "https://govtvibhag.com").strip().rstrip("/"),
    "wp_username": os.getenv("WP_USERNAME", "").strip(),
    "wp_app_password": os.getenv("WP_APP_PASSWORD", "").strip(),
    "wp_post_status": os.getenv("WP_POST_STATUS", "draft").strip().lower(),
    "gemini_api_key": os.getenv("GEMINI_API_KEY", "").strip(),
    "gemini_model": os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip(),
    "db_path": os.getenv("DB_PATH", "scraped_data_cache/govtvibhag_master.db").strip(),
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
    "Accept-Language": "en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7",
}


# ==============================================================================
# 2. OFFICIAL GOVERNMENT PORTALS
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
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}


# ==============================================================================
# 3. TIME & SQLITE DATABASE STATE
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
    conn = sqlite3.connect(CONFIG["db_path"])
    cur = conn.cursor()
    cur.execute("SELECT meta_value FROM runtime_meta WHERE meta_key = 'boot_started_iso'")
    row = cur.fetchone()
    if row and row[0]:
        conn.close()
        try:
            return datetime.fromisoformat(row[0]), False
        except Exception:
            return current_boot_dt, False

    cur.execute(
        "INSERT INTO runtime_meta (meta_key, meta_value) VALUES ('boot_started_iso', ?)",
        (current_boot_dt.isoformat(),),
    )
    conn.commit()
    conn.close()
    return current_boot_dt, True


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
        "topic_key": row[0], "portal_url": row[1], "short_org": row[2],
        "raw_title": row[3], "seo_title": row[4], "stage": row[5],
        "stages_history": json.loads(row[6] or "[]"), "target_url": row[7],
        "content_hash": row[8], "word_count": row[9], "wp_post_id": row[10],
        "created_at": row[11], "updated_at": row[12],
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
            record["topic_key"], record["portal_url"], record["short_org"],
            record["raw_title"], record["seo_title"], record["stage"],
            json.dumps(record["stages_history"], ensure_ascii=False),
            record["target_url"], record["content_hash"], record["word_count"],
            record["wp_post_id"], record["created_at"], record["updated_at"],
        ),
    )
    conn.commit()
    conn.close()


# ==============================================================================
# 4. TEXT CLEANING, STAGE & STRICT TOPIC KEY (PREVENT DUPLICATE ARTICLES)
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
    """
    एक ही भर्ती/परीक्षा/विषय के लिए हमेशा एक ही topic_key बनाता है
    (चाहे 'notification', 'admit card', 'answer key', 'result' या साल बदला हो),
    ताकि एक ही आर्टिकल दोबारा नया बनकर डुप्लीकेट न हो।
    """
    stripped = re.sub(
        r"\b(admit\s*card|hall\s*ticket|call\s*letter|exam\s*city|city\s*intimation|"
        r"answer\s*key|ans\s*key|response\s*sheet|objection|provisional|final|"
        r"result|results|merit\s*list|scorecard|cut\s*off|cutoff|"
        r"notification|recruitment|vacancy|vacancies|apply\s*online|bharti|"
        r"revised|corrigendum|schedule|notice|update|2024|2025|2026|2027)\b",
        " ",
        (title or "").lower(),
        flags=re.IGNORECASE,
    )
    stripped = re.sub(r"[^a-z0-9]+", " ", stripped)
    tokens = [t for t in stripped.split() if len(t) > 1][:5]
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
# 5. HTTP FETCH, FALLBACK, BOOT CUTOFF & CONTEXT EXTRACTION
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
    rss_url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en-IN&gl=IN&ceid=IN:en"

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
                "notice_sig": notice_sig, "topic_key": topic_key,
                "portal_url": portal_url, "org": portal_info["org"],
                "short_org": short_org, "title": raw_title,
                "target_url": link_val, "stage": stage, "fallback_dt": pub_dt,
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
    if is_in_baseline_snapshot(notice_sig):
        return False, "Pre-boot item locked in baseline"

    det_dt = details.get("detected_dt")
    has_exact_time = bool(details.get("has_exact_time"))

    if det_dt is not None:
        if has_exact_time and det_dt < boot_cutoff_dt:
            return False, f"Released before boot ({boot_cutoff_dt.strftime('%d-%m-%Y %H:%M')})"
        if not has_exact_time and det_dt.date() < boot_cutoff_dt.date():
            return False, f"Date earlier than boot date ({det_dt.strftime('%d-%m-%Y')})"

    return True, "Arrived after bot boot"


def extract_context_details(raw_title: str, target_url: str, fallback_dt: datetime | None = None) -> dict:
    is_pdf_link = target_url.lower().endswith(".pdf")
    details = {
        "doc_type": "Official PDF" if is_pdf_link else "Official Notice Link",
        "pdf_link": target_url if is_pdf_link else "",
        "text_excerpt": "",
        "headings": [],
        "vacancy_info": "As per official notification",
        "qualification_info": "As per post-wise official eligibility rules",
        "age_info": "As per official notification age rules",
        "fee_info": "As per category & official notification",
        "dates_info": "As per official schedule",
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
        is_pdf = is_pdf_link or "application/pdf" in ctype or (resp.content or b"").startswith(b"%PDF")

        if is_pdf:
            details["doc_type"] = "Official PDF"
            details["pdf_link"] = target_url

        if is_pdf and PYMUPDF_AVAILABLE and len(resp.content or b"") >= 300:
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
                for a_tag in soup.find_all("a", href=True):
                    href_full = urljoin(target_url, (a_tag.get("href") or "").strip())
                    if href_full.lower().endswith(".pdf"):
                        details["pdf_link"] = href_full
                        break
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
        details["vacancy_info"] = f"{vac_m.group(1)} Posts (As per official notice)"

    age_m = re.search(
        r"(?:age\s+limit|आयु\s+सीमा)[^\n\.]{0,80}?(\d{2})\s*(?:to|\-|से)\s*(\d{2})\s*(?:years|वर्ष|yrs)",
        extracted_text,
        flags=re.IGNORECASE,
    )
    if age_m:
        details["age_info"] = f"{age_m.group(1)} to {age_m.group(2)} Years (As per rules)"

    qual_found = []
    for pat, label in [
        (r"\b10th|matric|high\s*school\b", "10th Pass"),
        (r"\b12th|intermediate|higher\s*secondary\b", "12th Pass"),
        (r"\biti\b", "ITI"),
        (r"\bdiploma\b", "Diploma"),
        (r"\bgraduate|graduation|bachelor|degree|b\.tech|b\.sc|b\.a|b\.com\b", "Bachelor's Degree"),
        (r"\bpost\s*graduate|master|m\.sc|m\.a|m\.tech\b", "Master's Degree"),
        (r"\bb\.ed|ctet|tet\b", "B.Ed / TET"),
    ]:
        if re.search(pat, extracted_text, flags=re.IGNORECASE):
            qual_found.append(label)
    if qual_found:
        details["qualification_info"] = ", ".join(qual_found[:3]) + " (Post-wise check)"

    fee_m = re.search(
        r"(?:application\s+fee|fee|आवेदन\s+शुल्क)[^\n\.]{0,70}?(?:rs\.?|₹|inr)\s*(\d{1,4})",
        extracted_text,
        flags=re.IGNORECASE,
    )
    if fee_m:
        details["fee_info"] = f"Rs. {fee_m.group(1)} (Category rules apply)"

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
# 6. EXPERIENCED WRITER ENGINE: ENGLISH TITLE + CANDIDATE-FOCUSED HEADINGS
# ==============================================================================
def build_english_seo_title(short_org: str, raw_title: str, stage: str) -> str:
    yr = current_year_str()
    ascii_only = re.sub(r"[^\x20-\x7E]+", " ", clean_text(raw_title))
    ascii_only = re.sub(r"\.pdf$|\.html$|\.aspx$", "", ascii_only, flags=re.IGNORECASE)
    ascii_only = re.sub(
        r"\b(click here|download|view|new|latest|notice|notification|update)\b",
        "",
        ascii_only,
        flags=re.IGNORECASE,
    )
    ascii_only = re.sub(r"\s+", " ", ascii_only).strip(" -–|:")

    words = []
    for w in ascii_only.split():
        tok = w.strip("()[]\"',.")
        if len(tok) >= 2 and tok.lower() not in {"the", "of", "for", "and", "in", "on", "to"}:
            words.append(tok)

    topic_part = " ".join(words[:6]).strip()
    if not topic_part:
        topic_part = f"{short_org} Official Update"

    if short_org.lower() not in topic_part.lower():
        subject = f"{short_org} {topic_part}".strip()
    else:
        subject = topic_part

    deduped = []
    for w in subject.split():
        if not deduped or deduped[-1].lower() != w.lower():
            deduped.append(w)
    clean_subject = " ".join(deduped)[:70].strip()

    if stage == "Admit Card":
        return f"{clean_subject} Admit Card {yr}: Download Link, Exam Dates & Guidelines"
    if stage == "Answer Key":
        return f"{clean_subject} Answer Key {yr}: Response Sheet, Objection & Marking Guide"
    if stage == "Result":
        return f"{clean_subject} Result {yr}: Merit List, Scorecard Check & Next Steps"
    return f"{clean_subject} Recruitment {yr}: Eligibility, Qualification, Dates & How to Apply"


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
        print(f"   [WARN] Gemini writer fallback: {e}")
    return ""


def build_writer_html(portal_info: dict, raw_title: str, target_url: str, stage: str, details: dict) -> str:
    org = portal_info.get("org") or portal_info.get("short_org") or "Government Organization"
    short_org = portal_info.get("short_org") or org
    portal_url = portal_info.get("portal_url") or portal_info.get("url") or CONFIG["wp_site_url"]
    pdf_url = details.get("pdf_link") or ""
    updated_now = now_ist_str()

    pdf_row = (
        f'<tr><td><strong>Official PDF / Notice Link</strong></td>'
        f'<td><a href="{pdf_url}" target="_blank" rel="noopener noreferrer">Open Official PDF</a></td></tr>'
        if pdf_url
        else f'<tr><td><strong>Official Notice / Link</strong></td>'
        f'<td><a href="{target_url}" target="_blank" rel="noopener noreferrer">Open Official Notice</a></td></tr>'
    )

    website_row = (
        f'<tr><td><strong>Official Website Link</strong></td>'
        f'<td><a href="{portal_url}" target="_blank" rel="noopener noreferrer">{portal_url}</a></td></tr>'
    )

    overview_section = f"""
<p>Candidates tracking updates from <strong>{org}</strong> can review the complete details for <strong>{raw_title}</strong> below. As an experienced writer organizing information the way applicants actually read it, key links, stage details, and practical steps are structured clearly without fluff or FAQs.</p>

<h2>Quick Overview</h2>
<table border="1" cellpadding="8" cellspacing="0" width="100%" style="border-collapse:collapse;">
  <tbody>
    <tr><td><strong>Organization / Board</strong></td><td>{org} ({short_org})</td></tr>
    <tr><td><strong>Update Stage</strong></td><td><strong>{stage}</strong> ({details['doc_type']})</td></tr>
    <tr><td><strong>Notice / Title</strong></td><td>{raw_title}</td></tr>
    <tr><td><strong>Vacancy / Post Info</strong></td><td>{details['vacancy_info']}</td></tr>
    <tr><td><strong>Qualification &amp; Age Limit</strong></td><td>{details['qualification_info']} | {details['age_info']}</td></tr>
    <tr><td><strong>Application Fee &amp; Dates</strong></td><td>{details['fee_info']} | Dates: {details['dates_info']}</td></tr>
    {website_row}
    {pdf_row}
    <tr><td><strong>Last Updated</strong></td><td>{updated_now}</td></tr>
  </tbody>
</table>
"""

    if stage == "Admit Card":
        body_sections = f"""
<h2>Exam Schedule &amp; Shift Details</h2>
<p>Before downloading the <strong>{short_org}</strong> admit card, candidates should carefully check the examination date, shift timing, reporting time, and exam center details mentioned on the hall ticket or official schedule.</p>
<p>Arriving ahead of the reporting time helps avoid last-minute gate closure issues, traffic delays, or verification queues at the test center.</p>

<h2>Eligibility &amp; Admit Card Checkpoints</h2>
<ul>
  <li><strong>Candidate Identity Details:</strong> Verify your name, roll number, registration ID, category, photograph, and signature on the admit card.</li>
  <li><strong>Center &amp; Shift Accuracy:</strong> Match the exam center address, city, and shift timings with your registered application details.</li>
  <li><strong>Discrepancy Alert:</strong> If any printed detail is unclear or mismatched, refer to the official instructions on the portal promptly.</li>
</ul>

<h2>How to Download Admit Card</h2>
<ol>
  <li>Open the official website link listed in the Quick Overview table above.</li>
  <li>Locate the admit card or candidate login section for <strong>{raw_title}</strong>.</li>
  <li>Enter your registration/application number, date of birth, or password along with the captcha code.</li>
  <li>Download the admit card PDF and print clear copies for exam day use.</li>
</ol>

<h2>Exam Day Instructions &amp; Documents</h2>
<p>Carry a printed copy of the admit card along with a valid original photo identity proof (such as Aadhaar Card, Voter ID, Driving License, or Passport) and any additional items specified in the instructions.</p>
<p>Avoid carrying prohibited electronic gadgets, notes, or restricted items into the examination hall so your entry and test session proceed smoothly.</p>
"""
    elif stage == "Answer Key":
        body_sections = f"""
<h2>Answer Key &amp; Marking Overview</h2>
<p>This <strong>{short_org}</strong> answer key update helps candidates cross-check their responses and estimate probable scores before official results are compiled.</p>
<p>Always verify the question paper set, shift code, question ID, and official marking scheme before calculating your expected marks.</p>

<h2>How to Check Answer Key</h2>
<ol>
  <li>Visit the official portal or open the official notice/PDF link provided in the Quick Overview table.</li>
  <li>Open the answer key or response sheet link related to <strong>{raw_title}</strong>.</li>
  <li>Match your recorded responses with the official key for your specific paper/shift.</li>
  <li>Save a copy of the answer key and response sheet for personal reference.</li>
</ol>

<h2>Objection Process &amp; Timeline</h2>
<ul>
  <li><strong>Check Objection Window:</strong> Note the opening and closing dates if challenges/objections are invited against provisional answers.</li>
  <li><strong>Supporting Reference:</strong> Follow the exact procedure and fee/rule terms stated in the official notice when raising any objection.</li>
  <li><strong>Final Key Priority:</strong> Treat the final answer key issued by the authority as conclusive for evaluation.</li>
</ul>

<h2>Score Calculation Guidelines</h2>
<p>Count correct answers according to the positive marks per question and apply negative marking deductions wherever applicable under the exam rules.</p>
<p>Keep in mind that normalized scores or final merit lists may differ slightly from raw estimates once final evaluation is completed.</p>
"""
    elif stage == "Result":
        body_sections = f"""
<h2>Result &amp; Merit Highlights</h2>
<p>Candidates awaiting the outcome for <strong>{short_org}</strong> should verify their status strictly through the official result link or merit PDF listed in the Quick Overview table.</p>
<p>Check your roll number, registration number, name, and category carefully to confirm whether you have been shortlisted or selected for the next stage.</p>

<h2>How to Check Result &amp; Scorecard</h2>
<ol>
  <li>Open the official portal link or notice link from the Quick Overview table above.</li>
  <li>Select the result or merit list update corresponding to <strong>{raw_title}</strong>.</li>
  <li>Search your roll number/name in the merit PDF or log in with credentials to view your scorecard.</li>
  <li>Download and save the result page or scorecard for future stages.</li>
</ol>

<h2>Selection Stages &amp; Cut-Off Notes</h2>
<ul>
  <li><strong>Stage Progression:</strong> Note whether this result covers written exam, skill/trade test, physical test, interview, or final selection.</li>
  <li><strong>Category &amp; Cut-Offs:</strong> Review category-wise cut-off marks or qualifying criteria if published alongside the result.</li>
  <li><strong>Official Verification:</strong> Rely only on official portal files rather than forwarded screenshots or unverified messages.</li>
</ul>

<h2>Document Verification &amp; Next Steps</h2>
<p>Shortlisted candidates should keep original certificates, mark sheets, category/domicile certificates, and ID proofs organized in advance for verification.</p>
<p>Follow upcoming instructions on the official portal closely so no deadline or reporting schedule is missed.</p>
"""
    else:
        body_sections = f"""
<h2>Vacancy &amp; Post Highlights</h2>
<p>This recruitment update from <strong>{short_org}</strong> provides essential details for applicants looking at <strong>{raw_title}</strong>. Read the official notification carefully to confirm post-wise vacancies, pay/level details, and application rules before starting your form.</p>
<p>Because portals can slow down close to the deadline, verifying eligibility early and completing registration calmly helps avoid technical hurdles.</p>

<h2>Eligibility Criteria &amp; Age Limit</h2>
<p>Candidates must meet the prescribed age limit and eligibility conditions as of the reference date specified in the official notification.</p>
<ul>
  <li><strong>Age Bracket:</strong> Current extracted reference indicates <strong>{details['age_info']}</strong>.</li>
  <li><strong>Age Relaxation:</strong> Reserved categories may be eligible for age relaxation strictly as per government/notification norms.</li>
  <li><strong>Nationality &amp; Rules:</strong> Confirm citizenship and post-specific conditions in the official notice before applying.</li>
</ul>

<h2>Educational Qualification</h2>
<p>Applicants should possess the required educational qualification on or before the closing date mentioned in the recruitment notice.</p>
<ul>
  <li><strong>Qualification Summary:</strong> Current extracted reference indicates <strong>{details['qualification_info']}</strong>.</li>
  <li><strong>Stream / Trade / Degree:</strong> Check whether a specific degree, diploma, ITI trade, or board/university recognition is required for your target post.</li>
</ul>

<h2>Application Fee &amp; Selection Process</h2>
<p>Review the fee structure (<strong>{details['fee_info']}</strong>) and understand every stage of the selection process—such as written examination, skill/typing/physical test, document verification, and medical/interview stages—before submitting the application.</p>

<h2>How to Apply Online</h2>
<ol>
  <li>Go to the official website link or official notification link provided in the Quick Overview table.</li>
  <li>Read the instructions thoroughly and complete one-time/fresh registration with accurate personal details.</li>
  <li>Fill out the online application form, upload required documents/photo/signature in prescribed format, and pay the applicable fee.</li>
  <li>Submit the form and save/print the final confirmation page for future reference.</li>
</ol>
"""

    extracted_headings_note = ""
    if details.get("headings"):
        items_html = "".join(
            f"<li><strong>{clean_text(h)}:</strong> Covered in the official notice for candidate review.</li>"
            for h in details["headings"][:4]
        )
        extracted_headings_note = f"""
<h2>Key Sections Found in Official Notice</h2>
<ul>
  {items_html}
</ul>
"""

    writer_tips_section = f"""
{extracted_headings_note}
<h2>Important Candidate Tips</h2>
<p>An experienced applicant treats every recruitment or exam update as a sequence of verified steps rather than rushing through a single screen.</p>
<ul>
  <li><strong>Keep Details Consistent:</strong> Ensure your name, date of birth, category, and registration details match across your application, ID proof, and certificates.</li>
  <li><strong>Maintain a Dedicated Folder:</strong> Store PDFs of the notification, application form, fee receipt, admit card, and scorecard in one place.</li>
  <li><strong>Recheck Before Final Submit:</strong> Double-check spelling, exam center/post preferences, and uploaded files before final submission or deadline closure.</li>
</ul>
"""

    return f"{overview_section}\n{body_sections}\n{writer_tips_section}".strip()


def ensure_minimum_words(html_content: str, portal_info: dict, raw_title: str, stage: str, min_words: int) -> str:
    org = portal_info.get("org") or portal_info.get("short_org") or "Government Organization"
    short_org = portal_info.get("short_org") or org

    extra_blocks = [
        f"""
<h2>Practical Preparation &amp; Verification Checklist</h2>
<p>Candidates applying or tracking updates for <strong>{short_org}</strong> ({raw_title}) benefit from following a clear personal checklist at every stage. Rushing through instructions often leads to avoidable mistakes in form filling, document upload, or exam day reporting.</p>
<p>Always cross-check key details from the official notification or notice PDF so you rely on verified facts rather than assumptions or secondary rumors.</p>
<ul>
  <li><strong>Eligibility &amp; Dates Check:</strong> Confirm qualifications, age rules, and important dates before starting or acting on any step.</li>
  <li><strong>Document Readiness:</strong> Keep scanned copies and original certificates ready well ahead of time.</li>
  <li><strong>Timely Action:</strong> Avoid waiting until the final hours when portal traffic is usually highest.</li>
</ul>
""",
        f"""
<h2>Step-by-Step Candidate Approach</h2>
<p>Whether you are checking a new notification, downloading an admit card, matching an answer key, or viewing a result for <strong>{org}</strong>, a disciplined approach saves time and prevents errors.</p>
<p>Read each section of the official notice carefully, note any instructions specific to your category or post, and keep copies of every confirmation or download for future reference.</p>
""",
    ]

    out_html = html_content
    idx = 0
    while count_words_from_html(out_html) < min_words and idx < len(extra_blocks):
        out_html = f"{out_html}\n{extra_blocks[idx]}"
        idx += 1

    extra_num = 1
    while count_words_from_html(out_html) < min_words:
        out_html += (
            f"\n<p><strong>Candidate Note {extra_num}:</strong> For {short_org} ({raw_title}) under {stage}, "
            f"always verify all eligibility conditions, dates, instructions, and official links directly from "
            f"the official source and retain copies of your records for future reference.</p>"
        )
        extra_num += 1

    return out_html.strip()


def build_complete_article(
    portal_info: dict,
    raw_title: str,
    target_url: str,
    stage: str,
    details: dict,
    is_live_update: bool = False,
    stages_history: list | None = None,
) -> tuple[str, str, int]:
    short_org = portal_info.get("short_org") or portal_info.get("org") or "Govt"
    seo_title = build_english_seo_title(short_org, raw_title, stage)
    base_html = build_writer_html(portal_info, raw_title, target_url, stage, details)

    if is_live_update and stages_history:
        flow_str = " &rarr; ".join(stages_history)
        update_note = (
            f"<p><strong>Live Update:</strong> This existing post has been updated for the latest stage "
            f"(<strong>{stage}</strong> | Stage Flow: <strong>{flow_str}</strong>).</p>\n"
        )
        base_html = f"{update_note}{base_html}"

    if CONFIG["gemini_api_key"]:
        prompt = f"""
You are an experienced government jobs & exam content writer writing for an Indian candidate audience.
Improve and expand the HTML article below so it reads naturally, clearly, and thoroughly for candidates, with at least {CONFIG['min_words']} words.

Strict Rules:
- Write the SEO title mindset, all <h2>/<h3> headings, and the article body in clear, natural English.
- Do NOT include any FAQ section or Q&A blocks.
- Keep the Quick Overview table at the top with the official website link and official PDF/notice link; do NOT create a separate heading for official website.
- Structure headings around what a candidate actually needs for stage "{stage}" (such as Eligibility, Qualification, How to Apply, Admit Card/Exam Instructions, Answer Key/Objection, Result/Next Steps, Candidate Tips).
- Return ONLY clean HTML (<h2>, <h3>, <p>, <ul>, <ol>, <table>, <tr>, <td>, <strong>, <a>), no markdown ``` fences.
- Do not invent fake dates, vacancy numbers, or unverified claims; keep "As per official notification" where facts are not stated.

Title: {seo_title}
Organization: {portal_info.get('org', short_org)}
Stage: {stage}

Base HTML:
{base_html[:6500]}
"""
        ai_html = call_gemini_writer(prompt)
        if ai_html and count_words_from_html(ai_html) >= 700:
            ai_html = re.sub(r"<h[23][^>]*>.*?(?:faq|frequently asked questions).*?</h[23]>.*?(?=<h[23]|$)", "", ai_html, flags=re.IGNORECASE | re.DOTALL)
            final_html = ensure_minimum_words(ai_html, portal_info, raw_title, stage, CONFIG["min_words"])
            return seo_title, final_html, count_words_from_html(final_html)

    final_html = ensure_minimum_words(base_html, portal_info, raw_title, stage, CONFIG["min_words"])
    return seo_title, final_html, count_words_from_html(final_html)


# ==============================================================================
# 7. WORDPRESS PUBLISH & LIVE UPDATE (DRAFT BY DEFAULT)
# ==============================================================================
def push_to_wordpress(title: str, html_content: str, wp_post_id: int = 0) -> tuple[bool, int, str]:
    preview_file = os.path.join(CONFIG["cache_dir"], "last_generated_article.html")
    with open(preview_file, "w", encoding="utf-8") as f:
        f.write(f"<h1>{title}</h1>\n{html_content}")

    if not (CONFIG["wp_site_url"] and CONFIG["wp_username"] and CONFIG["wp_app_password"]):
        sim_id = wp_post_id if wp_post_id > 0 else int(hashlib.md5(title.encode("utf-8")).hexdigest()[:6], 16)
        print(f"   [DRY-RUN WP] {'UPDATE' if wp_post_id > 0 else 'CREATE'} -> {title}")
        return True, sim_id, f"{CONFIG['wp_site_url']}/?p={sim_id}"

    clean_pass = CONFIG["wp_app_password"].replace(" ", "")
    token = base64.b64encode(f"{CONFIG['wp_username']}:{clean_pass}".encode("utf-8")).decode("utf-8")
    headers = {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json",
        "User-Agent": HTTP_HEADERS["User-Agent"],
    }

    status_to_use = CONFIG["wp_post_status"] if CONFIG["wp_post_status"] in ("draft", "publish", "pending", "private") else "draft"
    payload = {"title": title, "content": html_content, "status": status_to_use}

    base_endpoint = f"{CONFIG['wp_site_url']}/wp-json/wp/v2/posts"
    endpoint = f"{base_endpoint}/{wp_post_id}" if wp_post_id > 0 else base_endpoint

    try:
        resp = requests.post(endpoint, headers=headers, json=payload, timeout=25)
        resp.raise_for_status()
        data = resp.json()
        return True, int(data.get("id") or wp_post_id or 0), str(data.get("link") or "")
    except Exception as e:
        print(f"   [WP ERROR] '{title}': {e}")
        return False, wp_post_id, ""


# ==============================================================================
# 8. MAIN EXECUTION PIPELINE
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
                    "notice_sig": notice_sig, "topic_key": topic_key,
                    "portal_url": portal_url, "org": portal_info["org"],
                    "short_org": short_org, "title": title,
                    "target_url": full_url, "stage": stage, "fallback_dt": None,
                })

                if len(candidates) >= CONFIG["max_items_per_portal"]:
                    break
        except Exception:
            pass

    if not candidates:
        fallback_items = fetch_fallback_updates(portal_info)
        if fallback_items:
            candidates.extend(fallback_items)

    return candidates


def run_writer_pipeline() -> None:
    boot_now_dt = now_ist_dt()
    init_db()
    boot_cutoff_dt, is_first_boot = get_or_lock_boot_time(boot_now_dt)

    print("=" * 72)
    print(f"{CONFIG['site_name']} Engine | Mode: {'FIRST BOOT (BASELINE LOCK)' if is_first_boot else 'LIVE SCAN MODE'}")
    print(f"Run Time (IST): {now_ist_str()} | Boot Cutoff: {boot_cutoff_dt.strftime('%d-%m-%Y %H:%M IST')}")
    print("=" * 72)

    new_created = 0
    live_updated = 0
    skipped_items = 0
    processed_topic_keys_this_run = set()

    for idx, portal in enumerate(GOVT_PORTALS, start=1):
        candidates = fetch_portal_candidates(portal)
        print(f"[{idx:02d}/{len(GOVT_PORTALS)}] {portal['short_org']}: {len(candidates)} items found")

        if is_first_boot:
            for item in candidates:
                add_to_baseline_snapshot(item["notice_sig"], item["portal_url"], item["title"], item["target_url"])
            continue

        for item in candidates:
            notice_sig = item["notice_sig"]
            topic_key = item["topic_key"]

            if topic_key in processed_topic_keys_this_run:
                skipped_items += 1
                continue

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
                eligible, _ = is_arrived_after_boot(details, notice_sig, boot_cutoff_dt)
                if not eligible:
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
                        "topic_key": topic_key, "portal_url": item["portal_url"],
                        "short_org": item["short_org"], "raw_title": item["title"],
                        "seo_title": seo_title, "stage": item["stage"],
                        "stages_history": history, "target_url": item["target_url"],
                        "content_hash": content_hash, "word_count": wc,
                        "wp_post_id": wp_id, "created_at": now_str, "updated_at": now_str,
                    })
                    processed_topic_keys_this_run.add(topic_key)
                    new_created += 1
                    print(f"   [NEW DRAFT] [{item['stage']}] ({wc} words) -> {seo_title}")

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
                        "topic_key": topic_key, "portal_url": item["portal_url"],
                        "short_org": item["short_org"], "raw_title": item["title"],
                        "seo_title": seo_title, "stage": item["stage"],
                        "stages_history": history, "target_url": item["target_url"],
                        "content_hash": content_hash, "word_count": wc,
                        "wp_post_id": wp_id or existing.get("wp_post_id", 0),
                        "created_at": existing.get("created_at") or now_str,
                        "updated_at": now_str,
                    })
                    processed_topic_keys_this_run.add(topic_key)
                    live_updated += 1
                    print(f"   [LIVE UPDATE] [{existing['stage']} -> {item['stage']}] ({wc} words) -> {seo_title}")

    print("-" * 72)
    if is_first_boot:
        print("पहला रन पूरा: पुराना डाटा लॉक कर दिया गया है। अगले रन से नए अपडेट्स पर ड्राफ्ट बनेंगे।")
    elif new_created == 0 and live_updated == 0:
        print("अभी कोई अपडेट नहीं आया")
    print(f"पूरा हुआ -> नए आर्टिकल: {new_created} | लाइव अपडेट: {live_updated} | स्किप: {skipped_items}")
    print("=" * 72)


if __name__ == "__main__":
    run_writer_pipeline()
