import os
import re
import sys
import json
import time
import ctypes
import base64
import sqlite3
import hashlib
import datetime
from email.utils import parsedate_to_datetime
import urllib3
from urllib.parse import urljoin, urlparse, urlunparse, quote_plus
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

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# =====================================================================
# 1. WORDPRESS & AI CONFIGURATION (Auto-Reads from GitHub Secrets / Env)
# =====================================================================
WP_SITE_URL = os.getenv("WP_SITE_URL", "https://govtvibhag.com").strip()
WP_USERNAME = os.getenv("WP_USERNAME", "jeetuforvideo@gmail.com").strip()
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD", "bFMI riXU vABH xwzR eD4r diWN").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AQ.Ab8RN6JOH2SGC7DbSEgC8JPV4rnwQtP64bCe_PlS-V-2eWi-7A").strip()

# अगर आप चाहते हैं कि आर्टिकल सीधे वेबसाइट के होमपेज पर लाइव दिखे तो "publish" लिखें,
# और अगर WordPress -> Posts -> Drafts में चेक करके पब्लिश करना चाहते हैं तो "draft" रहने दें:
WP_POST_STATUS = os.getenv("WP_POST_STATUS", "draft").strip()

DB_NAME = "govt_vibhag_master.db"
DATA_FOLDER = "scraped_data_cache"
BASELINE_VERSION_KEY = "v10_strict_baseline_locked"

def disable_cmd_quickedit():
    if os.name == 'nt':
        try:
            kernel32 = ctypes.windll.kernel32
            stdin_handle = kernel32.GetStdHandle(-10)
            mode = ctypes.c_ulong()
            kernel32.GetConsoleMode(stdin_handle, ctypes.byref(mode))
            new_mode = mode.value & ~0x0040
            kernel32.SetConsoleMode(stdin_handle, new_mode)
        except Exception:
            pass

# =====================================================================
# 2. 39 OFFICIAL GOVERNMENT PORTALS
# =====================================================================
GOVT_PORTALS = [
    {"url": "https://aiimsexams.ac.in", "org": "All India Institute of Medical Sciences (AIIMS, New Delhi)", "short_org": "AIIMS", "portal_name": "AIIMS Examination Portal"},
    {"url": "https://ssc.gov.in", "org": "Staff Selection Commission (SSC)", "short_org": "SSC", "portal_name": "Official SSC Portal"},
    {"url": "https://upsc.gov.in/whats-new", "org": "Union Public Service Commission (UPSC)", "short_org": "UPSC", "portal_name": "Official UPSC Portal"},
    {"url": "https://indianrailways.gov.in", "org": "Ministry of Railways (Indian Railways)", "short_org": "RRB Railway", "portal_name": "Indian Railways Official Portal"},
    {"url": "https://www.rrbcdg.gov.in", "org": "Railway Recruitment Board (RRB)", "short_org": "RRB", "portal_name": "RRB Official Portal"},
    {"url": "https://www.indiapost.gov.in", "org": "Department of Posts (India Post)", "short_org": "India Post", "portal_name": "India Post Official Portal"},
    {"url": "https://www.drdo.gov.in/drdo/whats-new", "org": "Defence Research and Development Organisation (DRDO)", "short_org": "DRDO", "portal_name": "DRDO Official Career Portal"},
    {"url": "https://www.isro.gov.in/Careers.html", "org": "Indian Space Research Organisation (ISRO)", "short_org": "ISRO", "portal_name": "ISRO Official Portal"},
    {"url": "https://nta.ac.in/NoticeBoardArchive", "org": "National Testing Agency (NTA)", "short_org": "NTA", "portal_name": "NTA Official Examination Portal"},
    {"url": "https://ctet.nic.in", "org": "Central Board of Secondary Education (CBSE CTET)", "short_org": "CBSE CTET", "portal_name": "CTET Official Examination Portal"},
    {"url": "https://kvsangathan.nic.in/en/announcement", "org": "Kendriya Vidyalaya Sangathan (KVS)", "short_org": "KVS", "portal_name": "KVS Official Portal"},
    {"url": "https://navodaya.gov.in", "org": "Navodaya Vidyalaya Samiti (NVS)", "short_org": "NVS", "portal_name": "NVS Official Portal"},
    {"url": "https://www.ibps.in", "org": "Institute of Banking Personnel Selection (IBPS)", "short_org": "IBPS", "portal_name": "IBPS Official Portal"},
    {"url": "https://sbi.co.in/web/careers/current-openings", "org": "State Bank of India (SBI Central Recruitment)", "short_org": "SBI", "portal_name": "SBI Careers Official Portal"},
    {"url": "https://opportunities.rbi.org.in/Scripts/Vacancies.aspx", "org": "Reserve Bank of India (RBI Services Board)", "short_org": "RBI", "portal_name": "RBI Opportunities Portal"},
    {"url": "https://licindia.in/Bottom-Links/Careers", "org": "Life Insurance Corporation of India (LIC)", "short_org": "LIC", "portal_name": "LIC Official Careers Portal"},
    {"url": "https://joinindianarmy.nic.in", "org": "Indian Army (Ministry of Defence)", "short_org": "Indian Army", "portal_name": "Join Indian Army Official Portal"},
    {"url": "https://www.joinindiannavy.gov.in", "org": "Indian Navy (Har Kaam Desh Ke Naam)", "short_org": "Indian Navy", "portal_name": "Join Indian Navy Official Portal"},
    {"url": "https://agnipathvayu.cdac.in", "org": "Indian Air Force (Central Airmen Selection Board)", "short_org": "IAF Agniveer", "portal_name": "IAF CASB Official Portal"},
    {"url": "https://joinindiancoastguard.cdac.in", "org": "Indian Coast Guard (ICG)", "short_org": "Coast Guard", "portal_name": "Indian Coast Guard Portal"},
    {"url": "https://rect.crpf.gov.in", "org": "Central Reserve Police Force (CRPF)", "short_org": "CRPF", "portal_name": "CRPF Recruitment Portal"},
    {"url": "https://rectt.bsf.gov.in", "org": "Border Security Force (BSF)", "short_org": "BSF", "portal_name": "BSF Official Recruitment Portal"},
    {"url": "https://cisfrectt.cisf.gov.in", "org": "Central Industrial Security Force (CISF)", "short_org": "CISF", "portal_name": "CISF Official Recruitment Portal"},
    {"url": "https://recruitment.itbpolice.nic.in", "org": "Indo-Tibetan Border Police Force (ITBP)", "short_org": "ITBP", "portal_name": "ITBP Recruitment Portal"},
    {"url": "https://uppsc.up.nic.in", "org": "Uttar Pradesh Public Service Commission (UPPSC)", "short_org": "UPPSC", "portal_name": "UPPSC Official Portal"},
    {"url": "https://uppbpb.gov.in", "org": "Uttar Pradesh Police Recruitment & Promotion Board (UPPRPB)", "short_org": "UP Police", "portal_name": "UPPRPB Official Portal"},
    {"url": "https://upsssc.gov.in", "org": "Uttar Pradesh Subordinate Services Selection Commission (UPSSSC)", "short_org": "UPSSSC", "portal_name": "UPSSSC Official Portal"},
    {"url": "https://dsssb.delhi.gov.in", "org": "Delhi Subordinate Services Selection Board (DSSSB)", "short_org": "DSSSB", "portal_name": "DSSSB Official Portal"},
    {"url": "https://bpsc.bih.nic.in", "org": "Bihar Public Service Commission (BPSC)", "short_org": "BPSC", "portal_name": "BPSC Official Portal"},
    {"url": "https://bssc.bihar.gov.in", "org": "Bihar Staff Selection Commission (BSSC)", "short_org": "BSSC", "portal_name": "BSSC Official Portal"},
    {"url": "https://csbc.bih.nic.in", "org": "Central Selection Board of Constable (CSBC, Bihar)", "short_org": "CSBC Bihar Police", "portal_name": "CSBC Bihar Official Portal"},
    {"url": "https://rpsc.rajasthan.gov.in/news", "org": "Rajasthan Public Service Commission (RPSC)", "short_org": "RPSC", "portal_name": "RPSC Official Portal"},
    {"url": "https://rssb.rajasthan.gov.in/news", "org": "Rajasthan Staff Selection Board (RSSB / RSMSSB)", "short_org": "RSSB Rajasthan", "portal_name": "RSSB Official Portal"},
    {"url": "https://esb.mp.gov.in", "org": "Madhya Pradesh Employees Selection Board (MPESB)", "short_org": "MPESB", "portal_name": "MPESB Official Portal"},
    {"url": "https://mppsc.mp.gov.in", "org": "Madhya Pradesh Public Service Commission (MPPSC)", "short_org": "MPPSC", "portal_name": "MPPSC Official Portal"},
    {"url": "https://hssc.gov.in", "org": "Haryana Staff Selection Commission (HSSC)", "short_org": "HSSC", "portal_name": "HSSC Official Portal"},
    {"url": "https://gpsc.gujarat.gov.in", "org": "Gujarat Public Service Commission (GPSC)", "short_org": "GPSC", "portal_name": "GPSC Official Portal"},
    {"url": "https://www.mpsc.gov.in", "org": "Maharashtra Public Service Commission (MPSC)", "short_org": "MPSC", "portal_name": "MPSC Official Portal"},
    {"url": "https://tnpsc.gov.in", "org": "Tamil Nadu Public Service Commission (TNPSC)", "short_org": "TNPSC", "portal_name": "TNPSC Official Portal"}
]

JOB_KEYWORDS = ["recruitment", "vacancy", "vacancies", "notification", "advt", "advertisement", "bharti", "apply online", "online form", "detailed notice", "short notice", "employment", "opening", "post of", "examination 2026", "exam 2026", "schedule", "calendar"]
ADMIT_CARD_KEYWORDS = ["admit card", "hall ticket", "call letter", "exam city", "intimation slip", "admission certificate", "e-admit", "exam date"]
ANSWER_KEY_KEYWORDS = ["answer key", "response sheet", "question paper", "objection", "model answer", "tentative answer"]
RESULT_KEYWORDS = ["result", "merit list", "score card", "scorecard", "shortlisted", "selected candidates", "cut-off", "cutoff", "stage-ii", "stage-i", "final result", "marks", "recommend", "qualified", "list of candidates"]

IGNORE_KEYWORDS = [
    "tender", "quotation", "auction", "deputation", "pension", "rti",
    "contact us", "about us", "disclaimer", "privacy policy", "terms", "faq",
    "helpdesk", "mock test", "annual report", "seniority list", "medical reimbursement",
    "screen reader", "skip to main", "sitemap", "feedback", "accessibility", "citizen charter",
    "archive", "old question", "previous year", "holiday list", "panel", "empaneled"
]

GENERIC_MENU_TITLES = [
    "recruitment", "recruitments", "result", "results", "admit card", "admit cards",
    "answer key", "answer keys", "notification", "notifications", "advertisements",
    "recruitment advertisements", "latest news", "what's new", "apply online",
    "cut-off marks", "cutoff marks", "merit list", "career", "careers", "vacancies",
    "vacancy", "examinations", "exams", "home", "click here", "download", "view", "pdf"
]

# =====================================================================
# 3. DATABASE & STRICT BASELINE LOCK ENGINE
# =====================================================================
def normalize_url(url_str):
    try:
        p = urlparse(url_str.strip())
        clean_path = re.sub(r'/+\$', '', p.path)
        return urlunparse((p.scheme.lower(), p.netloc.lower(), clean_path, '', p.query, ''))
    except Exception:
        return url_str.strip()

def normalize_notice_key(portal_url, text_str):
    alpha_num = re.sub(r'[^a-z0-9]+', '', text_str.lower())
    return f"{urlparse(portal_url).netloc.lower()}_{alpha_num[:60]}"

