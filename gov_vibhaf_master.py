import os
import re
import sys
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
# 1. WORDPRESS & AI CONFIGURATION (Auto-Reads from GitHub Secrets)
# =====================================================================
# Yahan aapko kuch bharne ki zaroorat nahi hai, yeh GitHub Secrets se apne aap le lega!
WP_SITE_URL = os.getenv("WP_SITE_URL", "https://govtvibhag.com").strip()
WP_USERNAME = os.getenv("WP_USERNAME", "your_wp_username").strip()
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD", "your_wp_application_password").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "your_gemini_api_key").strip()

DB_NAME = "govt_vibhag_master.db"
DATA_FOLDER = "scraped_data_cache"

# =====================================================================
# AUTOMATIC FIX: Disable Windows CMD QuickEdit Freeze on Mouse Click
# =====================================================================
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
# 2. 39 OFFICIAL GOVERNMENT PORTALS (.gov.in / .nic.in)
# =====================================================================
GOVT_PORTALS = [
    {"url": "https://aiimsexams.ac.in", "org": "All India Institute of Medical Sciences (AIIMS, New Delhi)", "short_org": "AIIMS", "portal_name": "AIIMS Examination Portal"},
    {"url": "https://ssc.gov.in", "org": "Staff Selection Commission (SSC)", "short_org": "SSC", "portal_name": "Official SSC Portal"},
    {"url": "https://upsc.gov.in", "org": "Union Public Service Commission (UPSC)", "short_org": "UPSC", "portal_name": "Official UPSC Portal"},
    {"url": "https://indianrailways.gov.in", "org": "Ministry of Railways (Indian Railways)", "short_org": "RRB Railway", "portal_name": "Indian Railways Official Portal"},
    {"url": "https://www.rrbcdg.gov.in", "org": "Railway Recruitment Board (RRB)", "short_org": "RRB", "portal_name": "RRB Official Portal"},
    {"url": "https://www.indiapost.gov.in", "org": "Department of Posts (India Post)", "short_org": "India Post", "portal_name": "India Post Official Portal"},
    {"url": "https://www.drdo.gov.in", "org": "Defence Research and Development Organisation (DRDO)", "short_org": "DRDO", "portal_name": "DRDO Official Career Portal"},
    {"url": "https://www.isro.gov.in", "org": "Indian Space Research Organisation (ISRO)", "short_org": "ISRO", "portal_name": "ISRO Official Portal"},
    {"url": "https://nta.ac.in", "org": "National Testing Agency (NTA)", "short_org": "NTA", "portal_name": "NTA Official Examination Portal"},
    {"url": "https://ctet.nic.in", "org": "Central Board of Secondary Education (CBSE CTET)", "short_org": "CBSE CTET", "portal_name": "CTET Official Examination Portal"},
    {"url": "https://kvsangathan.nic.in", "org": "Kendriya Vidyalaya Sangathan (KVS)", "short_org": "KVS", "portal_name": "KVS Official Portal"},
    {"url": "https://navodaya.gov.in", "org": "Navodaya Vidyalaya Samiti (NVS)", "short_org": "NVS", "portal_name": "NVS Official Portal"},
    {"url": "https://www.ibps.in", "org": "Institute of Banking Personnel Selection (IBPS)", "short_org": "IBPS", "portal_name": "IBPS Official Portal"},
    {"url": "https://sbi.co.in/web/careers", "org": "State Bank of India (SBI Central Recruitment)", "short_org": "SBI", "portal_name": "SBI Careers Official Portal"},
    {"url": "https://opportunities.rbi.org.in", "org": "Reserve Bank of India (RBI Services Board)", "short_org": "RBI", "portal_name": "RBI Opportunities Portal"},
    {"url": "https://licindia.in/test2", "org": "Life Insurance Corporation of India (LIC)", "short_org": "LIC", "portal_name": "LIC Official Careers Portal"},
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
    {"url": "https://rpsc.rajasthan.gov.in", "org": "Rajasthan Public Service Commission (RPSC)", "short_org": "RPSC", "portal_name": "RPSC Official Portal"},
    {"url": "https://rssb.rajasthan.gov.in", "org": "Rajasthan Staff Selection Board (RSSB / RSMSSB)", "short_org": "RSSB Rajasthan", "portal_name": "RSSB Official Portal"},
    {"url": "https://esb.mp.gov.in", "org": "Madhya Pradesh Employees Selection Board (MPESB)", "short_org": "MPESB", "portal_name": "MPESB Official Portal"},
    {"url": "https://mppsc.mp.gov.in", "org": "Madhya Pradesh Public Service Commission (MPPSC)", "short_org": "MPPSC", "portal_name": "MPPSC Official Portal"},
    {"url": "https://hssc.gov.in", "org": "Haryana Staff Selection Commission (HSSC)", "short_org": "HSSC", "portal_name": "HSSC Official Portal"},
    {"url": "https://gpsc.gujarat.gov.in", "org": "Gujarat Public Service Commission (GPSC)", "short_org": "GPSC", "portal_name": "GPSC Official Portal"},
    {"url": "https://www.mpsc.gov.in", "org": "Maharashtra Public Service Commission (MPSC)", "short_org": "MPSC", "portal_name": "MPSC Official Portal"},
    {"url": "https://tnpsc.gov.in", "org": "Tamil Nadu Public Service Commission (TNPSC)", "short_org": "TNPSC", "portal_name": "TNPSC Official Portal"}
]

JOB_KEYWORDS = ["recruitment", "vacancy", "notification", "advt", "advertisement", "bharti", "apply online", "online form", "detailed notice"]
ADMIT_CARD_KEYWORDS = ["admit card", "hall ticket", "call letter", "exam city", "intimation slip", "admission certificate"]
ANSWER_KEY_KEYWORDS = ["answer key", "response sheet", "question paper", "objection", "model answer"]
RESULT_KEYWORDS = ["result", "merit list", "score card", "shortlisted", "selected candidates", "cut-off", "cutoff", "stage-ii", "stage-i", "final result"]

IGNORE_KEYWORDS = [
    "tender", "corrigendum", "holiday", "quotation", "auction", "deputation",
    "transfer", "pension", "rti", "contact us", "about us", "login", "register",
    "archive", "disclaimer", "privacy policy", "terms", "faq", "helpdesk",
    "syllabus", "previous year", "mock test", "model paper", "gazette", "recruitment rules",
    "annual report", "seniority list", "promotion", "empanelment", "medical reimbursement",
    "screen reader", "skip to main", "sitemap", "feedback", "accessibility", "citizen charter"
]

GENERIC_MENU_TITLES = [
    "recruitment", "recruitments", "result", "results", "admit card", "admit cards",
    "answer key", "answer keys", "notification", "notifications", "advertisements",
    "recruitment advertisements", "latest news", "what's new", "apply online",
    "cut-off marks", "cutoff marks", "merit list", "career", "careers", "vacancies",
    "vacancy", "computer based recruitment test (cbrt)", "examinations", "exams",
    "department of posts government of india", "gazette notifications", "recruitment rules"
]

# =====================================================================
# 3. DATABASE & 4-LAYER ANTI-DUPLICATE ENGINE
# =====================================================================
def normalize_url(url_str):
    try:
        p = urlparse(url_str.strip())
        clean_path = re.sub(r'/+$', '', p.path)
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

def ensure_bot_start_time():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT setting_value FROM bot_settings WHERE setting_key = 'bot_start_iso'")
    row = cursor.fetchone()
    if not row:
        now_iso = datetime.datetime.now().isoformat()
        cursor.execute("INSERT INTO bot_settings (setting_key, setting_value) VALUES ('bot_start_iso', ?)", (now_iso,))
        conn.commit()
        conn.close()
        return datetime.datetime.fromisoformat(now_iso)
    conn.close()
    return datetime.datetime.fromisoformat(row[0])

def is_portal_synced(portal_url):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM synced_portals WHERE portal_url = ?", (portal_url,))
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

# =====================================================================
# 4. STRICT ANTI-GARBAGE & PDF METADATA FRESHNESS VERIFICATION
# =====================================================================
def is_genuine_notification(link_text, full_url):
    clean_text = sanitize_clean_text(link_text)
    lower_text = clean_text.lower()
    lower_url = full_url.lower()

    if len(clean_text) < 28 or len(clean_text.split()) < 4:
        return False

    if lower_text in GENERIC_MENU_TITLES:
        return False

    if any(bad in lower_text or bad in lower_url for bad in IGNORE_KEYWORDS):
        return False

    if lower_url.startswith("javascript:") or lower_url.startswith("mailto:") or full_url.endswith("#"):
        return False

    if re.search(r'\b(2015|2016|2017|2018|2019|2020|2021|2022|2023|2024|2025)\b', lower_text) and "2026" not in lower_text:
        return False

    has_exam_identifier = bool(re.search(
        r'(2026|\d{1,3}/2026|advt|stage|norcet|cet|cgl|chsl|mts|gd|ntpc|alp|je|constable|si|asi|clerk|po|so|officer|assistant|engineer|teacher|tgt|pgt|prt|stenographer|group\s*[a-d]|grade\s*[a-d])',
        lower_text
    ))
    is_pdf = lower_url.endswith(".pdf")

    if not (has_exam_identifier or is_pdf):
        return False

    all_valid_keywords = JOB_KEYWORDS + ADMIT_CARD_KEYWORDS + ANSWER_KEY_KEYWORDS + RESULT_KEYWORDS
    if not any(k in lower_text or k in lower_url for k in all_valid_keywords):
        return False

    return True

