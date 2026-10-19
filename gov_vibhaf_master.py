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
from urllib.parse import urljoin, urlparse, urlunparse
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
# 1. WORDPRESS & AI CONFIGURATION (Apni Details Yahan Bharein)
# =====================================================================
WP_SITE_URL = "https://govtvibhag.com"           # Apni website ka URL
WP_USERNAME = "your_wp_username"                 # Apna WordPress Username
WP_APP_PASSWORD = "your_wp_application_password" # Apna Application Password
GEMINI_API_KEY = "your_gemini_api_key"           # Optional: Gemini API Key

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
            # Disable QuickEdit (0x0040) so mouse click never pauses the bot
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
    {"url": "https://www.joinindiannavy.gov.in", "org": "Indian Navy (har Kaam Desh Ke Naam)", "short_org": "Indian Navy", "portal_name": "Join Indian Navy Official Portal"},
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
        # Remove fragments (#) and normalize scheme/netloc/path
        clean_path = re.sub(r'/+$', '', p.path)
        return urlunparse((p.scheme.lower(), p.netloc.lower(), clean_path, '', p.query, ''))
    except Exception:
        return url_str.strip()

def normalize_notice_key(portal_url, text_str):
    # Creates a unique fingerprint for any notice title on a portal so 2 links with same text never duplicate
    alpha_num = re.sub(r'[^a-z0-9]+', '', text_str.lower())
    return f"{urlparse(portal_url).netloc.lower()}_{alpha_num[:60]}"

def sanitize_clean_text(text_str):
    """
    Removes all broken font symbols, question-mark boxes (??? / \ufffd), CID codes, and non-printable characters.
    """
    if not text_str:
        return ""
    # Remove replacement chars and control chars
    cleaned = re.sub(r'[\ufffd\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', ' ', text_str)
    # Remove sequences of question marks or garbled symbol clusters
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

    # Check 1: Exact or Normalized URL
    cursor.execute("SELECT 1 FROM processed_posts WHERE target_url = ? OR target_url = ?", (target_url, norm_url))
    if cursor.fetchone() is not None:
        conn.close()
        return True

    # Check 2: Same Notice Title Key on the same portal (prevents 2 links of same notice from writing twice)
    if notice_key:
        cursor.execute("SELECT 1 FROM processed_posts WHERE notice_key = ?", (notice_key,))
        if cursor.fetchone() is not None:
            conn.close()
            return True

    # Check 3: Same Generated SEO Title (prevents writing the exact same article title twice!)
    if seo_title and not seo_title.startswith("OLD_") and not seo_title.startswith("DUPLICATE_"):
        cursor.execute("SELECT 1 FROM processed_posts WHERE seo_title = ?", (seo_title,))
        if cursor.fetchone() is not None:
            conn.close()
            return True

    # Check 4: Same PDF Content Hash
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

    # Reject if notice explicitly mentions old years (2015-2025) without 2026
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
    """
    Downloads PDF/Webpage and also extracts internal PDF Creation/Modification Date
    so old PDFs can NEVER fool the bot!
    """
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

            # Check internal PDF creation/modification date metadata (e.g., D:20260214...)
            meta = doc.metadata or {}
            raw_pdf_date = meta.get("modDate") or meta.get("creationDate") or ""
            m_date = re.search(r'D:(\d{4})(\d{2})(\d{2})', str(raw_pdf_date))
            if m_date:
                try:
                    pdf_internal_date = datetime.date(int(m_date.group(1)), int(m_date.group(2)), int(m_date.group(3)))
                except Exception:
                    pass

            text = ""
            for page in range(min(8, len(doc))):
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
    """
    4-Layer Freshness Check: Rejects any PDF/Notice created before the last 2 days.
    """
    today = datetime.datetime.now().date()
    combined = f"{raw_title} {source_text[:1500]}".lower()

    # Layer 1: Internal PDF Creation/Modification Date Check (Most Reliable!)
    if pdf_internal_date:
        days_old = (today - pdf_internal_date).days
        if days_old > 2:
            return False, f"Old PDF Metadata Date ({pdf_internal_date})"

    # Layer 2: HTTP Server Last-Modified Header Check
    if last_modified_header:
        try:
            mod_dt = parsedate_to_datetime(last_modified_header).replace(tzinfo=None)
            if (today - mod_dt.date()).days > 2:
                return False, f"Old Server File ({mod_dt.date()})"
        except Exception:
            pass

    # Layer 3: Reject old months of 2026 (Jan to Sept 2026) when current month is Oct 2026
    old_months_pattern = r'\b(january|february|march|april|may|june|july|august|september|jan|feb|mar|apr|jun|jul|aug|sep|sept)\s*[-/,]?\s*2026\b'
    if today.month >= 10 and re.search(old_months_pattern, combined) and "october" not in combined and "oct" not in combined:
        return False, "Old Month Session (Jan-Sep 2026)"

    # Layer 4: Reject if old years (2018-2025) appear in the notice title
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
# 5. CLEAN HUMAN TITLE & DATA RESEARCHER
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

def build_clean_human_title(portal_info, raw_notice_title, pdf_text, category):
    short_org = portal_info["short_org"]
    cleaned_notice = sanitize_clean_text(raw_notice_title)
    cleaned_notice = re.sub(r'\.pdf$|\.html$|\.aspx$', '', cleaned_notice, flags=re.IGNORECASE)
    cleaned_notice = re.sub(r'\b(page\s*\d+|ym\d+|ao\d+|file\s*no|ref\s*no|corrigendum)\b', '', cleaned_notice, flags=re.IGNORECASE)
    cleaned_notice = re.sub(r'\s+', ' ', cleaned_notice).strip()

    combined_search_space = f"{cleaned_notice} {pdf_text[:1000]}"

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

    short_exam_heading = f"{core_exam_name} {category} 2026"
    short_exam_heading = re.sub(r'2026\s+2026', '2026', short_exam_heading)

    if category == "Result":
        seo_title = f"{short_exam_heading}: Mains/Final Result PDF और Shortlisted Candidates"
    elif category == "Admit Card":
        seo_title = f"{short_exam_heading}: Exam Date, Hall Ticket Download और जरूरी निर्देश"
    elif category == "Answer Key":
        seo_title = f"{short_exam_heading}: Official Response Sheet PDF और Objection Link"
    else:
        seo_title = f"{core_exam_name} Recruitment 2026: Notification PDF, Eligibility और Online Form"
        short_exam_heading = f"{core_exam_name} Recruitment 2026"

    date_matches = re.findall(r'\b(\d{1,2}[./-]\d{1,2}[./-]2026|\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+2026)\b', combined_search_space, re.IGNORECASE)
    exam_date = date_matches[0] if date_matches else "आधिकारिक अधिसूचना के अनुसार"
    release_date = datetime.datetime.now().strftime("%d %B %Y")

    # Extract Advt No if available
    advt_match = re.search(r'(?:Advt\.?\s*No\.?|Advertisement\s*No\.?|Notice\s*No\.?)\s*[:/-]?\s*([A-Za-z0-9/-]{2,18})', combined_search_space, re.IGNORECASE)
    advt_no = advt_match.group(1) if advt_match else "आधिकारिक पोर्टल पर उपलब्ध"

    return {
        "seo_title": seo_title,
        "short_exam_name": short_exam_heading,
        "core_exam_name": core_exam_name,
        "raw_notice_title": cleaned_notice[:140],
        "exam_date": exam_date,
        "release_date": release_date,
        "advt_no": advt_no
    }