def sanitize_clean_text(text_str):
    if not text_str:
        return ""
    cleaned = re.sub(r'[\ufffd\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', ' ', text_str)
    cleaned = re.sub(r'\?{2,}', ' ', cleaned)
    cleaned = re.sub(r'\(cid:\d+\)', ' ', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned

def init_db():
    if not os.path.exists(DATA_FOLDER):
        os.makedirs(DATA_FOLDER)
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS processed_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            portal_url TEXT,
            target_url TEXT UNIQUE,
            notice_key TEXT,
            raw_notice_title TEXT,
            seo_title TEXT,
            category TEXT,
            wp_post_id INTEGER DEFAULT 0,
            content_hash TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS synced_portals (
            portal_url TEXT PRIMARY KEY,
            synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bot_settings (
            setting_key TEXT PRIMARY KEY,
            setting_value TEXT
        )
    """)
    conn.commit()
    conn.close()

def ensure_fresh_v10_baseline_and_start_time():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT setting_value FROM bot_settings WHERE setting_key = ?", (BASELINE_VERSION_KEY,))
    v_row = cursor.fetchone()

    if not v_row:
        now_iso = datetime.datetime.now().isoformat()
        cursor.execute("DELETE FROM synced_portals")
        cursor.execute("INSERT OR REPLACE INTO bot_settings (setting_key, setting_value) VALUES ('bot_start_iso', ?)", (now_iso,))
        cursor.execute("INSERT OR REPLACE INTO bot_settings (setting_key, setting_value) VALUES (?, 'LOCKED')", (BASELINE_VERSION_KEY,))
        conn.commit()
        conn.close()
        return datetime.datetime.fromisoformat(now_iso)

    cursor.execute("SELECT setting_value FROM bot_settings WHERE setting_key = 'bot_start_iso'")
    row = cursor.fetchone()
    conn.close()
    return datetime.datetime.fromisoformat(row[0])

def is_portal_synced(portal_url):
    domain = urlparse(portal_url).netloc.lower()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM synced_portals WHERE portal_url LIKE ?", (f"%{domain}%",))
    row = cursor.fetchone()
    conn.close()
    return row is not None

def mark_portal_synced(portal_url):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO synced_portals (portal_url) VALUES (?)", (portal_url,))
    conn.commit()
    conn.close()

def is_already_processed(target_url, notice_key="", seo_title="", content_hash=""):
    norm_url = normalize_url(target_url)
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("SELECT 1 FROM processed_posts WHERE target_url = ? OR target_url = ?", (target_url, norm_url))
    if cursor.fetchone() is not None:
        conn.close()
        return True

    if notice_key:
        cursor.execute("SELECT 1 FROM processed_posts WHERE notice_key = ?", (notice_key,))
        if cursor.fetchone() is not None:
            conn.close()
            return True

    if seo_title and not seo_title.startswith("OLD_") and not seo_title.startswith("DUPLICATE_"):
        cursor.execute("SELECT 1 FROM processed_posts WHERE seo_title = ?", (seo_title,))
        if cursor.fetchone() is not None:
            conn.close()
            return True

    if content_hash and len(content_hash) > 10:
        cursor.execute("SELECT 1 FROM processed_posts WHERE content_hash = ?", (content_hash,))
        if cursor.fetchone() is not None:
            conn.close()
            return True

    conn.close()
    return False

def mark_as_processed(portal_url, target_url, notice_key, raw_title, seo_title, category, wp_post_id, content_hash):
    norm_url = normalize_url(target_url)
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute(
            """INSERT OR IGNORE INTO processed_posts 
               (portal_url, target_url, notice_key, raw_notice_title, seo_title, category, wp_post_id, content_hash) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (portal_url, norm_url, notice_key, raw_title, seo_title, category, wp_post_id, content_hash)
        )
        conn.commit()
    except sqlite3.Error:
        pass
    conn.close()

def update_processed_post_record(post_db_id, new_seo_title, new_category, new_hash):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        cursor.execute(
            """UPDATE processed_posts 
               SET seo_title = ?, category = ?, content_hash = ?, updated_at = ?
               WHERE id = ?""",
            (new_seo_title, new_category, new_hash, now_str, post_db_id)
        )
        conn.commit()
    except sqlite3.Error:
        pass
    conn.close()

# =====================================================================
# 4. SMART NOTIFICATION FILTER & CONTEXT EXTRACTOR
# =====================================================================
def extract_smart_link_text(link_tag):
    raw_text = sanitize_clean_text(link_tag.get_text(" ", strip=True))
    if len(raw_text) < 22 or raw_text.lower() in ["click here", "download", "pdf", "view", "link", "notice", "read more"]:
        parent_row = link_tag.find_parent(["tr", "li", "p", "div"])
        if parent_row:
            row_text = sanitize_clean_text(parent_row.get_text(" ", strip=True))
            if 15 <= len(row_text) <= 350:
                return row_text
    return raw_text

def is_genuine_notification(link_text, full_url):
    clean_text = sanitize_clean_text(link_text)
    lower_text = clean_text.lower()
    lower_url = full_url.lower()

    if len(clean_text) < 12 or len(clean_text.split()) < 3:
        return False

    if lower_text in GENERIC_MENU_TITLES:
        return False

    if any(bad in lower_text for bad in IGNORE_KEYWORDS):
        return False

    if lower_url.startswith("javascript:") or lower_url.startswith("mailto:") or full_url.endswith("#"):
        return False

    if re.search(r'\b(2015|2016|2017|2018|2019|2020|2021|2022|2023|2024|2025)\b', lower_text + " " + lower_url) and "2026" not in (lower_text + " " + lower_url):
        return False

    all_valid_keywords = JOB_KEYWORDS + ADMIT_CARD_KEYWORDS + ANSWER_KEY_KEYWORDS + RESULT_KEYWORDS
    is_pdf = ".pdf" in lower_url

    has_keyword = any(k in lower_text or k in lower_url for k in all_valid_keywords)
    has_exam_code = bool(re.search(
        r'(2026|\d{1,3}/2026|advt|stage|tier|norcet|cet|cgl|chsl|mts|gd|ntpc|alp|je|constable|si|asi|clerk|po|so|officer|assistant|engineer|teacher|tgt|pgt|prt|stenographer|group\s*[a-d]|grade\s*[a-d])',
        lower_text
    ))

    if has_keyword or (is_pdf and has_exam_code):
        return True

    return False

def extract_source_and_metadata(target_url):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        response = requests.get(target_url, headers=headers, timeout=20, verify=False)
        if response.status_code != 200:
            return "", "Active Web Link", None, None, []

        last_mod_header = response.headers.get("Last-Modified", None)
        pdf_internal_date = None
        detected_headings = []

        if target_url.lower().endswith(".pdf") or b"%PDF" in response.content[:15]:
            if not PYMUPDF_AVAILABLE:
                return "", "Official PDF", last_mod_header, None, []
            temp_pdf = os.path.join(DATA_FOLDER, "temp_research.pdf")
            with open(temp_pdf, "wb") as f:
                f.write(response.content)
            doc = fitz.open(temp_pdf)

            meta = doc.metadata or {}
            raw_pdf_date = meta.get("modDate") or meta.get("creationDate") or ""
            m_date = re.search(r'D:(\d{4})(\d{2})(\d{2})', str(raw_pdf_date))
            if m_date:
                try:
                    pdf_internal_date = datetime.date(int(m_date.group(1)), int(m_date.group(2)), int(m_date.group(3)))
                except Exception:
                    pass

            raw_text_lines = []
            for page in range(min(12, len(doc))):
                page_text = doc[page].get_text("text")
                raw_text_lines.extend(page_text.splitlines())
            doc.close()

            heading_patterns = re.compile(
                r'^(?:\d+[\.\)]\s*|[A-Z]\.\s*)?(?:IMPORTANT\s+DATES|VACANCY\s+DETAILS|ELIGIBILITY\s+CRITERIA|EDUCATIONAL\s+QUALIFICATION|AGE\s+LIMIT|APPLICATION\s+FEE|SELECTION\s+PROCESS|SCHEME\s+OF\s+EXAMINATION|SYLLABUS|HOW\s+TO\s+APPLY|PAY\s+SCALE|SALARY|CUT[\s-]*OFF|MERIT\s+LIST|DOCUMENT\s+VERIFICATION|TIE[\s-]*BREAKING|NORMALIZATION|INSTRUCTIONS\s+FOR\s+CANDIDATES)',
                re.IGNORECASE
            )
            for line in raw_text_lines:
                clean_l = sanitize_clean_text(line)
                if 5 <= len(clean_l) <= 75 and heading_patterns.search(clean_l):
                    if clean_l.title() not in detected_headings:
                        detected_headings.append(clean_l.title())

            full_clean_text = sanitize_clean_text("\n".join(raw_text_lines))
            return full_clean_text, "Official PDF", last_mod_header, pdf_internal_date, detected_headings[:8]
        else:
            soup = BeautifulSoup(response.text, "html.parser")
            for h_tag in soup.find_all(["h1", "h2", "h3", "th"]):
                ht = sanitize_clean_text(h_tag.get_text(" ", strip=True))
                if 6 <= len(ht) <= 70 and ht not in detected_headings:
                    detected_headings.append(ht)
            for tag in soup(["script", "style", "nav", "header", "footer"]):
                tag.decompose()
            clean_web_text = sanitize_clean_text(soup.get_text(" ", strip=True)[:8000])
            return clean_web_text, "Active Online Link", last_mod_header, None, detected_headings[:6]
    except Exception:
        return "", "Official Link / Notice", None, None, []

def determine_category(text_combined):
    t = text_combined.lower()
    if any(k in t for k in RESULT_KEYWORDS):
        return "Result"
    elif any(k in t for k in ADMIT_CARD_KEYWORDS):
        return "Admit Card"
    elif any(k in t for k in ANSWER_KEY_KEYWORDS):
        return "Answer Key"
    return "Govt Job"

# =====================================================================
# 5. STRICT POST-START-TIME VERIFIER & GOOGLE + GEMINI CROSS-CHECK
# =====================================================================
def call_gemini_json_or_text(prompt_text, expect_json=False):
    if not GEMINI_API_KEY or GEMINI_API_KEY == "your_gemini_api_key":
        return None
    try:
        api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        payload = {"contents": [{"parts": [{"text": prompt_text}]}]}
        if expect_json:
            payload["generationConfig"] = {"responseMimeType": "application/json"}
        res = requests.post(api_url, json=payload, timeout=45)
        if res.status_code == 200:
            raw_out = res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            if expect_json:
                raw_out = re.sub(r'^```json\s*|\s*```$', '', raw_out, flags=re.I)
                return json.loads(raw_out)
            return raw_out
    except Exception:
        pass
    return None

def parse_any_date_from_text(text_sample):
    detected_dates = []
    for m in re.finditer(r'\b(\d{1,2})[./-](\d{1,2})[./-](202\d)\b', text_sample):
        d, mn, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            detected_dates.append(datetime.date(y, mn, d))
        except Exception:
            pass

    months_map = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12
    }
    for m in re.finditer(r'\b(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[\s,]+(202\d)\b', text_sample, re.I):
        d = int(m.group(1))
        mn = months_map.get(m.group(2)[:3].lower(), 1)
        y = int(m.group(3))
        try:
            detected_dates.append(datetime.date(y, mn, d))
        except Exception:
            pass
    return detected_dates

def cross_check_active_link_on_google(short_org, raw_notice_title, category, bot_start_dt, time_window="1d"):
    snippets = []
    trending_titles = []
    found_date = ""
    has_recent_google_hit = False

    try:
        search_q = f'"{short_org}" {raw_notice_title[:50]} {category} when:{time_window}'
        rss_url = f"https://news.google.com/rss/search?q={quote_plus(search_q)}&hl=en-IN&gl=IN&ceid=IN:en"
        res = requests.get(rss_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "xml")
            for item in soup.find_all("item")[:5]:
                t = item.find("title")
                pub = item.find("pubDate")
                if t and t.text:
                    clean_t = t.text.split(" - ")[0].strip()
                    trending_titles.append(clean_t)
                    pub_str = pub.text if pub else ""
                    snippets.append(f"{clean_t} (Published: {pub_str})")
                    if pub_str:
                        try:
                            pub_dt = parsedate_to_datetime(pub_str).replace(tzinfo=None)
                            if pub_dt.date() >= bot_start_dt.date():
                                has_recent_google_hit = True
                                found_date = pub_dt.strftime("%d %B %Y")
                        except Exception:
                            pass
    except Exception:
        pass

    return {
        "trending_titles": trending_titles,
        "google_snippets": snippets,
        "google_date": found_date,
        "has_recent_google_hit": has_recent_google_hit
    }