def extract_source_and_metadata(target_url):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        response = requests.get(target_url, headers=headers, timeout=25, verify=False)
        if response.status_code != 200:
            return "", "Webpage", None, None

        last_mod_header = response.headers.get("Last-Modified", None)
        pdf_internal_date = None

        if target_url.lower().endswith(".pdf") or b"%PDF" in response.content[:15]:
            if not PYMUPDF_AVAILABLE:
                return "", "PDF", last_mod_header, None
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

            text = ""
            for page in range(min(10, len(doc))):
                text += "\n" + doc[page].get_text("text")
            doc.close()
            return sanitize_clean_text(text), "PDF", last_mod_header, pdf_internal_date
        else:
            soup = BeautifulSoup(response.text, "html.parser")
            for tag in soup(["script", "style", "nav", "header", "footer"]):
                tag.decompose()
            clean_web_text = sanitize_clean_text(soup.get_text(" ", strip=True)[:8000])
            return clean_web_text, "Online Portal", last_mod_header, None
    except Exception:
        return "", "PDF / Online Link", None, None

def verify_is_truly_fresh(raw_title, source_text, last_modified_header, pdf_internal_date):
    today = datetime.datetime.now().date()
    combined = f"{raw_title} {source_text[:1500]}".lower()

    if pdf_internal_date:
        days_old = (today - pdf_internal_date).days
        if days_old > 2:
            return False, f"Old PDF Metadata Date ({pdf_internal_date})"

    if last_modified_header:
        try:
            mod_dt = parsedate_to_datetime(last_modified_header).replace(tzinfo=None)
            if (today - mod_dt.date()).days > 2:
                return False, f"Old Server File ({mod_dt.date()})"
        except Exception:
            pass

    old_months_pattern = r'\b(january|february|march|april|may|june|july|august|september|jan|feb|mar|apr|jun|jul|aug|sep|sept)\s*[-/,]?\s*2026\b'
    if today.month >= 10 and re.search(old_months_pattern, combined) and "october" not in combined and "oct" not in combined:
        return False, "Old Month Session (Jan-Sep 2026)"

    if re.search(r'\b(2018|2019|2020|2021|2022|2023|2024|2025)\b', raw_title.lower()) and "2026" not in raw_title.lower():
        return False, "Old Year in Title"

    return True, "100% Fresh Update"

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
# 5. PRO CONTENT WRITER: GOOGLE SEO TITLE & DEEP PDF RESEARCH ENGINE
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

def google_search_seo_research(query_text):
    """
    Step 1 of Content Writer: Searches Google News/Web to see trending SEO titles & dates if missing in PDF.
    """
    trending_titles = []
    found_date = ""
    try:
        rss_url = f"https://news.google.com/rss/search?q={quote_plus(query_text + ' 2026')}&hl=en-IN&gl=IN&ceid=IN:en"
        res = requests.get(rss_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "xml")
            for item in soup.find_all("item")[:5]:
                t = item.find("title")
                if t and t.text:
                    clean_t = t.text.split(" - ")[0].strip()
                    trending_titles.append(clean_t)
                    if not found_date:
                        dm = re.search(r'\b(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+2026)\b', clean_t, re.I)
                        if dm:
                            found_date = dm.group(1)
    except Exception:
        pass
    return trending_titles, found_date

def extract_deep_pdf_details_for_student(combined_text):
    """
    Step 2 of Content Writer: Reads the PDF thoroughly to extract Vacancies, Age, Fee, Qualification, Salary & Dates.
    """
    # 1. Total Vacancies
    vac_match = re.search(r'(?:total\s+vacanc(?:y|ies)|total\s+posts?|कुल\s+पद)\s*[:=-]?\s*(\d{1,6})', combined_text, re.I)
    if not vac_match:
        vac_match = re.search(r'\b(\d{2,6})\s+(?:vacancies|posts)\b', combined_text, re.I)
    total_posts = f"{vac_match.group(1)} Posts" if vac_match else "आधिकारिक नोटिफिकेशन के अनुसार (Check PDF)"

    # 2. Age Limit
    age_match = re.search(r'(\d{2})\s*(?:to|-|से)\s*(\d{2})\s*(?:years|वर्ष|yrs)', combined_text, re.I)
    age_limit = f"{age_match.group(1)} से {age_match.group(2)} वर्ष (आरक्षित वर्ग को नियमानुसार छूट)" if age_match else "न्यूनतम 18 वर्ष (अधिकतम आयु पदानुसार नोटिफिकेशन में देखें)"

    # 3. Educational Qualification
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
    qualification = ", ".join(quals[:3]) if quals else "संबंधित पद के अनुसार (आधिकारिक PDF में देखें)"

    # 4. Application Fee
    fee_match = re.search(r'(?:rs\.?|₹|inr)\s*(\d{2,4})\s*/-', combined_text, re.I)
    app_fee = f"₹{fee_match.group(1)}/- (SC/ST/PwBD व महिला वर्ग के लिए नियमानुसार छूट)" if fee_match else "श्रेणी के अनुसार (UR/OBC/SC/ST शुल्क विवरण PDF में देखें)"

    # 5. Pay Scale / Salary
    pay_match = re.search(r'(?:pay\s+level|level)[-\s]*(\d{1,2})', combined_text, re.I)
    salary_info = f"7th CPC Pay Level-{pay_match.group(1)} के अनुसार" if pay_match else "सरकारी वेतनमान (7th Pay Commission के अनुसार भत्ते सहित)"

    return {
        "total_posts": total_posts,
        "age_limit": age_limit,
        "qualification": qualification,
        "app_fee": app_fee,
        "salary_info": salary_info
    }

def build_clean_human_title(portal_info, raw_notice_title, pdf_text, category):
    short_org = portal_info["short_org"]
    cleaned_notice = sanitize_clean_text(raw_notice_title)
    cleaned_notice = re.sub(r'\.pdf$|\.html$\vert{}\.aspx$', '', cleaned_notice, flags=re.IGNORECASE)
    cleaned_notice = re.sub(r'\b(page\s*\d+|ym\d+|ao\d+|file\s*no|ref\s*no|corrigendum)\b', '', cleaned_notice, flags=re.IGNORECASE)
    cleaned_notice = re.sub(r'\s+', ' ', cleaned_notice).strip()

    combined_search_space = f"{cleaned_notice} {pdf_text[:4000]}"

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
        if clean_words:
            extracted_post = " ".join(clean_words[:4])
        else:
            extracted_post = "Various Posts"

    if short_org.lower() in extracted_post.lower():
        core_exam_name = extracted_post
    else:
        core_exam_name = f"{short_org} {extracted_post}".strip()

    dedup_words = []
    for w in core_exam_name.split():
        if w.lower() not in [x.lower() for x in dedup_words]:
            dedup_words.append(w)
    core_exam_name = " ".join(dedup_words)

    # Search Google for Trending SEO Title & Missing Date
    trending_titles, google_date = google_search_seo_research(f"{core_exam_name} {category}")

    short_exam_heading = f"{core_exam_name} {category} 2026"
    short_exam_heading = re.sub(r'2026\s+2026', '2026', short_exam_heading)

    student_details = extract_deep_pdf_details_for_student(combined_search_space)
    posts_badge = f" ({student_details['total_posts']})" if "Posts" in student_details["total_posts"] and category == "Govt Job" else ""

    if category == "Result":
        seo_title = f"{short_exam_heading} Out: Merit List PDF, Cut Off Marks और Roll Number यहाँ से चेक करें"
    elif category == "Admit Card":
        seo_title = f"{short_exam_heading} Download Link: Exam Date, City Intimation Slip और Hall Ticket निकालें"
    elif category == "Answer Key":
        seo_title = f"{short_exam_heading} Out: Response Sheet PDF डाउनलोड करें और Objection दर्ज करें"
    else:
        seo_title = f"{core_exam_name} Recruitment 2026{posts_badge}: Notification PDF, योग्यता, आयु सीमा और Online Form"
        short_exam_heading = f"{core_exam_name} Recruitment 2026"

    date_matches = re.findall(r'\b(\d{1,2}[./-]\d{1,2}[./-]2026|\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+2026)\b', combined_search_space, re.IGNORECASE)
    exam_date = date_matches[0] if date_matches else (google_date if google_date else "आधिकारिक अधिसूचना के अनुसार")
    last_date = date_matches[1] if len(date_matches) > 1 else "नोटिफिकेशन पीडीएफ में देखें"
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
        "trending_titles": trending_titles,
        "total_posts": student_details["total_posts"],
        "age_limit": student_details["age_limit"],
        "qualification": student_details["qualification"],
        "app_fee": student_details["app_fee"],
        "salary_info": student_details["salary_info"]
    }

