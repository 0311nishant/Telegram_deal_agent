import os

# ─────────────────────────────────────────
# CREDENTIALS
# ─────────────────────────────────────────
TELEGRAM_API_ID   = os.getenv("TELEGRAM_API_ID")
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH")
TELEGRAM_PHONE    = os.getenv("TELEGRAM_PHONE")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY") # For Agents 1 & 3
TELEGRAM_SESSION_STRING = os.getenv("TELEGRAM_SESSION_STRING") # For deployment
ALERT_USERNAME    = os.getenv("ALERT_TELEGRAM_USERNAME")
DATABASE_URL      = os.getenv("DATABASE_URL") # For PostgreSQL

# ─────────────────────────────────────────
# MODELS
# ─────────────────────────────────────────
DISCOVERY_MODEL  = "perplexity/sonar"               # web search — Agent 1
CONVERTER_MODEL  = "anthropic/claude-haiku-3-5"     # DM conversion — Agent 3

# ─────────────────────────────────────────
# SCHEDULE
# ─────────────────────────────────────────
MORNING_TIME   = os.getenv("MORNING_BROADCAST_TIME", "09:00")
EVENING_TIME   = os.getenv("EVENING_BROADCAST_TIME", "18:00")
DISCOVERY_TIME = os.getenv("DISCOVERY_TIME", "06:00")

# ─────────────────────────────────────────
# RATE LIMITING
# ─────────────────────────────────────────
MIN_DELAY_BETWEEN_GROUPS = 180   # seconds (3 min)
MAX_DELAY_BETWEEN_GROUPS = 360   # seconds (6 min)
DM_REPLY_MIN_DELAY       = 4     # seconds
DM_REPLY_MAX_DELAY       = 10    # seconds

# ─────────────────────────────────────────
# GROUP QUALITY FILTERS
# ─────────────────────────────────────────
MIN_MEMBERS = 100       # skip dead groups
MAX_MEMBERS = 100000    # skip broadcast-only mega channels

# ─────────────────────────────────────────
# FILE PATHS
# ─────────────────────────────────────────
DATABASE_FILE      = "data/agent.db"
SESSION_FILE       = "session" # Used for local development

# ─────────────────────────────────────────
# YOUR FIXED SKILL MESSAGE
# Edit this — it never changes, no AI rewrites
# ─────────────────────────────────────────
SKILL_MESSAGE = """
👋 Hey! I'm a freelance developer open for new projects.

✅ Test Automation (Selenium, Playwright, Cypress)
✅ QA & Testing Pipelines
✅ API Testing & Validation
✅ CI/CD Automation
✅ Python / Node.js Backend Development
✅ Web Scraping & Data Automation

Quick turnaround. Fair pricing. DM me if you have something in mind.
"""

# ─────────────────────────────────────────
# KEYWORD MATRIX — Agent 1
# Rotates daily: skill + intent + format + country
# 880+ unique combinations
# ─────────────────────────────────────────
SKILLS = [
    "QA automation", "software testing", "test automation",
    "selenium", "playwright", "cypress", "API testing",
    "CI CD automation", "python developer", "backend developer",
    "nodejs developer", "freelance developer", "web scraping",
    "automation engineer", "SDET", "quality assurance",
    "software automation", "integration testing", "regression testing",
    "performance testing"
]

INTENTS = [
    "freelancers", "professionals", "community", "jobs",
    "hiring", "projects", "developers", "engineers",
    "remote work", "outsourcing", "contractors",
    "for hire", "work opportunities"
]

FORMATS = [
    "telegram group",
    "telegram community",
    "telegram channel",
    "t.me group",
    "telegram network"
]

# ─────────────────────────────────────────
# COUNTRY MATRIX — Agent 1
# ─────────────────────────────────────────
COUNTRIES = {
    "us": {
        "names": ["USA", "United States"],
        "tgstat_code": "us",
        "google_domain": "https://www.google.com",
        "context": ["upwork", "silicon valley", "US remote"]
    },
    "uk": {
        "names": ["UK", "United Kingdom", "Britain"],
        "tgstat_code": "gb",
        "google_domain": "https://www.google.co.uk",
        "context": ["contract developer", "london tech", "UK remote"]
    },
    "in": {
        "names": ["India", "Indian"],
        "tgstat_code": "in",
        "google_domain": "https://www.google.co.in",
        "context": ["bangalore", "startup India", "Indian freelancer"]
    },
    "au": {
        "names": ["Australia", "Australian"],
        "tgstat_code": "au",
        "google_domain": "https://www.google.com.au",
        "context": ["sydney tech", "melbourne developers", "AU remote"]
    },
    "de": {
        "names": ["Germany", "German"],
        "tgstat_code": "de",
        "google_domain": "https://www.google.de",
        "context": ["berlin tech", "german startup", "EU remote"]
    },
    "ca": {
        "names": ["Canada", "Canadian"],
        "tgstat_code": "ca",
        "google_domain": "https://www.google.ca",
        "context": ["toronto tech", "vancouver developers", "CA remote"]
    },
    "ae": {
        "names": ["UAE", "Dubai"],
        "tgstat_code": "ae",
        "google_domain": "https://www.google.ae",
        "context": ["dubai tech", "MENA startup", "gulf developers"]
    },
    "sg": {
        "names": ["Singapore"],
        "tgstat_code": "sg",
        "google_domain": "https://www.google.com.sg",
        "context": ["singapore tech", "SEA developers", "APAC remote"]
    },
    "ng": {
        "names": ["Nigeria", "Nigerian"],
        "tgstat_code": "ng",
        "google_domain": "https://www.google.com.ng",
        "context": ["nigeria tech", "lagos developers", "africa remote"]
    },
    "pk": {
        "names": ["Pakistan", "Pakistani"],
        "tgstat_code": "pk",
        "google_domain": "https://www.google.com.pk",
        "context": ["karachi tech", "lahore developers", "pakistan freelance"]
    },
}