def verify_is_truly_published_after_bot_start(portal_info, raw_title, source_text, doc_format, last_modified_header, pdf_internal_date, google_cross_data, bot_start_dt):
    today_date = datetime.datetime.now().date()
    bot_start_date = bot_start_dt.date()

    if pdf_internal_date:
        if pdf_internal_date < bot_start_date:
            return False, f"Old PDF Created Before Code Start ({pdf_internal_date} < {bot_start_date})", ""

    if last_modified_header:
        try:
            mod_dt = parsedate_to_datetime(last_modified_header).replace(tzinfo=None)
            if mod_dt.date() < bot_start_date:
                return False, f"Server File Older Than Code Start ({mod_dt.date()} < {bot_start_date})", ""
        except Exception:
            pass

    header_snippet = f"{raw_title} {source_text[:600]}"
    dated_match = re.search(r'(?:dated|date|दिनांक|dt\.?)\s*[:=-]?\s*(\d{1,2}[./-]\d{1,2}[./-]202\d|\d{1,2}\s+[A-Za-z]+\s+202\d)', header_snippet, re.I)
    if dated_match:
        parsed_d_list = parse_any_date_from_text(dated_match.group(1))
        if parsed_d_list:
            notice_issue_date = parsed_d_list[0]
            if notice_issue_date < bot_start_date:
                return False, f"Notice Issue Date ({notice_issue_date}) is Older Than Code Start ({bot_start_date})", ""

    title_dates = parse_any_date_from_text(raw_title)
    if title_dates and max(title_dates) < bot_start_date:
        return False, f"Title Date ({max(title_dates)}) is Older Than Code Start ({bot_start_date})", ""

    if GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key":
        audit_prompt = f"""
        आप एक बहुत ही सख्त सरकारी नौकरी (Sarkari Naukri) वेरिफायर हैं।
        कोड चालू होने की तारीख (Bot Start Date): {bot_start_date.strftime('%d %B %Y')}
        आज की तारीख: {today_date.strftime('%d %B %Y')}

        नियम: हमें केवल उन्हीं वैकेंसी, रिजल्ट, एडमिट कार्ड या आंसर की पर आर्टिकल लिखना है जो {bot_start_date.strftime('%d %B %Y')} को या उसके बाद जारी (Release/Active) हुए हैं। पहले से पड़े हुए किसी भी पुराने नोटिस पर आर्टिकल नहीं लिखना है।

        नीचे दिए गए डेटा की बारीकी से जांच करें:
        - विभाग: {portal_info['org']}
        - नोटिस/लिंक का शीर्षक: {raw_title}
        - फॉर्मेट: {doc_format}
        - पीडीएफ मेटाडेटा तारीख: {pdf_internal_date}
        - गूगल क्रॉस-चेक डेटा: {" | ".join(google_cross_data.get("google_snippets", [])[:4])}
        - पीडीएफ/वेबपेज का शुरुआती टेक्स्ट: {source_text[:2500]}

        सख्त निर्णय लें:
        - यदि पीडीएफ या वेबपेज पर जारी होने की तारीख (Release/Dated) {bot_start_date.strftime('%d %B %Y')} से पहले की है, तो `is_fresh` को `false` रखें।
        - यदि यह कोई पुराना आर्काइव, टेंडर, या पुरानी भर्ती है, तो `is_fresh` को `false` रखें।

        Return strictly JSON:
        {{
            "is_fresh": true or false,
            "issue_date_detected": "Detected release date",
            "exact_purpose": "1 line summary",
            "rejection_reason": "Reason if false"
        }}
        """
        ai_verdict = call_gemini_json_or_text(audit_prompt, expect_json=True)
        if isinstance(ai_verdict, dict):
            if not ai_verdict.get("is_fresh", False):
                return False, f"Gemini Strict Audit Rejected: {ai_verdict.get('rejection_reason', 'Published before bot start')}", ""
            return True, f"Gemini Verified Fresh ({ai_verdict.get('issue_date_detected', 'Today')})", ai_verdict.get("exact_purpose", "")

    has_today_date_in_text = (today_date in parse_any_date_from_text(header_snippet)) or (bot_start_date in parse_any_date_from_text(header_snippet))
    has_fresh_pdf_or_server_date = (pdf_internal_date and pdf_internal_date >= bot_start_date)

    if has_fresh_pdf_or_server_date or has_today_date_in_text or google_cross_data.get("has_recent_google_hit", False):
        return True, f"Verified Fresh Post-{bot_start_date} Update", ""

    return False, f"No proof of release on/after {bot_start_date} (Blocked to prevent old notice)", ""

# =====================================================================
# 6. SEO TITLE RESEARCH, PDF HEADINGS & DATA EXTRACTION ENGINE
# =====================================================================
KNOWN_EXAMS_AND_POSTS = [
    r'NORCET[-\s]*\d+(?:\s*Stage[-\s]*(?:I|II|1|2))?',
    r'SSC\s+(?:CGL|CHSL|MTS|GD\s+Constable|CPO|JE|Stenographer|Selection\s+Post)',
    r'UPSC\s+(?:CSE|Civil\s+Services|NDA|CDS|CAPF|EPFO|CMS|ESE|IFS)',
    r'RRB\s+(?:NTPC|ALP|Group\s*D|JE|Technician|Paramedical|RPF\s+Constable|RPF\s+SI)',
    r'CTET\s+(?:July|December)?\s*2026',
    r'IBPS\s+(?:PO|Clerk|SO|RRB\s+PO|RRB\s+Clerk)',
    r'SBI\s+(?:PO|Clerk|Junior\s+Associate|Specialist\s+Officer|SO)',
    r'RBI\s+(?:Grade\s+B|Assistant|Officer)',
    r'(?:Constable|Head\s+Constable|Sub\s+Inspector|ASI|Tradesman|Driver|Fireman)\s*(?:GD|Executive|Ministerial)?',
    r'(?:Nursing\s+Officer|Staff\s+Nurse|Pharmacist|Lab\s+Technician|Junior\s+Engineer|Assistant\s+Engineer)',
    r'(?:TGT|PGT|PRT|Primary\s+Teacher|Assistant\s+Professor|Lecturer)',
    r'(?:Lower\s+Division\s+Clerk|LDC|UDC|Stenographer|Junior\s+Assistant|Multi\s+Tasking\s+Staff|MTS)',
    r'(?:Group\s*[A-D]|Grade\s*[A-D]|Post\s+Code\s*\d+/\d+|Advt\.?\s*No\.?\s*\d+/\d{2,4})'
]

def extract_deep_pdf_details_for_student(combined_text):
    vac_match = re.search(r'(?:total\s+vacanc(?:y|ies)|total\s+posts?|कुल\s+पद)\s*[:=-]?\s*(\d{1,6})', combined_text, re.I)
    if not vac_match:
        vac_match = re.search(r'\b(\d{2,6})\s+(?:vacancies|posts)\b', combined_text, re.I)
    total_posts = f"{vac_match.group(1)} Posts" if vac_match else "आधिकारिक नोटिफिकेशन के अनुसार (Check Notice)"

    age_match = re.search(r'(\d{2})\s*(?:to|-|से)\s*(\d{2})\s*(?:years|वर्ष|yrs)', combined_text, re.I)
    age_limit = f"{age_match.group(1)} से {age_match.group(2)} वर्ष (आरक्षित वर्ग को नियमानुसार छूट)" if age_match else "न्यूनतम 18 वर्ष (अधिकतम आयु पदानुसार नोटिफिकेशन में देखें)"

    quals = []
    for q_word, q_label in [
        (r'\b10th|matric|high\s*school\b', '10वीं (Matric) पास'),
        (r'\b12th|intermediate|higher\s*secondary\b', '12वीं (Intermediate) पास'),
        (r'\biti\b', 'ITI सर्टिफिकेट'),
        (r'\bdiploma\b', 'संबंधित ट्रेड में डिप्लोमा'),
        (r'\bgraduate|graduation|bachelor|degree|b\.tech|b\.sc|b\.a|b\.com\b', 'स्नातक डिग्री (Graduation)'),
        (r'\bpost\s*graduate|master|m\.sc|m\.a|m\.tech|pg\b', 'स्नातकोत्तर (Post Graduate)'),
        (r'\bb\.ed|ctet|tet\b', 'B.Ed / TET उत्तीर्ण'),
        (r'\bmbbs|bsc\s*nursing|gnm|anm|b\.pharm\b', 'मेडिकल / नर्सिंग डिग्री या डिप्लोमा')
    ]:
        if re.search(q_word, combined_text, re.I):
            quals.append(q_label)
    qualification = ", ".join(quals[:3]) if quals else "संबंधित पद के अनुसार (आधिकारिक सूचना में देखें)"

    fee_match = re.search(r'(?:rs\.?|₹|inr)\s*(\d{2,4})\s*/-', combined_text, re.I)
    app_fee = f"₹{fee_match.group(1)}/- (SC/ST/PwBD व महिला वर्ग के लिए नियमानुसार छूट)" if fee_match else "श्रेणी के अनुसार (UR/OBC/SC/ST शुल्क विवरण देखें)"

    pay_match = re.search(r'(?:pay\s+level|level)[-\s]*(\d{1,2})', combined_text, re.I)
    salary_info = f"7th CPC Pay Level-{pay_match.group(1)} के अनुसार" if pay_match else "सरकारी वेतनमान (7th Pay Commission के अनुसार भत्ते सहित)"

    return {
        "total_posts": total_posts,
        "age_limit": age_limit,
        "qualification": qualification,
        "app_fee": app_fee,
        "salary_info": salary_info
    }

def build_article_blueprint(portal_info, raw_notice_title, pdf_text, category, pdf_headings, google_cross_data, ai_purpose_summary=""):
    short_org = portal_info["short_org"]
    cleaned_notice = sanitize_clean_text(raw_notice_title)
    cleaned_notice = re.sub(r'\.pdf$|\.html$|\.aspx$', '', cleaned_notice, flags=re.IGNORECASE)
    cleaned_notice = re.sub(r'\b(page\s*\d+|ym\d+|ao\d+|file\s*no|ref\s*no|corrigendum)\b', '', cleaned_notice, flags=re.IGNORECASE)
    cleaned_notice = re.sub(r'\s+', ' ', cleaned_notice).strip()

    combined_search_space = f"{cleaned_notice} {pdf_text[:4500]}"

    extracted_post = ""
    for pattern in KNOWN_EXAMS_AND_POSTS:
        m = re.search(pattern, combined_search_space, re.IGNORECASE)
        if m:
            candidate = re.sub(r'\s+', ' ', m.group(0)).strip()
            candidate = re.sub(r'\b202$', '2026', candidate)
            if len(candidate) >= 3:
                extracted_post = candidate
                break

    if not extracted_post:
        temp = re.sub(
            r'\b(result|results|of|the|for|in|on|held|dated|notice|notification|recruitment|advertisement|advt|download|admit|card|answer|key|click|here|new|latest|uploading|declaration|provisional|final|list|candidates|roll|numbers|regarding|schedule|examination|exam)\b',
            ' ', cleaned_notice, flags=re.IGNORECASE
        )
        clean_words = []
        for w in temp.split():
            w_clean = w.strip(".,()-:/[]\"'")
            if len(w_clean) >= 3 and w_clean.isalpha():
                if not re.match(r'^[a-zA-Z]{1,2}\d+$', w_clean):
                    clean_words.append(w_clean.title() if w_clean.islower() else w_clean)
        extracted_post = " ".join(clean_words[:4]) if clean_words else "Various Posts"

    if short_org.lower() in extracted_post.lower():
        core_exam_name = extracted_post
    else:
        core_exam_name = f"{short_org} {extracted_post}".strip()

    dedup_words = []
    for w in core_exam_name.split():
        if w.lower() not in [x.lower() for x in dedup_words]:
            dedup_words.append(w)
    core_exam_name = " ".join(dedup_words)

    short_exam_heading = f"{core_exam_name} {category} 2026"
    short_exam_heading = re.sub(r'2026\s+2026', '2026', short_exam_heading)

    student_details = extract_deep_pdf_details_for_student(combined_search_space)
    posts_badge = f" ({student_details['total_posts']})" if "Posts" in student_details["total_posts"] and category == "Govt Job" else ""

    if category == "Result":
        seo_title = f"{short_exam_heading} Out: Merit List PDF, Cut Off Marks और Roll Number यहाँ से चेक करें"
        smart_headings = [
            f"{short_exam_heading}: संक्षिप्त विवरण (Overview Table)",
            f"{short_exam_heading} Latest Update: कब जारी हुआ और मुख्य जानकारी",
            f"{core_exam_name} Cut-Off Marks 2026 और Merit List के नियम",
            f"{short_exam_heading} में शॉर्टलिस्ट होने के बाद आगे की प्रक्रिया (DV & Medical)",
            f"मोबाइल या कंप्यूटर से {short_exam_heading} कैसे चेक करें? (Step-by-Step प्रक्रिया)",
            f"{short_exam_heading}: Direct Official Links"
        ]
    elif category == "Admit Card":
        seo_title = f"{short_exam_heading} Link Active: Exam Date, City Intimation Slip और Hall Ticket डाउनलोड करें"
        smart_headings = [
            f"{short_exam_heading}: संक्षिप्त विवरण (Overview Table)",
            f"{short_exam_heading} Download Link: कब एक्टिव हुआ और परीक्षा तिथि का विवरण",
            f"{core_exam_name} Exam Shift Timing, Reporting Time और जरूरी दिशा-निर्देश",
            f"परीक्षा केंद्र (Exam Hall) में साथ ले जाने वाले अनिवार्य दस्तावेज़",
            f"मोबाइल से {short_exam_heading} कैसे डाउनलोड करें? (Step-by-Step गाइड)",
            f"{short_exam_heading}: Direct Official Links"
        ]
    elif category == "Answer Key":
        seo_title = f"{short_exam_heading} Out: Response Sheet PDF डाउनलोड करें और Objection दर्ज करें"
        smart_headings = [
            f"{short_exam_heading}: संक्षिप्त विवरण (Overview Table)",
            f"{short_exam_heading} Released: Response Sheet और मुख्य अपडेट",
            f"{core_exam_name} Answer Key से अपने सटीक नंबर (Score) कैसे जोड़ें?",
            f"गलत प्रश्न या उत्तर पर ऑनलाइन आपत्ति (Objection Raise) कैसे दर्ज करें?",
            f"मोबाइल से {short_exam_heading} और Response Sheet कैसे डाउनलोड करें?",
            f"{short_exam_heading}: Direct Official Links"
        ]
    else:
        seo_title = f"{core_exam_name} Recruitment 2026{posts_badge}: Notification PDF, योग्यता, आयु सीमा और Online Form"
        short_exam_heading = f"{core_exam_name} Recruitment 2026"
        smart_headings = [
            f"{short_exam_heading}: संक्षिप्त विवरण (Overview Table)",
            f"{short_exam_heading} Notification: भर्ती का मुख्य उद्देश्य और पदों का विवरण",
            f"{core_exam_name} Eligibility Criteria: शैक्षणिक योग्यता और आयु सीमा (पॉइंट्स में)",
            f"{core_exam_name} Application Fee, वेतनमान (Salary) और चयन प्रक्रिया",
            f"{short_exam_heading} का Online Form कैसे भरें? (Step-by-Step आवेदन प्रक्रिया)",
            f"{short_exam_heading}: Direct Official Links"
        ]

    for ph in pdf_headings[:2]:
        custom_h = f"{core_exam_name}: {ph} (नोटिफिकेशन के अनुसार)"
        if custom_h not in smart_headings:
            smart_headings.insert(-2, custom_h)

    date_matches = re.findall(r'\b(\d{1,2}[./-]\d{1,2}[./-]2026|\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+2026)\b', combined_search_space, re.IGNORECASE)
    google_date = google_cross_data.get("google_date", "")
    exam_date = date_matches[0] if date_matches else (google_date if google_date else datetime.datetime.now().strftime("%d %B %Y"))
    last_date = date_matches[1] if len(date_matches) > 1 else "आधिकारिक सूचना / पीडीएफ के अनुसार"
    release_date = datetime.datetime.now().strftime("%d %B %Y")

    advt_match = re.search(r'(?:Advt\.?\s*No\.?|Advertisement\s*No\.?|Notice\s*No\.?)\s*[:/-]?\s*([A-Za-z0-9/-]{2,18})', combined_search_space, re.IGNORECASE)
    advt_no = advt_match.group(1) if advt_match else "आधिकारिक पोर्टल पर उपलब्ध"

    return {
        "seo_title": seo_title,
        "short_exam_name": short_exam_heading,
        "core_exam_name": core_exam_name,
        "raw_notice_title": cleaned_notice[:140],
        "exam_date": exam_date,
        "last_date": last_date,
        "release_date": release_date,
        "advt_no": advt_no,
        "trending_titles": google_cross_data.get("trending_titles", []),
        "google_snippets": google_cross_data.get("google_snippets", []),
        "pdf_headings": pdf_headings,
        "smart_headings": smart_headings,
        "ai_purpose_summary": ai_purpose_summary,
        "total_posts": student_details["total_posts"],
        "age_limit": student_details["age_limit"],
        "qualification": student_details["qualification"],
        "app_fee": student_details["app_fee"],
        "salary_info": student_details["salary_info"]
    }

