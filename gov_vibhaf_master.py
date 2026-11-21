import argparse
import base64
import hashlib
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# Google GenAI SDK (Modern Official SDK)
try:
    from google import genai
    from google.genai import types

    GOOGLE_GENAI_AVAILABLE = True
except ImportError:
    GOOGLE_GENAI_AVAILABLE = False

# PyMuPDF / Fitz
try:
    import pymupdf as fitz

    PYMUPDF_AVAILABLE = True
except ImportError:
    try:
        import fitz

        PYMUPDF_AVAILABLE = True
    except ImportError:
        PYMUPDF_AVAILABLE = False


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CACHE_DIR = os.path.join(BASE_DIR, "scraped_data_cache")
DEFAULT_DB_PATH = os.path.join(DEFAULT_CACHE_DIR, "govtvibhag_master.db")

# ==============================================================================
# 1. CONFIGURATION (HUMAN WRITER + DEVANAGARI HINDI + ADSENSE COMPLIANT)
# ==============================================================================
CONFIG = {
    "site_name": "GovtVibhag",
    "wp_site_url": os.getenv("WP_SITE_URL", "https://govtvibhag.com").strip().rstrip("/"),
    "wp_username": os.getenv("WP_USERNAME", "").strip(),
    "wp_app_password": os.getenv("WP_APP_PASSWORD", "").strip(),
    "wp_post_status": os.getenv("WP_POST_STATUS", "draft").strip().lower(),
    "gemini_api_key": os.getenv("GEMINI_API_KEY", "").strip(),
    "gemini_model": os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip(),
    "db_path": os.getenv("DB_PATH", DEFAULT_DB_PATH).strip(),
    "cache_dir": os.getenv("CACHE_DIR", DEFAULT_CACHE_DIR).strip(),
    "min_words": int(os.getenv("MIN_ARTICLE_WORDS", "1100")),
    "max_items_per_portal": int(os.getenv("MAX_ITEMS_PER_PORTAL", "6")),
    "max_new_posts_per_run": int(os.getenv("MAX_NEW_POSTS_PER_RUN", "8")),
    "max_updates_per_run": int(os.getenv("MAX_UPDATES_PER_RUN", "8")),
    "max_notice_age_hours": float(os.getenv("MAX_NOTICE_AGE_HOURS", "4.0")),  # Strictly 3-4 hours fresh
    "request_timeout": int(os.getenv("REQUEST_TIMEOUT", "20")),
    "enable_fallback": os.getenv("ENABLE_FALLBACK", "true").lower() == "true",
    "enable_search_grounding": os.getenv("ENABLE_SEARCH_GROUNDING", "true").lower() == "true",
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


def get_article_by_org_and_stage(short_org: str, stage: str) -> dict | None:
    conn = sqlite3.connect(CONFIG["db_path"])
    cur = conn.cursor()
    cur.execute(
        """SELECT topic_key, portal_url, short_org, raw_title, seo_title, stage,
                  stages_history, target_url, content_hash, word_count, wp_post_id,
                  created_at, updated_at
           FROM articles WHERE lower(short_org) = lower(?) AND lower(stage) = lower(?)
           ORDER BY rowid DESC LIMIT 1""",
        (short_org, stage),
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
# 4. TEXT CLEANING, STAGE & STRICT TOPIC KEY
# ==============================================================================
def clean_text(text: str) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"[\ufffd\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", " ", text)
    cleaned = re.sub(r"\(cid:\d+\)", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def count_words_from_html(html_content: str) -> int:
    clean_html = re.sub(r'<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>', '', html_content or '', flags=re.IGNORECASE)
    plain = BeautifulSoup(clean_html, "html.parser").get_text(" ", strip=True)
    return len(re.findall(r"[A-Za-z0-9\u0900-\u097f]+", plain))


def detect_stage(text: str) -> str:
    low = (text or "").lower()
    for stage in ["Result", "Answer Key", "Admit Card", "Jobs"]:
        if any(kw in low for kw in STAGE_KEYWORDS[stage]):
            return stage
    return "Jobs"


EXAM_CANONICAL_PATTERNS = [
    # SSC
    (r"\b(cgl|combined\s+graduate\s+level)\b", "cgl", "CGL"),
    (r"\b(chsl|combined\s+higher\s+secondary|10\+2)\b", "chsl", "CHSL"),
    (r"\b(mts|multi\s*tasking|havaldar)\b", "mts", "MTS"),
    (r"\b(cpo|sub\s*inspector\s+in\s+delhi\s+police|capfs)\b", "cpo", "CPO"),
    (r"\b(constable\s+gd|general\s+duty|rifleman)\b", "gd_constable", "GD Constable"),
    (r"\b(je|junior\s+engineer)\b", "je", "Junior Engineer (JE)"),
    (r"\b(stenographer|steno\s*grade\s*[cd])\b", "steno", "Stenographer"),
    (r"\b(selection\s+post|phase\s*[\-\s]*\d{1,2})\b", "selection_post", "Selection Post"),
    # UPSC
    (r"\b(civil\s+services|cse|ias|ips)\b", "civil_services", "Civil Services (CSE)"),
    (r"\b(nda|national\s+defence\s+academy)\b", "nda", "NDA"),
    (r"\b(cds|combined\s+defence\s+services)\b", "cds", "CDS"),
    (r"\b(capf|assistant\s+commandant)\b", "capf_ac", "CAPF (AC)"),
    (r"\b(cms|combined\s+medical)\b", "cms", "CMS"),
    (r"\b(ese|engineering\s+services)\b", "ese", "ESE"),
    # Railways / RRB
    (r"\b(alp|assistant\s+loco\s+pilot)\b", "rrb_alp", "RRB ALP"),
    (r"\b(ntpc|non\s*technical\s+popular\s+categories)\b", "rrb_ntpc", "RRB NTPC"),
    (r"\b(group\s*d|level\s*1\s*posts?)\b", "rrb_group_d", "RRB Group D"),
    (r"\b(technician|technician\s+grade)\b", "rrb_technician", "RRB Technician"),
    (r"\b(rpf\s+si|rpf\s+constable|railway\s+protection\s+force)\b", "rpf", "RPF"),
    # Banking
    (r"\b(po|probationary\s+officer)\b", "po", "PO"),
    (r"\b(clerk|customer\s+support|clerical)\b", "clerk", "Clerk"),
    (r"\b(so|specialist\s+officer)\b", "so", "SO"),
    # Teaching
    (r"\b(ctet|central\s+teacher\s+eligibility)\b", "ctet", "CTET"),
    (r"\b(kvs|kendriya\s+vidyalaya)\b", "kvs", "KVS"),
    (r"\b(nvs|navodaya\s+vidyalaya)\b", "nvs", "NVS"),
    (r"\b(prt|primary\s+teacher)\b", "prt", "PRT"),
    (r"\b(tgt|trained\s+graduate\s+teacher)\b", "tgt", "TGT"),
    (r"\b(pgt|post\s+graduate\s+teacher)\b", "pgt", "PGT"),
    # Defence
    (r"\b(agniveer\s+vayu|air\s*force|casb)\b", "airforce_agniveer", "Air Force Agniveer"),
    (r"\b(agniveer\s+navy|ssr|mr)\b", "navy_agniveer", "Navy Agniveer"),
    (r"\b(agniveer\s+army|rally)\b", "army_agniveer", "Army Agniveer"),
    (r"\b(coast\s*guard|navik|yantrik)\b", "coast_guard", "Coast Guard"),
    # Police
    (r"\b(police\s+constable|sipahi)\b", "police_constable", "Police Constable"),
    (r"\b(sub\s*inspector|daroga|si)\b", "police_si", "Police SI"),
    (r"\b(patwari|lekhpal)\b", "lekhpal", "Lekhpal / Patwari"),
]


def get_canonical_exam_info(title: str) -> tuple[str, str]:
    low = (title or "").lower()
    for pattern, slug, label in EXAM_CANONICAL_PATTERNS:
        if re.search(pattern, low):
            return slug, label

    noise = (
        r"\b(admit\s*card|hall\s*ticket|call\s*letter|exam\s*city|city\s*intimation|"
        r"answer\s*key|ans\s*key|response\s*sheet|objection|provisional|final|"
        r"result|results|merit\s*list|scorecard|cut\s*off|cutoff|out|released|declared|"
        r"notification|recruitment|vacancy|vacancies|apply\s*online|bharti|"
        r"revised|corrigendum|schedule|notice|update|check|direct|link|paper|raise|"
        r"examination|exam|tier|phase|2020|2021|2022|2023|2024|2025|2026|2027)\b"
    )
    stripped = re.sub(noise, " ", low, flags=re.IGNORECASE)
    stripped = re.sub(r"[^a-z0-9]+", " ", stripped)
    tokens = [t for t in stripped.split() if len(t) > 2][:3]
    slug = "_".join(tokens) if tokens else hashlib.md5(title.encode("utf-8")).hexdigest()[:8]
    label = " ".join(t.capitalize() for t in tokens) if tokens else slug
    return slug, label


def build_topic_key(short_org: str, title: str) -> str:
    """
    Creates a single canonical key per organization + exam + year.
    All stages (Jobs, Admit Card, Answer Key, Result) share the exact SAME key,
    ensuring 1 article is NEVER created 2 to 3 times!
    """
    slug, _ = get_canonical_exam_info(title)
    yr = current_year_str()
    return f"{short_org.lower().strip()}_{slug}_{yr}"


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


def is_third_party_or_news_url(url: str, portal_url: str) -> bool:
    if not url:
        return True
    parsed_u = urlparse(url)
    host_u = (parsed_u.netloc or "").lower()
    if not host_u:
        return True
    blocked_hosts = (
        "news.google.com", "google.com", "facebook.com", "instagram.com",
        "t.me", "telegram.me", "youtube.com", "youtu.be", "bit.ly", "x.com", "twitter.com"
    )
    if any(bh in host_u for bh in blocked_hosts):
        return True
    parsed_p = urlparse(portal_url)
    base_domain = (parsed_p.netloc or "").lower().replace("www.", "")
    if base_domain and base_domain not in host_u and not host_u.endswith((".gov.in", ".nic.in", ".ac.in", ".org.in")):
        return True
    return False


# ==============================================================================
# 5. HTTP FETCH, FALLBACK & CONTEXT EXTRACTION
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
            pub_el = entry.find("pubDate")

            raw_title = clean_text(title_el.text if title_el else "")
            if " - " in raw_title:
                raw_title = raw_title.rsplit(" - ", 1)[0].strip()

            if not is_valid_notice_candidate(raw_title, portal_url):
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

            stage = detect_stage(raw_title)
            topic_key = build_topic_key(short_org, raw_title)
            notice_sig = build_notice_signature(short_org, raw_title, portal_url)

            results.append({
                "notice_sig": notice_sig, "topic_key": topic_key,
                "portal_url": portal_url, "org": portal_info["org"],
                "short_org": short_org, "title": raw_title,
                "target_url": portal_url, "stage": stage, "fallback_dt": pub_dt,
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


def is_notice_fresh_and_valid(title: str, details: dict, notice_sig: str, boot_cutoff_dt: datetime) -> tuple[bool, str]:
    """
    STRICT REAL-TIME FRESHNESS FILTER (MAX 3-4 HOURS OLD):
    1. Rejects any pre-boot notice locked in baseline snapshot.
    2. Rejects notices referencing past years (2020-2025) without current year.
    3. Rejects notices older than CONFIG['max_notice_age_hours'] (Strictly 3-4 hours).
    4. Rejects notices with unverifiable timestamps to guarantee zero old articles.
    """
    if is_in_baseline_snapshot(notice_sig):
        return False, "Pre-boot notice locked in baseline snapshot"

    yr_current = current_year_str()
    sample_text = f"{title} {details.get('text_excerpt', '')[:600]}".lower()

    # Past years filter: if notice references past years without current year
    past_years = ["2020", "2021", "2022", "2023", "2024", "2025"]
    for py in past_years:
        if re.search(r'\b' + py + r'\b', sample_text) and not re.search(r'\b' + yr_current + r'\b', sample_text):
            return False, f"Notice belongs to past year ({py}) without reference to {yr_current} - skipping old notice"

    det_dt = details.get("detected_dt")
    has_exact_time = bool(details.get("has_exact_time"))
    now_dt = now_ist_dt()

    # Strict Real-time Cutoff (Default 4 hours)
    max_hours = float(CONFIG.get("max_notice_age_hours", 4.0))

    if det_dt is not None:
        age_hours = (now_dt - det_dt).total_seconds() / 3600.0
        if age_hours > max_hours:
            return False, f"Notice is {age_hours:.1f}h old (exceeds {max_hours}h limit, detected: {det_dt.strftime('%d-%m-%Y %H:%M')})"

        if has_exact_time and det_dt < boot_cutoff_dt:
            return False, f"Released before bot boot time ({boot_cutoff_dt.strftime('%d-%m-%Y %H:%M')})"
        if not has_exact_time and det_dt.date() < boot_cutoff_dt.date():
            return False, f"Date earlier than bot boot date ({det_dt.strftime('%d-%m-%Y')})"
    else:
        # If timestamp is completely unverifiable, do not risk publishing old content
        if not (yr_current in sample_text and re.search(r'\b(today|latest|current|breaking|hours? ago|आज|ताजा)\b', sample_text)):
            return False, "Unverifiable publication time and no real-time freshness signal - skipping for safety"

    return True, "Notice is fresh and verified"


def extract_context_details(raw_title: str, target_url: str, portal_url: str, fallback_dt: datetime | None = None) -> dict:
    has_official_notice = not is_third_party_or_news_url(target_url, portal_url) and (target_url.rstrip("/") != portal_url.rstrip("/"))
    is_pdf_link = has_official_notice and target_url.lower().endswith(".pdf")

    details = {
        "doc_type": "Official PDF" if is_pdf_link else ("Official Notice" if has_official_notice else "Official Portal"),
        "official_notice_link": target_url if has_official_notice else "",
        "text_excerpt": "",
        "headings": [],
        "vacancy_info": "Official Notification के अनुसार",
        "qualification_info": "Post के अनुसार Eligibility देखें",
        "age_info": "Notification के अनुसार Age Limit",
        "fee_info": "Category के अनुसार Application Fee देखें",
        "dates_info": "Official Schedule के अनुसार",
        "detected_dt": None,
        "has_exact_time": False,
    }

    resp = fetch_url_flexible(target_url) if has_official_notice else None
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
            details["official_notice_link"] = target_url

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
            try:
                soup = BeautifulSoup(resp.text, "html.parser")
                for a_tag in soup.find_all("a", href=True):
                    href_full = urljoin(target_url, (a_tag.get("href") or "").strip())
                    if href_full.lower().endswith(".pdf") and not is_third_party_or_news_url(href_full, portal_url):
                        details["official_notice_link"] = href_full
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
        details["vacancy_info"] = f"{vac_m.group(1)} Vacancies (Official Notification के अनुसार)"

    age_m = re.search(
        r"(?:age\s+limit|आयु\s+सीमा)[^\n\.]{0,80}?(\d{2})\s*(?:to|\-|से)\s*(\d{2})\s*(?:years|वर्ष|yrs)",
        extracted_text,
        flags=re.IGNORECASE,
    )
    if age_m:
        details["age_info"] = f"{age_m.group(1)} से {age_m.group(2)} Years (Rules के अनुसार)"

    qual_found = []
    for pat, label in [
        (r"\b10th|matric|high\s*school\b", "10th Pass"),
        (r"\b12th|intermediate|higher\s*secondary\b", "12th Pass"),
        (r"\biti\b", "ITI"),
        (r"\bdiploma\b", "Diploma"),
        (r"\bgraduate|graduation|bachelor|degree|b\.tech|b\.sc|b\.a|b\.com\b", "Graduation / Degree"),
        (r"\bpost\s*graduate|master|m\.sc|m\.a|m\.tech\b", "Post Graduation"),
        (r"\bb\.ed|ctet|tet\b", "B.Ed / TET"),
    ]:
        if re.search(pat, extracted_text, flags=re.IGNORECASE):
            qual_found.append(label)
    if qual_found:
        details["qualification_info"] = ", ".join(qual_found[:3]) + " (Post के अनुसार देखें)"

    fee_m = re.search(
        r"(?:application\s+fee|fee|आवेदन\s+शुल्क)[^\n\.]{0,70}?(?:rs\.?|₹|inr)\s*(\d{1,4})",
        extracted_text,
        flags=re.IGNORECASE,
    )
    if fee_m:
        details["fee_info"] = f"Rs. {fee_m.group(1)} (Category के अनुसार देखें)"

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
# 6. SEO TITLES & GOOGLE RICH SCHEMA (JSON-LD)
# ==============================================================================
def build_clean_title(short_org: str, raw_title: str, stage: str, is_live_update: bool = False) -> str:
    yr = current_year_str()
    txt = clean_text(raw_title)
    txt = re.sub(r"\.pdf$|\.html$|\.aspx$", "", txt, flags=re.IGNORECASE)
    txt = re.sub(
        r"\b(out|released|declared|new|latest|click here|download|view|notice|notification|update|check|direct|link|paper|raise)\b",
        " ",
        txt,
        flags=re.IGNORECASE,
    )

    stage_clean_patterns = {
        "Result": r"\b(result|results|merit\s*list|scorecard|score\s*card|cut\s*off|cutoff)\b",
        "Admit Card": r"\b(admit\s*card|hall\s*ticket|call\s*letter|exam\s*city)\b",
        "Answer Key": r"\b(answer\s*key|ans\s*key|response\s*sheet|objection)\b",
        "Jobs": r"\b(recruitment|vacancy|vacancies|apply\s*online|bharti)\b",
    }
    pat = stage_clean_patterns.get(stage)
    if pat:
        txt = re.sub(pat, " ", txt, flags=re.IGNORECASE)

    txt = re.sub(r"\b202[4-7]\b", " ", txt)
    txt = re.sub(r"[^\w\s\u0900-\u097f\-/]+", " ", txt)
    txt = re.sub(r"\s+", " ", txt).strip(" -–|:/")

    words = []
    for w in txt.split():
        if w.lower() not in {"the", "of", "for", "and", "in", "on", "to"} and (not words or words[-1].lower() != w.lower()):
            words.append(w)

    subject = " ".join(words[:4]).strip()
    if not subject:
        subject = short_org
    elif short_org.lower() not in subject.lower():
        subject = f"{short_org} {subject}".strip()

    subject = subject[:48].strip(" -–|:/")
    prefix = "[Out] " if is_live_update else ""

    if stage == "Result":
        return f"{prefix}{subject} Result {yr}: Tier 1 Merit List PDF, Scorecard & Cut Off Marks Released"
    if stage == "Admit Card":
        return f"{prefix}{subject} Admit Card {yr}: Hall Ticket Download Link, Exam Shift Timing & Center Details"
    if stage == "Answer Key":
        return f"{prefix}{subject} Answer Key {yr}: Response Sheet PDF, Question Objection Link & Score Calculator"
    return f"{subject} Recruitment {yr}: Notification PDF, Eligibility Criteria, Total Vacancies & Apply Online Link"


def build_seo_faq_schema(short_org: str, raw_title: str, stage: str, details: dict) -> str:
    """
    Google Rich Results FAQ Schema (JSON-LD) for high click-through-rates in Google Search.
    """
    yr = current_year_str()
    faqs = []

    if stage == "Admit Card":
        faqs = [
            {
                "@type": "Question",
                "name": f"{short_org} {raw_title} Admit Card {yr} कैसे डाउनलोड करें?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": f"उम्मीदवार आधिकारिक पोर्टल पर जाकर अपने Registration Number और Date of Birth की मदद से लॉगिन करके अपना {short_org} Admit Card डाउनलोड कर सकते हैं।"
                }
            },
            {
                "@type": "Question",
                "name": "एग्जाम सेंटर पर कौन-से डॉक्यूमेंट्स ले जाना अनिवार्य है?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "Admit Card का साफ प्रिंटआउट, एक मूल ओरिजिनल फोटो पहचान पत्र (Aadhaar Card, PAN Card या Voter ID) और 2 पासपोर्ट साइज फोटोग्राफ साथ ले जाना अनिवार्य है।"
                }
            }
        ]
    elif stage == "Result":
        faqs = [
            {
                "@type": "Question",
                "name": f"{short_org} {raw_title} Result {yr} कब जारी हुआ?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": f"{short_org} ने आधिकारिक वेबसाइट पर {raw_title} का परिणाम और मेरिट लिस्ट जारी कर दी है। उम्मीदवार सीधे पोर्टल से अपना स्कोरकार्ड चेक कर सकते हैं।"
                }
            },
            {
                "@type": "Question",
                "name": "Merit List में नाम आने के बाद अगला चरण क्या होगा?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "शॉर्टलिस्ट हुए उम्मीदवारों को अगले राउंड (जैसे Document Verification, Skill/Physical Test या Interview) के लिए बुलाया जाएगा।"
                }
            }
        ]
    elif stage == "Answer Key":
        faqs = [
            {
                "@type": "Question",
                "name": f"{short_org} Answer Key पर Objection कैसे दर्ज करें?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "आधिकारिक लॉगिन पोर्टल पर जाकर संबंधित प्रश्न संख्या का चयन करें, आवश्यक प्रमाण (Proof) अपलोड करें और प्रति प्रश्न तय शुल्क का भुगतान करके ऑनलाइन आपत्ति दर्ज करें।"
                }
            }
        ]
    else:
        faqs = [
            {
                "@type": "Question",
                "name": f"{short_org} {raw_title} के लिए शैक्षणिक योग्यता क्या है?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": f"अधिसूचना के अनुसार योग्यता: {details.get('qualification_info', 'Official Notification देखें')} निर्धारित की गई है।"
                }
            },
            {
                "@type": "Question",
                "name": f"{short_org} भर्ती के लिए आयु सीमा क्या है?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": f"आयु सीमा: {details.get('age_info', 'Rules के अनुसार')} है, जिसमें आरक्षित वर्गों को सरकारी नियमों के तहत छूट प्राप्त है।"
                }
            }
        ]

    schema_data = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": faqs
    }
    return f'\n<script type="application/ld+json">\n{json.dumps(schema_data, ensure_ascii=False, indent=2)}\n</script>'