# =====================================================================
# 6. PROFESSIONAL 1000+ WORDS EDITORIAL ARTICLE WRITER (NO GARBAGE CHARS)
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
    release_date = research_data["release_date"]
    advt_no = research_data["advt_no"]

    # Optional Gemini AI Writer (if key is configured)
    if GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key":
        try:
            api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
            prompt = f"""
            You are the Senior Chief Editor of govtvibhag.com.
            Write a highly professional, 950 to 1,100+ words Hindi + English mixed article on "{research_data['seo_title']}".
            - Never dump raw garbled PDF characters or question marks (???).
            - Write in 100% clean, natural human Hindi with English technical terms (roll number, qualifying status, merit list, cut-off marks, registration ID).
            - Include an Overview Table (Particular | Details), Dates Table, Detailed Step-by-Step Guide, What to Verify in PDF, Next Stage Process, Direct Official Links Table ({target_url} and {portal_url}), and 5 FAQs.
            """
            res = requests.post(api_url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=45)
            if res.status_code == 200:
                ai_text = sanitize_clean_text(res.json()["candidates"][0]["content"]["parts"][0]["text"])
                if len(ai_text.split()) >= 750:
                    return research_data["seo_title"], ai_text
        except Exception:
            pass

    # =================================================================
    # BUILT-IN SENIOR EDITOR ENGINE (Guaranteed 950–1,100+ Words Clean HTML)
    # =================================================================
    if category == "Result":
        lead_html = f"""
        <p><strong>{ org_name }</strong> ने <strong>{core_exam}</strong> परीक्षा का आधिकारिक परिणाम (Result / Merit List) जारी कर दिया है। आधिकारिक परीक्षा पोर्टल पर यह महत्वपूर्ण अपडेट <em>“{raw_notice}”</em> शीर्षक से उपलब्ध कराया गया है। वे सभी अभ्यर्थी जो इस भर्ती परीक्षा में शामिल हुए थे, वे अब आधिकारिक परिणाम {doc_format} या लॉगिन पोर्टल के माध्यम से अपना <strong>roll number</strong> खोजकर अपना <strong>qualifying status</strong> और अगले चरण की पात्रता जाँच सकते हैं।</p>
        <p>प्रतियोगी परीक्षाओं की तैयारी कर रहे लाखों उम्मीदवारों के लिए परिणाम का दिन बेहद महत्वपूर्ण होता है। {short_org} द्वारा जारी इस आधिकारिक सूची में उन सभी सफल उम्मीदवारों के रोल नंबर या स्कोर विवरण शामिल किए गए हैं जिन्होंने विभाग द्वारा निर्धारित न्यूनतम अर्हक अंक (Minimum Qualifying Marks) और श्रेणीवार कट-ऑफ (Category-wise Cut-off) को सफलतापूर्वक पार किया है। इस विस्तृत लेख में हमने परिणाम देखने की पूरी प्रक्रिया, कट-ऑफ के नियम और दस्तावेज़ सत्यापन (Document Verification) से जुड़ी संपूर्ण जानकारी सरल भाषा में उपलब्ध कराई है।</p>
        """

        sec2_heading = f"{short_exam} Released: मुख्य विवरण और आधिकारिक घोषणा"
        sec2_body = f"""
        <p>इस चरण की परीक्षा में शामिल हुए सभी उम्मीदवार आधिकारिक {doc_format} में अपना roll number या registration number देखकर अपने चयन की स्थिति की पुष्टि कर सकते हैं। {doc_format} में नाम या roll number मिलने के बाद आगे की चयन प्रक्रिया (जैसे Document Verification, Skill Test, Physical Test या Medical Examination) के लिए <strong>{org_name}</strong> द्वारा जारी विस्तृत दिशा-निर्देशों को ध्यानपूर्वक पढ़ना अत्यंत आवश्यक है।</p>
        <p>विभाग द्वारा स्पष्ट किया गया है कि यह परिणाम पूर्णतः अनंतिम (Provisional) है और उम्मीदवारों का अंतिम चयन उनके मूल शैक्षणिक व आरक्षण संबंधी प्रमाण पत्रों के सफल सत्यापन के अधीन होगा। यदि किसी उम्मीदवार के दस्तावेज़ों में आवेदन फॉर्म की तुलना में कोई भिन्नता पाई जाती है, तो संबंधित भर्ती नियमों के तहत आगे की कार्यवाही की जाती है।</p>
        """

        sec3_heading = f"{core_exam} Cut-Off Marks और Merit List तैयार करने के नियम"
        sec3_body = f"""
        <p>किसी भी बड़ी भर्ती परीक्षा में मेरिट सूची और कट-ऑफ अंक (Cut-off Marks) कई महत्वपूर्ण कारकों के आधार पर तय किए जाते हैं। उम्मीदवारों को यह समझना चाहिए कि {short_org} द्वारा अंतिम चयन सूची किस प्रकार तैयार की जाती है:</p>
        <ul>
            <li><strong>कुल रिक्त पदों की संख्या (Total Vacancies):</strong> जिस श्रेणी (UR, OBC, SC, ST, EWS, PwBD) में जितने पद विज्ञापित किए गए हैं, उसी के अनुपात में अगले चरण के लिए उम्मीदवारों को शॉर्टलिस्ट किया जाता है।</li>
            <li><strong>परीक्षा का कठिनाई स्तर और उपस्थिति (Difficulty Level & Attendance):</strong> प्रश्न पत्र की जटिलता और परीक्षा में उपस्थित होने वाले कुल अभ्यर्थियों की संख्या का सीधा प्रभाव कट-ऑफ अंकों पर पड़ता है।</li>
            <li><strong>Normalization Process (सामान्यीकरण पद्धति):</strong> यदि परीक्षा एक से अधिक शिफ्ट या दिनों में आयोजित की गई हो, तो सभी शिफ्टों के कठिनाई स्तर को बराबर करने के लिए Normalized Score के आधार पर मेरिट तैयार की जाती है।</li>
            <li><strong>Tie-Breaking Rules (समान अंक आने पर नियम):</strong> यदि दो या अधिक उम्मीदवारों के कुल अंक एक समान हो जाते हैं, तो मुख्य विषय के अंक, अधिक आयु (Date of Birth seniority) या नाम के वर्णमाला क्रम के अनुसार वरीयता तय की जाती है।</li>
        </ul>
        """

        how_to_heading = f"How to Check & Download {short_exam}?"
        how_to_steps = f"""
        <p>अधिकतर उम्मीदवारों को परिणाम जारी होने के तुरंत बाद आधिकारिक वेबसाइट पर सही लिंक खोजने में समय लगता है। आप नीचे दिए गए आसान चरणों का पालन करके बिना किसी रुकावट के अपना परिणाम देख सकते हैं:</p>
        <ol>
            <li>सबसे पहले <strong>{portal_name}</strong> (<a href="{portal_url}" target="_blank" rel="noopener">{portal_url}</a>) को अपने मोबाइल या कंप्यूटर ब्राउज़र में खोलें। इसका सीधा लिंक इस लेख की तालिका में भी दिया गया है।</li>
            <li>Homepage पर पहुंचकर <strong>Results / Latest Announcements / Public Notices</strong> सेक्शन पर जाएं।</li>
            <li>वहाँ हाल ही में जारी किए गए <strong>“{raw_notice}”</strong> वाले आधिकारिक लिंक का चयन करें।</li>
            <li>यदि परिणाम मेरिट लिस्ट PDF के रूप में है, तो फाइल आपके डिवाइस में डाउनलोड हो जाएगी। यदि स्कोरकार्ड लॉगिन आधारित है, तो अपना <strong>Roll Number / Application ID</strong> और <strong>Date of Birth</strong> दर्ज करें।</li>
            <li>खुलने वाली Result PDF के search option (कंप्यूटर पर <code>Ctrl + F</code> या मोबाइल PDF Viewer के सर्च आइकॉन) में अपना सटीक <strong>roll number</strong> टाइप करें।</li>
            <li>सूची में अपना roll number मिलने पर उसके सामने दिए गए Category, Rank या Remarks को ध्यान से पढ़ें और भविष्य के संदर्भ के लिए PDF की एक प्रति सुरक्षित सेव कर लें।</li>
        </ol>
        <p><strong>विशेष टिप:</strong> यदि एक बार में roll number सर्च में न दिखे, तो प्रवेश पत्र (Admit Card) से अपने रोल नंबर के अंकों का मिलान दोबारा करें और सुनिश्चित करें कि आपने अपने सही पद या चरण की PDF खोली है।</p>
        """

        what_to_check_heading = "Result PDF और Scorecard में कौन-सी जानकारी ध्यान से देखें?"
        what_to_check_list = """
        <p>Result PDF या ऑनलाइन स्कोरकार्ड में प्रत्येक उम्मीदवार से संबंधित महत्वपूर्ण प्रविष्टियां (entries) दर्ज होती हैं। दस्तावेज़ खोलने के बाद निम्नलिखित विवरणों की जांच अवश्य करें:</p>
        <ul>
            <li><strong>Roll Number एवं Registration Number:</strong> चयनित सूची में अपनी प्रविष्टि की 100% सटीक पहचान सुनिश्चित करने के लिए।</li>
            <li><strong>Candidate Category & Sub-Category:</strong> PDF में आपकी आरक्षित या अनारक्षित श्रेणी (UR/OBC/SC/ST/EWS/Ex-Servicemen) का जो कोड लिखा है, उसे अपने आवेदन फॉर्म से मिलाएं।</li>
            <li><strong>Raw Marks एवं Normalized Score:</strong> जहाँ स्कोरकार्ड जारी किया गया हो, वहाँ अपने विषयवार अंक और कुल प्राप्तांक ध्यान से पढ़ें।</li>
            <li><strong>Merit Position / All India Rank:</strong> यदि मेरिट सूची में रैंक का उल्लेख किया गया है, तो अपनी कैटेगरी रैंक और ओवरऑल रैंक दोनों देखें।</li>
            <li><strong>Qualifying Status & Official Notation:</strong> परिणाम के अंत में दिए गए निर्देशों (जैसे Qualified for Stage-II, Shortlisted for DV, या Provisional) का अर्थ समझें।</li>
            <li><strong>Cut-Off Table:</strong> परिणाम नोटिस के नीचे या अंत में दी गई श्रेणीवार कट-ऑफ तालिका से अपने अंकों की तुलना करें।</li>
        </ul>
        """

        next_stage_heading = f"{short_exam} के बाद आगे की प्रक्रिया (Document Verification & Next Steps)"
        next_stage_body = f"""
        <p>परीक्षा में सफल घोषित किए गए या शॉर्टलिस्ट हुए सभी उम्मीदवारों को अगले चरण के लिए अपने सभी आवश्यक प्रमाण पत्र समय रहते तैयार कर लेने चाहिए। {org_name} द्वारा दस्तावेज़ सत्यापन के समय आमतौर पर निम्नलिखित मूल दस्तावेज़ (Original Documents) मांगे जाते हैं:</p>
        <ul>
            <li><strong>शैक्षणिक प्रमाण पत्र:</strong> 10वीं (जन्मतिथि प्रमाण के लिए), 12वीं, स्नातक डिग्री/डिप्लोमा की मूल अंकतालिकाएं (Marksheets) और प्रमाण पत्र।</li>
            <li><strong>आरक्षण संबंधी प्रमाण पत्र:</strong> केंद्र या राज्य के निर्धारित प्रारूप में बना वैध जाति प्रमाण पत्र (SC/ST/OBC-NCL) तथा निर्धारित वित्तीय वर्ष का EWS प्रमाण पत्र।</li>
            <li><strong>प्रवेश पत्र और आवेदन का प्रिंट:</strong> मुख्य परीक्षा का मूल Admit Card और ऑनलाइन भरे गए Application Form की प्रति।</li>
            <li><strong>फोटो पहचान पत्र और फोटोग्राफ:</strong> आधार कार्ड, पैन कार्ड, पासपोर्ट या वोटर आईडी की मूल प्रति और 4 से 6 नवीनतम पासपोर्ट साइज रंगीन फोटो।</li>
        </ul>
        """
        link_label = f"Download {short_exam} Official PDF / Check Result"

    elif category == "Admit Card":
        lead_html = f"""
        <p><strong>{org_name}</strong> ने <strong>{core_exam}</strong> परीक्षा में शामिल होने जा रहे उम्मीदवारों के लिए आधिकारिक प्रवेश पत्र (Admit Card / Hall Ticket) और परीक्षा कार्यक्रम से जुड़ी महत्वपूर्ण सूचना जारी कर दी है। आधिकारिक परीक्षा पोर्टल पर यह अपडेट <em>“{raw_notice}”</em> शीर्षक से उपलब्ध है। जिन अभ्यर्थियों ने इस भर्ती परीक्षा के लिए सफलतापूर्वक ऑनलाइन आवेदन किया था, वे अब अपने registration number और जन्मतिथि (Date of Birth) की सहायता से अपना प्रवेश पत्र डाउनलोड कर सकते हैं।</p>
        <p>किसी भी प्रतियोगी परीक्षा में बैठने के लिए आधिकारिक प्रवेश पत्र सबसे अनिवार्य दस्तावेज़ होता है। बिना वैध प्रिंटेड Hall Ticket और मूल फोटो पहचान पत्र (Original Photo ID Proof) के किसी भी परीक्षार्थी को परीक्षा केंद्र (Exam Centre) के भीतर प्रवेश की अनुमति नहीं दी जाती है। इस लेख में हमने प्रवेश पत्र डाउनलोड करने की स्टेप-बाय-स्टेप प्रक्रिया, परीक्षा हॉल के कड़े नियम और साथ ले जाने वाले दस्तावेज़ों की पूरी जानकारी विस्तार से दी है।</p>
        """

        sec2_heading = f"{short_exam} Released: Exam City, Shift Timing और मुख्य जानकारी"
        sec2_body = f"""
        <p>{org_name} द्वारा जारी इस आधिकारिक अपडेट के माध्यम से उम्मीदवार अपनी सटीक परीक्षा तिथि (Exam Date), परीक्षा की पाली (Shift Timing), केंद्र पर रिपोर्टिंग का समय और परीक्षा शहर (Exam City & Centre Address) की जानकारी देख सकते हैं। कई बड़ी परीक्षाओं में विभाग द्वारा पहले Exam City Intimation Slip जारी की जाती है और परीक्षा तिथि से कुछ दिन पूर्व पूर्ण प्रवेश पत्र उपलब्ध कराया जाता है।</p>
        <p>सभी उम्मीदवारों को सलाह दी जाती है कि वे परीक्षा के अंतिम दिन का इंतज़ार न करें। अंतिम समय में सर्वर पर भारी ट्रैफिक होने के कारण डाउनलोड में देरी हो सकती है, इसलिए आज ही अपना {short_exam} डाउनलोड करें और उसकी कम से कम 2 साफ प्रतियां (A4 साइज पेपर पर) प्रिंट करवाकर सुरक्षित रख लें।</p>
        """

        sec3_heading = f"{core_exam} Exam Shift Guidelines और Reporting Time के नियम"
        sec3_body = f"""
        <p>परीक्षा के दिन केंद्र पर किसी भी प्रकार की घबराहट या परेशानी से बचने के लिए उम्मीदवारों को बोर्ड के समय-सारणी नियमों का विशेष ध्यान रखना चाहिए:</p>
        <ul>
            <li><strong>Reporting Time पर पहुंचना:</strong> एडमिट कार्ड पर अंकित रिपोर्टिंग समय पर केंद्र पर पहुंचना अनिवार्य है ताकि तलाशी (Frisking), बायोमेट्रिक उपस्थिति (Biometric Thumb & Photo Capture) और दस्तावेज़ जांच समय पर पूरी हो सके।</li>
            <li><strong>Gate Closing Time (गेट बंद होने का समय):</strong> परीक्षा शुरू होने से पहले निर्धारित Gate Closing Time के बाद केंद्र का मुख्य द्वार बंद कर दिया जाता है और इसके बाद किसी भी परिस्थिति में प्रवेश नहीं दिया जाता।</li>
            <li><strong>केंद्र की लोकेशन पहले से जांचें:</strong> यदि आपका परीक्षा केंद्र दूसरे शहर या अपरिचित क्षेत्र में है, तो परीक्षा से एक दिन पहले केंद्र की दूरी और यातायात के साधनों की जानकारी अवश्य प्राप्त कर लें।</li>
        </ul>
        """

        how_to_heading = f"How to Download {short_exam} Online?"
        how_to_steps = f"""
        <p>उम्मीदवार अपने मोबाइल या कंप्यूटर से नीचे दिए गए आसान चरणों का पालन करके चंद मिनटों में अपना आधिकारिक प्रवेश पत्र डाउनलोड कर सकते हैं:</p>
        <ol>
            <li>सबसे पहले <strong>{portal_name}</strong> (<a href="{portal_url}" target="_blank" rel="noopener">{portal_url}</a>) खोलें। इसका सीधा लिंक इस लेख की तालिका में भी दिया गया है।</li>
            <li>Homepage पर उपलब्ध <strong>Admit Card / Download Call Letter / Candidate Login</strong> सेक्शन पर क्लिक करें।</li>
            <li>वहाँ दिखाई दे रहे <strong>“{raw_notice}”</strong> वाले आधिकारिक लिंक को चुनें।</li>
            <li>लॉगिन विंडो खुलने पर अपना <strong>Registration Number / Roll Number</strong> और पासवर्ड के रूप में अपनी <strong>Date of Birth (DD/MM/YYYY)</strong> सही-सही दर्ज करें।</li>
            <li>स्क्रीन पर प्रदर्शित होने वाला Security Captcha Code बॉक्स में भरें और <strong>Submit / Download Admit Card</strong> बटन पर क्लिक करें।</li>
            <li>आपका प्रवेश पत्र स्क्रीन पर खुल जाएगा। इसमें सभी विवरण जाँचने के बाद PDF फाइल को सेव करें और प्रिंटर से A4 साइज पेपर पर साफ प्रिंटआउट निकाल लें।</li>
        </ol>
        <p><strong>यदि Registration Number भूल गए हों:</strong> लॉगिन पेज पर दिए गए 'Forgot Registration ID' विकल्प का उपयोग करें या अपने रजिस्टर्ड ईमेल इनबॉक्स और मोबाइल SMS में पुराने आवेदन संदेश को सर्च करें।</p>
        """

        what_to_check_heading = "Admit Card डाउनलोड करने के बाद कौन-सी जानकारी अवश्य जाँचें?"
        what_to_check_list = """
        <p>प्रवेश पत्र डाउनलोड करने के तुरंत बाद प्रत्येक उम्मीदवार को उस पर छपे सभी विवरणों का मिलान अपने मूल दस्तावेज़ों से करना चाहिए:</p>
        <ul>
            <li><strong>Candidate Name & Father/Mother Name:</strong> सुनिश्चित करें कि आपके नाम की स्पेलिंग आपके मूल फोटो पहचान पत्र (Aadhaar/PAN Card) से पूरी तरह मेल खाती हो।</li>
            <li><strong>Roll Number & Application Number:</strong> कंप्यूटर आधारित परीक्षा (CBT) या OMR शीट में भरने के लिए यह नंबर सबसे महत्वपूर्ण है।</li>
            <li><strong>Date of Birth & Category:</strong> आपकी जन्मतिथि और श्रेणी (UR/OBC/SC/ST/EWS) सही दर्ज होनी चाहिए।</li>
            <li><strong>Exam Date, Shift & Timing:</strong> परीक्षा की तारीख, परीक्षा शुरू होने का समय और कुल अवधि ध्यान से देखें।</li>
            <li><strong>Exam Centre Name, Code & Full Address:</strong> परीक्षा केंद्र का पूरा पता, पिन कोड और लैंडमार्क ध्यानपूर्वक पढ़ें।</li>
            <li><strong>Photograph, Signature & Barcode:</strong> एडमिट कार्ड पर आपकी फोटो, हस्ताक्षर और बारकोड स्पष्ट रूप से छपे होने चाहिए।</li>
        </ul>
        """

        next_stage_heading = "Exam Hall में साथ ले जाने वाले जरूरी दस्तावेज़ और वर्जित वस्तुएं"
        next_stage_body = """
        <p>परीक्षा केंद्र पर प्रवेश के समय सुरक्षा जांच के दौरान उम्मीदवारों के पास निम्नलिखित दस्तावेज़ होने अनिवार्य हैं:</p>
        <ul>
            <li><strong>Printed Admit Card:</strong> आधिकारिक पोर्टल से डाउनलोड किए गए प्रवेश पत्र की साफ प्रिंट कॉपी (जिस पर सभी निर्देश पठनीय हों)।</li>
            <li><strong>Original Valid Photo ID Proof:</strong> आधार कार्ड (ई-आधार प्रिंट), पैन कार्ड, वोटर आईडी, ड्राइविंग लाइसेंस या पासपोर्ट में से कोई एक मूल (Original) पहचान पत्र। फोटोकॉपी या मोबाइल में फोटो मान्य नहीं होती।</li>
            <li><strong>Passport Size Photographs:</strong> ऑनलाइन आवेदन फॉर्म में अपलोड की गई फोटो जैसी 2 नवीनतम पासपोर्ट साइज रंगीन फोटो।</li>
            <li><strong>सख्त वर्जित वस्तुएं (Prohibited Items):</strong> परीक्षा कक्ष में मोबाइल फोन, स्मार्टवॉच, डिजिटल घड़ी, ब्लूटूथ, कैलकुलेटर, ईयरफोन, बैग, किताबें या किसी भी प्रकार के इलेक्ट्रॉनिक गैजेट ले जाना सख्त मना है।</li>
        </ul>
        """
        link_label = f"Download {short_exam} Direct Link"

    elif category == "Answer Key":
        lead_html = f"""
        <p><strong>{org_name}</strong> ने हाल ही में आयोजित की गई <strong>{core_exam}</strong> परीक्षा की आधिकारिक उत्तर कुंजी (Answer Key / Response Sheet) जारी कर दी है। आधिकारिक परीक्षा पोर्टल पर यह महत्वपूर्ण अपडेट <em>“{raw_notice}”</em> शीर्षक से उपलब्ध कराया गया है। परीक्षा में उपस्थित हुए सभी उम्मीदवार अब आधिकारिक पोर्टल पर लॉगिन करके या जारी की गई PDF के माध्यम से अपने उत्तरों का मिलान कर सकते हैं और अपने संभावित प्राप्तांक (Expected Score) की सटीक गणना कर सकते हैं।</p>
        <p>चयन प्रक्रिया में पूर्ण पारदर्शिता बनाए रखने के उद्देश्य से {short_org} द्वारा परिणाम घोषित होने से पूर्व प्रोविजनल या अंतिम उत्तर कुंजी जारी की जाती है। इसके साथ ही, यदि किसी परीक्षार्थी को आयोग द्वारा दिए गए किसी उत्तर या प्रश्न के विकल्पों में कोई त्रुटि नज़र आती है, तो निर्धारित समय-सीमा के भीतर ऑनलाइन आपत्ति (Objection / Challenge) दर्ज कराने का अवसर भी प्रदान किया जाता है।</p>
        """

        sec2_heading = f"{short_exam} Released: Response Sheet और Objection Window की जानकारी"
        sec2_body = f"""
        <p>आधिकारिक पोर्टल पर जारी किए गए इस लिंक के माध्यम से अभ्यर्थी अपने द्वारा परीक्षा में टिक किए गए विकल्प (Chosen Option) और बोर्ड द्वारा सही माने गए आधिकारिक उत्तर (Correct Answer) दोनों को एक साथ देख सकते हैं। इससे उम्मीदवार परिणाम आने से पहले ही अपनी तैयारी और चयन की संभावनाओं का सही आकलन कर पाते हैं।</p>
        <p>उम्मीदवारों को विशेष रूप से ध्यान देना चाहिए कि ऑनलाइन रिस्पॉन्स शीट और आपत्ति दर्ज करने का लिंक पोर्टल पर केवल कुछ सीमित दिनों के लिए ही सक्रिय रहता है। समय-सीमा समाप्त होने के बाद रिस्पॉन्स शीट डाउनलोड करने या आपत्ति दर्ज करने की सुविधा बंद कर दी जाती है, इसलिए समय रहते अपनी उत्तर कुंजी की PDF कॉपी अपने पास सेव कर लें।</p>
        """

        sec3_heading = f"{core_exam} Score Calculation: अपने अंकों की गणना कैसे करें?"
        sec3_body = f"""
        <p>उत्तर कुंजी डाउनलोड करने के बाद अपने कुल संभावित अंक (Raw Score) निकालने के लिए उम्मीदवारों को परीक्षा की आधिकारिक Marking Scheme का पालन करना चाहिए:</p>
        <ul>
            <li><strong>सही उत्तरों की गिनती (Total Correct Answers):</strong> सबसे पहले अपनी पूरी शीट में उन सभी प्रश्नों की संख्या गिनें जिनका उत्तर आधिकारिक Answer Key से बिल्कुल मेल खाता है।</li>
            <li><strong>गलत उत्तर और Negative Marking:</strong> अब उन प्रश्नों को गिनें जिनका उत्तर गलत हुआ है। यदि परीक्षा में नकारात्मक अंकन (जैसे 1/4 यानी 0.25 अंक या 1/3 अंक) लागू है, तो कुल गलत उत्तरों के निर्धारित अंक घटाएं।</li>
            <li><strong>छोड़े गए प्रश्न (Unattempted Questions):</strong> जिन प्रश्नों का आपने परीक्षा में कोई उत्तर नहीं दिया है, उनके लिए न तो कोई अंक जोड़ा जाता है और न ही कोई नेगेटिव मार्किंग होती है।</li>
            <li><strong>कुल स्कोर का सूत्र (Formula):</strong> <code>कुल प्राप्तांक = (सही उत्तर × प्रति प्रश्न अंक) − (गलत उत्तर × नेगेटिव मार्किंग अंक)</code>।</li>
        </ul>
        """

        how_to_heading = f"How to Check & Download {short_exam}?"
        how_to_steps = f"""
        <p>अपनी शिफ्ट की आधिकारिक उत्तर कुंजी और रिस्पॉन्स शीट डाउनलोड करने के लिए नीचे दिए गए चरणों का क्रमवार पालन करें:</p>
        <ol>
            <li>सबसे पहले <strong>{portal_name}</strong> (<a href="{portal_url}" target="_blank" rel="noopener">{portal_url}</a>) को अपने ब्राउज़र में खोलें।</li>
            <li>Homepage पर <strong>Answer Key / Candidate Response Sheet</strong> या Latest Notifications सेक्शन में जाएं।</li>
            <li>वहाँ उपलब्ध <strong>“{raw_notice}”</strong> वाले आधिकारिक लिंक पर क्लिक करें।</li>
            <li>लॉगिन पेज खुलने पर अपना <strong>Roll Number / Registration ID</strong> और <strong>Password / Date of Birth</strong> दर्ज करें।</li>
            <li>लॉगिन होने के बाद डैशबोर्ड पर <em>'Click here to generate Question Paper & Answer Key'</em> या संबंधित PDF लिंक पर क्लिक करें।</li>
            <li>स्क्रीन पर खुलने वाली उत्तर कुंजी से अपने उत्तरों का मिलान करें और भविष्य के संदर्भ के लिए इसे Print / Save as PDF कर लें।</li>
        </ol>
        """

        what_to_check_heading = "Answer Key PDF और Response Sheet में कौन-सी जानकारी देखें?"
        what_to_check_list = """
        <p>ऑनलाइन CBT परीक्षा या OMR उत्तर कुंजी का मिलान करते समय उम्मीदवारों को निम्नलिखित तकनीकी विवरणों को ध्यान से देखना चाहिए:</p>
        <ul>
            <li><strong>Question ID & Option ID:</strong> ऑनलाइन परीक्षा में प्रत्येक उम्मीदवार के प्रश्नों का क्रम अलग होता है, इसलिए केवल प्रश्न संख्या के बजाय हमेशा <strong>Question ID</strong> और <strong>Option ID</strong> से ही मिलान करें।</li>
            <li><strong>Status (Answered / Not Answered / Marked for Review):</strong> जांचें कि आपका उत्तर सिस्टम में सफलतापूर्वक सेव हुआ था या नहीं।</li>
            <li><strong>Chosen Option vs Official Correct Option:</strong> आपके द्वारा चुने गए विकल्प और हरे रंग (या टिक निशान) से दर्शाए गए आधिकारिक सही उत्तर की तुलना करें।</li>
            <li><strong>Shift Date & Paper Code:</strong> यदि उत्तर कुंजी मास्टर PDF के रूप में है, तो अपनी सही परीक्षा तिथि, शिफ्ट और पेपर सेट (Set A/B/C/D) का मिलान करें।</li>
        </ul>
        """

        next_stage_heading = "गलत प्रश्न या उत्तर पर ऑनलाइन आपत्ति (Objection) कैसे दर्ज करें?"
        next_stage_body = f"""
        <p>यदि आपको पूर्ण विश्वास है कि किसी प्रश्न का आधिकारिक उत्तर गलत दिया गया है या प्रश्न के सभी विकल्प त्रुटिपूर्ण हैं, तो आप {portal_name} के माध्यम से अपनी आपत्ति दर्ज करा सकते हैं:</p>
        <ul>
            <li><strong>प्रामाणिक पुस्तक का साक्ष्य (Authentic Proof):</strong> आपत्ति स्वीकार किए जाने के लिए NCERT, सरकारी प्रकाशन या मानक संदर्भ पुस्तक (Standard Textbook) के संबंधित पन्ने की साफ PDF/फोटो अपलोड करना अनिवार्य होता है।</li>
            <li><strong>प्रति प्रश्न निर्धारित शुल्क:</strong> विभाग द्वारा तय किया गया प्रति प्रश्न ऑनलाइन शुल्क जमा करना होता है। कई बोर्डों में आपत्ति सही पाए जाने पर यह शुल्क उम्मीदवार के खाते में वापस (Refund) कर दिया जाता है।</li>
            <li><strong>Final Answer Key का निर्माण:</strong> विषय विशेषज्ञों की समिति द्वारा सभी प्राप्त आपत्तियों की गहन समीक्षा करने के बाद ही अंतिम उत्तर कुंजी (Final Answer Key) और अंतिम परिणाम जारी किया जाता है।</li>
        </ul>
        """
        link_label = f"Download {short_exam} PDF / Response Sheet Link"

    else:  # Govt Job (Recruitment / Vacancy Notification)
        lead_html = f"""
        <p><strong>{org_name}</strong> ने <strong>{core_exam}</strong> भर्ती प्रक्रिया के लिए आधिकारिक विज्ञापन (Official Notification) जारी कर दिया है। आधिकारिक भर्ती पोर्टल पर यह अधिसूचना <em>“{raw_notice}”</em> शीर्षक के अंतर्गत उपलब्ध कराई गई है। केंद्र और राज्य सरकार के अधीन प्रतिष्ठित पदों पर सरकारी नौकरी की तैयारी कर रहे योग्य उम्मीदवारों के लिए यह एक अत्यंत महत्वपूर्ण अवसर है। इच्छुक अभ्यर्थी आधिकारिक नोटिफिकेशन {doc_format} के माध्यम से रिक्त पदों का विवरण, पात्रता शर्तें और आवेदन प्रक्रिया की जांच कर सकते हैं।</p>
        <p>{short_org} द्वारा जारी इस आधिकारिक विज्ञापन में पद के अनुसार शैक्षणिक योग्यता (Educational Qualification), आयु सीमा (Age Limit), वेतनमान (Pay Scale), आवेदन शुल्क और चयन प्रक्रिया के सभी नियम विस्तार से स्पष्ट किए गए हैं। उम्मीदवारों को सलाह दी जाती है कि ऑनलाइन फॉर्म भरने से पहले इस लेख में दी गई संपूर्ण जानकारी और आधिकारिक पीडीएफ को ध्यानपूर्वक पढ़ लें ताकि आवेदन के समय किसी भी प्रकार की त्रुटि न हो।</p>
        """

        sec2_heading = f"{short_exam} Notification Released: भर्ती का मुख्य विवरण"
        sec2_body = f"""
        <p>इस भर्ती अभियान के अंतर्गत योग्य और मेधावी उम्मीदवारों से ऑनलाइन माध्यम (Online Mode) द्वारा आवेदन आमंत्रित किए गए हैं। {org_name} ने स्पष्ट किया है कि आवेदन करने वाले प्रत्येक अभ्यर्थी को विज्ञापित कट-ऑफ तिथि (Crucial Date for Eligibility) तक सभी आवश्यक शैक्षणिक और आयु संबंधी शर्तें पूरी करनी होंगी।</p>
        <p>आरक्षित वर्गों (SC, ST, OBC-NCL, EWS, Ex-Servicemen और PwBD) के उम्मीदवारों को सरकारी नियमों के अनुसार रिक्त पदों में आरक्षण और ऊपरी आयु सीमा व आवेदन शुल्क में विशेष छूट प्रदान की जाएगी। श्रेणीवार पदों की सटीक संख्या और विभागवार विवरण के लिए उम्मीदवार नीचे दिए गए सीधे लिंक से आधिकारिक नोटिफिकेशन डाउनलोड कर सकते हैं।</p>
        """

        sec3_heading = f"{core_exam} Eligibility Criteria, Age Limit और Selection Process"
        sec3_body = f"""
        <p>किसी भी सरकारी भर्ती में आवेदन करने से पहले उम्मीदवार को मुख्य पात्रता मापदंडों और चयन के चरणों को अच्छी तरह समझ लेना चाहिए:</p>
        <ul>
            <li><strong>Educational Qualification (शैक्षणिक योग्यता):</strong> आवेदक के पास संबंधित पद की आवश्यकता के अनुसार किसी मान्यता प्राप्त बोर्ड, संस्थान या विश्वविद्यालय से 10वीं / 12वीं / स्नातक डिग्री / डिप्लोमा या समकक्ष योग्यता होनी चाहिए।</li>
            <li><strong>Age Limit & Relaxation (आयु सीमा एवं छूट):</strong> न्यूनतम और अधिकतम आयु की गणना आधिकारिक नोटिफिकेशन में निर्धारित तिथि के आधार पर की जाएगी। सरकारी नियमानुसार OBC को 3 वर्ष, SC/ST को 5 वर्ष और दिव्यांगजन (PwBD) उम्मीदवारों को 10 से 15 वर्ष तक की आयु छूट देय होती है।</li>
            <li><strong>Application Fee (आवेदन शुल्क):</strong> सामान्य (UR), ओबीसी और ईडब्ल्यूएस वर्ग के लिए निर्धारित परीक्षा शुल्क तथा आरक्षित/महिला उम्मीदवारों के लिए शुल्क छूट का विवरण आधिकारिक पीडीएफ में दिया गया है। शुल्क का भुगतान डेबिट कार्ड, क्रेडिट कार्ड, नेट बैंकिंग या UPI से किया जा सकता है।</li>
            <li><strong>Selection Process (चयन प्रक्रिया):</strong> इस भर्ती में अंतिम चयन लिखित परीक्षा (CBT / OMR Exam), कौशल या शारीरिक परीक्षा (Skill Test / PET / PST - यदि लागू हो), दस्तावेज़ सत्यापन (Document Verification) और चिकित्सा परीक्षण के आधार पर किया जाएगा।</li>
        </ul>
        """

        how_to_heading = f"How to Apply Online for {short_exam}?"
        how_to_steps = f"""
        <p>इच्छुक और पात्र उम्मीदवार अंतिम तिथि का इंतज़ार किए बिना नीचे दिए गए चरणों का पालन करके आसानी से अपना ऑनलाइन आवेदन फॉर्म सबमिट कर सकते हैं:</p>
        <ol>
            <li>सबसे पहले <strong>{portal_name}</strong> (<a href="{portal_url}" target="_blank" rel="noopener">{portal_url}</a>) की आधिकारिक वेबसाइट खोलें। इसका सीधा लिंक इस लेख की तालिका में भी उपलब्ध है।</li>
            <li>Homepage पर उपलब्ध <strong>Recruitment / Advertisements / Apply Online</strong> सेक्शन में जाएं।</li>
            <li>वहाँ सूचीबद्ध <strong>“{raw_notice}”</strong> के आधिकारिक नोटिफिकेशन PDF को डाउनलोड करें और सभी निर्देश ध्यान से पढ़ें।</li>
            <li>अब <strong>New Registration / One-Time Registration (OTR)</strong> लिंक पर क्लिक करके अपने सक्रिय मोबाइल नंबर और वैध ईमेल आईडी की मदद से पंजीकरण पूरा करें।</li>
            <li>प्राप्त Registration ID और Password से पोर्टल पर लॉगिन करें और आवेदन फॉर्म में अपनी व्यक्तिगत, शैक्षणिक और पते की जानकारी बिल्कुल सही-सही भरें।</li>
            <li>नोटिफिकेशन में निर्धारित साइज (KB) और डाइमेंशन के अनुसार अपनी नवीनतम पासपोर्ट साइज फोटो, स्पष्ट हस्ताक्षर और आवश्यक प्रमाण पत्र अपलोड करें।</li>
            <li>फॉर्म का <strong>Preview</strong> ध्यान से जांचें, अपनी श्रेणी के अनुसार ऑनलाइन परीक्षा शुल्क जमा करें और <strong>Final Submit</strong> करने के बाद आवेदन फॉर्म का प्रिंटआउट (PDF) सुरक्षित रख लें।</li>
        </ol>
        """

        what_to_check_heading = "Notification PDF में आवेदन करने से पहले कौन-सी जानकारी देखें?"
        what_to_check_list = """
        <p>अक्सर फॉर्म भरते समय छोटी सी अनदेखी के कारण बाद में Document Verification के समय उम्मीदवारों को परेशानी का सामना करना पड़ता है। इसलिए आधिकारिक PDF में निम्न बिंदु अवश्य जांचें:</p>
        <ul>
            <li><strong>Post Name & Category-wise Vacancy:</strong> जिस पद के लिए आप आवेदन कर रहे हैं, उसमें आपकी अपनी श्रेणी (Category) में कितनी सीटें उपलब्ध हैं।</li>
            <li><strong>Crucial Date for Qualification & Certificates:</strong> आपकी डिग्री/मार्कशीट और जाति/EWS प्रमाण पत्र किस तारीख से पहले का बना होना चाहिए।</li>
            <li><strong>Photo & Signature Guidelines:</strong> फोटो का बैकग्राउंड (सफेद या हल्का रंग), फोटो पर तारीख का नियम और हस्ताक्षर की स्याही (काली या नीली) से जुड़े निर्देश।</li>
            <li><strong>Exam Pattern & Syllabus:</strong> लिखित परीक्षा में पूछे जाने वाले विषय, प्रश्नों की संख्या, कुल अंक, समय अवधि और नेगेटिव मार्किंग का विवरण।</li>
            <li><strong>Correction Window Rules:</strong> फॉर्म सबमिट होने के बाद यदि कोई त्रुटि रह जाए, तो क्या विभाग द्वारा संशोधन (Correction Window) का अवसर दिया जाएगा या नहीं।</li>
        </ul>
        """

        next_stage_heading = f"{short_exam} फॉर्म भरते समय जरूरी दस्तावेज़ों की सूची"
        next_stage_body = """
        <p>ऑनलाइन आवेदन शुरू करने से पहले उम्मीदवारों को निम्नलिखित दस्तावेज़ अपने पास स्कैन करके तैयार रखने चाहिए ताकि फॉर्म भरते समय कोई रुकावट न आए:</p>
        <ul>
            <li><strong>10वीं (Matriculation) का प्रमाण पत्र:</strong> नाम, माता-पिता का नाम और जन्मतिथि बिल्कुल 10वीं के सर्टिफिकेट के अनुसार ही दर्ज करें।</li>
            <li><strong>आवश्यक शैक्षणिक अंकतालिकाएं:</strong> 12वीं, स्नातक या डिप्लोमा के रोल नंबर, उत्तीर्ण वर्ष और प्राप्तांक प्रतिशत का विवरण।</li>
            <li><strong>वैध फोटो पहचान पत्र:</strong> आधार कार्ड, वोटर आईडी, पैन कार्ड या ड्राइविंग लाइसेंस संख्या।</li>
            <li><strong>आरक्षण एवं मूल निवास प्रमाण पत्र:</strong> SC/ST/OBC/EWS और दिव्यांगता प्रमाण पत्र (यदि लागू हो)।</li>
        </ul>
        """
        link_label = f"Download {short_exam} Notification PDF / Apply Online"

    # Assemble the Complete 1000+ Words Clean HTML Article
    full_html = f"""
    {lead_html}

    <h2>{short_exam}: Overview</h2>
    <p>नीचे दी गई तालिका में उम्मीदवारों की सुविधा के लिए इस आधिकारिक अद्यतन (Official Update) से संबंधित सभी प्रमुख विवरणों का संक्षिप्त सार प्रस्तुत किया गया है:</p>
    <table border="1" cellpadding="10" cellspacing="0" style="width:100%; border-collapse:collapse; margin:15px 0 25px 0;">
        <thead>
            <tr style="background-color:#f8f9fa;">
                <th style="width:38%; text-align:left;">Particular (विवरण)</th>
                <th style="width:62%; text-align:left;">Official Details (आधिकारिक जानकारी)</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td><strong>Conducting Authority</strong></td>
                <td>{org_name}</td>
            </tr>
            <tr>
                <td><strong>Exam / Recruitment Name</strong></td>
                <td>{core_exam}</td>
            </tr>
            <tr>
                <td><strong>Official Notice Title</strong></td>
                <td>{raw_notice}</td>
            </tr>
            <tr>
                <td><strong>Advertisement / Ref No.</strong></td>
                <td>{advt_no}</td>
            </tr>
            <tr>
                <td><strong>Update Category</strong></td>
                <td>Official {category}</td>
            </tr>
            <tr>
                <td><strong>Key Exam / Event Date</strong></td>
                <td>{exam_date}</td>
            </tr>
            <tr>
                <td><strong>Update Release Date</strong></td>
                <td>{release_date}</td>
            </tr>
            <tr>
                <td><strong>Document Format</strong></td>
                <td>{doc_format}</td>
            </tr>
            <tr>
                <td><strong>Mode of Process</strong></td>
                <td>Online (आधिकारिक पोर्टल के माध्यम से)</td>
            </tr>
            <tr>
                <td><strong>Official Website</strong></td>
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
                <th style="width:55%; text-align:left;">Important Official Link</th>
                <th style="width:45%; text-align:left;">Direct Action Link</th>
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

    <h2>Frequently Asked Questions (FAQs)</h2>
    <p><strong>1. {short_exam} आधिकारिक रूप से कहाँ जारी किया गया है?</strong><br>
    उत्तर: यह आधिकारिक अपडेट {org_name} द्वारा अपने आधिकारिक पोर्टल ({portal_name}) पर “{raw_notice}” शीर्षक से जारी किया गया है।</p>

    <p><strong>2. मैं {short_exam} की आधिकारिक PDF या डायरेक्ट लिंक कैसे खोल सकता हूँ?</strong><br>
    उत्तर: आप इस लेख में ऊपर दी गई 'Important Official Links' तालिका में मौजूद सीधे लिंक पर क्लिक करके आधिकारिक {doc_format} या वेबपेज खोल सकते हैं।</p>

    <p><strong>3. क्या इस {category} के लिए किसी ऑफलाइन प्रक्रिया की आवश्यकता है?</strong><br>
    उत्तर: नहीं, विभाग द्वारा यह संपूर्ण प्रक्रिया ऑनलाइन माध्यम से आधिकारिक पोर्टल पर उपलब्ध कराई गई है। उम्मीदवारों को केवल आधिकारिक वेबसाइट का ही उपयोग करना चाहिए।</p>

    <p><strong>4. यदि आधिकारिक वेबसाइट खुलने में समय ले रही हो तो क्या करें?</strong><br>
    उत्तर: नया आधिकारिक अपडेट आने पर एक साथ हजारों उम्मीदवारों के विजिट करने से सर्वर कभी-कभी धीमा हो जाता है। ऐसी स्थिति में कुछ मिनट प्रतीक्षा करें और पेज को रिफ्रेश करके पुनः प्रयास करें।</p>

    <p><strong>5. {core_exam} से जुड़े आगामी अपडेट्स और नोटिस कहाँ मिलेंगे?</strong><br>
    उत्तर: इस परीक्षा के अगले चरणों से जुड़ी सभी आधिकारिक सूचनाएं समय-समय पर {portal_name} ({portal_url}) पर प्रकाशित की जाएंगी।</p>
    """

    return research_data["seo_title"], full_html.strip()