# =====================================================================
# 7. HUMAN-STYLE 1000+ WORDS ARTICLE ENGINE
# =====================================================================
def generate_professional_1000_words_article(portal_info, research_data, target_url, category, source_text, doc_format, weekly_update_note=""):
    org_name = portal_info["org"]
    short_org = portal_info["short_org"]
    portal_name = portal_info["portal_name"]
    portal_url = portal_info["url"]
    short_exam = research_data["short_exam_name"]
    core_exam = research_data["core_exam_name"]
    raw_notice = research_data["raw_notice_title"]
    exam_date = research_data["exam_date"]
    last_date = research_data["last_date"]
    release_date = research_data["release_date"]
    advt_no = research_data["advt_no"]
    total_posts = research_data["total_posts"]
    age_limit = research_data["age_limit"]
    qualification = research_data["qualification"]
    app_fee = research_data["app_fee"]
    salary_info = research_data["salary_info"]
    pdf_headings_str = ", ".join(research_data.get("pdf_headings", [])) or "Standard Exam Sections"
    smart_headings_list = "\n".join([f"- {h}" for h in research_data.get("smart_headings", [])])
    trending_ref = " | ".join(research_data["trending_titles"][:4]) if research_data["trending_titles"] else research_data["seo_title"]
    google_context = " | ".join(research_data.get("google_snippets", [])[:3])

    weekly_banner_html = ""
    if weekly_update_note:
        weekly_banner_html = f"""
        <div style="background-color:#fff8e5; border-left:5px solid #ff9800; padding:15px; margin:15px 0; border-radius:4px;">
            <strong>🔄 साप्ताहिक बुधवार एडिटोरियल अपडेट ({release_date}):</strong> {weekly_update_note}
        </div>
        """

    if GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key":
        writer_prompt = f"""
        आप एक बहुत ही अनुभवी, प्रोफेशनल हिंदी कंटेंट राइटर (Sarkari Naukri & Competitive Exam Expert) हैं।
        आपको "{research_data['seo_title']}" विषय पर **1,100 से 1,300 शब्दों (1000+ Words)** का एक बेहद आकर्षक, साफ-सुथरा और यूजर-फ्रेंडली आर्टिकल लिखना/अपडेट करना है।

        ### मेरे लिखने का खास तरीका (आपको बिल्कुल यही पैटर्न फॉलो करना है):
        1. **सबसे पहले परिचय और 6-7 लाइन का संक्षिप्त Overview Table:**
           - शुरू में 2 पैराग्राफ में बताएं कि यह पीडीएफ या नया एक्टिव लिंक कब जारी/अपडेट हुआ है ({release_date}), किस विभाग ({org_name}) का है और किस परीक्षा ({core_exam}) के लिए है।
           - यदि यह साप्ताहिक बुधवार अपडेट है ({weekly_update_note}), तो गूगल क्रॉस-चेक से मिली ताज़ा स्थिति को शुरू में ही स्पष्ट करें।
           - तुरंत बाद **6 से 7 पंक्तियों (Rows) का एक साफ-सुथरा Overview Table** बनाएं जिसमें भर्ती बोर्ड, परीक्षा का नाम, अपडेट कैटेगरी ({category}), कुल पद/स्थितियां, जारी/अपडेट होने की तिथि ({release_date}) और आधिकारिक वेबसाइट एक नज़र में समझ आ जाएं।
        2. **हेडिंग्स का चुनाव (PDF Headings + Smart Category Headings):**
           - पीडीएफ/पेज से निकली असली हेडिंग्स: {pdf_headings_str}
           - इस कैटेगरी के लिए जरूरी हेडिंग्स:
             {smart_headings_list}
           - इन सभी हेडिंग्स को `<h2>` और `<h3>` में लगाएं।
        3. **पैराग्राफ + बुलेट पॉइंट्स का कॉम्बिनेशन (Paragraphs + Bullet Points):**
           - हर हेडिंग के अंदर पहले 1-2 सरल और जानकारीपूर्ण **पैराग्राफ (`<p>`)** लिखें।
           - उसके तुरंत बाद मुख्य बातों को **बुलेट पॉइंट्स (`<ul><li><strong>...</strong>: ...</li></ul>`)** में लिखें ताकि आर्टिकल देखने में सुंदर लगे और छात्र को पढ़ने में बिल्कुल बोरियत न हो।
        4. **कैटेगरी का विशेष ध्यान रखें ({category}):**
           - यदि यह **Govt Job** है: तो पदों का विवरण, योग्यता, आयु सीमा, फीस, सैलरी और ऑनलाइन फॉर्म भरने के स्टेप्स विस्तार से लिखें।
           - यदि यह **Admit Card / Result / Answer Key** है: तो यह साफ बताएं कि लिंक कब एक्टिव हुई है, लॉगिन करके कैसे चेक/डाउनलोड करना है, उसमें कौन-सी डिटेल्स मिलानी हैं और अगला स्टेप क्या होगा।
        5. **Important Official Links Table और 5 FAQs:**
           - अंत में डायरेक्ट पीडीएफ/एक्टिव लिंक ({target_url}) और आधिकारिक वेबसाइट ({portal_url}) की टेबल बनाएं और 5 अक्सर पूछे जाने वाले प्रश्न (FAQs) लिखें।
           - आउटपुट सिर्फ शुद्ध HTML (`<h2>`, `<h3>`, `<p>`, `<ul>`, `<ol>`, `<table>`) में दें, कोई markdown ```html ब्लॉक न लगाएं।

        ### उपलब्ध सटीक डेटा:
        - विभाग: {org_name} ({short_org})
        - आधिकारिक नोटिस/लिंक का नाम: {raw_notice}
        - फॉर्मेट: {doc_format}
        - साप्ताहिक गूगल क्रॉस-चेक नोट: {weekly_update_note}
        - गूगल क्रॉस-चेक व ट्रेंडिंग एसईओ संदर्भ: {trending_ref} | {google_context}
        - मुख्य विवरण: कुल पद: {total_posts} | योग्यता: {qualification} | आयु: {age_limit} | शुल्क: {app_fee} | वेतन: {salary_info} | तिथि: {exam_date}
        - पीडीएफ/वेबपेज का मूल टेक्स्ट: {source_text[:3800]}
        """
        ai_html = call_gemini_json_or_text(writer_prompt, expect_json=False)
        if ai_html:
            clean_ai_html = re.sub(r'^```html\s*|\s*```$', '', ai_html.strip(), flags=re.I)
            if len(clean_ai_html.split()) >= 800:
                return research_data["seo_title"], f"{weekly_banner_html}\n{clean_ai_html}".strip()

    overview_6_line_table = f"""
    <h2>{short_exam}: एक नज़र में संपूर्ण विवरण (Quick Overview Table)</h2>
    <p>जो उम्मीदवार कम समय में इस आधिकारिक अपडेट की पूरी जानकारी समझना चाहते हैं, उनके लिए हमने नीचे मुख्य बिंदुओं की यह सारणी (Overview Table) तैयार की है। इसमें विभाग के नाम से लेकर आधिकारिक लिंक तक सभी जरूरी तथ्य शामिल हैं:</p>
    <table border="1" cellpadding="10" cellspacing="0" style="width:100%; border-collapse:collapse; margin:15px 0 25px 0;">
        <tbody>
            <tr style="background-color:#f8f9fa;"><td><strong>1. भर्ती बोर्ड / विभाग का नाम</strong></td><td>{org_name}</td></tr>
            <tr><td><strong>2. परीक्षा / भर्ती का नाम</strong></td><td>{core_exam} (Advt/Ref: {advt_no})</td></tr>
            <tr style="background-color:#f8f9fa;"><td><strong>3. जारी अपडेट की श्रेणी (Category)</strong></td><td>Official {category} ({doc_format})</td></tr>
            <tr><td><strong>4. आधिकारिक नोटिस / लिंक का विषय</strong></td><td>{raw_notice}</td></tr>
            <tr style="background-color:#f8f9fa;"><td><strong>5. पद संख्या एवं पात्रता सार</strong></td><td>{total_posts} | {qualification}</td></tr>
            <tr><td><strong>6. ताज़ा अपडेट / पुनरीक्षण तिथि</strong></td><td>{release_date} (महत्वपूर्ण तिथि: {exam_date})</td></tr>
            <tr style="background-color:#f8f9fa;"><td><strong>7. आधिकारिक वेबसाइट</strong></td><td><a href="{portal_url}" target="_blank" rel="noopener">{portal_name} ({portal_url})</a></td></tr>
        </tbody>
    </table>
    """

    student_verification_box = f"""
    <div style="background-color:#eef6ff; border-left:5px solid #0056b3; padding:15px; margin:20px 0; border-radius:4px;">
        <strong>🔍 पीडीएफ एवं एक्टिव लिंक की बारीकी से जांच (Editorial Verification Note):</strong> हमारी टीम द्वारा <strong>{portal_name}</strong> और गूगल अपडेट्स से क्रॉस-चेक करने के बाद यह पुष्टि की गई है कि <em>“{raw_notice}”</em> से जुड़ा यह {doc_format} अपडेट पूर्णतः प्रामाणिक और आधिकारिक है। छात्रों की सुविधा के लिए हमने इसके सभी महत्वपूर्ण नियमों को नीचे पैराग्राफ और आसान बुलेट पॉइंट्स में समझाया है।
    </div>
    """

    extra_pdf_heading_html = ""
    if research_data.get("pdf_headings"):
        bullet_items = "".join([f"<li><strong>{ph}:</strong> आधिकारिक {doc_format} के इस खंड में उम्मीदवारों के लिए श्रेणीवार नियम, समय-सारणी और आवश्यक मानकों का विस्तृत उल्लेख किया गया है।</li>" for ph in research_data["pdf_headings"][:5]])
        extra_pdf_heading_html = f"""
        <h2>आधिकारिक {doc_format} में शामिल प्रमुख अनुभाग (Key Sections Inside Official Notice)</h2>
        <p>जब आप विभाग द्वारा जारी की गई मूल फाइल या वेब विंडो को खोलते हैं, तो उसमें कई तकनीकी सेक्शन दिए होते हैं। एक अभ्यर्थी के तौर पर आपको यह पता होना चाहिए कि किस हेडिंग के अंदर आपके काम की कौन-सी जानकारी छिपी है:</p>
        <ul>
            {bullet_items}
        </ul>
        """

    if category == "Result":
        body_sections = f"""
        {weekly_banner_html}
        <p><strong>{org_name}</strong> ने प्रतियोगी परीक्षा में शामिल हुए लाखों अभ्यर्थियों का इंतजार खत्म करते हुए <strong>{core_exam}</strong> का आधिकारिक परिणाम (Result / Merit List) जारी कर दिया है। विभाग के आधिकारिक पोर्टल पर यह ताज़ा अपडेट <em>“{raw_notice}”</em> शीर्षक के साथ सक्रिय किया गया है। वे सभी उम्मीदवार जिन्होंने इस परीक्षा में भाग लिया था, वे अब नीचे दिए गए डायरेक्ट लिंक की मदद से अपना रोल नंबर और चयन की स्थिति (Qualifying Status) जांच सकते हैं।</p>
        <p>अक्सर जब कोई बड़ा रिजल्ट जारी होता है, तो वेबसाइट पर ट्रैफिक अधिक होने या पीडीएफ लंबी होने के कारण छात्रों को अपना नाम ढूंढने में परेशानी होती है। इसी बात को ध्यान में रखते हुए हमने इस लेख में रिजल्ट लिंक के क्रॉस-चेक विवरण, कट-ऑफ (Cut-Off Marks) के नियमों और आगे होने वाले डॉक्यूमेंट वेरिफिकेशन की पूरी जानकारी क्रमवार तैयार की है।</p>
        {student_verification_box}
        {overview_6_line_table}

        <h2>{short_exam} Latest Update: कब जारी हुआ और इसमें क्या खास है?</h2>
        <p>विभाग द्वारा जारी इस आधिकारिक अपडेट की बारीकी से जांच करने पर स्पष्ट होता है कि बोर्ड ने पारदर्शी मूल्यांकन के बाद सफल उम्मीदवारों की सूची (या स्कोरकार्ड लॉगिन लिंक) को ऑनलाइन लाइव कर दिया है। जिन परीक्षाओं में लिखित या कंप्यूटर आधारित टेस्ट (CBT) आयोजित हुआ था, उनके अंकों और नॉर्मलाइजेशन के आधार पर यह सूची तैयार की गई है।</p>
        <p>इस परिणाम से जुड़ी सबसे महत्वपूर्ण बातें नीचे पॉइंट्स में दी गई हैं जिन्हें हर छात्र को ध्यान से पढ़ना चाहिए:</p>
        <ul>
            <li><strong>परिणाम का प्रारूप ({doc_format}):</strong> यह अपडेट आधिकारिक पोर्टल पर सीधे {doc_format} के रूप में उपलब्ध कराया गया है जहाँ से छात्र तुरंत अपना स्टेटस देख सकते हैं।</li>
            <li><strong>अनंतिम चयन (Provisional Selection):</strong> सूची में शामिल सभी रोल नंबर अभी प्रोविजनल हैं और अंतिम नियुक्ति मूल प्रमाण पत्रों की जांच (Document Verification) के बाद होगी।</li>
            <li><strong>श्रेणीवार शॉर्टलिस्टिंग:</strong> सामान्य (UR), ओबीसी (OBC), अनुसूचित जाति (SC), अनुसूचित जनजाति (ST) और ईडब्ल्यूएस (EWS) के उम्मीदवारों को उनके कोटे के विज्ञापित पदों के अनुपात में पास किया गया है।</li>
            <li><strong>स्कोरकार्ड और कट-ऑफ अंक:</strong> व्यक्तिगत प्राप्तांक और श्रेणीवार कट-ऑफ तालिका आधिकारिक पोर्टल के लॉगिन डैशबोर्ड या नोटिस के अंतिम पृष्ठ पर देखे जा सकते हैं।</li>
        </ul>

        <h2>{core_exam} Cut-Off Marks 2026 और Merit List तैयार होने के नियम</h2>
        <p>किसी भी सरकारी परीक्षा के रिजल्ट के साथ छात्रों के मन में सबसे बड़ा सवाल यह होता है कि आखिर कट-ऑफ किस आधार पर तय की गई है और बराबर नंबर आने पर किसे वरीयता मिलती है। <strong>{short_org}</strong> द्वारा मेरिट सूची तैयार करते समय एक निश्चित वैज्ञानिक प्रक्रिया अपनाई जाती है।</p>
        <p>नीचे दिए गए बिंदुओं से आप समझ सकते हैं कि इस परीक्षा की कट-ऑफ और मेरिट को किन कारकों ने प्रभावित किया है:</p>
        <ul>
            <li><strong>कुल विज्ञापित पदों की संख्या:</strong> इस भर्ती में उपलब्ध <strong>{total_posts}</strong> के सापेक्ष ही अगले चरण के लिए निर्धारित गुना (जैसे 2 गुना या 5 गुना) अभ्यर्थियों को बुलाया जाता है।</li>
            <li><strong>प्रश्न पत्र का कठिनाई स्तर (Difficulty Level):</strong> जिन शिफ्टों में प्रश्न पत्र कठिन था, वहाँ रॉ स्कोर कम होने के बावजूद उम्मीदवारों को नॉर्मलाइजेशन का सीधा लाभ मिलता है।</li>
            <li><strong>नॉर्मलाइजेशन फॉर्मूला (Percentile / Equi-Percentile Method):</strong> एक से अधिक शिफ्ट में हुई परीक्षाओं में सभी छात्रों को बराबरी पर लाने के लिए Normalized Marks निकाले जाते हैं।</li>
            <li><strong>टाई-ब्रेकिंग नियम (Tie-Breaking Rules):</strong> यदि दो या अधिक छात्रों के दशमलव के बाद भी समान अंक आते हैं, तो मुख्य विषय में अधिक अंक या जन्मतिथि में वरिष्ठता (अधिक आयु) वाले उम्मीदवार को ऊपर रखा जाता है।</li>
            <li><strong>न्यूनतम अर्हक अंक (Minimum Qualifying Marks):</strong> प्रत्येक श्रेणी के लिए बोर्ड द्वारा तय किए गए न्यूनतम प्रतिशत अंक प्राप्त करना अनिवार्य होता है।</li>
        </ul>
        {extra_pdf_heading_html}

        <h2>{short_exam} में पास होने के बाद आगे की प्रक्रिया (Document Verification)</h2>
        <p>जिन उम्मीदवारों का रोल नंबर इस परिणाम में सफल घोषित हुआ है, उन्हें अब बिना समय गंवाए अगले चरण की तैयारी शुरू कर देनी चाहिए। कई बार छात्र लिखित परीक्षा पास कर लेते हैं, लेकिन डॉक्यूमेंट वेरिफिकेशन के समय किसी एक प्रमाण पत्र की कमी के कारण उन्हें बाहर होना पड़ता है।</p>
        <p>अपने दस्तावेज़ों की फाइल तैयार करते समय नीचे दिए गए सभी मूल प्रमाण पत्र और उनकी स्व-सत्यापित (Self-Attested) फोटोकॉपी अवश्य रख लें:</p>
        <ul>
            <li><strong>आयु एवं मैट्रिक प्रमाण पत्र:</strong> जन्मतिथि के प्रमाण के रूप में 10वीं (High School) की मूल मार्कशीट और सर्टिफिकेट।</li>
            <li><strong>शैक्षणिक योग्यता के दस्तावेज़:</strong> पद की मांग के अनुसार ({qualification}) की सभी सेमेस्टर/वर्षों की मूल अंकतालिकाएं और डिग्री।</li>
            <li><strong>आरक्षण एवं श्रेणी प्रमाण पत्र:</strong> निर्धारित सरकारी फॉर्मेट में जारी वैध OBC (NCL), SC, ST या EWS प्रमाण पत्र (Crucial Date के नियम के अनुसार)।</li>
            <li><strong>मूल फोटो पहचान पत्र एवं एडमिट कार्ड:</strong> लिखित परीक्षा का मूल प्रवेश पत्र, पैन कार्ड / वोटर आईडी / ड्राइविंग लाइसेंस और 4 से 6 नवीनतम पासपोर्ट साइज फोटोग्राफ।</li>
        </ul>

        <h2>मोबाइल या कंप्यूटर से {short_exam} कैसे चेक करें? (Step-by-Step प्रक्रिया)</h2>
        <p>उम्मीदवारों की सुविधा के लिए हमने रिजल्ट चेक करने और मेरिट लिस्ट पीडीएफ डाउनलोड करने की पूरी प्रक्रिया को बहुत ही सरल स्टेप्स में नीचे लिखा है:</p>
        <ol>
            <li><strong>आधिकारिक पोर्टल खोलें:</strong> सबसे पहले <strong>{portal_name}</strong> की आधिकारिक वेबसाइट (<a href="{portal_url}" target="_blank" rel="noopener">{portal_url}</a>) पर जाएं या नीचे टेबल में दिए गए <strong>Direct Result Link</strong> पर क्लिक करें।</li>
            <li><strong>Result / What's New सेक्शन चुनें:</strong> होमपेज पर दिख रहे नवीनतम सूचना पटल (Notice Board) में <strong>“{raw_notice}”</strong> वाले लिंक को खोजें और उस पर क्लिक करें।</li>
            <li><strong>रोल नंबर या लॉगिन विवरण दर्ज करें:</strong> यदि परिणाम पीडीएफ में है तो फाइल डाउनलोड करके <code>Ctrl + F</code> दबाएं और अपना Roll Number लिखें; यदि लॉगिन लिंक एक्टिव हुआ है तो अपना Registration Number और Date of Birth डालकर सबमिट करें।</li>
            <li><strong>भविष्य के लिए प्रिंट सुरक्षित रखें:</strong> स्क्रीन पर अपना परिणाम और अंक दिखने के बाद उसे PDF के रूप में सेव कर लें और एक प्रिंटआउट निकाल कर अपने पास रख लें।</li>
        </ol>
        """
        link_label = f"Download {short_exam} Official PDF / Direct Login Link"

    elif category == "Admit Card":
        body_sections = f"""
        {weekly_banner_html}
        <p><strong>{org_name}</strong> ने <strong>{core_exam}</strong> परीक्षा की तैयारी कर रहे उम्मीदवारों के लिए आधिकारिक प्रवेश पत्र (Admit Card / Hall Ticket) और परीक्षा शहर की सूचना से जुड़ी नई लिंक जारी कर दी है। विभाग की वेबसाइट पर यह अपडेट <em>“{raw_notice}”</em> के नाम से एक्टिव किया गया है। जिन अभ्यर्थियों ने इस भर्ती के लिए सफलतापूर्वक ऑनलाइन आवेदन किया था, वे अब अपने लॉगिन विवरण की सहायता से अपना एडमिट कार्ड डाउनलोड कर सकते हैं।</p>
        <p>हमने गूगल और आधिकारिक पोर्टल पर क्रॉस-चेक करके यह सुनिश्चित किया है कि यह लिंक/सूचना हाल ही में सक्रिय हुई है। परीक्षा से पहले हर छात्र को अपने परीक्षा केंद्र के पते, रिपोर्टिंग टाइम और शिफ्ट के नियमों की सटीक जानकारी होनी चाहिए, जिसे हमने नीचे पैराग्राफ और बुलेट पॉइंट्स में विस्तार से समझाया है।</p>
        {student_verification_box}
        {overview_6_line_table}

        <h2>{short_exam} Download Link: कब एक्टिव हुआ और इसमें क्या-क्या जानकारी मिलेगी?</h2>
        <p>जब भी किसी प्रतियोगी परीक्षा का एडमिट कार्ड या एग्जाम सिटी स्लिप जारी होती है, तो सबसे पहले यह समझना जरूरी होता है कि क्या यह केवल परीक्षा शहर की जानकारी (City Intimation) है या मुख्य प्रवेश पत्र (Final e-Admit Card)। <strong>{short_org}</strong> द्वारा जारी इस अपडेट के जरिए उम्मीदवार अपने परीक्षा कार्यक्रम की पूरी पुष्टि कर सकते हैं।</p>
        <p>एडमिट कार्ड डाउनलोड करने के बाद आपको उसमें नीचे दिए गए मुख्य बिंदु स्पष्ट रूप से दिखाई देंगे:</p>
        <ul>
            <li><strong>परीक्षा की सटीक तिथि और पाली (Exam Date & Shift):</strong> आपकी परीक्षा किस तारीख को और किस शिफ्ट (सुबह, दोपहर या शाम) में आयोजित होगी।</li>
            <li><strong>परीक्षा केंद्र का पूरा पता (Exam Centre Address & Code):</strong> जिस स्कूल, कॉलेज या ऑनलाइन लैब में आपकी परीक्षा होनी है, उसका नाम, शहर और पिन कोड।</li>
            <li><strong>रिपोर्टिंग समय और गेट बंद होने का समय:</strong> केंद्र पर पहुंचने का समय (Reporting Time) और गेट बंद होने का अंतिम समय (Gate Closing Time)।</li>
            <li><strong>उम्मीदवार की व्यक्तिगत पहचान:</strong> आपका नाम, रोल नंबर, एप्लीकेशन नंबर, कैटेगरी, स्कैन किया हुआ फोटो और हस्ताक्षर।</li>
        </ul>

        <h2>{core_exam} Exam Hall Guidelines और शिफ्ट के कड़े नियम</h2>
        <p>परीक्षा के दिन किसी भी प्रकार की घबराहट या असुविधा से बचने के लिए उम्मीदवारों को परीक्षा बोर्ड के अनुशासन नियमों का पालन करना होता है। हर साल हजारों छात्र सिर्फ 5 मिनट की देरी या गलत आईडी प्रूफ ले जाने के कारण परीक्षा देने से वंचित रह जाते हैं।</p>
        <p>परीक्षा केंद्र पर जाते समय नीचे दिए गए नियमों को हमेशा ध्यान में रखें:</p>
        <ul>
            <li><strong>समय से पहले उपस्थिति:</strong> एडमिट कार्ड पर लिखे रिपोर्टिंग समय से कम से कम 30 मिनट पहले केंद्र पर पहुंचें ताकि बायोमेट्रिक और फ्रिस्किंग (तलाशी) समय पर पूरी हो सके।</li>
            <li><strong>मूल फोटो पहचान पत्र (Original Photo ID):</strong> प्रवेश पत्र के साथ एक मूल सरकारी फोटो आईडी (जैसे पैन कार्ड, वोटर आईडी कार्ड, ड्राइविंग लाइसेंस या पासपोर्ट) ले जाना अनिवार्य है, जिसमें नाम और जन्मतिथि एडमिट कार्ड से बिल्कुल मेल खाती हो।</li>
            <li><strong>पासपोर्ट साइज फोटो और पेन:</strong> अपने साथ कम से कम 2 नवीनतम रंगीन पासपोर्ट साइज फोटो और पारदर्शी बॉल प्वाइंट पेन अवश्य रखें।</li>
            <li><strong>प्रतिबंधित वस्तुएं (Banned Items):</strong> मोबाइल फोन, स्मार्ट वॉच, ब्लूटूथ, कैलकुलेटर, किसी भी प्रकार की पर्ची या मेटल की वस्तुएं परीक्षा कक्ष में ले जाना सख्त मना है।</li>
        </ul>
        {extra_pdf_heading_html}

        <h2>मोबाइल से {short_exam} कैसे डाउनलोड करें? (Step-by-Step गाइड)</h2>
        <p>अभ्यर्थी बिना किसी साइबर कैफे गए अपने मोबाइल फोन से भी मात्र 2 मिनट में अपना एडमिट कार्ड पीडीएफ डाउनलोड कर सकते हैं। इसके लिए नीचे दिए गए स्टेप्स को फॉलो करें:</p>
        <ol>
            <li><strong>डायरेक्ट लिंक पर क्लिक करें:</strong> इस लेख के अंत में दिए गए <strong>Download {short_exam} Link</strong> पर क्लिक करें या सीधे <a href="{portal_url}" target="_blank" rel="noopener">{portal_name}</a> पर जाएं।</li>
            <li><strong>लॉगिन क्रेडेंशियल भरें:</strong> खुलने वाले नए पेज पर अपना <strong>Registration Number / Application ID</strong> और <strong>Date of Birth / Password</strong> सही-सही दर्ज करें।</li>
            <li><strong>सिक्योरिटी कैप्चा सबमिट करें:</strong> स्क्रीन पर दिख रहे सुरक्षा कोड (Captcha) को भरकर 'Login' या 'Download Admit Card' बटन पर टैप करें।</li>
            <li><strong>A4 साइज में प्रिंट निकालें:</strong> आपका प्रवेश पत्र स्क्रीन पर खुल जाएगा; इसे पीडीएफ में सेव करें और साफ-सुथरा रंगीन या ब्लैक एंड व्हाइट प्रिंटआउट निकाल लें।</li>
        </ol>
        """
        link_label = f"Download {short_exam} Direct Active Link"

    elif category == "Answer Key":
        body_sections = f"""
        {weekly_banner_html}
        <p><strong>{org_name}</strong> ने हाल ही में संपन्न हुई <strong>{core_exam}</strong> परीक्षा की आधिकारिक उत्तर कुंजी (Answer Key) और रिस्पॉन्स शीट (Response Sheet) से जुड़ा नया अपडेट जारी कर दिया है। आधिकारिक वेबसाइट पर यह सूचना <em>“{raw_notice}”</em> शीर्षक के अंतर्गत लाइव की गई है। परीक्षा में बैठने वाले सभी छात्र अब अपने लॉगिन विवरण के माध्यम से अपने द्वारा चुने गए उत्तरों और बोर्ड के सही उत्तरों का मिलान कर सकते हैं।</p>
        <p>रिजल्ट आने से पहले अपने संभावित नंबर (Raw Score) जानने और यदि किसी प्रश्न में आयोग से गलती हुई है तो उस पर आपत्ति (Objection) दर्ज कराने का यह सबसे महत्वपूर्ण अवसर होता है। हमने इस नई लिंक/पीडीएफ की पूरी जांच करके नीचे सभी नियम आसान पैराग्राफ और पॉइंट्स में दिए हैं।</p>
        {student_verification_box}
        {overview_6_line_table}

        <h2>{short_exam} Released: Response Sheet और Objection Link की पूरी जानकारी</h2>
        <p>बोर्ड द्वारा जारी इस उत्तर कुंजी का मुख्य उद्देश्य भर्ती प्रक्रिया में 100% पारदर्शिता बनाए रखना है। जब आप अपनी रिस्पॉन्स शीट डाउनलोड करते हैं, तो उसमें प्रत्येक प्रश्न की एक यूनिक आईडी (Question ID) और आपके द्वारा चुने गए विकल्प की स्थिति (Chosen Option) दर्ज होती है।</p>
        <p>इस आधिकारिक आंसर की से जुड़े प्रमुख बिंदु नीचे दिए गए हैं:</p>
        <ul>
            <li><strong>प्रोविजनल बनाम फाइनल आंसर की:</strong> प्रारंभ में जारी की जाने वाली उत्तर कुंजी अनंतिम (Provisional) होती है जिस पर छात्रों से आपत्तियां मांगी जाती हैं।</li>
            <li><strong>Question ID और Option ID का मिलान:</strong> ऑनलाइन परीक्षाओं में प्रश्नों का क्रम अलग-अलग होता है, इसलिए मिलान करते समय हमेशा Question ID और करेक्ट Option ID को ध्यान से देखें।</li>
            <li><strong>आपत्ति दर्ज करने की समय-सीमा:</strong> बोर्ड द्वारा केवल कुछ ही दिनों के लिए Objection Window खोली जाती है; अंतिम तिथि निकलने के बाद किसी भी ईमेल या डाक से भेजी गई आपत्ति स्वीकार नहीं होती।</li>
            <li><strong>फाइनल मेरिट पर असर:</strong> छात्रों द्वारा भेजी गई वैध आपत्तियों की विषय विशेषज्ञों (Subject Experts) द्वारा जांच की जाती है और उसके बाद ही संशोधित उत्तर कुंजी व रिजल्ट जारी होता है।</li>
        </ul>

        <h2>{core_exam} Answer Key से अपने सटीक नंबर (Score) कैसे निकालें?</h2>
        <p>उत्तर कुंजी डाउनलोड करने के बाद कई छात्र नेगेटिव मार्किंग के कारण अपने कुल अंक जोड़ने में गलती कर बैठते हैं। अपने सही रॉ मार्क्स (Raw Score) निकालने के लिए आपको परीक्षा की मार्किंग स्कीम को ध्यान में रखना चाहिए:</p>
        <ul>
            <li><strong>सही उत्तरों की गिनती करें:</strong> सबसे पहले पूरी शीट में उन प्रश्नों को गिनें जिनका उत्तर आधिकारिक कुंजी से 100% मेल खाता है।</li>
            <li><strong>गलत उत्तरों (Negative Marking) को अलग लिखें:</strong> जिन प्रश्नों का उत्तर आपने गलत दिया है, उनकी कुल संख्या नोट करें और परीक्षा के नियम (जैसे 1/4 या 1/3 नेगेटिव मार्किंग) के अनुसार कटौती करें।</li>
            <li><strong>छोड़े गए प्रश्न (Unattempted Questions):</strong> जिन प्रश्नों को आपने खाली छोड़ा है, उनके लिए न तो कोई अंक मिलता है और न ही कोई नेगेटिव मार्किंग होती है।</li>
            <li><strong>आसान सूत्र:</strong> <code>कुल प्राप्तांक = (सही प्रश्न × निर्धारित अंक) − (गलत प्रश्न × नेगेटिव अंक)</code>।</li>
        </ul>
        {extra_pdf_heading_html}

        <h2>गलत प्रश्न या उत्तर पर ऑनलाइन आपत्ति (Objection) कैसे दर्ज करें? और कैसे डाउनलोड करें?</h2>
        <p>यदि आपको पूरा विश्वास है कि आयोग द्वारा दिया गया कोई उत्तर गलत है, तो आप नीचे दिए गए स्टेप्स से अपनी आंसर की डाउनलोड करके ऑनलाइन आपत्ति दर्ज कर सकते हैं:</p>
        <ol>
            <li><strong>आधिकारिक लिंक खोलें:</strong> नीचे टेबल में दिए गए <strong>Direct Answer Key / Response Sheet Link</strong> पर क्लिक करें।</li>
            <li><strong>लॉगिन करें:</strong> अपना Roll Number / Application Number और Password (या जन्मतिथि) दर्ज करके डैशबोर्ड में प्रवेश करें।</li>
            <li><strong>Response Sheet PDF सेव करें:</strong> स्क्रीन पर दिखने वाली प्रश्न पत्र और उत्तर कुंजी की फाइल को प्रिंट या सेव कर लें।</li>
            <li><strong>Objection दर्ज करें (यदि आवश्यक हो):</strong> 'Raise Objection' टैब पर क्लिक करें, संबंधित Question ID चुनें, मानक पुस्तक (NCERT या सरकारी रेफरेंस बुक) के पेज की पीडीएफ अपलोड करें और निर्धारित शुल्क जमा करके सबमिट कर दें।</li>
        </ol>
        """
        link_label = f"Download {short_exam} PDF / Response Sheet Active Link"

    else:
        body_sections = f"""
        {weekly_banner_html}
        <p><strong>{org_name}</strong> ने सरकारी नौकरी की तलाश कर रहे योग्य उम्मीदवारों के लिए <strong>{core_exam}</strong> भर्ती का आधिकारिक विज्ञापन (Official Notification) जारी कर दिया है। विभाग के आधिकारिक पोर्टल पर यह नई भर्ती सूचना <em>“{raw_notice}”</em> शीर्षक के अंतर्गत प्रकाशित की गई है। जो भी युवा केंद्र या राज्य सरकार के इस प्रतिष्ठित विभाग में अपनी सेवाएं देना चाहते हैं, उनके लिए यह एक अत्यंत सुनहरा अवसर है।</p>
        <p>हमने इस नए नोटिफिकेशन पीडीएफ को डाउनलोड करके इसकी बारीकी से जांच की है ताकि आपको लंबी-चौड़ी फाइल पढ़ने में समय न गंवाना पड़े। इस लेख में आपको सबसे पहले ओवरव्यू टेबल मिलेगी और उसके बाद शैक्षणिक योग्यता, आयु सीमा, आवेदन शुल्क, वेतनमान और ऑनलाइन फॉर्म भरने की पूरी जानकारी साफ-सुथरे पैराग्राफ व बुलेट पॉइंट्स में पढ़ने को मिलेगी।</p>
        {student_verification_box}
        {overview_6_line_table}

        <h2>{short_exam} Notification: भर्ती का मुख्य विवरण और पदों की जानकारी</h2>
        <p>जब भी कोई नई सरकारी वैकेंसी आती है, तो फॉर्म भरने से पहले हर उम्मीदवार को यह समझना चाहिए कि यह भर्ती किस प्रकृति की है और इसमें किन-किन श्रेणियों के लिए अवसर उपलब्ध हैं। <strong>{short_org}</strong> द्वारा जारी इस आधिकारिक नोटिफिकेशन के अनुसार, विभाग में रिक्त पदों को भरने के लिए योग्य भारतीय नागरिकों से आवेदन आमंत्रित किए गए हैं।</p>
        <p>इस भर्ती अभियान से जुड़ी सबसे प्रमुख विशेषताएं नीचे बुलेट पॉइंट्स में दी गई हैं:</p>
        <ul>
            <li><strong>कुल विज्ञापित पद (Total Vacancies):</strong> आधिकारिक सूचना के विश्लेषण के अनुसार इस भर्ती के तहत <strong>{total_posts}</strong> के लिए चयन प्रक्रिया आयोजित की जाएगी।</li>
            <li><strong>विज्ञापन एवं संदर्भ संख्या:</strong> यह भर्ती आधिकारिक सूचना संख्या <strong>{advt_no}</strong> के अंतर्गत जारी की गई है।</li>
            <li><strong>आवेदन का माध्यम:</strong> उम्मीदवारों को केवल आधिकारिक वेबसाइट (<a href="{portal_url}" target="_blank" rel="noopener">{portal_name}</a>) के माध्यम से ही अपना फॉर्म जमा करना होगा; किसी अन्य माध्यम से भेजे गए फॉर्म स्वीकार नहीं होंगे।</li>
            <li><strong>आरक्षण का लाभ:</strong> अनुसूचित जाति (SC), अनुसूचित जनजाति (ST), अन्य पिछड़ा वर्ग (OBC-NCL), आर्थिक रूप से कमजोर वर्ग (EWS), पूर्व सैनिक (Ex-Servicemen) और दिव्यांग (PwBD) अभ्यर्थियों को सरकारी नियमों के अनुसार पदों व आयु में छूट दी जाएगी।</li>
        </ul>

        <h2>{core_exam} Eligibility Criteria: शैक्षणिक योग्यता और आयु सीमा (पॉइंट्स में)</h2>
        <p>ऑनलाइन आवेदन शुरू करने से पहले सबसे जरूरी कदम अपनी पात्रता (Eligibility) की जांच करना है। यदि कोई उम्मीदवार निर्धारित कट-ऑफ तिथि (Crucial Date) तक आवश्यक डिग्री या आयु सीमा पूरी नहीं करता है, तो बाद में डॉक्यूमेंट वेरिफिकेशन के समय उसका आवेदन निरस्त किया जा सकता है।</p>
        <p>नोटिफिकेशन पीडीएफ के अनुसार पात्रता के मुख्य मापदंड इस प्रकार हैं:</p>
        <ul>
            <li><strong>शैक्षणिक योग्यता (Educational Qualification):</strong> उम्मीदवार के पास किसी मान्यता प्राप्त बोर्ड, विश्वविद्यालय या संस्थान से <strong>{qualification}</strong> होना अनिवार्य है। (पदानुसार विस्तृत योग्यता के लिए नीचे दी गई आधिकारिक पीडीएफ अवश्य देखें)।</li>
            <li><strong>आयु सीमा (Age Limit):</strong> इस भर्ती के लिए उम्मीदवार की आयु <strong>{age_limit}</strong> निर्धारित की गई है।</li>
            <li><strong>अधिकतम आयु में छूट (Age Relaxation):</strong> आरक्षित वर्ग के उम्मीदवारों को सरकारी नियमानुसार ऊपरी आयु सीमा में विशेष छूट मिलती है—जैसे OBC (NCL) को 3 वर्ष, SC/ST को 5 वर्ष और PwBD उम्मीदवारों को श्रेणी के अनुसार 10 से 15 वर्ष तक की छूट।</li>
            <li><strong>नागरिकता एवं अन्य शर्तें:</strong> अभ्यर्थी भारत का नागरिक होना चाहिए तथा संबंधित पद के लिए निर्धारित शारीरिक व चिकित्सीय मानकों को पूरा करता हो।</li>
        </ul>

        <h2>{core_exam} Application Fee, वेतनमान (Salary) और चयन प्रक्रिया</h2>
        <p>एक प्रतियोगी छात्र के लिए फॉर्म की फीस, सिलेक्शन का तरीका और चयन के बाद मिलने वाली सैलरी जानना बेहद महत्वपूर्ण होता है। विभाग ने अपने आधिकारिक विज्ञापन में इन तीनों बिंदुओं को स्पष्ट किया है:</p>
        <ul>
            <li><strong>आवेदन शुल्क (Application Fee):</strong> उम्मीदवारों के लिए आवेदन शुल्क <strong>{app_fee}</strong> रखा गया है। शुल्क का भुगतान डेबिट कार्ड, क्रेडिट कार्ड, नेट बैंकिंग या UPI के माध्यम से ऑनलाइन किया जा सकता है।</li>
            <li><strong>वेतनमान और भत्ते (Pay Scale & Perks):</strong> चयनित होने वाले उम्मीदवारों को <strong>{salary_info}</strong> के तहत मूल वेतन के साथ महंगाई भत्ता (DA), मकान किराया भत्ता (HRA), यात्रा भत्ता और मेडिकल सुविधाएं प्रदान की जाएंगी।</li>
            <li><strong>चयन प्रक्रिया के चरण (Selection Process):</strong> इस भर्ती में उम्मीदवारों का अंतिम चयन लिखित / कंप्यूटर आधारित परीक्षा (CBT/Written Exam), कौशल या शारीरिक परीक्षण (यदि पद के लिए लागू हो), डॉक्यूमेंट वेरिफिकेशन (DV) और मेडिकल जांच के आधार पर किया जाएगा।</li>
        </ul>
        {extra_pdf_heading_html}

        <h2>{short_exam} का Online Form कैसे भरें? (Step-by-Step आवेदन प्रक्रिया)</h2>
        <p>जो उम्मीदवार ऊपर दी गई सभी पात्रता शर्तों को पूरा करते हैं, वे अंतिम तिथि से पहले नीचे बताए गए आसान स्टेप्स को फॉलो करके अपना ऑनलाइन फॉर्म बिना किसी गलती के भर सकते हैं:</p>
        <ol>
            <li><strong>आधिकारिक पीडीएफ ध्यान से पढ़ें:</strong> सबसे पहले नीचे दिए गए <strong>Important Links</strong> सेक्शन से आधिकारिक नोटिफिकेशन डाउनलोड करें और अपने पद की योग्यता व शर्तें पढ़ लें।</li>
            <li><strong>पोर्टल पर नया रजिस्ट्रेशन (OTR / Registration) करें:</strong> <a href="{portal_url}" target="_blank" rel="noopener">{portal_name}</a> पर जाएं और अपने चालू मोबाइल नंबर व ईमेल आईडी की मदद से बेसिक रजिस्ट्रेशन पूरा करें।</li>
            <li><strong>विस्तृत आवेदन फॉर्म भरें:</strong> लॉगिन करने के बाद अपनी व्यक्तिगत जानकारी, माता-पिता का नाम, स्थायी पता और शैक्षणिक योग्यता (10वीं/12वीं/स्नातक के रोल नंबर व प्रतिशत) बिल्कुल मार्कशीट के अनुसार भरें।</li>
            <li><strong>फोटो, सिग्नेचर और दस्तावेज़ अपलोड करें:</strong> निर्धारित साइज (KB) और फॉर्मेट (JPG/PDF) में अपनी नवीनतम पासपोर्ट साइज फोटो, स्पष्ट हस्ताक्षर और मांगे गए प्रमाण पत्र अपलोड करें।</li>
            <li><strong>फीस जमा करें और फाइनल प्रिंट निकालें:</strong> फॉर्म का Preview ध्यान से जांचने के बाद ऑनलाइन आवेदन शुल्क जमा करें और Final Submit होने पर एप्लीकेशन फॉर्म की पीडीएफ सेव करके प्रिंटआउट रख लें।</li>
        </ol>
        """
        link_label = f"Download {short_exam} Notification PDF / Apply Online"

    faq_and_links_html = f"""
    <h2>{short_exam}: Important Official Links</h2>
    <p>उम्मीदवारों की सुविधा और समय की बचत के लिए हमने आधिकारिक पीडीएफ/एक्टिव लिंक और मुख्य वेबसाइट के डायरेक्ट लिंक नीचे टेबल में उपलब्ध करा दिए हैं:</p>
    <table border="1" cellpadding="10" cellspacing="0" style="width:100%; border-collapse:collapse; margin:15px 0 25px 0;">
        <tbody>
            <tr style="background-color:#eef6ff;">
                <td><strong>{link_label}</strong></td>
                <td><a href="{target_url}" target="_blank" rel="noopener"><strong>Click Here for Official {category} ({doc_format})</strong></a></td>
            </tr>
            <tr>
                <td><strong>Official Website ({short_org})</strong></td>
                <td><a href="{portal_url}" target="_blank" rel="noopener"><strong>Visit {portal_name} Official Page</strong></a></td>
            </tr>
        </tbody>
    </table>

    <h2>अक्सर पूछे जाने वाले प्रश्न (FAQs) – {short_exam}</h2>
    <p>इस अपडेट को लेकर छात्रों द्वारा सबसे ज्यादा पूछे जाने वाले सवालों के संक्षिप्त उत्तर नीचे दिए गए हैं:</p>
    <ul>
        <li><strong>प्रश्न 1: {short_exam} का यह आधिकारिक अपडेट कब जारी/अपडेट किया गया है?</strong><br>
        उत्तर: विभाग द्वारा यह आधिकारिक {doc_format} अपडेट {release_date} को आधिकारिक पोर्टल पर सत्यापित/सक्रिय किया गया है।</li>
        <li><strong>प्रश्न 2: यह सूचना किस भर्ती बोर्ड द्वारा जारी की गई है?</strong><br>
        उत्तर: यह सूचना आधिकारिक तौर पर <strong>{org_name}</strong> द्वारा जारी की गई है।</li>
        <li><strong>प्रश्न 3: {core_exam} के लिए मुख्य पात्रता या पद विवरण क्या है?</strong><br>
        उत्तर: उपलब्ध विवरण के अनुसार कुल पद: {total_posts} हैं और आवश्यक योग्यता: {qualification} निर्धारित है।</li>
        <li><strong>प्रश्न 4: मैं आधिकारिक पीडीएफ या डायरेक्ट लिंक कहाँ से एक्सेस कर सकता हूँ?</strong><br>
        उत्तर: आप इस लेख के ऊपर दी गई <strong>Important Official Links</strong> टेबल में डायरेक्ट क्लिक करके या <a href="{portal_url}" target="_blank" rel="noopener">{portal_name}</a> पर जाकर इसे देख सकते हैं।</li>
        <li><strong>प्रश्न 5: यदि वेबसाइट स्लो चल रही हो तो छात्रों को क्या करना चाहिए?</strong><br>
        उत्तर: नया अपडेट आने पर सर्वर पर लोड बढ़ जाता है; ऐसे में कुछ देर प्रतीक्षा करें या सुबह/देर रात के समय पुनः प्रयास करें और अपना रजिस्ट्रेशन नंबर पहले से तैयार रखें।</li>
    </ul>
    """

    full_html = f"{body_sections}\n{faq_and_links_html}"
    return research_data["seo_title"], full_html.strip()