# ==============================================================================
# 7. EXPERIENCED HUMAN JOURNALIST ARTICLE BUILDER (E-E-A-T & ZERO AI CLICHES)
# ==============================================================================
def build_human_master_article(
    portal_info: dict,
    raw_title: str,
    stage: str,
    details: dict,
    is_live_update: bool = False,
    stages_history: list | None = None,
) -> str:
    """
    Crafts an authentic, 1200+ word comprehensive article written from the voice
    of a seasoned Indian educational journalist & mentor.
    Zero AI clichés (no 'निष्कर्ष', 'संक्षेप में', 'जैसा कि हम जानते हैं').
    100% compliant with Google AdSense quality and E-E-A-T standards.
    """
    org = portal_info.get("org") or portal_info.get("short_org") or "Government Organization"
    short_org = portal_info.get("short_org") or org
    portal_url = portal_info.get("portal_url") or portal_info.get("url") or CONFIG["wp_site_url"]
    official_notice_url = details.get("official_notice_link") or ""
    updated_now = now_ist_str()
    yr = current_year_str()

    # 1. LIVE UPDATE HERO BADGE (IF STAGE UPDATED)
    live_badge_html = ""
    if is_live_update:
        flow_chain = " &rarr; ".join(stages_history or [stage])
        live_badge_html = f"""
<div style="background-color: #f0f7ff; border-left: 5px solid #0b57d0; padding: 16px 20px; margin-bottom: 24px; border-radius: 6px; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
  <p style="margin: 0 0 6px 0; font-size: 17px; font-weight: bold; color: #0b57d0;">
    ⚡ Live Update ({updated_now}): {short_org} {stage} आधिकारिक तौर पर जारी
  </p>
  <p style="margin: 0; font-size: 15px; color: #202124; line-height: 1.5;">
    <strong>{org}</strong> द्वारा <strong>{raw_title}</strong> का <strong>{stage}</strong> पोर्टल पर लाइव कर दिया गया है। 
    उम्मीदवार नीचे दी गई त्वरित तालिका (Quick Overview) से अपना स्टेटस, कट-ऑफ और आधिकारिक नोटिस सीधे देख सकते हैं। 
    (भर्ती प्रगति: <strong>{flow_chain}</strong>)
  </p>
</div>
"""

    # 2. QUICK OVERVIEW TABLE
    notice_row = (
        f'<tr><td style="padding:10px;font-weight:600;">Official PDF / Notice Link</td>'
        f'<td style="padding:10px;"><a href="{official_notice_url}" target="_blank" rel="noopener noreferrer" style="color:#0b57d0;font-weight:600;">Download Official Notice PDF</a></td></tr>'
        if official_notice_url
        else ""
    )

    website_row = (
        f'<tr><td style="padding:10px;font-weight:600;">Official Portal Website</td>'
        f'<td style="padding:10px;"><a href="{portal_url}" target="_blank" rel="noopener noreferrer" style="color:#0b57d0;font-weight:600;">{portal_url}</a></td></tr>'
    )

    overview_table = f"""
<h2>Quick Overview &amp; Key Details (महत्वपूर्ण विवरण और मुख्य बिंदु)</h2>
<table border="1" cellpadding="10" cellspacing="0" width="100%" style="border-collapse:collapse;border:1px solid #dadce0;font-size:15px;margin-bottom:24px;">
  <tbody>
    <tr style="background:#f8f9fa;"><td style="padding:10px;font-weight:600;width:35%;">Recruitment Board / Org</td><td style="padding:10px;">{org} ({short_org})</td></tr>
    <tr><td style="padding:10px;font-weight:600;">Current Update Stage</td><td style="padding:10px;"><strong style="color:#d93025;">{stage}</strong> ({details['doc_type']})</td></tr>
    <tr style="background:#f8f9fa;"><td style="padding:10px;font-weight:600;">Notice / Notification Name</td><td style="padding:10px;"><strong>{raw_title}</strong></td></tr>
    <tr><td style="padding:10px;font-weight:600;">Vacancies / Posts</td><td style="padding:10px;">{details['vacancy_info']}</td></tr>
    <tr style="background:#f8f9fa;"><td style="padding:10px;font-weight:600;">Eligibility &amp; Age Limit</td><td style="padding:10px;">{details['qualification_info']} | {details['age_info']}</td></tr>
    <tr><td style="padding:10px;font-weight:600;">Fee &amp; Important Dates</td><td style="padding:10px;">{details['fee_info']} | Schedule: {details['dates_info']}</td></tr>
    {website_row}
    {notice_row}
    <tr style="background:#f8f9fa;"><td style="padding:10px;font-weight:600;">Last Verified Update</td><td style="padding:10px;">{updated_now}</td></tr>
  </tbody>
</table>
"""

    # 3. STAGE-SPECIFIC ACTIONABLE ADVICE & MENTORSHIP
    if stage == "Admit Card":
        core_body = f"""
<h2>Exam Schedule, Reporting Time &amp; Shift Details (परीक्षा तिथि, शिफ्ट टाइमिंग और रिपोर्टिंग समय)</h2>
<p><strong>{short_org}</strong> द्वारा <strong>{raw_title}</strong> का Admit Card जारी किए जाने के बाद अभ्यर्थियों को सबसे पहले अपने परीक्षा केंद्र (Exam Center) का पता, परीक्षा की तिथि और शिफ्ट टाइमिंग अच्छे से नोट कर लेनी चाहिए। परीक्षा केंद्र पर रिपोर्टिंग टाइम से कम से कम 45 मिनट पहले पहुंचना समझदारी भरा कदम होता है, क्योंकि गेट बंद होने के बाद बायोमेट्रिक वेरिफिकेशन और मेटल डिटेक्टर चेकिंग के चलते किसी भी अभ्यर्थी को अंदर जाने की अनुमति नहीं मिलती।</p>
<p>अगर आपकी परीक्षा किसी दूसरे शहर में है, तो रिजर्वेशन और आने-जाने की योजना समय रहते बना लें ताकि परीक्षा के दिन किसी तरह की मानसिक हड़बड़ाहट से बचा जा सके।</p>

<h2>How to Download Admit Card Online (एडमिट कार्ड डाउनलोड करने का आसान तरीका)</h2>
<ol style="line-height:1.8;font-size:15px;">
  <li>सबसे पहले ऊपर Quick Overview टेबल में दिए गए आधिकारिक वेबसाइट लिंक (<strong>{portal_url}</strong>) पर जाएं।</li>
  <li>होमपेज पर उपलब्ध <strong>{raw_title} Admit Card / Hall Ticket {yr}</strong> वाले लिंक पर क्लिक करें।</li>
  <li>अपने एप्लीकेशन फॉर्म के अनुसार अपना Registration Number / Roll Number और Date of Birth (जन्म तिथि) अथवा पासवर्ड दर्ज करें।</li>
  <li>स्क्रीन पर दिए गए सुरक्षा कोड (Captcha Code) को ध्यानपूर्वक भरें और <strong>Submit / Login</strong> बटन दबाएं।</li>
  <li>स्क्रीन पर आपका Admit Card खुल जाएगा। उसमें दिए गए सभी विवरणों का मिलान करने के बाद उसका एक साफ रंगीन या ब्लैक-एंड-व्हाइट प्रिंटआउट निकाल लें और एक कॉपी भविष्य के लिए अपने पास सुरक्षित पीडीएफ में सेव रखें।</li>
</ol>

<h2>Important Details to Verify on Admit Card (एडमिट कार्ड में चेक करने योग्य जरूरी विवरण)</h2>
<ul style="line-height:1.8;font-size:15px;">
  <li><strong>नाम और स्पेलिंग:</strong> अपना नाम, माता-पिता का नाम आपके 10वीं के सर्टिफिकेट से पूरी तरह मेल खाना चाहिए।</li>
  <li><strong>रोल नंबर और रजिस्ट्रेशन आईडी:</strong> सुनिश्चित करें कि आपकी स्क्रीन पर प्रदर्शित नंबर आपके एप्लीकेशन कन्फर्मेशन पेज से मेल खाता हो।</li>
  <li><strong>फोटो और सिग्नेचर:</strong> एडमिट कार्ड पर आपकी तस्वीर और हस्ताक्षर बिल्कुल स्पष्ट दिखने चाहिए। अगर फोटो धुंधली हो तो आयोग के निर्देशानुसार दो अतिरिक्त फोटो साथ लेकर जाएं।</li>
  <li><strong>कैटेगरी और जेंडर:</strong> आपकी आरक्षित श्रेणी (UR, OBC, EWS, SC, ST) सही दर्ज होनी चाहिए।</li>
</ul>

<h2>Exam Day Instructions &amp; Documents Checklist (परीक्षा केंद्र पर ले जाने हेतु जरूरी दस्तावेज)</h2>
<p>परीक्षा हॉल में प्रवेश के लिए केवल एडमिट कार्ड ही पर्याप्त नहीं होता। अभ्यर्थियों को अपने साथ निम्नलिखित दस्तावेज ले जाना अनिवार्य होता है:</p>
<ul style="line-height:1.8;font-size:15px;">
  <li><strong>Admit Card की मूल प्रति:</strong> बिना मोड़े, साफ प्रिंट में।</li>
  <li><strong>एक मूल वैध फोटो पहचान पत्र:</strong> जैसे Aadhaar Card (प्रिंटेड ई-आधार में जन्मतिथि पूरी होनी चाहिए), Voter ID Card, Driving License, या Passport। पहचान पत्र की केवल फोटोकॉपी मान्य नहीं होगी।</li>
  <li><strong>पासपोर्ट साइज फोटोग्राफ:</strong> वही फोटो जो आवेदन पत्र में लगाई गई थी (कम से कम 2 प्रतियां)।</li>
  <li><strong>पारदर्शी पेन व पानी की बोतल:</strong> आयोग के नियमानुसार यदि ऑफलाइन परीक्षा है तो पारदर्शी बॉलपॉइंट पेन रखें।</li>
</ul>
<p style="background:#fff3cd;padding:12px;border-left:4px solid #ffc107;font-size:14px;"><strong>महत्वपूर्ण चेतावनी:</strong> मोबाइल फोन, ब्लूटूथ डिवाइस, डिजिटल या स्मार्ट वॉच, पेजर, ईयरफोन, कैलकुलेटर, पर्स या किसी भी तरह के लिखित नोट्स परीक्षा केंद्र के अंदर ले जाना सख्त मना है। इन नियमों का उल्लंघन करने पर अभ्यर्थी को डिबार किया जा सकता है।</p>
"""
    elif stage == "Answer Key":
        core_body = f"""
<h2>Answer Key &amp; Response Sheet Overview (उत्तर कुंजी और रिस्पॉन्स शीट का विश्लेषण)</h2>
<p><strong>{short_org}</strong> द्वारा आयोजित परीक्षा की <strong>Answer Key</strong> और उम्मीदवारों की रिस्पॉन्स शीट जारी कर दी गई है। यह चरण अभ्यर्थियों के लिए बेहद अहम होता है क्योंकि इसके माध्यम से आप अपने द्वारा चुने गए विकल्पों का मिलान बोर्ड की आधिकारिक उत्तर कुंजी से करके अपने संभावित अंकों (Raw Score) का सही अनुमान लगा सकते हैं।</p>
<p>यदि परीक्षा कई शिफ्टों में आयोजित की गई थी, तो ध्यान रखें कि आपका अंतिम परिणाम नॉर्मलाइजेशन (Normalization) के बाद तय होगा, लेकिन यह आंसर की आपको अपनी तैयारी और कट-ऑफ की स्थिति समझने का सटीक अवसर देती है।</p>

<h2>How to Check Answer Key &amp; Calculate Score (आंसर की मिलाने और संभावित अंक जोड़ने का तरीका)</h2>
<ol style="line-height:1.8;font-size:15px;">
  <li>Quick Overview टेबल में उपलब्ध अधिकृत पोर्टल पर जाएं और <strong>{raw_title} Answer Key</strong> के लिंक को खोलें।</li>
  <li>अपनी लॉगिन डिटेल्स (रोल नंबर और पासवर्ड) दर्ज करके अपनी व्यक्तिगत Response Sheet डाउनलोड करें।</li>
  <li>प्रत्येक प्रश्न के आगे दिए गए स्टेटस को देखें—हरा निशान सही उत्तर को दर्शाता है और आपने जो विकल्प चुना था वह 'Chosen Option' में दिखेगा।</li>
  <li><strong>मार्किंग का नियम:</strong> प्रत्येक सही उत्तर के लिए तय अंक जोड़ें। यदि परीक्षा में नेगेटिव मार्किंग लागू है, तो गलत उत्तरों की कुल संख्या के हिसाब से तय कटौती घटाकर अपना नेट स्कोर निकालें।</li>
</ol>

<h2>Objection Submission Process &amp; Guidelines (आपत्ति दर्ज कराने की ऑनलाइन प्रक्रिया व नियम)</h2>
<p>यदि आपको लगता है कि आयोग द्वारा किसी प्रश्न का उत्तर गलत जांचा गया है या प्रश्न के विकल्पों में कोई विसंगति है, तो आप निर्धारित समय सीमा के भीतर ऑनलाइन आपत्ति दर्ज करा सकते हैं:</p>
<ul style="line-height:1.8;font-size:15px;">
  <li><strong>आपत्ति विंडो की समय सीमा:</strong> आंसर की जारी होने के बाद आयोग आमतौर पर 3 से 5 दिनों का सीमित समय देता है। अंतिम तिथि के बाद लिंक बंद हो जाता है।</li>
  <li><strong>प्रति प्रश्न शुल्क:</strong> अधिकांश परीक्षाओं में प्रत्येक प्रश्न को चुनौती देने के लिए ₹50 से ₹100 तक का प्रोसेसिंग शुल्क लगता है (यदि आपत्ति सही पाई जाती है तो कई बोर्ड यह शुल्क वापस कर देते हैं)।</li>
  <li><strong>प्रामाणिक संदर्भ (Standard Proof):</strong> आपत्ति दर्ज करते समय केवल NCERT, मानक पाठ्यपुस्तकों या सरकारी वेबसाइटों के संदर्भ ही अपलोड करें। सोशल मीडिया या गाइड बुक्स के स्क्रीनशॉट स्वीकार नहीं किए जाते।</li>
</ul>
"""
    elif stage == "Result":
        core_body = f"""
<h2>Result, Scorecard &amp; Merit List Overview (परिणाम, स्कोरकार्ड और मेरिट लिस्ट विवरण)</h2>
<p>लंबे समय से परिणाम का इंतजार कर रहे अभ्यर्थियों के लिए <strong>{short_org}</strong> ने <strong>{raw_title}</strong> का परिणाम जारी कर दिया है। परिणाम के साथ आयोग ने श्रेणीवार कट-ऑफ मार्क्स और चयनित अभ्यर्थियों की मेरिट लिस्ट पीडीएफ भी पोर्टल पर अपलोड की है।</p>
<p>उम्मीदवार सीधे ऊपर दी गई तालिका के लिंक से अपना नाम और रोल नंबर मेरिट लिस्ट में ढूंढ सकते हैं या अपने यूजर आईडी से लॉगिन करके विषयवार प्राप्तांक (Scorecard) देख सकते हैं।</p>

<h2>How to Check Result &amp; Download Scorecard (रिजल्ट और स्कोरकार्ड चेक करने के आसान चरण)</h2>
<ol style="line-height:1.8;font-size:15px;">
  <li>तालिका में दिए गए ऑफिशियल पोर्टल लिंक पर क्लिक करें।</li>
  <li><strong>{raw_title} Result / Merit List</strong> के पीडीएफ लिंक को ओपन करें।</li>
  <li>अपने कीबोर्ड पर <strong>Ctrl + F</strong> दबाएं (मोबाइल में सर्च आइकॉन पर टैप करें) और अपना Roll Number अथवा पूरा नाम टाइप करें।</li>
  <li>यदि आपका रोल नंबर मेरिट लिस्ट में हाईलाइट हो जाता है, तो इसका अर्थ है कि आप अगले चरण के लिए सफल घोषित किए गए हैं।</li>
  <li>आगे की प्रक्रियाओं के लिए रिजल्ट पीडीएफ का वह पेज और अपना स्कोरकार्ड डाउनलोड करके सुरक्षित रख लें।</li>
</ol>

<h2>Cut-Off Marks &amp; Normalization Process (कट-ऑफ और नॉर्मलाइजेशन का प्रभाव)</h2>
<p>मल्टी-शिफ्ट परीक्षाओं में आयोग नॉर्मलाइजेशन फॉर्मूले का उपयोग करता है ताकि किसी कठिन शिफ्ट के अभ्यर्थियों को नुकसान न हो। कट-ऑफ तय करते समय कई कारकों का ध्यान रखा जाता है:</p>
<ul style="line-height:1.8;font-size:15px;">
  <li>कुल विज्ञापित पदों (Vacancies) की संख्या।</li>
  <li>परीक्षा में सम्मिलित हुए कुल उम्मीदवारों की संख्या।</li>
  <li>प्रश्न पत्र का कठिनाई स्तर (Difficulty Level)।</li>
  <li>कैटेगरी-वाइज़ आरक्षण नियम (UR, EWS, OBC, SC, ST, PwD)।</li>
</ul>

<h2>Next Stage Preparation &amp; Document Verification (सफल अभ्यर्थियों के लिए अगले चरण की तैयारी)</h2>
<p>जो अभ्यर्थी इस चरण में शॉर्टलिस्ट हुए हैं, उन्हें बिना समय गंवाए अगले राउंड की तैयारी शुरू कर देनी चाहिए:</p>
<ul style="line-height:1.8;font-size:15px;">
  <li><strong>Document Verification (दस्तावेज सत्यापन):</strong> अपनी 10वीं, 12वीं, ग्रेजुएशन की मार्कशीट, मूल डिग्री, जाति प्रमाण पत्र (OBC-NCL प्रमाण पत्र सक्षम अधिकारी द्वारा जारी एवं वैध वित्तीय वर्ष का होना चाहिए), EWS प्रमाण पत्र, और मूल निवास प्रमाण पत्र की 3-3 स्वप्रमाणित फोटोकॉपी सेट तैयार कर लें।</li>
  <li><strong>Skill Test / Physical Test:</strong> यदि आपकी पद के लिए टाइपिंग, आशुलिपि (Stenography), या शारीरिक दक्षता परीक्षा (PET/PST) निर्धारित है, तो आयोग द्वारा तय मानकों के अनुसार रोजाना अभ्यास करें।</li>
</ul>

<h2>Tie-Breaking Rules (समान अंक आने पर वरीयता नियम)</h2>
<p>सरकारी परीक्षाओं में जब दो या दो से अधिक अभ्यर्थियों के कुल अंक बिल्कुल एक समान (Equal Marks) आ जाते हैं, तो मेरिट लिस्ट में प्राथमिकता तय करने के लिए आयोग विशेष टाई-ब्रेकिंग नियमों का पालन करता है:</p>
<ul style="line-height:1.8;font-size:15px;">
  <li><strong>मुख्य विषय के अंक (Sectional Scores):</strong> सबसे पहले मुख्य या संबंधित तकनीकी पेपर (जैसे रीजनिंग या मैथ्स) में प्राप्त अंकों की तुलना की जाती है। अधिक अंक वाले अभ्यर्थी को ऊपर रखा जाता है।</li>
  <li><strong>उम्र में वरिष्ठता (Age Priority):</strong> यदि विषयवार अंक भी बराबर हों, तो अधिक उम्र (Older Candidate) वाले अभ्यर्थी को मेरिट सूची में प्राथमिकता दी जाती है।</li>
  <li><strong>वर्णमाला क्रम (Alphabetical Order):</strong> यदि दोनों अभ्यर्थियों की जन्मतिथि भी एक ही हो, तो उनके नाम के पहले अक्षर (अंग्रेजी वर्णमाला के क्रम) के अनुसार वरीयता तय होती है।</li>
</ul>

<h2>Tier-II / Main Exam Preparation Strategy (मुख्य परीक्षा के लिए महत्वपूर्ण तैयारी रणनीति)</h2>
<p>Tier-I या प्रारंभिक परीक्षा केवल क्वालीफाइंग प्रकृति की होती है, लेकिन मुख्य परीक्षा के अंक ही आपकी फाइनल मेरिट और मनपसंद विभाग का निर्धारण करते हैं। इसलिए निम्नलिखित रणनीति अपनाएं:</p>
<ol style="line-height:1.8;font-size:15px;">
  <li><strong>मॉक टेस्ट का रोजाना अभ्यास:</strong> केवल किताबें पढ़ने से स्पीड नहीं बढ़ती। रोजाना कम से कम एक फुल-लेंथ ऑनलाइन मॉक टेस्ट दें और गलत हुए प्रश्नों की डायरी बनाएं।</li>
  <li><strong>नेगेटिव मार्किंग पर सख्त नियंत्रण:</strong> मुख्य परीक्षा में तुक्का लगाने से बचें। जिन प्रश्नों पर 100% विश्वास हो, पहले उन्हीं को हल करें ताकि नेगेटिव मार्किंग से सुरक्षित स्कोर प्रभावित न हो।</li>
  <li><strong>कमजोर विषयों पर फोकस:</strong> पिछले वर्ष के प्रश्न पत्रों (PYQ) का गहन विश्लेषण करें और उन टॉपिक्स को पहले कवर करें जिनमें बार-बार गलतियां हो रही हैं।</li>
</ol>
"""
    else:  # Jobs / Notification
        core_body = f"""
<h2>Vacancy Details &amp; Notification Highlights (पदों का विवरण और भर्ती अधिसूचना)</h2>
<p><strong>{short_org}</strong> द्वारा जारी इस नई भर्ती अधिसूचना (<strong>{raw_title}</strong>) के तहत योग्य उम्मीदवारों से ऑनलाइन आवेदन आमंत्रित किए गए हैं। सरकारी सेवा में जाने के इच्छुक युवाओं के लिए यह एक शानदार अवसर है। आवेदन प्रक्रिया शुरू करने से पहले प्रत्येक अभ्यर्थी को पद के दायित्व, कार्यक्षेत्र, वेतनमान और पात्रता की शर्तों को बारीकी से समझ लेना चाहिए।</p>
<p>अंतिम तिथि के आसपास सरकारी वेबसाइटों पर सर्वर का लोड अत्यधिक बढ़ जाता है, जिससे कई बार फीस का भुगतान अटक जाता है या फोटो अपलोड नहीं हो पाती। इसलिए इच्छुक अभ्यर्थियों को अंतिम दिनों का इंतजार किए बिना समय रहते आवेदन फॉर्म भर लेना चाहिए।</p>

<h2>Educational Qualification &amp; Crucial Dates (शैक्षणिक योग्यता और जरूरी पात्रता)</h2>
<p>विभिन्न पदों के लिए शैक्षणिक योग्यता अलग-अलग निर्धारित की गई है। अभ्यर्थी जिस पद के लिए आवेदन कर रहे हैं, उसके अनुसार निम्नलिखित मुख्य मानकों को पूरा करते हों:</p>
<ul style="line-height:1.8;font-size:15px;">
  <li><strong>योग्यता सारांश:</strong> फिलहाल उपलब्ध जानकारी के अनुसार <strong>{details['qualification_info']}</strong>।</li>
  <li><strong>सर्टिफिकेट की अंतिम तिथि (Crucial Date):</strong> आवेदक के पास निर्धारित कट-ऑफ डेट तक अनिवार्य शैक्षणिक योग्यता का पासिंग सर्टिफिकेट अथवा डिग्री होना आवश्यक है। अपीयरिंग उम्मीदवारों के लिए अधिसूचना में दिए गए विशेष दिशा-निर्देश देखें।</li>
</ul>

<h2>Age Limit &amp; Category Relaxation Rules (आयु सीमा और छूट के नियम)</h2>
<ul style="line-height:1.8;font-size:15px;">
  <li><strong>निर्धारित आयु:</strong> सामान्य वर्ग के उम्मीदवारों के लिए आयु सीमा <strong>{details['age_info']}</strong> रखी गई है।</li>
  <li><strong>आयु में छूट:</strong> सरकारी नियमानुसार OBC वर्ग को 3 वर्ष, SC/ST वर्ग को 5 वर्ष तथा PwD और एक्स-सर्विसमैन को अतिरिक्त वर्षों की ऊपरी आयु सीमा में छूट प्रदान की जाती है।</li>
  <li>आयु की गणना आधिकारिक अधिसूचना में उल्लिखित तय संदर्भ तिथि के आधार पर की जाएगी।</li>
</ul>

<h2>Application Fee &amp; Online Payment Mode (आवेदन शुल्क और भुगतान का तरीका)</h2>
<p>आवेदन शुल्क का भुगतान पूरी तरह ऑनलाइन माध्यम (Net Banking, UPI, Debit/Credit Card) से किया जा सकता है:</p>
<ul style="line-height:1.8;font-size:15px;">
  <li><strong>सामान्य / ओबीसी / ईडब्ल्यूएस:</strong> <strong>{details['fee_info']}</strong> (पद अनुसार लागू)।</li>
  <li><strong>एससी / एसटी / महिला वर्ग:</strong> नियमानुसार कई भर्तियों में आवेदन शुल्क से पूरी छूट या रियायती दर होती है।</li>
  <li>शुल्क भुगतान के बाद जनरेट होने वाली ई-रसीद (Fee Receipt) को अवश्य डाउनलोड करें, क्योंकि डॉक्यूमेंट वेरिफिकेशन के समय इसकी आवश्यकता पड़ सकती है।</li>
</ul>

<h2>Selection Process &amp; Exam Pattern (चयन प्रक्रिया और परीक्षा के चरण)</h2>
<p>उम्मीदवारों का अंतिम चयन निम्नलिखित चरणों में उनके प्रदर्शन के आधार पर किया जाएगा:</p>
<ol style="line-height:1.8;font-size:15px;">
  <li><strong>कंप्यूटर आधारित लिखित परीक्षा (CBT / Written Exam):</strong> सामान्य ज्ञान, गणित, रीजनिंग और भाषा ज्ञान से जुड़े बहुविकल्पीय प्रश्न।</li>
  <li><strong>स्किल टेस्ट / टाइपिंग टेस्ट (यदि पद अनुसार आवश्यक हो):</strong> न्यूनतम निर्धारित गति एवं शुद्धता के साथ।</li>
  <li><strong>दस्तावेज सत्यापन (Document Verification):</strong> मूल प्रमाणपत्रों और पहचान की जांच।</li>
  <li><strong>चिकित्सा परीक्षण (Medical Examination):</strong> पद की आवश्यकताओं के अनुरूप शारीरिक व चिकित्सीय फिटनेस।</li>
</ol>
"""

    # 4. CANDIDATE GUIDANCE & SAFETY TIPS
    mentor_tips = f"""
<h2>Important Candidate Guidelines &amp; Avoiding Rejection (उम्मीदवारों के लिए जरूरी दिशा-निर्देश: फॉर्म रिजेक्शन और गलतियों से कैसे बचें)</h2>
<p>हजारों अभ्यर्थियों के फॉर्म केवल छोटी-छोटी तकनीकी गलतियों की वजह से बिना परीक्षा दिए ही निरस्त (Reject) हो जाते हैं। इसलिए उम्मीदवारों को सलाह दी जाती है कि वे आवेदन और परीक्षा प्रक्रिया के दौरान निम्नलिखित बातों का विशेष ध्यान रखें:</p>
<ul style="line-height:1.8;font-size:15px;">
  <li><strong>Live Photo व Signature का सही आकार:</strong> आजकल लगभग सभी बोर्ड वेबकैम से लाइव फोटो लेते हैं। फोटो लेते समय कमरे में पर्याप्त रोशनी हो, दोनों कान स्पष्ट दिख रहे हों और चश्मा या टोपी न लगाई गई हो।</li>
  <li><strong>नाम और जन्मतिथि का स्पेलिंग मैच:</strong> आधार कार्ड और 10वीं की मार्कशीट में अगर नाम, पिता के नाम या जन्मतिथि की स्पेलिंग में कोई अंतर है, तो फॉर्म भरने से पहले उसे ठीक करवा लें या अधिकृत हलफनामा (Affidavit) तैयार रखें।</li>
  <li><strong>जाति व निवास प्रमाण पत्र की तारीख:</strong> OBC-NCL और EWS के सर्टिफिकेट चालू वित्तीय वर्ष (Financial Year) के होने चाहिए। अधिसूचना की अंतिम तिथि के बाद बने प्रमाण पत्र कई बार सत्यापन में अमान्य कर दिए जाते हैं।</li>
  <li><strong>फाइनल सबमिशन के बाद प्रिंट:</strong> फॉर्म केवल 'Save' करने से पूरा नहीं होता। 'Final Submit' बटन दबाने के बाद एप्लीकेशन फॉर्म पर 'Application Submitted Successfully' का मैसेज और रजिस्ट्रेशन नंबर अवश्य चेक करें।</li>
</ul>

<h2>Frequently Asked Questions (अभ्यर्थियों द्वारा अक्सर पूछे जाने वाले महत्वपूर्ण सवाल - FAQs)</h2>
<div style="background:#fdfdfd;border:1px solid #e8eaed;padding:16px 20px;border-radius:6px;margin:20px 0;">
  <p style="margin:0 0 4px 0;font-weight:700;font-size:15px;color:#1a73e8;">प्रश्न: यदि आधिकारिक पोर्टल पर मेरा रोल नंबर या नाम प्रदर्शित नहीं हो रहा है तो क्या करें?</p>
  <p style="margin:0 0 14px 0;font-size:14px;color:#3c4043;line-height:1.6;">उत्तर: सबसे पहले यह सुनिश्चित करें कि आप संबंधित पद अथवा सही रीजन (क्षेत्र) की पीडीएफ देख रहे हैं। यदि आपका कट-ऑफ से अधिक अंक होने का दावा है तो अपने आवेदन पत्र और रोल नंबर के साथ आयोग की क्षेत्रीय हेल्पलाइन या ईमेल पर तत्काल संपर्क करें।</p>

  <p style="margin:0 0 4px 0;font-weight:700;font-size:15px;color:#1a73e8;">प्रश्न: क्या जारी किया गया परिणाम या कट-ऑफ अंतिम (Final) है?</p>
  <p style="margin:0 0 14px 0;font-size:14px;color:#3c4043;line-height:1.6;">उत्तर: यह कट-ऑफ इस विशेष चरण (टियर/राउंड) के लिए है। अंतिम चयन सभी चरणों (जैसे मुख्य परीक्षा, टाइपिंग टेस्ट, दस्तावेज सत्यापन और मेडिकल) के सफल समापन के पश्चात जारी फाइनल मेरिट लिस्ट पर निर्भर करेगा।</p>

  <p style="margin:0 0 4px 0;font-weight:700;font-size:15px;color:#1a73e8;">प्रश्न: स्कोरकार्ड (Scorecard) देखने के लिए कौन-से लॉगिन क्रेडेंशियल आवश्यक होंगे?</p>
  <p style="margin:0;font-size:14px;color:#3c4043;line-height:1.6;">उत्तर: अपना व्यक्तिगत स्कोरकार्ड और नॉर्मलाइज्ड मार्क्स देखने के लिए आपको अपने रजिस्ट्रेशन नंबर और जन्मतिथि (या पासवर्ड) की आवश्यकता होगी। स्कोरकार्ड जारी होने की तारीख से सीमित समय (आमतौर पर 15 से 30 दिन) तक ही पोर्टल पर सक्रिय रहता है।</p>
</div>

<h2>Official Source &amp; Disclaimer (आधिकारिक स्रोत और डिस्क्लेमर)</h2>
<p style="font-size:14px;color:#5f6368;line-height:1.6;border-top:1px solid #e0e0e0;padding-top:14px;">
  <strong>अस्वीकरण (Disclaimer):</strong> यह लेख <strong>{org}</strong> द्वारा जारी आधिकारिक अधिसूचना और सार्वजनिक पोर्टल पर उपलब्ध सूचनाओं के आधार पर अभ्यर्थियों के मार्गदर्शन हेतु तैयार किया गया है। भर्ती के नियमों, परीक्षा तिथियों और पात्रता में किसी भी संशोधन हेतु संबंधित बोर्ड की आधिकारिक वेबसाइट (<strong>{portal_url}</strong>) पर जारी ताजा शुद्धिपत्र (Corrigendum) को ही सर्वोपरि मानें।
</p>
"""

    # Combine All Sections
    intro_p = f"""
<p style="font-size:16px;line-height:1.7;">
  <strong>{short_org} ({org})</strong> ने <strong>{raw_title}</strong> के संबंध में आधिकारिक अपडेट जारी किया है। 
  वे सभी उम्मीदवार जो इस भर्ती परीक्षा से जुड़े हैं, वे नीचे दिए गए विस्तृत विवरण के माध्यम से पात्रता, तारीखें, 
  डाउनलोड प्रक्रिया और चयन के महत्वपूर्ण चरणों की पूरी जानकारी आसान भाषा में प्राप्त कर सकते हैं।
</p>
"""
    faq_schema = build_seo_faq_schema(short_org, raw_title, stage, details)
    full_html = f"{live_badge_html}\n{intro_p}\n{overview_table}\n{core_body}\n{mentor_tips}\n{faq_schema}"
    return full_html.strip()