# =====================================================================
# 6. PROFESSIONAL CONTENT WRITER & FORMER STUDENT EDITORIAL ENGINE
# =====================================================================
def generate_professional_1000_words_article(portal_info, research_data, target_url, category, source_text, doc_format):
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
    trending_ref = " | ".join(research_data["trending_titles"][:3]) if research_data["trending_titles"] else research_data["seo_title"]

    # 1. Optional Gemini AI Writer (If API Key is configured in GitHub Secrets)
    if GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key":
        try:
            api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
            prompt = f"""
            You are an expert SEO Content Writer and a former competitive exam student who knows exactly what job seekers need.
            Write a 1,100+ words comprehensive, well-structured HTML article in Hindi (mixed with natural English exam terms) for "{research_data['seo_title']}".
            
            Trending Google Search Titles for SEO Context: {trending_ref}
            Official Conducting Body: {org_name}
            Notice Title: {raw_notice}
            Category: {category}
            Extracted PDF Data: Total Posts: {total_posts}, Qualification: {qualification}, Age Limit: {age_limit}, Fee: {app_fee}, Salary: {salary_info}, Key Date: {exam_date}
            Direct Official PDF/Link: {target_url}
            Official Website: {portal_url}
            PDF Text Excerpt: {source_text[:3500]}

            Rules:
            - Write from the perspective of a helpful senior student guiding other students.
            - Use clean HTML tags (<h2>, <h3>, <p>, <ul>, <ol>, <table>). Do not use markdown ```html blocks.
            - Include an Overview Table, Important Dates & Fee Table, Eligibility/Process details, Step-by-Step Guide, Student Tips, Important Links Table, and 5 FAQs.
            """
            res = requests.post(api_url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=45)
            if res.status_code == 200:
                ai_text = sanitize_clean_text(res.json()["candidates"][0]["content"]["parts"][0]["text"])
                ai_text = re.sub(r'^```html\s*|\s*```$', '', ai_text, flags=re.I)
                if len(ai_text.split()) >= 750:
                    return research_data["seo_title"], ai_text
        except Exception:
            pass

    # 2. BUILT-IN SENIOR CONTENT WRITER & FORMER STUDENT ENGINE (Guaranteed 1,100+ Words Clean HTML)
    student_tip_box = f"""
    <div style="background-color:#eef6ff; border-left:5px solid #0056b3; padding:15px; margin:20px 0; border-radius:4px;">
        <strong>💡 एक्सपर्ट और सीनियर छात्र की सलाह (Student Desk Note):</strong> एक प्रतियोगी छात्र के रूप में हम समझते हैं कि जब कोई नया नोटिफिकेशन या रिजल्ट आता है, तो सही जानकारी और असली पीडीएफ लिंक ढूंढना कितना जरूरी होता है। किसी भी अधूरी खबर या सोशल मीडिया की अफवाह पर भरोसा करने के बजाय, इस लेख के अंत में दिए गए <strong>Direct Official {doc_format} Link</strong> से मूल फाइल डाउनलोड करें और हर नियम को खुद भी एक बार जरूर पढ़ें।
    </div>
    """

    if category == "Result":
        lead_html = f"""
        <p><strong>{org_name}</strong> ने प्रतियोगी परीक्षा में शामिल हुए लाखों उम्मीदवारों का इंतजार समाप्त करते हुए <strong>{core_exam}</strong> परीक्षा का आधिकारिक परिणाम (Result / Merit List) जारी कर दिया है। विभाग के आधिकारिक पोर्टल पर यह महत्वपूर्ण अपडेट <em>“{raw_notice}”</em> शीर्षक से उपलब्ध कराया गया है। वे सभी छात्र-छात्राएं जो इस भर्ती परीक्षा में उपस्थित हुए थे, वे अब आधिकारिक परिणाम {doc_format} या लॉगिन पोर्टल के माध्यम से अपना <strong>Roll Number</strong> खोजकर अपना <strong>Qualifying Status</strong> और अगले चरण की पात्रता जांच सकते हैं।</p>
        <p>जब हम महीनों की दिन-रात की पढ़ाई और प्रैक्टिस के बाद कोई सरकारी परीक्षा देते हैं, तो रिजल्ट के दिन दिल की धड़कनें बढ़ना स्वाभाविक है। इस समय एक छात्र को सबसे ज्यादा जरूरत सीधे पीडीएफ लिंक, कट-ऑफ (Cut-off Marks) की सही जानकारी और आगे होने वाले डॉक्यूमेंट वेरिफिकेशन (DV) की सटीक गाइड की होती है। आपकी इसी जरूरत को ध्यान में रखते हुए हमने इस लेख में रिजल्ट से जुड़ी हर छोटी-बड़ी जानकारी सरल भाषा में तैयार की है।</p>
        {student_tip_box}
        """

        sec2_heading = f"{short_exam} Released: मेरिट लिस्ट और आधिकारिक घोषणा का सार"
        sec2_body = f"""
        <p>इस चरण की परीक्षा में शामिल हुए सभी उम्मीदवार आधिकारिक {doc_format} में अपना roll number या registration number देखकर अपने चयन की स्थिति की पुष्टि कर सकते हैं। {doc_format} में नाम या roll number मिलने के बाद आगे की चयन प्रक्रिया (जैसे Document Verification, Skill Test, Physical Test या Medical Examination) के लिए <strong>{org_name}</strong> द्वारा जारी विस्तृत दिशा-निर्देशों को ध्यानपूर्वक पढ़ना अत्यंत आवश्यक है।</p>
        <p>विभाग द्वारा स्पष्ट किया गया है कि यह परिणाम पूर्णतः अनंतिम (Provisional) है और उम्मीदवारों का अंतिम चयन उनके मूल शैक्षणिक व आरक्षण संबंधी प्रमाण पत्रों के सफल सत्यापन के अधीन होगा। यदि किसी उम्मीदवार के दस्तावेज़ों में ऑनलाइन आवेदन फॉर्म की तुलना में कोई भिन्नता पाई जाती है, तो संबंधित भर्ती नियमों के तहत आगे की कार्यवाही की जाती है।</p>
        """

        sec3_heading = f"{core_exam} Cut-Off Marks, Normalization और Merit के नियम"
        sec3_body = f"""
        <p>अक्सर छात्रों के मन में यह सवाल रहता है कि उनके नंबर अच्छे होने के बावजूद मेरिट लिस्ट किस आधार पर बनी। {short_org} द्वारा कट-ऑफ और मेरिट सूची इन 4 प्रमुख वैज्ञानिक मापदंडों पर तैयार की जाती है:</p>
        <ul>
            <li><strong>कुल रिक्त पदों की संख्या (Total Vacancies):</strong> जिस श्रेणी (UR, OBC, SC, ST, EWS, PwBD) में जितने पद विज्ञापित किए गए हैं, उसी के अनुपात में अगले चरण के लिए उम्मीदवारों को शॉर्टलिस्ट किया जाता है।</li>
            <li><strong>परीक्षा का कठिनाई स्तर और उपस्थिति (Difficulty Level & Attendance):</strong> प्रश्न पत्र की जटिलता और परीक्षा में उपस्थित होने वाले कुल अभ्यर्थियों की संख्या का सीधा प्रभाव कट-ऑफ अंकों पर पड़ता है।</li>
            <li><strong>Normalization Process (सामान्यीकरण पद्धति):</strong> यदि परीक्षा एक से अधिक शिफ्ट या दिनों में आयोजित की गई हो, तो कठिन और सरल शिफ्ट के अंतर को बराबर करने के लिए Normalized Score के आधार पर मेरिट तैयार की जाती है।</li>
            <li><strong>Tie-Breaking Rules (बराबर अंक आने पर नियम):</strong> यदि दो या अधिक छात्रों के कुल अंक एक समान हो जाते हैं, तो मुख्य विषय के अंक, अधिक आयु (Date of Birth seniority) या नाम के वर्णमाला क्रम के अनुसार वरीयता तय की जाती है।</li>
        </ul>
        """

        how_to_heading = f"मोबाइल या कंप्यूटर से {short_exam} कैसे चेक करें? (Step-by-Step)"
        how_to_steps = f"""
        <p>अधिकतर छात्रों को परिणाम जारी होने के तुरंत बाद सर्वर स्लो होने या वेबसाइट पर सही टैब न मिलने से परेशानी होती है। आप नीचे दिए गए आसान चरणों का पालन करके बिना किसी रुकावट के अपना परिणाम देख सकते हैं:</p>
        <ol>
            <li>सबसे पहले <strong>{portal_name}</strong> (<a href="{portal_url}" target="_blank" rel="noopener">{portal_url}</a>) को अपने मोबाइल या कंप्यूटर ब्राउज़र में खोलें, या नीचे टेबल में दिए गए <strong>Direct Result Link</strong> पर क्लिक करें।</li>
            <li>Homepage पर पहुंचकर <strong>Results / Latest Announcements / Public Notices</strong> सेक्शन पर जाएं।</li>
            <li>वहाँ हाल ही में जारी किए गए <strong>“{raw_notice}”</strong> वाले आधिकारिक लिंक का चयन करें।</li>
            <li>यदि परिणाम मेरिट लिस्ट PDF के रूप में है, तो फाइल आपके डिवाइस में डाउनलोड हो जाएगी। यदि स्कोरकार्ड लॉगिन आधारित है, तो अपना <strong>Roll Number / Application ID</strong> और <strong>Date of Birth</strong> दर्ज करें।</li>
            <li>खुलने वाली Result PDF के search option (कंप्यूटर पर <code>Ctrl + F</code> या मोबाइल PDF Viewer के सर्च आइकॉन) में अपना सटीक <strong>Roll Number</strong> टाइप करें।</li>
            <li>सूची में अपना रोल नंबर मिलने पर उसके सामने दिए गए Category, Rank या Remarks को ध्यान से पढ़ें और भविष्य के संदर्भ के लिए PDF की एक प्रति सुरक्षित सेव कर लें।</li>
        </ol>
        """

        what_to_check_heading = "Result PDF और Scorecard में छात्र कौन-सी 6 बातें ध्यान से देखें?"
        what_to_check_list = """
        <p>Result PDF या ऑनलाइन स्कोरकार्ड खोलने के बाद प्रत्येक छात्र को निम्नलिखित विवरणों की जांच अवश्य करनी चाहिए:</p>
        <ul>
            <li><strong>Roll Number एवं Registration Number:</strong> केवल नाम के भरोसे न रहें, हमेशा अपने एडमिट कार्ड पर लिखे रोल नंबर के एक-एक अंक का मिलान करें।</li>
            <li><strong>Candidate Category & Sub-Category:</strong> PDF में आपकी आरक्षित या अनारक्षित श्रेणी (UR/OBC/SC/ST/EWS/Ex-Servicemen) का जो कोड लिखा है, उसे अपने आवेदन फॉर्म से मिलाएं।</li>
            <li><strong>Raw Marks एवं Normalized Score:</strong> जहाँ स्कोरकार्ड जारी किया गया हो, वहाँ अपने विषयवार अंक और नॉर्मलाइज्ड प्राप्तांक ध्यान से पढ़ें।</li>
            <li><strong>Merit Position / All India Rank:</strong> यदि मेरिट सूची में रैंक का उल्लेख किया गया है, तो अपनी कैटेगरी रैंक और ओवरऑल रैंक दोनों देखें।</li>
            <li><strong>Qualifying Status & Official Remarks:</strong> परिणाम के अंत में दिए गए निर्देशों (जैसे Qualified for Stage-II, Shortlisted for DV, या Provisional) का अर्थ समझें।</li>
            <li><strong>Category-wise Cut-Off Table:</strong> परिणाम नोटिस के नीचे दी गई श्रेणीवार कट-ऑफ तालिका से अपने अंकों की तुलना करें।</li>
        </ul>
        """

        next_stage_heading = f"{short_exam} में पास होने के बाद आगे की प्रक्रिया (Document Verification Checklist)"
        next_stage_body = f"""
        <p>परीक्षा में सफल घोषित किए गए सभी छात्रों को अगले चरण (Document Verification / Medical / Skill Test) के लिए अपनी फाइल अभी से तैयार कर लेनी चाहिए। {org_name} द्वारा सत्यापन के समय निम्नलिखित मूल दस्तावेज़ (Original Documents + 2 Sets Self-Attested Photocopies) मांगे जाते हैं:</p>
        <ul>
            <li><strong>शैक्षणिक प्रमाण पत्र:</strong> 10वीं (जन्मतिथि प्रमाण के लिए), 12वीं, स्नातक डिग्री/डिप्लोमा की मूल अंकतालिकाएं (Marksheets) और पासिंग सर्टिफिकेट।</li>
            <li><strong>आरक्षण संबंधी प्रमाण पत्र:</strong> केंद्र या राज्य के निर्धारित प्रारूप में बना वैध जाति प्रमाण पत्र (SC/ST/OBC-NCL) तथा निर्धारित वित्तीय वर्ष का EWS प्रमाण पत्र।</li>
            <li><strong>प्रवेश पत्र और आवेदन का प्रिंट:</strong> परीक्षा का मूल Admit Card और ऑनलाइन भरे गए Application Form की प्रिंट कॉपी।</li>
            <li><strong>वैध फोटो पहचान पत्र और फोटोग्राफ:</strong> मूल फोटो आईडी (जैसे पैन कार्ड, पासपोर्ट, वोटर आईडी या ड्राइविंग लाइसेंस) और 6 नवीनतम पासपोर्ट साइज रंगीन फोटो।</li>
        </ul>
        """
        link_label = f"Download {short_exam} Official PDF / Check Result"

    elif category == "Admit Card":
        lead_html = f"""
        <p><strong>{org_name}</strong> ने <strong>{core_exam}</strong> परीक्षा में शामिल होने जा रहे उम्मीदवारों के लिए आधिकारिक प्रवेश पत्र (Admit Card / Hall Ticket) और परीक्षा कार्यक्रम से जुड़ी महत्वपूर्ण सूचना जारी कर दी है। आधिकारिक परीक्षा पोर्टल पर यह अपडेट <em>“{raw_notice}”</em> शीर्षक से उपलब्ध है। जिन अभ्यर्थियों ने इस भर्ती परीक्षा के लिए सफलतापूर्वक ऑनलाइन आवेदन किया था, वे अब अपने Registration Number और जन्मतिथि (Date of Birth) की सहायता से अपना प्रवेश पत्र डाउनलोड कर सकते हैं।</p>
        <p>एक छात्र के रूप में जब परीक्षा की तारीख करीब आती है, तो सबसे पहले यही जानना जरूरी होता है कि हमारा एग्जाम किस शहर (Exam City) में है, कौन-सी शिफ्ट में है और सेंटर पर कितने बजे रिपोर्ट करना है। बिना वैध प्रिंटेड Hall Ticket और मूल फोटो पहचान पत्र (Original Photo ID Proof) के किसी भी परीक्षार्थी को परीक्षा केंद्र के भीतर प्रवेश की अनुमति नहीं दी जाती है।</p>
        {student_tip_box}
        """

        sec2_heading = f"{short_exam} Released: Exam City, Shift Timing और मुख्य जानकारी"
        sec2_body = f"""
        <p>{org_name} द्वारा जारी इस आधिकारिक अपडेट के माध्यम से उम्मीदवार अपनी सटीक परीक्षा तिथि (Exam Date), परीक्षा की पाली (Shift Timing), केंद्र पर रिपोर्टिंग का समय और परीक्षा शहर (Exam City & Centre Address) की जानकारी देख सकते हैं। कई बड़ी परीक्षाओं में विभाग द्वारा पहले Exam City Intimation Slip जारी की जाती है और परीक्षा तिथि से 3 से 4 दिन पूर्व पूर्ण प्रवेश पत्र उपलब्ध कराया जाता है।</p>
        <p>सभी छात्रों को सलाह दी जाती है कि वे परीक्षा के अंतिम दिन का इंतज़ार न करें। अंतिम समय में सर्वर पर भारी ट्रैफिक होने के कारण डाउनलोड में दिक्कत आ सकती है, इसलिए समय रहते अपना {short_exam} डाउनलोड करें और उसकी कम से कम 2 साफ प्रतियां (A4 साइज पेपर पर) प्रिंट करवाकर रख लें।</p>
        """

        sec3_heading = f"{core_exam} Exam Shift Guidelines और Reporting Time के सख्त नियम"
        sec3_body = f"""
        <p>परीक्षा के दिन केंद्र पर किसी भी प्रकार की घबराहट या गेट बंद होने की समस्या से बचने के लिए छात्रों को इन नियमों का विशेष ध्यान रखना चाहिए:</p>
        <ul>
            <li><strong>Reporting Time पर पहुंचना:</strong> एडमिट कार्ड पर अंकित रिपोर्टिंग समय पर केंद्र पर पहुंचना अनिवार्य है ताकि तलाशी (Frisking), बायोमेट्रिक उपस्थिति (Biometric Thumb & Photo Capture) और दस्तावेज़ जांच समय पर पूरी हो सके।</li>
            <li><strong>Gate Closing Time (गेट बंद होने का समय):</strong> परीक्षा शुरू होने से पहले निर्धारित Gate Closing Time के बाद केंद्र का मुख्य द्वार बंद कर दिया जाता है और इसके 1 मिनट बाद भी किसी भी परिस्थिति में प्रवेश नहीं दिया जाता।</li>
            <li><strong>केंद्र की लोकेशन पहले से जांचें:</strong> यदि आपका परीक्षा केंद्र दूसरे शहर या अपरिचित क्षेत्र में है, तो परीक्षा से एक दिन पहले गूगल मैप्स या स्थानीय माध्यम से केंद्र की दूरी और रास्ते की जानकारी अवश्य प्राप्त कर लें।</li>
        </ul>
        """

        how_to_heading = f"मोबाइल से {short_exam} कैसे डाउनलोड करें? (Step-by-Step)"
        how_to_steps = f"""
        <p>उम्मीदवार अपने मोबाइल या कंप्यूटर से नीचे दिए गए आसान चरणों का पालन करके चंद मिनटों में अपना आधिकारिक प्रवेश पत्र डाउनलोड कर सकते हैं:</p>
        <ol>
            <li>सबसे पहले <strong>{portal_name}</strong> (<a href="{portal_url}" target="_blank" rel="noopener">{portal_url}</a>) खोलें या नीचे दी गई तालिका में मौजूद <strong>Direct Admit Card Link</strong> पर क्लिक करें।</li>
            <li>Homepage पर उपलब्ध <strong>Admit Card / Download Call Letter / Candidate Login</strong> सेक्शन पर क्लिक करें।</li>
            <li>वहाँ दिखाई दे रहे <strong>“{raw_notice}”</strong> वाले आधिकारिक लिंक को चुनें।</li>
            <li>लॉगिन विंडो खुलने पर अपना <strong>Registration Number / Roll Number</strong> और पासवर्ड के रूप में अपनी <strong>Date of Birth (DD/MM/YYYY)</strong> सही-सही दर्ज करें।</li>
            <li>स्क्रीन पर प्रदर्शित होने वाला Security Captcha Code बॉक्स में भरें और <strong>Submit / Download Admit Card</strong> बटन पर क्लिक करें।</li>
            <li>आपका प्रवेश पत्र स्क्रीन पर खुल जाएगा। सभी विवरण जाँचने के बाद PDF फाइल को सेव करें और A4 साइज पेपर पर साफ प्रिंटआउट निकाल लें।</li>
        </ol>
        <p><strong>यदि Registration Number भूल गए हों:</strong> लॉगिन पेज पर दिए गए 'Forgot Registration ID' विकल्प का उपयोग करें या अपने रजिस्टर्ड ईमेल इनबॉक्स और मोबाइल SMS में पुराने आवेदन संदेश को सर्च करें।</p>
        """

        what_to_check_heading = "Admit Card डाउनलोड करने के बाद छात्र कौन-सी जानकारी अवश्य मिलाएं?"
        what_to_check_list = """
        <p>प्रवेश पत्र डाउनलोड करने के तुरंत बाद प्रत्येक छात्र को उस पर छपे सभी विवरणों का मिलान अपने मूल पहचान पत्र से करना चाहिए:</p>
        <ul>
            <li><strong>Candidate Name & Father/Mother Name:</strong> सुनिश्चित करें कि आपके नाम की स्पेलिंग आपके मूल फोटो पहचान पत्र (PAN Card / Driving License / Voter ID) से पूरी तरह मेल खाती हो।</li>
            <li><strong>Roll Number & Application Number:</strong> कंप्यूटर आधारित परीक्षा (CBT) या OMR शीट में भरने के लिए यह नंबर सबसे महत्वपूर्ण है।</li>
            <li><strong>Date of Birth & Category:</strong> आपकी जन्मतिथि और श्रेणी (UR/OBC/SC/ST/EWS) बिल्कुल सही दर्ज होनी चाहिए।</li>
            <li><strong>Exam Date, Shift & Timing:</strong> परीक्षा की तारीख, रिपोर्टिंग समय और गेट क्लोजिंग टाइम को ध्यान से पढ़ें।</li>
            <li><strong>Exam Centre Name, Code & Full Address:</strong> परीक्षा केंद्र का पूरा पता, सेंटर कोड और लैंडमार्क ध्यानपूर्वक देखें।</li>
            <li><strong>Photograph, Signature & Barcode:</strong> एडमिट कार्ड पर आपकी फोटो, हस्ताक्षर और बारकोड साफ-साफ छपे होने चाहिए।</li>
        </ul>
        """

        next_stage_heading = "Exam Hall में साथ ले जाने वाले जरूरी दस्तावेज़ और वर्जित वस्तुएं"
        next_stage_body = """
        <p>परीक्षा केंद्र पर प्रवेश के समय सुरक्षा जांच के दौरान छात्रों के पास निम्नलिखित दस्तावेज़ होने अनिवार्य हैं:</p>
        <ul>
            <li><strong>Printed Admit Card:</strong> आधिकारिक पोर्टल से डाउनलोड किए गए प्रवेश पत्र की साफ प्रिंट कॉपी।</li>
            <li><strong>Original Valid Photo ID Proof:</strong> पैन कार्ड, वोटर आईडी, ड्राइविंग लाइसेंस, पासपोर्ट या सरकार द्वारा जारी मूल (Original) फोटो पहचान पत्र (जिसमें नाम और जन्मतिथि एडमिट कार्ड से मैच हो)। फोटोकॉपी या मोबाइल में फोटो मान्य नहीं होती।</li>
            <li><strong>Passport Size Photographs:</strong> ऑनलाइन आवेदन फॉर्म में अपलोड की गई फोटो जैसी 2 नवीनतम पासपोर्ट साइज रंगीन फोटो।</li>
            <li><strong>सख्त वर्जित वस्तुएं (Prohibited Items):</strong> परीक्षा कक्ष में मोबाइल फोन, स्मार्टवॉच, डिजिटल घड़ी, ब्लूटूथ, कैलकुलेटर, ईयरफोन, ज्वेलरी, बेल्ट या किसी भी प्रकार के इलेक्ट्रॉनिक गैजेट ले जाना सख्त मना है।</li>
        </ul>
        """
        link_label = f"Download {short_exam} Direct Link"

    elif category == "Answer Key":
        lead_html = f"""
        <p><strong>{org_name}</strong> ने हाल ही में आयोजित की गई <strong>{core_exam}</strong> परीक्षा की आधिकारिक उत्तर कुंजी (Answer Key / Response Sheet) जारी कर दी है। आधिकारिक परीक्षा पोर्टल पर यह महत्वपूर्ण अपडेट <em>“{raw_notice}”</em> शीर्षक से उपलब्ध कराया गया है। परीक्षा में उपस्थित हुए सभी छात्र-छात्राएं अब आधिकारिक पोर्टल पर लॉगिन करके या जारी की गई PDF के माध्यम से अपने उत्तरों का मिलान कर सकते हैं और अपने संभावित प्राप्तांक (Expected Raw Score) की सटीक गणना कर सकते हैं।</p>
        <p>एक परीक्षार्थी के नजरिए से देखें तो आंसर की आने से हमें रिजल्ट से पहले ही यह साफ अंदाजा लग जाता है कि हमारे कितने सवाल सही हुए हैं और क्या हमें अगले चरण (Mains / Physical / DV) की तैयारी शुरू कर देनी चाहिए। इसके अलावा, यदि आयोग ने किसी सवाल का उत्तर गलत दिया है, तो छात्र निर्धारित समय में अपनी आपत्ति (Objection) भी दर्ज करा सकते हैं।</p>
        {student_tip_box}
        """

        sec2_heading = f"{short_exam} Released: Response Sheet और Objection Window की जानकारी"
        sec2_body = f"""
        <p>आधिकारिक पोर्टल पर जारी किए गए इस लिंक के माध्यम से अभ्यर्थी अपने द्वारा परीक्षा में टिक किए गए विकल्प (Chosen Option) और बोर्ड द्वारा सही माने गए आधिकारिक उत्तर (Correct Answer) दोनों को एक साथ देख सकते हैं।</p>
        <p>छात्रों को विशेष रूप से ध्यान देना चाहिए कि ऑनलाइन रिस्पॉन्स शीट और आपत्ति दर्ज करने का लिंक पोर्टल पर केवल 3 से 5 दिनों के लिए ही सक्रिय रहता है। समय-सीमा समाप्त होने के बाद रिस्पॉन्स शीट डाउनलोड करने की सुविधा बंद कर दी जाती है, इसलिए आज ही अपनी उत्तर कुंजी की PDF कॉपी अपने फोन या कंप्यूटर में सेव कर लें।</p>
        """

        sec3_heading = f"{core_exam} Score Calculation: नेगेटिव मार्किंग हटाकर अपने नंबर कैसे जोड़ें?"
        sec3_body = f"""
        <p>उत्तर कुंजी डाउनलोड करने के बाद अपने कुल संभावित अंक (Raw Score) निकालने के लिए छात्रों को परीक्षा की आधिकारिक Marking Scheme का पालन करना चाहिए:</p>
        <ul>
            <li><strong>सही उत्तरों की गिनती (Total Correct Answers):</strong> सबसे पहले अपनी पूरी शीट में उन सभी प्रश्नों की संख्या गिनें जिनका उत्तर आधिकारिक Answer Key से बिल्कुल मेल खाता है।</li>
            <li><strong>गलत उत्तर और Negative Marking:</strong> अब उन प्रश्नों को गिनें जिनका उत्तर गलत हुआ है। यदि परीक्षा में नकारात्मक अंकन (जैसे 1/4 यानी 0.25 अंक या 1/3 अंक) लागू है, तो कुल गलत उत्तरों के निर्धारित अंक घटाएं।</li>
            <li><strong>छोड़े गए प्रश्न (Unattempted Questions):</strong> जिन प्रश्नों का आपने परीक्षा में कोई उत्तर नहीं दिया है, उनके लिए न तो कोई अंक जोड़ा जाता है और न ही कोई नेगेटिव मार्किंग होती है।</li>
            <li><strong>कुल स्कोर निकालने का सूत्र (Formula):</strong> <code>कुल प्राप्तांक = (सही उत्तर × प्रति प्रश्न अंक) − (गलत उत्तर × नेगेटिव मार्किंग अंक)</code>।</li>
        </ul>
        """

        how_to_heading = f"मोबाइल से {short_exam} और Response Sheet कैसे डाउनलोड करें?"
        how_to_steps = f"""
        <p>अपनी शिफ्ट की आधिकारिक उत्तर कुंजी और रिस्पॉन्स शीट डाउनलोड करने के लिए नीचे दिए गए चरणों का पालन करें:</p>
        <ol>
            <li>सबसे पहले <strong>{portal_name}</strong> (<a href="{portal_url}" target="_blank" rel="noopener">{portal_url}</a>) खोलें या नीचे टेबल में दिए गए <strong>Direct Answer Key Link</strong> पर क्लिक करें।</li>
            <li>Homepage पर <strong>Answer Key / Candidate Response Sheet</strong> सेक्शन में जाएं।</li>
            <li>वहाँ उपलब्ध <strong>“{raw_notice}”</strong> वाले आधिकारिक लिंक पर क्लिक करें।</li>
            <li>लॉगिन पेज खुलने पर अपना <strong>Roll Number / Registration ID</strong> और <strong>Password / Date of Birth</strong> दर्ज करें।</li>
            <li>डैशबोर्ड पर <em>'Click here to generate Question Paper & Answer Key'</em> या संबंधित PDF लिंक पर क्लिक करें।</li>
            <li>स्क्रीन पर खुलने वाली उत्तर कुंजी से अपने उत्तरों का मिलान करें और ऊपर <strong>Print / Save as PDF</strong> दबाकर फाइल सुरक्षित कर लें।</li>
        </ol>
        """

        what_to_check_heading = "Answer Key PDF और Response Sheet में छात्र कौन-सी बातें देखें?"
        what_to_check_list = """
        <p>ऑनलाइन CBT परीक्षा या OMR उत्तर कुंजी का मिलान करते समय छात्रों को निम्नलिखित तकनीकी विवरणों को ध्यान से देखना चाहिए:</p>
        <ul>
            <li><strong>Question ID & Option ID:</strong> ऑनलाइन परीक्षा में प्रत्येक छात्र के प्रश्नों का क्रम अलग होता है, इसलिए केवल प्रश्न संख्या के बजाय हमेशा <strong>Question ID</strong> और <strong>Option ID</strong> से ही मिलान करें।</li>
            <li><strong>Status (Answered / Not Answered / Marked for Review):</strong> जांचें कि आपका उत्तर सिस्टम में सफलतापूर्वक सेव हुआ था या नहीं।</li>
            <li><strong>Chosen Option vs Official Correct Option:</strong> आपके द्वारा चुने गए विकल्प और हरे रंग (या टिक निशान) से दर्शाए गए आधिकारिक सही उत्तर की तुलना करें।</li>
            <li><strong>Shift Date & Paper Set Code:</strong> यदि उत्तर कुंजी मास्टर PDF के रूप में है, तो अपनी सही परीक्षा तिथि, शिफ्ट और पेपर सेट (Set A/B/C/D) का मिलान करें।</li>
        </ul>
        """

        next_stage_heading = "गलत प्रश्न या उत्तर पर ऑनलाइन आपत्ति (Objection) कैसे दर्ज करें?"
        next_stage_body = f"""
        <p>यदि आपको पूर्ण विश्वास है कि किसी प्रश्न का आधिकारिक उत्तर गलत दिया गया है या प्रश्न के सभी विकल्प गलत हैं, तो आप {portal_name} के माध्यम से अपनी आपत्ति (Challenge) दर्ज करा सकते हैं:</p>
        <ul>
            <li><strong>प्रामाणिक पुस्तक का साक्ष्य (Authentic Proof):</strong> आपत्ति स्वीकार किए जाने के लिए NCERT, सरकारी प्रकाशन या मानक संदर्भ पुस्तक (Standard Textbook) के संबंधित पन्ने की साफ PDF/फोटो अपलोड करना अनिवार्य होता है।</li>
            <li><strong>प्रति प्रश्न निर्धारित शुल्क:</strong> विभाग द्वारा तय किया गया प्रति प्रश्न ऑनलाइन शुल्क जमा करना होता है। कई आयोगों में आपत्ति सही पाए जाने पर यह शुल्क छात्र के बैंक खाते में वापस (Refund) कर दिया जाता है।</li>
            <li><strong>Final Answer Key का निर्माण:</strong> विषय विशेषज्ञों की समिति द्वारा सभी आपत्तियों की जांच करने के बाद ही अंतिम उत्तर कुंजी (Final Answer Key) और रिजल्ट जारी किया जाता है।</li>
        </ul>
        """
        link_label = f"Download {short_exam} PDF / Response Sheet Link"

    else:  # Govt Job (Fresh Recruitment / Vacancy Notification)
        lead_html = f"""
        <p><strong>{org_name}</strong> ने सरकारी नौकरी की तैयारी कर रहे युवाओं के लिए <strong>{core_exam}</strong> भर्ती प्रक्रिया का आधिकारिक विज्ञापन (Official Notification PDF) जारी कर दिया है। आधिकारिक भर्ती पोर्टल पर यह अधिसूचना <em>“{raw_notice}”</em> शीर्षक के अंतर्गत उपलब्ध कराई गई है। केंद्र और राज्य सरकार के अधीन प्रतिष्ठित पदों पर स्थायी नौकरी पाने का सपना देख रहे योग्य छात्रों के लिए यह एक बेहद शानदार अवसर है। इच्छुक अभ्यर्थी आधिकारिक नोटिफिकेशन {doc_format} के माध्यम से रिक्त पदों का विवरण, पात्रता शर्तें और ऑनलाइन आवेदन प्रक्रिया की जांच कर सकते हैं।</p>
        <p>एक छात्र के नजरिए से जब भी कोई नई सरकारी भर्ती आती है, तो सबसे पहले हमारे मन में यही सवाल उठते हैं—<strong>इसमें कुल कितनी वैकेंसी हैं? क्या मेरी योग्यता और उम्र इसके लिए फिट है? फॉर्म भरने की फीस और सिलेक्शन प्रोसेस क्या रहेगा?</strong> एक प्रोफेशनल गाइड की तरह हमने आधिकारिक पीडीएफ का गहराई से अध्ययन करके आपके इन सभी सवालों का सटीक जवाब इस लेख में तैयार किया है।</p>
        {student_tip_box}
        """

        sec2_heading = f"{short_exam} Notification Out: पदों का विवरण और भर्ती की मुख्य बातें"
        sec2_body = f"""
        <p>इस भर्ती अभियान के अंतर्गत योग्य और मेधावी उम्मीदवारों से ऑनलाइन माध्यम (Online Mode) द्वारा आवेदन आमंत्रित किए गए हैं। पीडीएफ विश्लेषण के अनुसार, इस भर्ती में <strong>कुल पद: {total_posts}</strong> के लिए प्रक्रिया शुरू की गई है। {org_name} ने स्पष्ट किया है कि आवेदन करने वाले प्रत्येक छात्र को विज्ञापित कट-ऑफ तिथि (Crucial Date for Eligibility) तक सभी आवश्यक शैक्षणिक और आयु संबंधी शर्तें पूरी करनी होंगी।</p>
        <p>आरक्षित वर्गों (SC, ST, OBC-NCL, EWS, Ex-Servicemen और PwBD) के उम्मीदवारों को सरकारी नियमों के अनुसार रिक्त पदों में आरक्षण तथा ऊपरी आयु सीमा व आवेदन शुल्क में विशेष छूट प्रदान की जाएगी। श्रेणीवार (Category-wise) सीटों की सटीक संख्या देखने के लिए छात्र नीचे दिए गए सीधे लिंक से आधिकारिक नोटिफिकेशन डाउनलोड कर सकते हैं।</p>
        """

        sec3_heading = f"{core_exam} Eligibility Criteria: शैक्षणिक योग्यता, आयु सीमा, शुल्क और वेतनमान"
        sec3_body = f"""
        <p>ऑनलाइन आवेदन फॉर्म भरने से पहले प्रत्येक छात्र को यह जांच लेना चाहिए कि वह {short_org} द्वारा निर्धारित निम्नलिखित पात्रता मापदंडों को पूरा करता है:</p>
        <ul>
            <li><strong>Educational Qualification (शैक्षणिक योग्यता):</strong> आधिकारिक पीडीएफ के अनुसार आवेदक के पास किसी मान्यता प्राप्त बोर्ड, संस्थान या विश्वविद्यालय से <strong>{qualification}</strong> होना अनिवार्य है। (अलग-अलग पदों के अनुसार विशेष योग्यता का विवरण आधिकारिक पीडीएफ में अवश्य देखें)।</li>
            <li><strong>Age Limit & Relaxation (आयु सीमा एवं छूट):</strong> इस भर्ती के लिए निर्धारित आयु सीमा <strong>{age_limit}</strong> है। सरकारी नियमानुसार OBC-NCL वर्ग को 3 वर्ष, SC/ST वर्ग को 5 वर्ष और दिव्यांगजन (PwBD) उम्मीदवारों को 10 से 15 वर्ष तक की ऊपरी आयु छूट देय होती है।</li>
            <li><strong>Application Fee (आवेदन शुल्क):</strong> उम्मीदवारों के लिए परीक्षा शुल्क <strong>{app_fee}</strong> निर्धारित है। शुल्क का भुगतान डेबिट कार्ड, क्रेडिट कार्ड, नेट बैंकिंग या UPI के माध्यम से ऑनलाइन किया जा सकता है।</li>
            <li><strong>Pay Scale / Salary (वेतनमान):</strong> चयनित होने वाले उम्मीदवारों को <strong>{salary_info}</strong> मासिक वेतन, महंगाई भत्ता (DA), मकान किराया भत्ता (HRA) और अन्य सरकारी सुविधाएं प्रदान की जाएंगी।</li>
            <li><strong>Selection Process (चयन प्रक्रिया):</strong> इस भर्ती में अंतिम चयन लिखित परीक्षा (CBT / OMR Exam), कौशल या शारीरिक परीक्षा (Skill Test / PET / PST - यदि लागू हो), दस्तावेज़ सत्यापन (Document Verification) और मेडिकल टेस्ट के आधार पर किया जाएगा।</li>
        </ul>
        """

        how_to_heading = f"{short_exam} का Online Form कैसे भरें? (Step-by-Step छात्र गाइड)"
        how_to_steps = f"""
        <p>फॉर्म भरते समय एक छोटी सी स्पेलिंग या कैटेगरी की गलती भी बाद में परेशानी खड़ी कर सकती है। इसलिए छात्र अंतिम तिथि का इंतज़ार किए बिना नीचे दिए गए चरणों का पालन करके सावधानीपूर्वक अपना फॉर्म भरें:</p>
        <ol>
            <li>सबसे पहले नीचे दी गई तालिका से <strong>Official Notification PDF</strong> डाउनलोड करें और अपनी योग्यता व सीटों का विवरण ध्यान से पढ़ लें।</li>
            <li>अब <strong>{portal_name}</strong> (<a href="{portal_url}" target="_blank" rel="noopener">{portal_url}</a>) की आधिकारिक वेबसाइट खोलें।</li>
            <li>Homepage पर उपलब्ध <strong>Recruitment / Online Application / One-Time Registration (OTR)</strong> सेक्शन में जाएं।</li>
            <li>अपने सक्रिय मोबाइल नंबर और वैध ईमेल आईडी की मदद से <strong>New Registration</strong> पूरा करें।</li>
            <li>प्राप्त Registration ID और Password से लॉगिन करें और फॉर्म में अपना नाम, माता-पिता का नाम और जन्मतिथि बिल्कुल <strong>10वीं (Matric) की मार्कशीट</strong> के अनुसार ही दर्ज करें।</li>
            <li>नोटिफिकेशन में निर्धारित साइज (KB) के अनुसार अपनी ताज़ा पासपोर्ट साइज फोटो, स्पष्ट हस्ताक्षर और मांगे गए प्रमाण पत्र अपलोड करें।</li>
            <li>फीस जमा करने से पहले पूरे फॉर्म का <strong>Preview</strong> कम से कम दो बार चेक करें, फिर ऑनलाइन शुल्क जमा करके <strong>Final Submit</strong> करें और आवेदन फॉर्म का प्रिंटआउट (PDF) अपने पास सुरक्षित रख लें।</li>
        </ol>
        """

        what_to_check_heading = "Notification PDF में फॉर्म भरने से पहले छात्र कौन-सी 5 बातें जरूर देखें?"
        what_to_check_list = """
        <p>एक अनुभवी छात्र के तौर पर हम सलाह देते हैं कि फॉर्म सबमिट करने से पहले आधिकारिक PDF में ये 5 बिंदु जरूर चेक करें:</p>
        <ul>
            <li><strong>Post Name & Category-wise Vacancy:</strong> जिस पद के लिए आप आवेदन कर रहे हैं, उसमें आपकी अपनी श्रेणी (UR/OBC/SC/ST/EWS) में कितनी सीटें हैं।</li>
            <li><strong>Crucial Date for Qualification & Certificates:</strong> आपकी डिग्री/मार्कशीट और जाति/EWS सर्टिफिकेट किस तारीख (Cut-off Date) से पहले का बना होना चाहिए।</li>
            <li><strong>Photo & Signature Rules:</strong> फोटो का बैकग्राउंड (सफेद या हल्का रंग) और हस्ताक्षर करने के पेन (काली या नीली स्याही) से जुड़े नियम।</li>
            <li><strong>Exam Pattern, Syllabus & Negative Marking:</strong> लिखित परीक्षा में कौन-कौन से विषय आएंगे, कितने नंबर का पेपर होगा और नेगेटिव मार्किंग कितनी है।</li>
            <li><strong>Correction Window Dates:</strong> फॉर्म सबमिट होने के बाद यदि कोई गलती हो जाए, तो क्या विभाग द्वारा सुधार (Correction Window) का मौका दिया जाएगा या नहीं।</li>
        </ul>
        """

        next_stage_heading = f"{short_exam} ऑनलाइन आवेदन के लिए जरूरी दस्तावेज़ों की सूची"
        next_stage_body = """
        <p>ऑनलाइन आवेदन शुरू करने से पहले छात्रों को निम्नलिखित दस्तावेज़ अपने पास स्कैन करके तैयार रखने चाहिए:</p>
        <ul>
            <li><strong>10वीं (Matriculation) का प्रमाण पत्र:</strong> नाम और जन्मतिथि के सटीक मिलान के लिए।</li>
            <li><strong>आवश्यक शैक्षणिक अंकतालिकाएं:</strong> 12वीं, स्नातक या डिप्लोमा के रोल नंबर, उत्तीर्ण वर्ष और प्राप्तांक प्रतिशत का विवरण।</li>
            <li><strong>वैध फोटो पहचान पत्र:</strong> पैन कार्ड, वोटर आईडी, पासपोर्ट या ड्राइविंग लाइसेंस आदि का नंबर।</li>
            <li><strong>आरक्षण एवं मूल निवास प्रमाण पत्र:</strong> SC/ST/OBC-NCL/EWS और दिव्यांगता प्रमाण पत्र (यदि लागू हो)।</li>
            <li><strong>फोटोग्राफ और सिग्नेचर:</strong> साफ बैकग्राउंड वाली नवीनतम रंगीन फोटो और सफेद कागज पर किए गए स्पष्ट हस्ताक्षर।</li>
        </ul>
        """
        link_label = f"Download {short_exam} Notification PDF / Apply Online"

    # Assemble the Complete 1,100+ Words Clean HTML Article
    full_html = f"""
    {lead_html}

    <h2>{short_exam}: संक्षिप्त विवरण (Overview Table)</h2>
    <p>छात्रों के समय की बचत के लिए हमने इस आधिकारिक अपडेट (Official Notification) से संबंधित सभी प्रमुख बिंदुओं का संक्षिप्त सार नीचे दी गई तालिका में प्रस्तुत किया है:</p>
    <table border="1" cellpadding="10" cellspacing="0" style="width:100%; border-collapse:collapse; margin:15px 0 25px 0;">
        <thead>
            <tr style="background-color:#f8f9fa;">
                <th style="width:38%; text-align:left;">विवरण (Particulars)</th>
                <th style="width:62%; text-align:left;">आधिकारिक जानकारी (Official Details)</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td><strong>भर्ती बोर्ड / विभाग (Conducting Authority)</strong></td>
                <td>{org_name}</td>
            </tr>
            <tr>
                <td><strong>परीक्षा / भर्ती का नाम (Exam / Post Name)</strong></td>
                <td>{core_exam}</td>
            </tr>
            <tr>
                <td><strong>आधिकारिक नोटिस शीर्षक (Notice Title)</strong></td>
                <td>{raw_notice}</td>
            </tr>
            <tr>
                <td><strong>विज्ञापन संख्या (Advt / Ref No.)</strong></td>
                <td>{advt_no}</td>
            </tr>
            <tr>
                <td><strong>अपडेट कैटेगरी (Update Category)</strong></td>
                <td>Official {category}</td>
            </tr>
            <tr>
                <td><strong>कुल पद (Total Vacancies)</strong></td>
                <td>{total_posts}</td>
            </tr>
            <tr>
                <td><strong>शैक्षणिक योग्यता (Qualification)</strong></td>
                <td>{qualification}</td>
            </tr>
            <tr>
                <td><strong>आयु सीमा (Age Limit)</strong></td>
                <td>{age_limit}</td>
            </tr>
            <tr>
                <td><strong>आवेदन शुल्क (Application Fee)</strong></td>
                <td>{app_fee}</td>
            </tr>
            <tr>
                <td><strong>वेतनमान (Pay Scale / Salary)</strong></td>
                <td>{salary_info}</td>
            </tr>
            <tr>
                <td><strong>महत्वपूर्ण तिथि (Key / Exam Date)</strong></td>
                <td>{exam_date}</td>
            </tr>
            <tr>
                <td><strong>अंतिम तिथि (Last Date / Schedule)</strong></td>
                <td>{last_date}</td>
            </tr>
            <tr>
                <td><strong>अपडेट जारी होने की तिथि</strong></td>
                <td>{release_date}</td>
            </tr>
            <tr>
                <td><strong>दस्तावेज़ का प्रारूप (Format)</strong></td>
                <td>{doc_format} (Online Mode)</td>
            </tr>
            <tr>
                <td><strong>आधिकारिक वेबसाइट (Official Website)</strong></td>
                <td><a href="{portal_url}" target="_blank" rel="noopener">{portal_name}</a></td>
            </tr>
        </tbody>
    </table>

    <h2>{sec2_heading}</h2>
    {sec2_body}

    <h2>{sec3_heading}</h2>
    {sec3_body}

    <h2>{how_to_heading}</h2>
    {how_to_steps}

    <h2>{what_to_check_heading}</h2>
    {what_to_check_list}

    <h2>{next_stage_heading}</h2>
    {next_stage_body}

    <h2>{short_exam}: Important Official Links</h2>
    <p>अभ्यर्थियों को किसी भी असुरक्षित या थर्ड-पार्टी स्रोत पर निर्भर रहने की आवश्यकता नहीं है। नीचे दी गई तालिका में सीधे आधिकारिक सरकारी पोर्टल के प्रमाणित लिंक उपलब्ध कराए गए हैं:</p>
    <table border="1" cellpadding="10" cellspacing="0" style="width:100%; border-collapse:collapse; margin:15px 0 25px 0;">
        <thead>
            <tr style="background-color:#f8f9fa;">
                <th style="width:55%; text-align:left;">महत्वपूर्ण आधिकारिक लिंक (Important Official Link)</th>
                <th style="width:45%; text-align:left;">डायरेक्ट एक्शन लिंक (Direct Action Link)</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td><strong>{link_label}</strong></td>
                <td><a href="{target_url}" target="_blank" rel="noopener"><strong>Click Here for Official {category} ({doc_format})</strong></a></td>
            </tr>
            <tr>
                <td><strong>Official Website ({short_org})</strong></td>
                <td><a href="{portal_url}" target="_blank" rel="noopener"><strong>Visit {portal_name}</strong></a></td>
            </tr>
        </tbody>
    </table>

    <h2>अक्सर पूछे जाने वाले प्रश्न (FAQs)</h2>
    <p><strong>1. {short_exam} आधिकारिक रूप से कहाँ जारी किया गया है?</strong><br>
    उत्तर: यह आधिकारिक अपडेट {org_name} द्वारा अपने आधिकारिक पोर्टल ({portal_name}) पर “{raw_notice}” शीर्षक से जारी किया गया है।</p>

    <p><strong>2. मैं {short_exam} की आधिकारिक PDF या डायरेक्ट लिंक कैसे खोल सकता हूँ?</strong><br>
    उत्तर: आप इस लेख में ऊपर दी गई 'Important Official Links' तालिका में मौजूद सीधे लिंक पर क्लिक करके आधिकारिक {doc_format} या वेबपेज खोल सकते हैं।</p>

    <p><strong>3. {core_exam} के लिए आवश्यक योग्यता और आयु सीमा क्या रखी गई है?</strong><br>
    उत्तर: पीडीएफ विवरण के अनुसार इसके लिए शैक्षणिक योग्यता '{qualification}' और आयु सीमा '{age_limit}' निर्धारित है। विस्तृत जानकारी के लिए आधिकारिक पीडीएफ अवश्य पढ़ें।</p>

    <p><strong>4. यदि आधिकारिक वेबसाइट खुलने में समय ले रही हो तो छात्र क्या करें?</strong><br>
    उत्तर: नया आधिकारिक अपडेट आने पर एक साथ हजारों छात्रों के विजिट करने से सर्वर कभी-कभी धीमा हो जाता है। ऐसी स्थिति में कुछ मिनट प्रतीक्षा करें और पेज को रिफ्रेश करके पुनः प्रयास करें।</p>

    <p><strong>5. {core_exam} से जुड़े आगामी अपडेट्स और नोटिस कहाँ मिलेंगे?</strong><br>
    उत्तर: इस परीक्षा के अगले चरणों से जुड़ी सभी आधिकारिक सूचनाएं समय-समय पर {portal_name} ({portal_url}) और हमारी वेबसाइट पर प्रकाशित की जाएंगी।</p>
    """

    return research_data["seo_title"], full_html.strip()