# ─────────────────────────────────────────
# CATEGORY QUERIES — Broader Net
# ─────────────────────────────────────────
CATEGORY_QUERIES = {
    "direct_freelance": [
        "freelance developer telegram group",
        "freelance programmer telegram community",
        "software freelancer telegram",
        "remote developer for hire telegram",
        "hire developer telegram group",
    ],
    "qa_testing": [
        "QA automation telegram group",
        "software testing professionals telegram",
        "selenium playwright telegram community",
        "test engineer telegram group",
        "SDET community telegram",
    ],
    "job_boards": [
        "tech jobs telegram group",
        "remote developer jobs telegram",
        "software engineering jobs telegram",
        "IT jobs telegram channel",
        "programming projects telegram",
    ],
    "startup_entrepreneur": [
        "startup founders telegram group",
        "tech startup community telegram",
        "entrepreneur tech telegram",
        "startup hiring developers telegram",
        "saas founders telegram",
    ],
    "skill_specific": [
        "python developers telegram group",
        "nodejs developers telegram",
        "backend developers community telegram",
        "API developers telegram",
        "automation engineers telegram",
    ],
    "platform_specific": [
        "upwork freelancers telegram",
        "fiverr sellers telegram group",
        "freelancer community telegram",
        "remote work community telegram",
        "digital nomad developers telegram",
    ],
    "adjacent": [
        "web agency owners telegram",
        "CTO community telegram",
        "product managers telegram group",
        "digital agency telegram",
        "no code builders telegram",
    ],
}

# ─────────────────────────────────────────
# DAILY COUNTRY ROTATION
# ─────────────────────────────────────────
DAILY_COUNTRY_ROTATION = {
    "monday":    ["us", "uk", "ca"],
    "tuesday":   ["in", "ae", "sg"],
    "wednesday": ["de", "au", "ng"],
    "thursday":  ["us", "pk", "ca"],
    "friday":    ["uk", "in", "ae"],
    "saturday":  ["sg", "de", "au"],
    "sunday":    ["us", "uk", "in"],
}

# ─────────────────────────────────────────
# AGENT 3 — CONVERTER SYSTEM PROMPT
# ─────────────────────────────────────────
CONVERTER_SYSTEM_PROMPT = """
You are a professional assistant handling client inquiries for a freelance developer.

Developer's skills:
- Test Automation: Selenium, Playwright, Cypress
- QA pipeline setup and CI/CD automation
- API testing and validation
- Web scraping and data automation
- Python and Node.js backend development

Internal pricing reference (never share unless asked):
- Small script or automation task: $100–400
- QA setup or test suite: $500–1500
- Full backend project: $1000–5000
- Hourly rate: $25–45/hr

Conversation rules:
1. Always ask about their project BEFORE quoting any price
2. Ask: what they need, timeline, and rough budget (in that order)
3. Be conversational and warm — this is Telegram, not email
4. Keep replies SHORT — max 3 sentences per message
5. Never undersell or immediately discount
6. If they mention budget and timeline together → they are a HOT lead, add [HOT_LEAD] at the very end of your reply (hidden tag)
7. If they seem interested but vague → they are WARM, keep asking questions
8. If they are just browsing → stay friendly, don't push
9. Never say you are an AI or assistant — just respond naturally as the developer's representative
10. If asked something technical you don't know → say "let me check on that and get back to you"

Goal: Understand their need → build trust → close the deal at fair market rate.
"""

# ─────────────────────────────────────────
# HOT LEAD DETECTION KEYWORDS
# ─────────────────────────────────────────
HOT_LEAD_KEYWORDS = [
    "budget", "how much", "price", "cost", "rate",
    "timeline", "deadline", "urgent", "asap", "immediately",
    "hire", "contract", "project", "let's do it", "ready to start",
    "when can you start", "available", "per hour", "fixed price"
]