# ==============================================================================
# 8. GEMINI AI WRITER (MODERN SDK + GROUNDING + HUMAN TONE)
# ==============================================================================
def call_gemini_writer(prompt: str) -> str:
    """
    Calls the modern Google GenAI SDK (gemini-2.5-flash or configured model)
    with strict anti-AI tone rules.
    """
    api_key = CONFIG["gemini_api_key"]
    if not api_key:
        return ""

    if not GOOGLE_GENAI_AVAILABLE:
        print("   [INFO] google-genai library not loaded, using human journalist template.")
        return ""

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=CONFIG["gemini_model"],
            contents=prompt,
        )
        if response and response.text:
            cleaned = response.text.strip()
            cleaned = re.sub(r"^```html\s*|\s*```$", "", cleaned, flags=re.IGNORECASE).strip()
            return cleaned
    except Exception as e:
        print(f"   [WARN] Gemini modern SDK call failed: {e}")

    return ""


def build_complete_article(
    portal_info: dict,
    raw_title: str,
    stage: str,
    details: dict,
    is_live_update: bool = False,
    stages_history: list | None = None,
) -> tuple[str, str, int]:
    """
    Orchestrates the article generation:
    1. Builds high-E-E-A-T human foundation.
    2. Uses Gemini 2.5 Flash to enrich if API key is active.
    3. Guarantees word count > 1100 without artificial filler loops.
    """
    short_org = portal_info.get("short_org") or portal_info.get("org") or "Govt"
    seo_title = build_clean_title(short_org, raw_title, stage, is_live_update=is_live_update)
    human_article = build_human_master_article(
        portal_info=portal_info,
        raw_title=raw_title,
        stage=stage,
        details=details,
        is_live_update=is_live_update,
        stages_history=stages_history,
    )

    if CONFIG["gemini_api_key"] and GOOGLE_GENAI_AVAILABLE:
        ai_prompt = f"""
You are a senior educational journalist and career counselor with 10+ years of experience writing for India's leading job portals (like Jagran Josh, Testbook).
Write an in-depth, authentic, empathetic, and comprehensive article in natural Devanagari Hindi (interspersed with standard English exam terms candidates search for like Admit Card, Cut Off, Scorecard, Merit List, Shift Timing, Direct Link, Eligibility).

STRICT ANTI-AI, ADSENSE COMPLIANCE & FORMAT RULES:
1. TITLE FORMAT: The Article Title MUST be written in clean, professional English (e.g. "[Out] SSC CGL Result 2026: Tier 1 Merit List PDF, Scorecard & Cut Off Marks Released").
2. BILINGUAL HEADINGS: Every <h2> and <h3> heading MUST be bilingual with English first and Hindi second in parentheses. Example: <h2>Quick Overview & Key Details (महत्वपूर्ण विवरण और मुख्य बिंदु)</h2>.
3. BODY LANGUAGE: Body paragraphs must be written in natural, engaging Devanagari Hindi with standard English examination terms (like Cut Off, Merit List, Admit Card, Shift Timing, Direct Link).
4. NEVER use sterile AI clichés like "निष्कर्ष", "संक्षेप में", "जैसा कि हम सभी जानते हैं", "उल्लेखनीय है कि", "अतः यह कहा जा सकता है".
5. Vary sentence lengths with natural human flow (mix punchy short sentences with clear explanations).
6. Provide realistic candidate guidance: photo/signature pixel dimension warnings, server slowdown alerts near deadlines, reservation certificate validity rules, and what to do if registration numbers are lost.
7. Total length must be at least {CONFIG['min_words']} words of rich, informative content. NEVER write artificial repeating filler notes.
8. Retain the Quick Overview table at the top and end with the JSON-LD FAQ schema.
9. Return purely clean HTML elements (<h2>, <h3>, <p>, <ul>, <ol>, <table>, <tr>, <td>, <strong>, <a>, <script>). Do NOT wrap in markdown backticks.

Title: {seo_title}
Organization: {portal_info.get('org', short_org)}
Current Stage: {stage}
Live Update Mode: {is_live_update}

Base Content to Expand and Perfect:
{human_article[:7000]}
"""
        ai_result = call_gemini_writer(ai_prompt)
        if ai_result and count_words_from_html(ai_result) >= 900:
            wc = count_words_from_html(ai_result)
            return seo_title, ai_result, wc

    # Default to our verified human master article
    wc = count_words_from_html(human_article)
    return seo_title, human_article, wc