# =====================================================================
# 7. WORDPRESS DRAFT PUBLISHER
# =====================================================================
def save_or_update_wordpress_draft(title, html_content, existing_wp_id=0):
    # Always save a local preview copy so you can inspect the formatting anytime
    preview_path = os.path.join(DATA_FOLDER, "latest_govtvibhag_style_draft.html")
    try:
        with open(preview_path, "w", encoding="utf-8") as f:
            f.write(f"<h1>{title}</h1>\n{html_content}")
    except Exception:
        pass

    if "your_wp_username" in WP_USERNAME or "your-wordpress-site.com" in WP_SITE_URL:
        print(f"   [+] Saved Local Preview (1000+ Words): {preview_path}")
        return 0

    try:
        base_api = f"{WP_SITE_URL.rstrip('/')}/wp-json/wp/v2/posts"
        api_url = f"{base_api}/{existing_wp_id}" if existing_wp_id > 0 else base_api
        credentials = f"{WP_USERNAME}:{WP_APP_PASSWORD}"
        token = base64.b64encode(credentials.encode()).decode("utf-8")
        headers = {
            "Authorization": f"Basic {token}",
            "Content-Type": "application/json"
        }
        payload = {
            "title": title,
            "content": html_content,
            "status": "draft"
        }
        res = requests.post(api_url, json=payload, headers=headers, timeout=25)
        if res.status_code in [200, 201]:
            wp_id = res.json().get("id", 0)
            print(f"   [SUCCESS] Professional Draft Created in WordPress: {title}")
            return wp_id
        else:
            print(f"   [!] WordPress API Status: {res.status_code}")
    except Exception as e:
        print(f"   [!] WordPress Error: {e}")
    return 0