# =====================================================================
# 8. WORDPRESS PUBLISHER + STARTUP CONNECTION DIAGNOSTIC
# =====================================================================
def test_wordpress_connection():
    if not WP_USERNAME or "your_wp_username" in WP_USERNAME or "your_wp_application_password" in WP_APP_PASSWORD:
        print("   [WP WARNING] WordPress Username ya Application Password abhi set nahi hai!")
        return False

    try:
        test_url = f"{WP_SITE_URL.rstrip('/')}/wp-json/wp/v2/users/me"
        clean_app_pass = WP_APP_PASSWORD.replace(" ", "")
        token = base64.b64encode(f"{WP_USERNAME}:{clean_app_pass}".encode()).decode("utf-8")
        headers = {
            "Authorization": f"Basic {token}",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36"
        }
        res = requests.get(test_url, headers=headers, timeout=15)
        if res.status_code == 200:
            user_name = res.json().get("name", WP_USERNAME)
            print(f"   [WP CONNECTED OK] Successfully connected to {WP_SITE_URL} as '{user_name}' (Post Mode: {WP_POST_STATUS.upper()})")
            return True
        else:
            print(f"   [WP AUTH ERROR {res.status_code}] Website ne login reject kiya: {res.text[:180]}")
            return False
    except Exception as e:
        print(f"   [WP CONNECTION FAILED] {e}")
        return False