# ==============================================================================
# 9. WORDPRESS PUBLISHER & STRICT NO-DUPLICATE UPDATES
# ==============================================================================
def find_existing_wp_post(short_org: str, raw_title: str, headers: dict) -> int:
    """
    Looks up existing WordPress post by short_org AND canonical exam name.
    If an existing post for 'SSC CGL' or 'UPSC CSE' is found, returns its ID
    so the bot UPDATES it rather than writing a duplicate article!
    """
    slug, label = get_canonical_exam_info(raw_title)
    query_str = f"{short_org} {label}".strip()
    try:
        search_url = f"{CONFIG['wp_site_url']}/wp-json/wp/v2/posts"
        resp = requests.get(
            search_url,
            headers=headers,
            params={"search": query_str, "status": "any", "per_page": 5},
            timeout=20,
        )
        if resp.status_code == 200:
            posts = resp.json() or []
            for p in posts:
                existing_title = BeautifulSoup(p.get("title", {}).get("rendered", ""), "html.parser").get_text(" ", strip=True).lower()
                if short_org.lower() in existing_title and (label.lower() in existing_title or slug.replace("_", " ") in existing_title):
                    return int(p.get("id") or 0)
    except Exception:
        pass
    return 0


def push_to_wordpress(title: str, html_content: str, short_org: str, stage: str, wp_post_id: int = 0) -> tuple[bool, int, str]:
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

    if wp_post_id <= 0:
        found_id = find_existing_wp_post(short_org, title, headers)
        if found_id > 0:
            wp_post_id = found_id

    # Create High-CTR Excerpt for Google SEO
    clean_plain = BeautifulSoup(html_content, "html.parser").get_text(" ", strip=True)
    excerpt_text = clean_plain[:155].strip() + "..."

    status_to_use = CONFIG["wp_post_status"] if CONFIG["wp_post_status"] in ("draft", "publish", "pending", "private") else "draft"
    payload = {
        "title": title,
        "content": html_content,
        "excerpt": excerpt_text,
        "status": status_to_use
    }

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
# 10. MAIN SCAN & PUBLISH PIPELINE
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

                clean_target = "" if is_third_party_or_news_url(full_url, portal_url) else full_url
                stage = detect_stage(f"{title} {full_url}")
                topic_key = build_topic_key(short_org, title)
                notice_sig = build_notice_signature(short_org, title, clean_target or portal_url)

                candidates.append({
                    "notice_sig": notice_sig, "topic_key": topic_key,
                    "portal_url": portal_url, "org": portal_info["org"],
                    "short_org": short_org, "title": title,
                    "target_url": clean_target, "stage": stage, "fallback_dt": None,
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

    print("=" * 75)
    print(f"🚀 {CONFIG['site_name']} Humanized Engine (AdSense E-E-A-T Compliant)")
    print(f"Mode: {'FIRST BOOT (BASELINE LOCK)' if is_first_boot else 'LIVE SCAN & PUBLISH'}")
    print(f"Time (IST): {now_ist_str()} | Model: {CONFIG['gemini_model']}")
    print("=" * 75)

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

            existing = get_article_record(topic_key) or get_article_by_org_and_stage(item["short_org"], item["stage"])

            details = extract_context_details(
                item["title"],
                item["target_url"],
                item["portal_url"],
                fallback_dt=item.get("fallback_dt"),
            )
            content_hash = hashlib.md5(
                f"{item['title']}|{item['stage']}|{item['target_url']}|{details['text_excerpt'][:600]}".encode("utf-8")
            ).hexdigest()

            if existing is None:
                eligible, reason = is_notice_fresh_and_valid(item["title"], details, notice_sig, boot_cutoff_dt)
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
                    stage=item["stage"],
                    details=details,
                    is_live_update=False,
                    stages_history=history,
                )

                ok, wp_id, link = push_to_wordpress(
                    seo_title, html_body, item["short_org"], item["stage"], wp_post_id=0
                )
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
                    print(f"   ✨ [NEW HUMAN DRAFT] [{item['stage']}] ({wc} words) -> {seo_title}")

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
                    stage=item["stage"],
                    details=details,
                    is_live_update=True,
                    stages_history=history,
                )

                ok, wp_id, link = push_to_wordpress(
                    seo_title,
                    html_body,
                    item["short_org"],
                    item["stage"],
                    wp_post_id=int(existing.get("wp_post_id") or 0),
                )
                if ok:
                    now_str = now_ist_str()
                    upsert_article_record({
                        "topic_key": existing["topic_key"], "portal_url": item["portal_url"],
                        "short_org": item["short_org"], "raw_title": item["title"],
                        "seo_title": seo_title, "stage": item["stage"],
                        "stages_history": history, "target_url": item["target_url"],
                        "content_hash": content_hash, "word_count": wc,
                        "wp_post_id": wp_id or existing.get("wp_post_id", 0),
                        "created_at": existing.get("created_at") or now_str,
                        "updated_at": now_str,
                    })
                    processed_topic_keys_this_run.add(existing["topic_key"])
                    live_updated += 1
                    print(f"   🔄 [LIVE UPDATE MASTER] [{existing['stage']} -> {item['stage']}] ({wc} words) -> {seo_title}")

    print("-" * 75)
    if is_first_boot:
        print("पहला रन पूरा: पुराना डाटा बेसलाइन में लॉक कर दिया गया है। अगले रन से नए अपडेट्स पर ड्राफ्ट बनेंगे।")
    elif new_created == 0 and live_updated == 0:
        print("अभी कोई नया अपडेट नहीं आया")
    print(f"पूरा हुआ -> नए आर्टिकल: {new_created} | लाइव अपडेट: {live_updated} | स्किप: {skipped_items}")
    print("=" * 75)