# =====================================================================
# 8. SMART PER-PORTAL BASELINE + STRICT FRESH & ANTI-DUPLICATE SCANNER
# =====================================================================
def run_hourly_scanner():
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    current_check_str = datetime.datetime.now().strftime("%I:%M %p")
    print(f"\n[HOURLY SCAN - {current_check_str}] Checking all 39 official portals...")

    new_found_total = 0

    for portal_info in GOVT_PORTALS:
        portal = portal_info["url"]
        portal_already_synced = is_portal_synced(portal)

        try:
            response = requests.get(portal, headers=headers, timeout=18, verify=False)
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

                # Check URL & Notice Key before downloading
                if is_already_processed(full_target_url, notice_key=n_key):
                    continue

                # Extract content + Internal PDF Metadata Creation Date
                source_text, doc_format, last_mod, pdf_date = extract_source_and_metadata(full_target_url)
                content_hash = hashlib.md5(source_text.encode("utf-8", errors="ignore")).hexdigest() if source_text else ""

                combined_info = (link_text + " " + href).lower()
                category = determine_category(combined_info)
                research_data = build_clean_human_title(portal_info, link_text, source_text, category)
                proposed_seo_title = research_data["seo_title"]

                # 4-Layer Duplicate Check (URL + Notice Key + SEO Title + Content Hash)
                if is_already_processed(full_target_url, notice_key=n_key, seo_title=proposed_seo_title, content_hash=content_hash):
                    mark_as_processed(portal, full_target_url, n_key, link_text[:100], "DUPLICATE_IGNORED", "IGNORED_DUP", 0, content_hash)
                    continue

                # 4-Layer Freshness Check (PDF Metadata Date + HTTP Last-Modified + Session Check)
                is_fresh, reason = verify_is_truly_fresh(link_text, source_text, last_mod, pdf_date)
                if not is_fresh:
                    print(f"   [Rejected Old Notice] {link_text[:50]}... -> {reason}")
                    mark_as_processed(portal, full_target_url, n_key, link_text[:100], f"OLD_REJECTED ({reason})", "IGNORED_OLD", 0, content_hash)
                    continue

                # Genuine Fresh Notification Found! Write 1000+ Words Professional Article
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

        time.sleep(1)

    if new_found_total == 0:
        print("   [STATUS] Scan complete. Kisi bhi portal par abhi koi naya fresh update nahi aaya hai.")

if __name__ == "__main__":
    disable_cmd_quickedit()
    print("=========================================================================")
    print("   GOVTVIBHAG.COM PROFESSIONAL EDITORIAL BOT v6.0                        ")
    print("   - Length: 950 to 1,100+ Words Professional Editorial Format           ")
    print("   - Zero Garbled/Question Mark Characters (Clean Unicode Sanitizer)     ")
    print("   - 4-Layer Anti-Duplicate & PDF Metadata Creation Date Verification    ")
    print("=========================================================================")

    init_db()
    bot_start_dt = ensure_bot_start_time()
    print(f"   [ACTIVE] Monitoring fresh updates since: {bot_start_dt.strftime('%d %b %Y, %I:%M %p')}")

    while True:
        run_hourly_scanner()
        print("\n[WAITING] Next hourly scan countdown started:")
        for remaining in range(60, 0, -1):
            sys.stdout.write(f"\r   -> Agla scan {remaining} minute mein hoga... (Bot 24/7 Active Hai)   ")
            sys.stdout.flush()
            time.sleep(60)
        print("\n")

