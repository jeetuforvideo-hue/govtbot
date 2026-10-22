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
WP_SITE_URL = os.getenv("WP_SITE_URL", "https://govtvibhag.com").strip()
WP_USERNAME = os.getenv("WP_USERNAME", "your_wp_username").strip()
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD", "your_wp_application_password").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "your_gemini_api_key").strip()

DB_NAME = "govt_vibhag_master.db"
DATA_FOLDER = "scraped_data_cache"

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
# 2. 39 OFFICIAL GOVERNMENT PORTALS (Direct Recruitment & Notice Pages)
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
    "screen reader", "skip to main", "sitemap", "feedback", "accessibility", "citizen charter"
]

GENERIC_MENU_TITLES = [
    "recruitment", "recruitments", "result", "results", "admit card", "admit cards",
    "answer key", "answer keys", "notification", "notifications", "advertisements",
    "recruitment advertisements", "latest news", "what's new", "apply online",
    "cut-off marks", "cutoff marks", "merit list", "career", "careers", "vacancies",
    "vacancy", "examinations", "exams", "home", "click here", "download", "view", "pdf"
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

# =====================================================================
# 4. SMART NOTIFICATION FILTER & CONTEXT EXTRACTOR (FIXED)
# =====================================================================
def extract_smart_link_text(link_tag):
    """
    Agar link ke andar sirf 'Click Here' ya 'PDF' likha hai, toh uski Table Row (<tr>) ya Parent (<li>/<div>)
    ka pura text uthata hai taaki asli notification title kabhi miss na ho!
    """
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

    # Relaxed length check so real notices aren't dropped
    if len(clean_text) < 12 or len(clean_text.split()) < 3:
        return False

    if lower_text in GENERIC_MENU_TITLES:
        return False

    if any(bad in lower_text for bad in IGNORE_KEYWORDS):
        return False

    if lower_url.startswith("javascript:") or lower_url.startswith("mailto:") or full_url.endswith("#"):
        return False

    # Reject only if an older year is explicitly in the title AND 2026 is not
    if re.search(r'\b(2015|2016|2017|2018|2019|2020|2021|2022|2023|2024)\b', lower_text) and "2026" not in lower_text and "2025" not in lower_text:
        return False

    all_valid_keywords = JOB_KEYWORDS + ADMIT_CARD_KEYWORDS + ANSWER_KEY_KEYWORDS + RESULT_KEYWORDS
    is_pdf = ".pdf" in lower_url

    has_keyword = any(k in lower_text or k in lower_url for k in all_valid_keywords)
    has_exam_code = bool(re.search(
        r'(2026|2025-26|\d{1,3}/2026|advt|stage|tier|norcet|cet|cgl|chsl|mts|gd|ntpc|alp|je|constable|si|asi|clerk|po|so|officer|assistant|engineer|teacher|tgt|pgt|prt|stenographer|group\s*[a-d]|grade\s*[a-d])',
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

    # Allow up to 10 days window for PDF creation (since Govt signs PDFs a few days before uploading)
    if pdf_internal_date:
        days_old = (today - pdf_internal_date).days
        if days_old > 10:
            return False, f"Old PDF Metadata Date ({pdf_internal_date})"

    if last_modified_header:
        try:
            mod_dt = parsedate_to_datetime(last_modified_header).replace(tzinfo=None)
            if (today - mod_dt.date()).days > 10:
                return False, f"Old Server File ({mod_dt.date()})"
        except Exception:
            pass

    if re.search(r'\b(2018|2019|2020|2021|2022|2023|2024)\b', raw_title.lower()) and "2026" not in raw_title.lower():
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
    vac_match = re.search(r'(?:total\s+vacanc(?:y|ies)|total\s+posts?|कुल\s+पद)\s*[:=-]?\s*(\d{1,6})', combined_text, re.I)
    if not vac_match:
        vac_match = re.search(r'\b(\d{2,6})\s+(?:vacancies|posts)\b', combined_text, re.I)
    total_posts = f"{vac_match.group(1)} Posts" if vac_match else "आधिकारिक नोटिफिकेशन के अनुसार (Check PDF)"

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
    qualification = ", ".join(quals[:3]) if quals else "संबंधित पद के अनुसार (आधिकारिक PDF में देखें)"

    fee_match = re.search(r'(?:rs\.?|₹|inr)\s*(\d{2,4})\s*/-', combined_text, re.I)
    app_fee = f"₹{fee_match.group(1)}/- (SC/ST/PwBD व महिला वर्ग के लिए नियमानुसार छूट)" if fee_match else "श्रेणी के अनुसार (UR/OBC/SC/ST शुल्क विवरण PDF में देखें)"

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
    cleaned_notice = re.sub(r'\.pdf$|\.html$|\.aspx$', '', cleaned_notice, flags=re.IGNORECASE)
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
        "app_fee": app_fee if 'app_fee' in locals() else student_details["app_fee"],
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
        <p>विभाग द्वारा स्पष्ट किया गया है कि यह परिणाम पूर्णतः अनंतिम (Provisional) है और उम्मीदवारों का अंतिम चयन उनके मूल शैक्षणिक व आरक्षण संबंधी प्रमाण पत्रों के सफल सत्यापन के अधीन होगा।</p>
        """
        sec3_heading = f"{core_exam} Cut-Off Marks, Normalization और Merit के नियम"
        sec3_body = f"""
        <p>{short_org} द्वारा कट-ऑफ और मेरिट सूची इन 4 प्रमुख वैज्ञानिक मापदंडों पर तैयार की जाती है:</p>
        <ul>
            <li><strong>कुल रिक्त पदों की संख्या (Total Vacancies):</strong> जिस श्रेणी (UR, OBC, SC, ST, EWS, PwBD) में जितने पद विज्ञापित किए गए हैं, उसी के अनुपात में उम्मीदवारों को शॉर्टलिस्ट किया जाता है।</li>
            <li><strong>परीक्षा का कठिनाई स्तर और उपस्थिति:</strong> प्रश्न पत्र की जटिलता और परीक्षा में उपस्थित होने वाले कुल अभ्यर्थियों की संख्या का सीधा प्रभाव कट-ऑफ अंकों पर पड़ता है।</li>
            <li><strong>Normalization Process:</strong> यदि परीक्षा एक से अधिक शिफ्ट में आयोजित की गई हो, तो Normalized Score के आधार पर मेरिट तैयार की जाती है।</li>
            <li><strong>Tie-Breaking Rules:</strong> बराबर अंक आने पर मुख्य विषय के अंक या अधिक आयु (Date of Birth seniority) के अनुसार वरीयता तय की जाती है।</li>
        </ul>
        """
        how_to_heading = f"मोबाइल या कंप्यूटर से {short_exam} कैसे चेक करें? (Step-by-Step)"
        how_to_steps = f"""
        <ol>
            <li>सबसे पहले <strong>{portal_name}</strong> (<a href="{portal_url}" target="_blank" rel="noopener">{portal_url}</a>) को खोलें या नीचे दिए गए <strong>Direct Result Link</strong> पर क्लिक करें।</li>
            <li>Homepage पर <strong>Results / Latest Announcements</strong> सेक्शन पर जाएं।</li>
            <li>वहाँ हाल ही में जारी किए गए <strong>“{raw_notice}”</strong> वाले आधिकारिक लिंक का चयन करें।</li>
            <li>खुलने वाली Result PDF में <code>Ctrl + F</code> या सर्च आइकॉन से अपना <strong>Roll Number</strong> टाइप करें और PDF सेव कर लें।</li>
        </ol>
        """
        what_to_check_heading = "Result PDF और Scorecard में छात्र कौन-सी बातें ध्यान से देखें?"
        what_to_check_list = """
        <ul>
            <li><strong>Roll Number एवं Registration Number:</strong> अपने एडमिट कार्ड पर लिखे रोल नंबर के एक-एक अंक का मिलान करें।</li>
            <li><strong>Candidate Category:</strong> PDF में आपकी श्रेणी (UR/OBC/SC/ST/EWS) का जो कोड लिखा है, उसे मिलाएं।</li>
            <li><strong>Qualifying Status & Cut-Off Table:</strong> परिणाम नोटिस के नीचे दी गई श्रेणीवार कट-ऑफ तालिका से अपने अंकों की तुलना करें।</li>
        </ul>
        """
        next_stage_heading = f"{short_exam} में पास होने के बाद आगे की प्रक्रिया (Document Verification)"
        next_stage_body = f"""
        <p>सफल घोषित किए गए सभी छात्रों को अगले चरण (Document Verification) के लिए 10वीं, 12वीं, स्नातक की मूल अंकतालिकाएं, वैध जाति/EWS प्रमाण पत्र, एडमिट कार्ड और मूल फोटो पहचान पत्र (PAN Card / Voter ID / Driving License) तैयार रखने चाहिए।</p>
        """
        link_label = f"Download {short_exam} Official PDF / Check Result"

    elif category == "Admit Card":
        lead_html = f"""
        <p><strong>{org_name}</strong> ने <strong>{core_exam}</strong> परीक्षा में शामिल होने जा रहे उम्मीदवारों के लिए आधिकारिक प्रवेश पत्र (Admit Card / Hall Ticket) और परीक्षा तिथि से जुड़ी महत्वपूर्ण सूचना जारी कर दी है। आधिकारिक पोर्टल पर यह अपडेट <em>“{raw_notice}”</em> शीर्षक से उपलब्ध है।</p>
        {student_tip_box}
        """
        sec2_heading = f"{short_exam} Released: Exam City, Shift Timing और मुख्य जानकारी"
        sec2_body = f"<p>{org_name} द्वारा जारी इस आधिकारिक अपडेट के माध्यम से उम्मीदवार अपनी सटीक परीक्षा तिथि (Exam Date), परीक्षा की पाली (Shift Timing), रिपोर्टिंग समय और परीक्षा शहर (Exam City & Centre Address) की जानकारी देख सकते हैं।</p>"
        sec3_heading = f"{core_exam} Exam Shift Guidelines और Reporting Time के नियम"
        sec3_body = "<ul><li>एडमिट कार्ड पर अंकित रिपोर्टिंग समय पर केंद्र पर पहुंचना अनिवार्य है।</li><li>Gate Closing Time के बाद किसी भी परिस्थिति में प्रवेश नहीं दिया जाता।</li></ul>"
        how_to_heading = f"मोबाइल से {short_exam} कैसे डाउनलोड करें?"
        how_to_steps = f"<ol><li><strong>{portal_name}</strong> खोलें या नीचे दिए गए Direct Link पर क्लिक करें।</li><li>अपना Registration Number और Date of Birth दर्ज करके एडमिट कार्ड डाउनलोड करें और A4 साइज पेपर पर प्रिंट निकाल लें।</li></ol>"
        what_to_check_heading = "Admit Card डाउनलोड करने के बाद क्या चेक करें?"
        what_to_check_list = "<ul><li>अपना नाम, रोल नंबर, जन्मतिथि, परीक्षा तिथि, शिफ्ट और परीक्षा केंद्र का पूरा पता ध्यान से मिलाएं।</li></ul>"
        next_stage_heading = "Exam Hall में साथ ले जाने वाले जरूरी दस्तावेज़"
        next_stage_body = "<p>प्रिंटेड एडमिट कार्ड के साथ मूल फोटो पहचान पत्र (पैन कार्ड, वोटर आईडी, ड्राइविंग लाइसेंस या पासपोर्ट) और 2 पासपोर्ट साइज फोटो अवश्य साथ ले जाएं।</p>"
        link_label = f"Download {short_exam} Direct Link"

    elif category == "Answer Key":
        lead_html = f"""
        <p><strong>{org_name}</strong> ने हाल ही में आयोजित की गई <strong>{core_exam}</strong> परीक्षा की आधिकारिक उत्तर कुंजी (Answer Key / Response Sheet) जारी कर दी है। आधिकारिक पोर्टल पर यह अपडेट <em>“{raw_notice}”</em> शीर्षक से उपलब्ध है।</p>
        {student_tip_box}
        """
        sec2_heading = f"{short_exam} Released: Response Sheet और Objection Window"
        sec2_body = "<p>अभ्यर्थी अपने द्वारा टिक किए गए विकल्प और बोर्ड द्वारा सही माने गए आधिकारिक उत्तर दोनों का मिलान कर सकते हैं और किसी प्रश्न पर संदेह होने पर निर्धारित समय में आपत्ति (Objection) दर्ज कर सकते हैं।</p>"
        sec3_heading = f"{core_exam} Score Calculation कैसे करें?"
        sec3_body = "<p>कुल प्राप्तांक = (सही उत्तर × प्रति प्रश्न अंक) − (गलत उत्तर × नेगेटिव मार्किंग अंक)।</p>"
        how_to_heading = f"मोबाइल से {short_exam} कैसे डाउनलोड करें?"
        how_to_steps = f"<ol><li>नीचे दिए गए Direct Link पर क्लिक करें।</li><li>Roll Number और Password/DOB से लॉगिन करके अपनी Response Sheet PDF सेव कर लें।</li></ol>"
        what_to_check_heading = "Answer Key में कौन-सी बातें देखें?"
        what_to_check_list = "<ul><li>Question ID, Option ID और आधिकारिक सही विकल्प का ध्यानपूर्वक मिलान करें।</li></ul>"
        next_stage_heading = "गलत प्रश्न या उत्तर पर आपत्ति (Objection) कैसे दर्ज करें?"
        next_stage_body = f"<p>यदि किसी प्रश्न का उत्तर गलत है, तो {portal_name} पर लॉगिन करके मानक पुस्तक (NCERT/Standard Book) के प्रूफ के साथ ऑनलाइन आपत्ति दर्ज कराएं।</p>"
        link_label = f"Download {short_exam} PDF / Response Sheet Link"

    else:
        lead_html = f"""
        <p><strong>{org_name}</strong> ने सरकारी नौकरी की तैयारी कर रहे युवाओं के लिए <strong>{core_exam}</strong> भर्ती प्रक्रिया का आधिकारिक विज्ञापन (Official Notification PDF) जारी कर दिया है। आधिकारिक भर्ती पोर्टल पर यह अधिसूचना <em>“{raw_notice}”</em> शीर्षक के अंतर्गत उपलब्ध कराई गई है।</p>
        {student_tip_box}
        """
        sec2_heading = f"{short_exam} Notification Out: पदों का विवरण और मुख्य बातें"
        sec2_body = f"<p>पीडीएफ विश्लेषण के अनुसार, इस भर्ती में <strong>कुल पद: {total_posts}</strong> के लिए प्रक्रिया शुरू की गई है। आरक्षित वर्गों (SC, ST, OBC-NCL, EWS, PwBD) को सरकारी नियमों के अनुसार छूट प्रदान की जाएगी।</p>"
        sec3_heading = f"{core_exam} Eligibility Criteria: योग्यता, आयु सीमा, शुल्क और वेतनमान"
        sec3_body = f"""
        <ul>
            <li><strong>शैक्षणिक योग्यता:</strong> {qualification}</li>
            <li><strong>आयु सीमा:</strong> {age_limit}</li>
            <li><strong>आवेदन शुल्क:</strong> {app_fee}</li>
            <li><strong>वेतनमान:</strong> {salary_info}</li>
        </ul>
        """
        how_to_heading = f"{short_exam} का Online Form कैसे भरें?"
        how_to_steps = f"<ol><li>नीचे दिए गए लिंक से Official Notification PDF डाउनलोड करके पढ़ें।</li><li>{portal_name} पर जाकर OTR/New Registration करें, दस्तावेज़ अपलोड करें और फीस जमा करके फाइनल सबमिट करें।</li></ol>"
        what_to_check_heading = "Notification PDF में फॉर्म भरने से पहले क्या देखें?"
        what_to_check_list = "<ul><li>Category-wise Vacancy, Crucial Cut-off Date, Exam Pattern और Syllabus ध्यान से पढ़ें।</li></ul>"
        next_stage_heading = f"{short_exam} ऑनलाइन आवेदन के लिए जरूरी दस्तावेज़"
        next_stage_body = "<p>10वीं/12वीं/स्नातक की मार्कशीट, वैध फोटो आईडी (पैन कार्ड, वोटर आईडी या ड्राइविंग लाइसेंस), जाति/EWS सर्टिफिकेट, नवीनतम फोटो और सिग्नेचर स्कैन करके तैयार रखें।</p>"
        link_label = f"Download {short_exam} Notification PDF / Apply Online"

    full_html = f"""
    {lead_html}
    <h2>{short_exam}: संक्षिप्त विवरण (Overview Table)</h2>
    <table border="1" cellpadding="10" cellspacing="0" style="width:100%; border-collapse:collapse; margin:15px 0 25px 0;">
        <tbody>
            <tr><td><strong>भर्ती बोर्ड / विभाग</strong></td><td>{org_name}</td></tr>
            <tr><td><strong>परीक्षा / भर्ती का नाम</strong></td><td>{core_exam}</td></tr>
            <tr><td><strong>आधिकारिक नोटिस शीर्षक</strong></td><td>{raw_notice}</td></tr>
            <tr><td><strong>विज्ञापन संख्या</strong></td><td>{advt_no}</td></tr>
            <tr><td><strong>अपडेट कैटेगरी</strong></td><td>Official {category}</td></tr>
            <tr><td><strong>कुल पद</strong></td><td>{total_posts}</td></tr>
            <tr><td><strong>शैक्षणिक योग्यता</strong></td><td>{qualification}</td></tr>
            <tr><td><strong>आयु सीमा</strong></td><td>{age_limit}</td></tr>
            <tr><td><strong>आवेदन शुल्क</strong></td><td>{app_fee}</td></tr>
            <tr><td><strong>वेतनमान</strong></td><td>{salary_info}</td></tr>
            <tr><td><strong>महत्वपूर्ण तिथि</strong></td><td>{exam_date}</td></tr>
            <tr><td><strong>अंतिम तिथि</strong></td><td>{last_date}</td></tr>
            <tr><td><strong>आधिकारिक वेबसाइट</strong></td><td><a href="{portal_url}" target="_blank" rel="noopener">{portal_name}</a></td></tr>
        </tbody>
    </table>
    <h2>{sec2_heading}</h2>{sec2_body}
    <h2>{sec3_heading}</h2>{sec3_body}
    <h2>{how_to_heading}</h2>{how_to_steps}
    <h2>{what_to_check_heading}</h2>{what_to_check_list}
    <h2>{next_stage_heading}</h2>{next_stage_body}
    <h2>{short_exam}: Important Official Links</h2>
    <table border="1" cellpadding="10" cellspacing="0" style="width:100%; border-collapse:collapse; margin:15px 0 25px 0;">
        <tbody>
            <tr><td><strong>{link_label}</strong></td><td><a href="{target_url}" target="_blank" rel="noopener"><strong>Click Here for Official {category} ({doc_format})</strong></a></td></tr>
            <tr><td><strong>Official Website ({short_org})</strong></td><td><a href="{portal_url}" target="_blank" rel="noopener"><strong>Visit {portal_name}</strong></a></td></tr>
        </tbody>
    </table>
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
        print(f"    [!] WordPress credentials missing! Saved Local Preview: {preview_path}")
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
            print(f"    [SUCCESS] Professional Draft Created in WordPress (ID: {wp_id}): {title}")
            return wp_id
        else:
            print(f"    [!] WordPress API Status: {res.status_code} - {res.text[:150]}")
    except Exception as e:
        print(f"    [!] WordPress Error: {e}")
    return 0

# =====================================================================
# 8. SMART SCANNER WITH JS-PORTAL RSS FALLBACK
# =====================================================================
def fetch_fallback_updates_for_js_portal(portal_info):
    """
    Jin portals (jaise SSC, AIIMS, RRB) par JavaScript ki wajah se direct HTML links nahi aate,
    unke liye fresh 24-hour updates discover karta hai.
    """
    discovered = []
    short_org = portal_info["short_org"]
    portal_url = portal_info["url"]
    try:
        q = f'"{short_org}" (recruitment OR result OR "admit card" OR "answer key" OR notification) when:2d'
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

def run_hourly_scanner():
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

        # STEP A: Initial Sync Lock
        if not portal_already_synced:
            for link_text, full_target_url in candidate_links:
                n_key = normalize_notice_key(portal, link_text)
                mark_as_processed(portal, full_target_url, n_key, link_text[:100], "OLD_LOCKED", "IGNORED_OLD", 0, "")
            mark_portal_synced(portal)
            print(f"   [{idx:02d}/{total_portals}] [Initial Lock] {portal_name}: Locked {len(candidate_links)} existing links.")
            continue

        # Add Fallback Discovery if JS portal returned very few notice links
        if len(candidate_links) < 15:
            candidate_links.extend(fetch_fallback_updates_for_js_portal(portal_info))

        # STEP B: Check for New Genuine Notices
        processed_count = 0
        for link_text, full_target_url in candidate_links:
            if not is_genuine_notification(link_text, full_target_url):
                continue

            n_key = normalize_notice_key(portal, link_text)
            if is_already_processed(full_target_url if full_target_url != portal else f"{portal}#{n_key}", notice_key=n_key):
                continue

            source_text, doc_format, last_mod, pdf_date = extract_source_and_metadata(full_target_url)
            content_hash = hashlib.md5((link_text + source_text[:500]).encode("utf-8", errors="ignore")).hexdigest()

            combined_info = (link_text + " " + full_target_url).lower()
            category = determine_category(combined_info)
            research_data = build_clean_human_title(portal_info, link_text, source_text, category)
            proposed_seo_title = research_data["seo_title"]

            unique_target = full_target_url if full_target_url != portal else f"{portal}#{n_key}"

            if is_already_processed(unique_target, notice_key=n_key, seo_title=proposed_seo_title, content_hash=content_hash):
                mark_as_processed(portal, unique_target, n_key, link_text[:100], "DUPLICATE_IGNORED", "IGNORED_DUP", 0, content_hash)
                continue

            is_fresh, reason = verify_is_truly_fresh(link_text, source_text, last_mod, pdf_date)
            if not is_fresh:
                print(f"   [{idx:02d}/{total_portals}] [Rejected Old Notice] {portal_name}: {link_text[:45]}... -> {reason}")
                mark_as_processed(portal, unique_target, n_key, link_text[:100], f"OLD_REJECTED ({reason})", "IGNORED_OLD", 0, content_hash)
                continue

            print(f"   [{idx:02d}/{total_portals}] [FRESH {category.upper()} FOUND!] {portal_name}: {link_text[:60]}...")
            print(f"       [PROFESSIONAL TITLE] -> {proposed_seo_title}")

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
            print(f"   [{idx:02d}/{total_portals}] [Checked OK] {portal_name} (Scanned {len(candidate_links)} items - No new update)")

        time.sleep(0.3)

    if new_found_total == 0:
        print("\n   [STATUS] Scan complete. Sabhi 39 portals check ho gaye, abhi koi naya fresh update nahi aaya hai.")
    else:
        print(f"\n   [STATUS] Scan complete! Total {new_found_total} naye professional articles WordPress Draft mein bheje gaye.")

if __name__ == "__main__":
    disable_cmd_quickedit()
    print("=========================================================================")
    print("   GOVTVIBHAG.COM PROFESSIONAL EDITORIAL BOT v8.0 (TURBO EDITION)        ")
    print("=========================================================================")
    init_db()
    bot_start_dt = ensure_bot_start_time()
    print(f"   [ACTIVE] Monitoring fresh updates since: {bot_start_dt.strftime('%d %b %Y, %I:%M %p')}")
    run_hourly_scanner()