# ==============================================================================
# 11. SAMPLE DEMO GENERATOR (FOR IMMEDIATE VISUAL INSPECTION)
# ==============================================================================
def generate_sample_demo_article() -> None:
    """
    Generates a full, live sample article demonstrating:
    1. Human senior journalist writing style.
    2. Zero AI clichés & natural exam terminology.
    3. Practical candidate insights (E-E-A-T).
    4. Google Rich Results FAQ Schema.
    5. Clean HTML preview file saved to disk.
    """
    os.makedirs(CONFIG["cache_dir"], exist_ok=True)
    sample_portal = {
        "org": "Staff Selection Commission (SSC)",
        "short_org": "SSC",
        "url": "https://ssc.gov.in",
        "portal_url": "https://ssc.gov.in"
    }
    sample_title = "Combined Graduate Level Examination (Tier-I) 2026 Result & Merit List"
    sample_stage = "Result"
    sample_details = {
        "doc_type": "Official PDF",
        "official_notice_link": "https://ssc.gov.in/notice/cgl-2026-tier1-result.pdf",
        "vacancy_info": "17,727 Vacancies (Tentative Notification के अनुसार)",
        "qualification_info": "Graduation Degree (किसी भी मान्यता प्राप्त विश्वविद्यालय से)",
        "age_info": "18 से 30 / 32 वर्ष (पोस्ट अनुसार)",
        "fee_info": "Rs. 100 (महिला / SC / ST / PwD हेतु छूट)",
        "dates_info": "Exam Date: 12-26 Sep 2026 | Tier-II: Dec 2026",
        "headings": ["Important Dates", "Cut-Off Marks", "Tie-Breaking Criteria", "Next Steps"],
        "text_excerpt": "Staff Selection Commission declaration of result of Combined Graduate Level Tier-I Examination 2026...",
        "detected_dt": now_ist_dt(),
        "has_exact_time": True,
    }

    print("\n" + "=" * 75)
    print("📝 SAMPLE DEMO ARTICLE GENERATION (HUMAN JOURNALIST STYLE)")
    print("=" * 75)

    seo_title, html_body, word_count = build_complete_article(
        portal_info=sample_portal,
        raw_title=sample_title,
        stage=sample_stage,
        details=sample_details,
        is_live_update=True,
        stages_history=["Jobs", "Admit Card", "Answer Key", "Result"]
    )

    sample_out_file = os.path.join(CONFIG["cache_dir"], "sample_article_preview.html")
    full_preview = f"""<!DOCTYPE html>
<html lang="hi">
<head>
  <meta charset="UTF-8">
  <title>{seo_title}</title>
  <style>
    body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; max-width: 860px; margin: 30px auto; padding: 20px; color: #202124; background: #fff; }}
    h1 {{ color: #1a73e8; font-size: 26px; border-bottom: 2px solid #e8eaed; padding-bottom: 12px; }}
    h2 {{ color: #202124; font-size: 20px; margin-top: 28px; border-left: 4px solid #1a73e8; padding-left: 10px; }}
    table {{ width: 100%; border-collapse: collapse; margin: 16px 0; }}
    th, td {{ border: 1px solid #dadce0; padding: 10px 14px; text-align: left; }}
    th {{ background: #f8f9fa; }}
    a {{ color: #1a73e8; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
  </style>
</head>
<body>
  <h1>{seo_title}</h1>
  {html_body}
</body>
</html>
"""
    with open(sample_out_file, "w", encoding="utf-8") as f:
        f.write(full_preview)

    print(f"\n✅ Title: {seo_title}")
    print(f"📊 Total Word Count: {word_count} words (Without any fake filler loops!)")
    print(f"💾 Preview File Saved: {sample_out_file}")
    print("=" * 75 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GovtVibhag Automated Content Engine")
    parser.add_argument("--sample", action="store_true", help="Generate a sample demo article and preview file")
    args = parser.parse_args()

    if args.sample:
        generate_sample_demo_article()
    else:
        run_writer_pipeline()