# =====================================================================
# 7. WORDPRESS DRAFT PUBLISHER
# =====================================================================
def save_or_update_wordpress_draft(title, html_content, existing_wp_id=0):
    preview_path = os.path.join(DATA_FOLDER, "latest_govtvibhag_style_draft.html")
    try:
        with open(preview_path, "w", encoding="utf-8") as f:
            f.write(f"<h1>{title}</h1>\n{html_content}")
    except Exception:
        pass

    if not WP_USERNAME or "your_wp_username" in WP_USERNAME or "your-wordpress-site.com" in WP_SITE_URL:
        print(f"   [!] WordPress credentials missing! Saved Local Preview: {preview_path}")
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
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }
        payload = {
            "title": title,
            "content": html_content,
            "status": "draft"
        }
        res = requests.post(api_url, json=payload, headers=headers, timeout=25)
        if res.status_code in [200, 201]:
            wp_id = res.json().get("id", 0)
            print(f"   [SUCCESS] Professional Draft Created in WordPress (ID: {wp_id}): {title}")
            return wp_id
        else:
            print(f"   [!] WordPress API Status: {res.status_code} - {res.text[:150]}")
    except Exception as e:
        print(f"   [!] WordPress Error: {e}")
    return 0

# =====================================================================
# 8. SMART SINGLE-RUN SCANNER FOR GITHUB ACTIONS 24/7 AUTOMATION
# =====================================================================
def run_hourly_scanner():
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    current_check_str = datetime.datetime.now().strftime("%d %b %Y, %I:%M %p")
    print(f"\n[HOURLY SCAN - {current_check_str}] Checking all 39 official portals...")

    new_found_total = 0

    for portal_info in GOVT_PORTALS:
        portal = portal_info["url"]
        portal_already_synced = is_portal_synced(portal)

        try:
            response = requests.get(portal, headers=headers, timeout=15, verify=False)
            if response.status_code != 200:
                continue

            soup = BeautifulSoup(response.text, "html.parser")
            for menu_tag in soup.find_all(["nav", "header", "footer"]):
                menu_tag.decompose()

            links = soup.find_all("a", href=True)

            # STEP A: IF PORTAL WAS NEVER LOCKED BEFORE, LOCK ALL CURRENT LINKS ON THE PAGE!
            if not portal_already_synced:
                locked_count = 0
                for link in links:
                    href = link["href"].strip()
                    link_text = sanitize_clean_text(link.get_text(" ", strip=True))
                    if not href or len(link_text) < 4:
                        continue
                    full_target_url = urljoin(portal, href)
                    n_key = normalize_notice_key(portal, link_text)
                    mark_as_processed(portal, full_target_url, n_key, link_text[:100], "OLD_LOCKED", "IGNORED_OLD", 0, "")
                    locked_count += 1
                mark_portal_synced(portal)
                print(f"   [Initial Lock] {portal_info['portal_name']}: Locked {locked_count} existing links.")
                continue

            # STEP B: PORTAL IS ALREADY LOCKED -> CHECK ONLY FOR NEW & 100% FRESH NOTICES
            processed_count = 0
            for link in links:
                href = link["href"].strip()
                link_text = sanitize_clean_text(link.get_text(" ", strip=True))
                full_target_url = urljoin(portal, href)

                if not is_genuine_notification(link_text, full_target_url):
                    continue

                n_key = normalize_notice_key(portal, link_text)

                if is_already_processed(full_target_url, notice_key=n_key):
                    continue

                source_text, doc_format, last_mod, pdf_date = extract_source_and_metadata(full_target_url)
                content_hash = hashlib.md5(source_text.encode("utf-8", errors="ignore")).hexdigest() if source_text else ""

                combined_info = (link_text + " " + href).lower()
                category = determine_category(combined_info)
                research_data = build_clean_human_title(portal_info, link_text, source_text, category)
                proposed_seo_title = research_data["seo_title"]

                if is_already_processed(full_target_url, notice_key=n_key, seo_title=proposed_seo_title, content_hash=content_hash):
                    mark_as_processed(portal, full_target_url, n_key, link_text[:100], "DUPLICATE_IGNORED", "IGNORED_DUP", 0, content_hash)
                    continue

                is_fresh, reason = verify_is_truly_fresh(link_text, source_text, last_mod, pdf_date)
                if not is_fresh:
                    print(f"   [Rejected Old Notice] {link_text[:50]}... -> {reason}")
                    mark_as_processed(portal, full_target_url, n_key, link_text[:100], f"OLD_REJECTED ({reason})", "IGNORED_OLD", 0, content_hash)
                    continue

                print(f"   [FRESH {category.upper()} FOUND!] {link_text[:65]}...")
                print(f"   [PROFESSIONAL TITLE] -> {proposed_seo_title}")

                seo_title, article_html = generate_professional_1000_words_article(
                    portal_info, research_data, full_target_url, category, source_text, doc_format
                )

                wp_id = save_or_update_wordpress_draft(seo_title, article_html)
                mark_as_processed(portal, full_target_url, n_key, link_text, seo_title, category, wp_id, content_hash)

                processed_count += 1
                new_found_total += 1
                if processed_count >= 2:
                    break

        except Exception:
            print(f"   [Skip] Portal currently slow: {portal_info['portal_name']}")

        time.sleep(0.5)

    if new_found_total == 0:
        print("   [STATUS] Scan complete. Kisi bhi portal par abhi koi naya fresh update nahi aaya hai.")
    else:
        print(f"   [STATUS] Scan complete! Total {new_found_total} naye professional articles WordPress Draft mein bheje gaye.")

if __name__ == "__main__":
    disable_cmd_quickedit()
    print("=========================================================================")
    print("   GOVTVIBHAG.COM PROFESSIONAL EDITORIAL BOT v7.0 (CLOUD EDITION)        ")
    print("   - Length: 1,000 to 1,200+ Words Student-Centric Editorial Format      ")
    print("   - Deep PDF Extraction (Vacancies, Age, Fee, Salary, Qualification)    ")
    print("   - Google Trending SEO Title Researcher & 4-Layer Anti-Duplicate       ")
    print("=========================================================================")

    init_db()
    bot_start_dt = ensure_bot_start_time()
    print(f"   [ACTIVE] Monitoring fresh updates since: {bot_start_dt.strftime('%d %b %Y, %I:%M %p')}")

    # GitHub Actions ke liye Single Run (Taaki 2 minute mein kaam karke सफलतापूर्वक बंद हो जाए)
    run_hourly_scanner()