def save_or_update_wordpress_draft(title, html_content, existing_wp_id=0):
    preview_path = os.path.join(DATA_FOLDER, "latest_govtvibhag_style_draft.html")
    try:
        with open(preview_path, "w", encoding="utf-8") as f:
            f.write(f"<h1>{title}</h1>\n{html_content}")
    except Exception:
        pass

    if not WP_USERNAME or "your_wp_username" in WP_USERNAME or "your_wp_application_password" in WP_APP_PASSWORD:
        print(f"    [!] WordPress credentials missing! Saved Local Preview Only: {preview_path}")
        return 0

    try:
        base_api = f"{WP_SITE_URL.rstrip('/')}/wp-json/wp/v2/posts"
        api_url = f"{base_api}/{existing_wp_id}" if existing_wp_id > 0 else base_api
        clean_app_pass = WP_APP_PASSWORD.replace(" ", "")
        credentials = f"{WP_USERNAME}:{clean_app_pass}"
        token = base64.b64encode(credentials.encode()).decode("utf-8")
        headers = {
            "Authorization": f"Basic {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        }
        payload = {
            "title": title,
            "content": html_content,
            "status": WP_POST_STATUS
        }
        res = requests.post(api_url, json=payload, headers=headers, timeout=25)
        if res.status_code in [200, 201]:
            wp_id = res.json().get("id", 0)
            wp_link = res.json().get("link", "")
            action_word = "UPDATED" if existing_wp_id > 0 else "UPLOADED"
            print(f"    [SUCCESS] Article {action_word} on WordPress ({WP_POST_STATUS.upper()} | ID: {wp_id}) -> {wp_link}")
            return wp_id
        else:
            print(f"    [!] WordPress API Status: {res.status_code} - {res.text[:200]}")
    except Exception as e:
        print(f"    [!] WordPress Upload Error: {e}")
    return 0

# =====================================================================
# 9. WEDNESDAY EXPERIENCED EDITOR AUTO-UPDATER (GOOGLE CROSS-CHECK)
# =====================================================================
def find_portal_info_by_url(portal_url):
    domain = urlparse(portal_url).netloc.lower()
    for p in GOVT_PORTALS:
        if domain in urlparse(p["url"]).netloc.lower():
            return p
    return GOVT_PORTALS[0]

def run_wednesday_article_updater(bot_start_dt):
    """
    हर बुधवार (Wednesday) को चलने वाला अनुभवी एडिटर फंक्शन:
    1. चेक करता है कि क्या आज बुधवार (weekday == 2) है।
    2. डेटाबेस से पुराने पब्लिश/ड्राफ्ट किए गए आर्टिकल्स (wp_post_id > 0) निकालता है जो आज अपडेट नहीं हुए हैं।
    3. पहले Google News RSS (पिछले 7 दिन) और आधिकारिक लिंक पर क्रॉस-चेक करता है।
    4. एक अनुभवी वर्कर की तरह ताज़ा स्टेटस जोड़कर WordPress पर उसी पोस्ट (wp_post_id) को अपडेट करता है।
    """
    now_dt = datetime.datetime.now()
    if now_dt.weekday() != 2:  # Monday=0, Tuesday=1, Wednesday=2
        return

    today_str = now_dt.strftime("%Y-%m-%d")
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, portal_url, target_url, raw_notice_title, seo_title, category, wp_post_id, content_hash
        FROM processed_posts
        WHERE wp_post_id > 0
          AND DATE(updated_at) < ?
        ORDER BY updated_at ASC
        LIMIT 3
    """, (today_str,))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        print("\n   [WEDNESDAY UPDATER] Aaj Wednesday hai, aur sabhi purane articles pehle hi update aur cross-check ho chuke hain.")
        return

    print(f"\n   [WEDNESDAY EDITORIAL UPDATER] Aaj Wednesday hai! {len(rows)} purane articles ko Google par cross-check karke update kiya ja raha hai...")

    for row in rows:
        db_id, portal_url, target_url, raw_title, old_seo_title, old_cat, wp_post_id, old_hash = row
        portal_info = find_portal_info_by_url(portal_url)
        short_org = portal_info["short_org"]

        print(f"   -> [Cross-Checking Old Article ID #{wp_post_id}] {old_seo_title[:65]}...")

        # 1. Google News par pichhle 7 dino ka cross-check
        google_7d_data = cross_check_active_link_on_google(short_org, raw_title, old_cat, bot_start_dt, time_window="7d")
        # 2. Target URL / Official Page ko dobara inspect karna
        source_text, doc_format, _, _, pdf_headings = extract_source_and_metadata(target_url)

        snippets_list = google_7d_data.get("google_snippets", [])
        combined_latest_signals = " ".join(snippets_list + [raw_title, source_text[:1000]])
        updated_category = determine_category(combined_latest_signals) if snippets_list else old_cat

        # 3. Experienced Editor Note taiyar karna (Gemini + Google Verification)
        weekly_editorial_note = (
            f"हमारी एडिटोरियल टीम ने आज बुधवार ({now_dt.strftime('%d %B %Y')}) को गूगल और "
            f"<strong>{portal_info['portal_name']}</strong> पर इस अपडेट को दोबारा क्रॉस-चेक किया है। "
            f"वर्तमान में इसकी आधिकारिक लिंक और दिशा-निर्देश पूर्णतः सक्रिय हैं।"
        )

        if GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key":
            check_prompt = f"""
            आप एक अनुभवी सरकारी नौकरी कंटेंट एडिटर हैं। आज बुधवार ({now_dt.strftime('%d %B %Y')}) को आप अपने पुराने आर्टिकल "{old_seo_title}" को गूगल और आधिकारिक वेबसाइट से क्रॉस-चेक करके अपडेट कर रहे हैं।
            - विभाग: {portal_info['org']}
            - मूल नोटिस: {raw_title}
            - पिछले 7 दिनों के गूगल न्यूज़ अपडेट्स: {" | ".join(snippets_list[:4]) if snippets_list else "कोई नया बदलाव नहीं, पुरानी प्रक्रिया चालू है"}
            - आधिकारिक पेज का ताज़ा टेक्स्ट: {source_text[:1500]}

            कृपया 2 से 3 वाक्यों में एक प्रोफेशनल 'साप्ताहिक एडिटोरियल रिव्यू नोट' (Hindi में) लिखें जो छात्रों को बताए कि आज बुधवार को गूगल और आधिकारिक पोर्टल पर क्रॉस-चेक करने पर इस भर्ती/परीक्षा की वर्तमान स्थिति क्या है।
            """
            ai_note = call_gemini_json_or_text(check_prompt, expect_json=False)
            if ai_note and len(ai_note.strip()) > 25:
                weekly_editorial_note = sanitize_clean_text(ai_note)

        # 4. Blueprint aur Updated 1000+ Words Article banana
        research_data = build_article_blueprint(
            portal_info, raw_title, source_text, updated_category, pdf_headings, google_7d_data, weekly_editorial_note
        )
        new_seo_title, updated_html = generate_professional_1000_words_article(
            portal_info, research_data, target_url, updated_category, source_text, doc_format, weekly_update_note=weekly_editorial_note
        )

        # 5. WordPress par usi Post ID ko update karna
        updated_wp_id = save_or_update_wordpress_draft(new_seo_title, updated_html, existing_wp_id=wp_post_id)
        if updated_wp_id > 0:
            new_hash = hashlib.md5((new_seo_title + weekly_editorial_note).encode("utf-8", errors="ignore")).hexdigest()
            update_processed_post_record(db_id, new_seo_title, updated_category, new_hash)
            print(f"      [WEDNESDAY UPDATE SUCCESS] Post ID #{wp_post_id} successfully refreshed with Google cross-check!")

        time.sleep(1.0)

# =====================================================================
# 10. SMART SCANNER WITH COMPLETE INITIAL LOCK (HTML + RSS BOTH LOCKED)
# =====================================================================
def fetch_fallback_updates_for_js_portal(portal_info):
    discovered = []
    short_org = portal_info["short_org"]
    portal_url = portal_info["url"]
    try:
        q = f'"{short_org}" (recruitment OR result OR "admit card" OR "answer key" OR notification) when:1d'
        rss_url = f"[https://news.google.com/rss/search?q=](https://news.google.com/rss/search?q=){quote_plus(q)}&hl=en-IN&gl=IN&ceid=IN:en"
        res = requests.get(rss_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "xml")
            for item in soup.find_all("item")[:4]:
                title_el = item.find("title")
                if title_el and title_el.text:
                    clean_t = title_el.text.split(" - ")[0].strip()
                    discovered.append((clean_t, portal_url))
    except Exception:
        pass
    return discovered

def run_hourly_scanner(bot_start_dt):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-IN,en-US;q=0.9,en;q=0.8"
    }
    current_check_str = datetime.datetime.now().strftime("%d %b %Y, %I:%M %p")
    total_portals = len(GOVT_PORTALS)
    print(f"\n[SCAN - {current_check_str}] Checking all {total_portals} official portals...")

    new_found_total = 0

    for idx, portal_info in enumerate(GOVT_PORTALS, start=1):
        portal = portal_info["url"]
        portal_name = portal_info["portal_name"]
        portal_already_synced = is_portal_synced(portal)

        candidate_links = []
        try:
            response = requests.get(portal, headers=headers, timeout=20, verify=False)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, "html.parser")
                for menu_tag in soup.find_all(["nav", "footer"]):
                    menu_tag.decompose()
                for a_tag in soup.find_all("a", href=True):
                    href = a_tag["href"].strip()
                    smart_text = extract_smart_link_text(a_tag)
                    if href and len(smart_text) >= 8:
                        candidate_links.append((smart_text, urljoin(portal, href)))
        except Exception:
            print(f"   [{idx:02d}/{total_portals}] [Direct Connect Slow] Using Smart Backup for: {portal_name}")

        if len(candidate_links) < 15 or not portal_already_synced:
            candidate_links.extend(fetch_fallback_updates_for_js_portal(portal_info))

        # STEP A: Complete Initial Baseline Lock
        if not portal_already_synced:
            for link_text, full_target_url in candidate_links:
                n_key = normalize_notice_key(portal, link_text)
                unique_target = full_target_url if full_target_url != portal else f"{portal}#{n_key}"
                mark_as_processed(portal, unique_target, n_key, link_text[:100], "OLD_BASELINE_LOCKED", "IGNORED_OLD", 0, "")
            mark_portal_synced(portal)
            print(f"   [{idx:02d}/{total_portals}] [Baseline Lock] {portal_name}: Locked {len(candidate_links)} existing items (Zero articles written for pre-existing items).")
            continue

        # STEP B: Only Check Newly Arrived Links After Baseline Lock
        processed_count = 0
        for link_text, full_target_url in candidate_links:
            if not is_genuine_notification(link_text, full_target_url):
                continue

            n_key = normalize_notice_key(portal, link_text)
            unique_target = full_target_url if full_target_url != portal else f"{portal}#{n_key}"

            if is_already_processed(unique_target, notice_key=n_key):
                continue

            source_text, doc_format, last_mod, pdf_date, pdf_headings = extract_source_and_metadata(full_target_url)
            content_hash = hashlib.md5((link_text + source_text[:500]).encode("utf-8", errors="ignore")).hexdigest()

            combined_info = (link_text + " " + full_target_url).lower()
            category = determine_category(combined_info)

            google_cross_data = cross_check_active_link_on_google(portal_info["short_org"], link_text, category, bot_start_dt)

            is_fresh, reason, ai_purpose = verify_is_truly_published_after_bot_start(
                portal_info, link_text, source_text, doc_format, last_mod, pdf_date, google_cross_data, bot_start_dt
            )
            if not is_fresh:
                print(f"   [{idx:02d}/{total_portals}] [Blocked Pre-Existing/Old Notice] {portal_name}: {link_text[:45]}... -> {reason}")
                mark_as_processed(portal, unique_target, n_key, link_text[:100], f"OLD_REJECTED ({reason})", "IGNORED_OLD", 0, content_hash)
                continue

            research_data = build_article_blueprint(
                portal_info, link_text, source_text, category, pdf_headings, google_cross_data, ai_purpose
            )
            proposed_seo_title = research_data["seo_title"]

            if is_already_processed(unique_target, notice_key=n_key, seo_title=proposed_seo_title, content_hash=content_hash):
                mark_as_processed(portal, unique_target, n_key, link_text[:100], "DUPLICATE_IGNORED", "IGNORED_DUP", 0, content_hash)
                continue

            print(f"   [{idx:02d}/{total_portals}] [NEW POST-START {category.upper()} VERIFIED!] {portal_name}: {link_text[:60]}...")
            print(f"       [VERIFICATION] -> {reason}")
            print(f"       [SEO TITLE] -> {proposed_seo_title}")

            seo_title, article_html = generate_professional_1000_words_article(
                portal_info, research_data, full_target_url, category, source_text, doc_format
            )

            wp_id = save_or_update_wordpress_draft(seo_title, article_html)
            mark_as_processed(portal, unique_target, n_key, link_text, seo_title, category, wp_id, content_hash)

            processed_count += 1
            new_found_total += 1
            if processed_count >= 2:
                break

        if processed_count == 0:
            print(f"   [{idx:02d}/{total_portals}] [Checked OK] {portal_name} (Scanned {len(candidate_links)} items - No new post-start update)")

        time.sleep(0.3)

    if new_found_total == 0:
        print("\n   [STATUS] Scan complete. Sabhi 39 portals check ho gaye, code dalne ke baad abhi koi naya update nahi aaya hai.")
    else:
        print(f"\n   [STATUS] Scan complete! Total {new_found_total} naye articles WordPress ({WP_POST_STATUS}) mein bheje gaye.")

    # STEP C: Har Wednesday ko purane articles ko Google par cross-check karke update karein
    run_wednesday_article_updater(bot_start_dt)

if __name__ == "__main__":
    disable_cmd_quickedit()
    print("=========================================================================")
    print("   GOVTVIBHAG.COM PROFESSIONAL EDITORIAL BOT v10.0 (STRICT LOCK EDITION) ")
    print("=========================================================================")
    init_db()
    bot_start_dt = ensure_fresh_v10_baseline_and_start_time()
    print(f"   [STRICT LOCK ACTIVE] Only writing articles released ON/AFTER: {bot_start_dt.strftime('%d %b %Y, %I:%M %p')}")
    test_wordpress_connection()
    run_hourly_scanner(bot_start_dt)
