import asyncio
import random
import logging
import httpx
import re
from datetime import datetime
from telethon import TelegramClient, events
from telethon.tl.types import User

from config import (
    TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE,
    OPENROUTER_API_KEY, CONVERTER_MODEL, SESSION_FILE,
    DM_REPLY_MIN_DELAY, DM_REPLY_MAX_DELAY,
    ALERT_USERNAME, HOT_LEAD_KEYWORDS
)
from models import (
    get_conversation, save_conversation, append_message,
    update_lead_score, get_hot_leads
)

logging.basicConfig(
    filename="logs/converter.log",
    level=logging.INFO,
    format="%(asctime)s — %(message)s"
)
log = logging.getLogger("converter")


# ─────────────────────────────────────────
# ULTRA-HUMAN SYSTEM PROMPT
# ─────────────────────────────────────────

ENHANCED_SYSTEM_PROMPT = """
You are Alex, a freelance developer. This is YOUR Telegram account. You're chatting directly with potential clients.

YOUR SKILLS & EXPERTISE:
- Test Automation: Selenium, Playwright, Cypress, TestNG, Jest
- QA Engineering: Full test pipeline setup, CI/CD integration (Jenkins, GitHub Actions, GitLab CI)
- API Testing: Postman, REST Assured, automated API validation
- Backend Development: Python (Django, Flask, FastAPI), Node.js (Express, NestJS)
- Web Scraping: Beautiful Soup, Scrapy, Puppeteer, anti-bot bypass
- Automation: Task automation, data pipelines, workflow optimization
- Database: PostgreSQL, MongoDB, Redis
- Cloud: AWS, Docker, basic DevOps

PRICING FRAMEWORK (Your internal reference - never show this list):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PROJECT TYPE                    RANGE           TYPICAL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Simple script/automation        $100-$400       $250
Web scraper (basic)             $300-$800       $500
Web scraper (complex/anti-bot)  $800-$2000      $1200
Small test suite (5-10 tests)   $400-$900       $600
Full QA setup + CI/CD          $1000-$2500     $1500
API testing framework          $600-$1500      $900
Medium backend project         $1500-$4000     $2500
Large/ongoing project          $3000-$8000     $5000
Hourly rate                    $30-$50/hr      $40/hr
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CONVERSATION STAGES:

STAGE 1 — OPENING (Messages 1-2)
├─ Match their energy (if casual, be casual; if formal, be professional)
├─ Ask: "What's the project?" or "What do you need built?"
└─ Don't mention price yet

STAGE 2 — DISCOVERY (Messages 3-6)
├─ Ask these naturally (not all at once):
│  • What exactly needs to be built?
│  • What problem does this solve?
│  • What's the timeline?
│  • What's the budget?
│  • Any technical requirements?
└─ Probe deeper on vague answers

STAGE 3 — POSITIONING (Messages 7-10)
├─ Once you know scope + timeline + budget:
│  → Good budget: Confirm you can do it, share similar experience
│  → Low/unclear budget: Get ALL details, then tag [NEEDS_REVIEW]
│  → High budget: Match it confidently
├─ Show expertise: "Yeah I've built something similar with..."
├─ Suggest what you'll deliver
└─ Address concerns

STAGE 4 — CLOSING (Messages 11+)
├─ When they seem ready: Propose concrete next steps
├─ "I can have this done by [date]. Does that work?"
├─ "Let's do [X] for $[Y], I'll start this week"
├─ Get commitment: "Sound good?" "Should we move forward?"
└─ When they say YES → confirm details and tag [COMMITTED]

COMMITMENT SIGNALS (client is saying YES):
✅ "Let's do it"
✅ "Sounds good, let's start"
✅ "OK, go ahead"
✅ "When can you start?"
✅ "I agree to the price"
✅ "Perfect, let's proceed"
✅ Any clear agreement to move forward

When you detect commitment:
1. Confirm the agreement naturally
2. Summarize: scope, price, timeline
3. Mention next steps (you'll send them details, payment info, etc.)
4. Tag [COMMITTED] at the end

HOW TO SOUND HUMAN (Critical - client must never suspect):

DO:
✅ Use casual phrases: "Yeah", "Gotcha", "Makes sense", "Cool", "Sure thing"
✅ Vary your greetings: "Hey", "Hi", "Hey there", "What's up"
✅ Be brief - 1-3 sentences max
✅ Use natural transitions: "Before we dive into pricing...", "Quick question..."
✅ Make small typos occasionally (but rarely): "teh" → "the", miss a comma
✅ Use contractions: "I'm", "you're", "that's", "I'll", "doesn't"
✅ Add natural hesitation words: "probably", "maybe", "I think", "usually"
✅ Mirror their style (if they use emojis, you can too; if formal, stay formal)
✅ React naturally: "Oh interesting", "Hmm", "Ah got it"
✅ Ask follow-ups like a human: "Wait, so you need it to run daily or just once?"

DON'T:
❌ NEVER say: "I'm an AI", "I'm an assistant", "I'm here to help"
❌ NO corporate phrases: "I hope this message finds you well", "Dear", "Kind regards"
❌ NO overly perfect grammar - be natural
❌ NO bullet points in responses (this is chat, not email)
❌ NO numbered lists unless they specifically ask
❌ NO saying "Certainly", "Absolutely", "I'd be happy to" (too formal)
❌ NO apologizing excessively: "Sorry for the confusion", "Apologies"
❌ NO long paragraphs - break into multiple short messages if needed
❌ NO asking "How can I assist you today?" (sounds like customer service bot)

EXAMPLE NATURAL RESPONSES:

BAD (sounds like AI):
"Thank you for reaching out! I'd be happy to assist you with your web scraping project. Could you please provide more details about the specific requirements?"

GOOD (sounds human):
"Hey! Yeah I can help with that. What site are you looking to scrape?"

BAD:
"I understand your budget constraints. Let me see what I can do within your price range."

GOOD:
"Got it. Let me think about what's possible at that budget."

BAD:
"I have extensive experience with Selenium and have successfully completed similar projects."

GOOD:
"Yeah I've built scrapers like this before with Selenium, should be straightforward."

PRICING STRATEGY:

✅ Never quote immediately - always ask about scope first
✅ If budget is reasonable → confirm and move forward
✅ If budget is very low → don't reject, gather all info and tag [NEEDS_REVIEW]
✅ If no budget mentioned → ask: "What's your budget for this?"
✅ Offer options when possible: "Basic version for $X, or full-featured for $Y"
✅ For low budgets: "Let me see what I can do at that price" then [NEEDS_REVIEW]

TAGGING SYSTEM (invisible to client - always add at very end):

[HOT_LEAD] - They're interested and have budget, ready to close
- Has mentioned specific budget ($300+)
- Has timeline/urgency
- Asking when you can start
- Engaged in detailed discussion

[WARM_LEAD] - Engaged but not ready yet
- Multiple messages exchanged
- Asking detailed questions
- No budget mentioned yet
- Seems interested but exploring

[COLD_LEAD] - Low engagement
- Short replies
- "Just looking"
- Vague, no urgency
- Not progressing

[NEEDS_REVIEW] - You need human to make decision
- Budget mentioned but very low ($50 for complex work)
- Unclear/contradictory requirements
- Asking for something borderline unethical
- You're unsure how to proceed
- Major budget/scope mismatch

[COMMITTED] - CLIENT SAID YES! Project agreed upon
- They agreed to move forward
- Said "let's do it", "sounds good", "yes go ahead"
- Confirmed budget and timeline
- Ready to start
Important: When you tag [COMMITTED], summarize in your previous message:
- What you're building
- Price agreed
- Deadline/timeline
- Next steps

INFORMATION TO TRACK (mental notes throughout conversation):

PROJECT DETAILS:
- Name: [what they want built]
- Type: [scraper/QA/backend/bot/etc]
- Scope: [detailed requirements]
- Technical specs: [languages, platforms, integrations needed]
- Deliverables: [what exactly you'll hand over]

TIMELINE:
- Deadline: [specific date or timeframe]
- Urgency: [ASAP/flexible/specific date]
- Milestones: [if multi-phase project]

BUDGET:
- Amount: [agreed price]
- Payment terms: [upfront%, milestone-based, hourly]
- Currency: [USD assumed unless stated]

CLIENT INFO:
- Experience level: [first time hiring vs experienced]
- Communication style: [casual/formal]
- Red flags: [any concerns]

EXAMPLE FLOW - COMMITMENT:

Client: "Ok $800 works for me. When can you start?"
You: "Perfect! I can start this week and have it done in 7-10 days. So just to confirm: Amazon product scraper, 500 products daily, auto-updates to Google Sheet, includes anti-bot handling. I'll build it in Python with scheduled runs. Sound good? [HOT_LEAD]"

Client: "Yes let's do it"
You: "Awesome! So we're locked in at $800, delivery in 10 days. I'll send you a quick project agreement and payment details (30% upfront, 70% on delivery). I'll start building tomorrow and keep you updated on progress. Cool? [COMMITTED]"

NATURAL CONVERSATION EXAMPLES:

Opening:
- "Hey! What's up?"
- "Hi there, what do you need?"
- "Hey, saw your message - what's the project?"

Asking for details:
- "What site are we scraping?"
- "Just to clarify - you need this running daily or one-time?"
- "Wait, does it need to handle login or just public data?"

Showing expertise:
- "Yeah I've done this before with Playwright"
- "Scraped Amazon a bunch of times, their bot protection is tricky but doable"
- "I usually use rotating proxies for this kind of thing"

Discussing price:
- "What's your budget looking like?"
- "For something like that I'd usually charge around $500-800"
- "Let me think about what's doable at that price"

Closing:
- "I can knock this out in a week, works for you?"
- "Cool, let's do it"
- "I'll start on this tomorrow"

NOW RESPOND AS ALEX. You are not an AI assistant - you're a real developer having a normal Telegram conversation.
Keep it short, natural, and human.
Remember to tag at the end.
"""


# ─────────────────────────────────────────
# AI REPLY GENERATOR
# ─────────────────────────────────────────

async def generate_ai_reply(conversation_history: list) -> tuple[str, str, dict]:
    """
    Calls OpenRouter API with full conversation context.
    Returns: (reply_text, lead_score, extracted_info)
    """
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # Build message list
    messages = [{"role": "system", "content": ENHANCED_SYSTEM_PROMPT}]
    
    # Add conversation history (last 20 messages)
    for msg in conversation_history[-20:]:
        role = "assistant" if msg["role"] == "bot" else "user"
        messages.append({
            "role": role,
            "content": msg["content"]
        })
    
    payload = {
        "model": CONVERTER_MODEL,
        "messages": messages,
        "max_tokens": 300,
        "temperature": 0.8,  # Slightly higher for more natural variation
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            reply = response.json()["choices"][0]["message"]["content"].strip()
        
        # Extract lead score tags (invisible to user)
        lead_score = "cold"
        if "[COMMITTED]" in reply:
            lead_score = "committed"
            reply = reply.replace("[COMMITTED]", "").strip()
        elif "[HOT_LEAD]" in reply:
            lead_score = "hot"
            reply = reply.replace("[HOT_LEAD]", "").strip()
        elif "[WARM_LEAD]" in reply:
            lead_score = "warm"
            reply = reply.replace("[WARM_LEAD]", "").strip()
        elif "[NEEDS_REVIEW]" in reply:
            lead_score = "needs_review"
            reply = reply.replace("[NEEDS_REVIEW]", "").strip()
        elif "[COLD_LEAD]" in reply:
            lead_score = "cold"
            reply = reply.replace("[COLD_LEAD]", "").strip()
        else:
            # Auto-detect from keywords if not tagged
            lead_score = detect_lead_score(reply, conversation_history)
        
        # Extract project information
        extracted_info = extract_project_info(conversation_history)
        
        return reply, lead_score, extracted_info
        
    except Exception as e:
        log.error(f"OpenRouter API error: {e}")
        # Fallback reply (very human)
        return (
            "Hey! What's the project about?",
            "cold",
            {}
        )


def detect_lead_score(reply: str, history: list) -> str:
    """
    Fallback lead scoring based on conversation patterns
    """
    recent_messages = " ".join([m["content"].lower() for m in history[-7:]])
    
    # Committed signals
    commit_signals = [
        "let's do it", "sounds good", "let's start", "go ahead",
        "i agree", "yes let's", "perfect let's", "ok let's proceed"
    ]
    if any(signal in recent_messages for signal in commit_signals):
        return "committed"
    
    # Needs review signals
    very_low_budget = any([
        "$20" in recent_messages, "$30" in recent_messages,
        "$50" in recent_messages, "$80" in recent_messages,
    ])
    
    if very_low_budget and len(history) >= 3:
        return "needs_review"
    
    # Hot signals
    hot_signals = sum([
        "budget" in recent_messages,
        "timeline" in recent_messages or "deadline" in recent_messages,
        "when can you start" in recent_messages,
        "$" in recent_messages and not very_low_budget,
        len(history) >= 5,
    ])
    
    if hot_signals >= 3:
        return "hot"
    elif hot_signals >= 1 or len(history) >= 3:
        return "warm"
    else:
        return "cold"


def extract_project_info(conversation_history: list) -> dict:
    """
    Extracts structured information from conversation for alerts
    """
    full_text = " ".join([m["content"] for m in conversation_history])
    user_messages = " ".join([m["content"] for m in conversation_history if m["role"] == "user"])
    bot_messages = " ".join([m["content"] for m in conversation_history if m["role"] == "bot"])
    
    # Extract budget mentions
    budget_patterns = [
        r'\$(\d+(?:,\d{3})*)',
        r'(\d+)\s*(?:dollars|USD|usd|\$)',
        r'budget.*?(\d+)',
    ]
    budgets = []
    for pattern in budget_patterns:
        matches = re.findall(pattern, full_text, re.IGNORECASE)
        budgets.extend([m.replace(',', '') for m in matches])
    
    budget = f"${budgets[-1]}" if budgets else "Not mentioned"
    
    # Extract timeline/deadline
    timeline = "Not mentioned"
    timeline_patterns = [
        r'(\d+)\s*(?:days?|weeks?|months?)',
        r'(?:by|before|until)\s+([A-Za-z]+\s+\d+)',
        r'(?:in|within)\s+(\d+\s+\w+)',
    ]
    for pattern in timeline_patterns:
        matches = re.findall(pattern, full_text, re.IGNORECASE)
        if matches:
            timeline = matches[-1]
            break
    
    # Check for ASAP/urgent
    if any(word in full_text.lower() for word in ["asap", "urgent", "immediately", "today", "tomorrow", "this week"]):
        if timeline == "Not mentioned":
            timeline = "ASAP"
    
    # Detect project type
    project_type = "Unknown"
    project_keywords = {
        "Web Scraping": ["scrape", "scraper", "scraping", "crawl", "extract data"],
        "QA/Test Automation": ["test", "qa", "automation", "selenium", "playwright", "cypress", "testing"],
        "Backend Development": ["api", "backend", "database", "server", "django", "flask", "fastapi", "express"],
        "Bot Development": ["bot", "telegram bot", "discord bot", "chatbot"],
        "Web Development": ["website", "web app", "frontend", "react", "vue"],
        "Data Automation": ["automate", "automation", "pipeline", "workflow", "script"],
    }
    
    for proj_type, keywords in project_keywords.items():
        if any(keyword in full_text.lower() for keyword in keywords):
            project_type = proj_type
            break
    
    # Get scope (collect key requirements)
    scope_lines = []
    
    # Look for technical details
    tech_keywords = {
        "Language": ["python", "node", "javascript", "java"],
        "Platform": ["aws", "docker", "heroku", "cloud"],
        "Database": ["postgres", "mongodb", "mysql", "redis"],
        "Integration": ["google sheet", "api", "webhook", "slack"],
    }
    
    tech_details = []
    for category, keywords in tech_keywords.items():
        for keyword in keywords:
            if keyword in full_text.lower():
                tech_details.append(f"{keyword}")
    
    # Extract what they need built (from user messages)
    if user_messages:
        # Get sentences that describe what they need
        need_patterns = [
            r"i need (.*?)(?:\.|$)",
            r"looking for (.*?)(?:\.|$)",
            r"want (.*?)(?:\.|$)",
            r"require (.*?)(?:\.|$)",
        ]
        for pattern in need_patterns:
            matches = re.findall(pattern, user_messages.lower(), re.IGNORECASE)
            scope_lines.extend([m.strip()[:100] for m in matches if len(m.strip()) > 10])
    
    # Combine scope
    scope = " | ".join(scope_lines[:3]) if scope_lines else user_messages[:300]
    if tech_details:
        scope += f" | Tech: {', '.join(tech_details[:5])}"
    
    # Detect urgency
    urgency = "Low"
    if any(word in full_text.lower() for word in ["asap", "urgent", "immediately", "today", "tomorrow"]):
        urgency = "High"
    elif any(word in full_text.lower() for word in ["soon", "this week", "few days", "next week"]):
        urgency = "Medium"
    
    # Extract deliverables (what you'll hand over)
    deliverables = []
    deliverable_patterns = [
        r"deliver (.*?)(?:\.|$)",
        r"you'll get (.*?)(?:\.|$)",
        r"i'll (?:build|create|make) (.*?)(?:\.|$)",
    ]
    for pattern in deliverable_patterns:
        matches = re.findall(pattern, bot_messages.lower(), re.IGNORECASE)
        deliverables.extend([m.strip()[:80] for m in matches])
    
    deliverables_text = " | ".join(deliverables[:3]) if deliverables else "To be confirmed"
    
    # Payment terms detection
    payment_terms = "Not discussed"
    if "upfront" in full_text.lower() or "deposit" in full_text.lower():
        upfront_match = re.search(r'(\d+)%?\s*upfront', full_text.lower())
        if upfront_match:
            payment_terms = f"{upfront_match.group(1)}% upfront, rest on delivery"
        else:
            payment_terms = "Partial upfront, rest on delivery"
    elif "milestone" in full_text.lower():
        payment_terms = "Milestone-based"
    elif "hourly" in full_text.lower():
        payment_terms = "Hourly billing"
    
    # Experience level detection
    experience_level = "Unknown"
    if any(phrase in full_text.lower() for phrase in ["first time", "never hired", "new to this"]):
        experience_level = "First-time client"
    elif any(phrase in full_text.lower() for phrase in ["worked with", "previous developer", "have hired"]):
        experience_level = "Experienced client"
    
    return {
        "project_type": project_type,
        "scope": scope[:400],
        "budget": budget,
        "timeline": timeline,
        "urgency": urgency,
        "message_count": len(conversation_history),
        "deliverables": deliverables_text[:300],
        "payment_terms": payment_terms,
        "experience_level": experience_level,
    }


# ─────────────────────────────────────────
# ALERT SYSTEM (Enhanced with Commitment)
# ─────────────────────────────────────────

async def send_committed_alert(client: TelegramClient, user_info: dict, conversation: dict, project_info: dict):
    """
    🎉 CLIENT AGREED TO WORK! Send full project brief
    """
    if not ALERT_USERNAME:
        log.warning("ALERT_USERNAME not configured, skipping alert")
        return
    
    try:
        name = user_info.get("name", "Unknown")
        user_id = user_info.get("user_id", "Unknown")
        username = user_info.get("username", "No username")
        
        # Get full conversation context
        all_messages = conversation["messages"]
        recent_context = "\n".join([
            f"{'🤖 You' if m['role'] == 'bot' else f'👤 {name}'}: {m['content']}"
            for m in all_messages[-8:]
        ])
        
        # Create professional project brief
        alert = (
            f"🎉🎉🎉 PROJECT SECURED! 🎉🎉🎉\n"
            f"{'='*50}\n\n"
            f"CLIENT DETAILS:\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 Name: {name}\n"
            f"📱 Username: @{username}\n"
            f"🆔 Telegram ID: {user_id}\n"
            f"💼 Experience: {project_info.get('experience_level', 'Unknown')}\n\n"
            f"PROJECT BRIEF:\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📦 Project Type: {project_info.get('project_type', 'Unknown')}\n"
            f"📋 Scope:\n   {project_info.get('scope', 'See conversation')}\n\n"
            f"💰 AGREED BUDGET: {project_info.get('budget', 'TBD')}\n"
            f"💳 Payment Terms: {project_info.get('payment_terms', 'Not discussed')}\n\n"
            f"⏰ DEADLINE: {project_info.get('timeline', 'TBD')}\n"
            f"🚨 Urgency: {project_info.get('urgency', 'Unknown')}\n\n"
            f"📦 DELIVERABLES:\n   {project_info.get('deliverables', 'To be confirmed')}\n\n"
            f"CONVERSATION SUMMARY:\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{recent_context}\n\n"
            f"{'='*50}\n"
            f"✅ NEXT STEPS:\n"
            f"1. Open chat with @{username}\n"
            f"2. Send project agreement/contract\n"
            f"3. Share payment details ({project_info.get('payment_terms', 'TBD')})\n"
            f"4. Confirm delivery date: {project_info.get('timeline', 'TBD')}\n"
            f"5. Start development!\n\n"
            f"🚀 Time to deliver great work and get paid!\n"
            f"💬 Reply to @{username} now to finalize details."
        )
        
        await client.send_message(ALERT_USERNAME, alert)
        log.info(f"🎉 COMMITTED alert sent for {name} - ${project_info.get('budget', 'N/A')}")
        
        # Mark as alerted
        conversation["alerted"] = True
        conversation["alert_type"] = "committed"
        conversation["project_secured_at"] = datetime.now().isoformat()
        save_conversation(user_id, conversation)
        
    except Exception as e:
        log.error(f"Failed to send committed alert: {e}")


async def send_hot_lead_alert(client: TelegramClient, user_info: dict, conversation: dict, project_info: dict):
    """
    🔥 HOT LEAD - Almost ready to close
    """
    if not ALERT_USERNAME:
        log.warning("ALERT_USERNAME not configured, skipping alert")
        return
    
    try:
        name = user_info.get("name", "Unknown")
        user_id = user_info.get("user_id", "Unknown")
        username = user_info.get("username", "No username")
        
        last_messages = conversation["messages"][-5:]
        context = "\n".join([
            f"{'🤖' if m['role'] == 'bot' else '👤'} {m['content'][:150]}"
            for m in last_messages
        ])
        
        alert = (
            f"🔥 HOT LEAD - ALMOST CLOSED!\n"
            f"{'='*40}\n\n"
            f"👤 CLIENT INFO:\n"
            f"   Name: {name}\n"
            f"   Username: @{username}\n"
            f"   User ID: {user_id}\n\n"
            f"📋 PROJECT DETAILS:\n"
            f"   Type: {project_info.get('project_type', 'Unknown')}\n"
            f"   Budget: {project_info.get('budget', 'Not mentioned')}\n"
            f"   Timeline: {project_info.get('timeline', 'Not mentioned')}\n"
            f"   Urgency: {project_info.get('urgency', 'Unknown')}\n"
            f"   Messages: {project_info.get('message_count', 0)}\n\n"
            f"💬 RECENT CONVERSATION:\n{context}\n\n"
            f"🎯 STATUS: Lead is engaged and discussing details.\n"
            f"AI is working on closing the deal.\n\n"
            f"💡 Consider jumping in if you want to close personally."
        )
        
        await client.send_message(ALERT_USERNAME, alert)
        log.info(f"🔥 Hot lead alert sent for {name}")
        
        conversation["alerted"] = True
        conversation["alert_type"] = "hot"
        save_conversation(user_id, conversation)
        
    except Exception as e:
        log.error(f"Failed to send hot lead alert: {e}")


async def send_review_needed_alert(client: TelegramClient, user_info: dict, conversation: dict, project_info: dict):
    """
    ⚠️ NEEDS YOUR DECISION - Low budget or unclear
    """
    if not ALERT_USERNAME:
        log.warning("ALERT_USERNAME not configured, skipping alert")
        return
    
    try:
        name = user_info.get("name", "Unknown")
        user_id = user_info.get("user_id", "Unknown")
        username = user_info.get("username", "No username")
        
        last_messages = conversation["messages"][-8:]
        context = "\n".join([
            f"{'🤖' if m['role'] == 'bot' else '👤'} {m['content'][:150]}"
            for m in last_messages
        ])
        
        # Determine why review is needed
        budget = project_info.get('budget', 'Not mentioned')
        reason = "Budget/scope mismatch or unclear requirements"
        
        if budget != "Not mentioned":
            try:
                budget_amount = int(budget.replace('$', '').replace(',', ''))
                if budget_amount < 100:
                    reason = f"⚠️ Low budget: {budget} (seems low for scope)"
                elif budget_amount < 200:
                    reason = f"⚠️ Budget {budget} may be low depending on complexity"
            except:
                pass
        
        alert = (
            f"⚠️ LEAD NEEDS YOUR DECISION\n"
            f"{'='*40}\n\n"
            f"👤 CLIENT INFO:\n"
            f"   Name: {name}\n"
            f"   Username: @{username}\n"
            f"   User ID: {user_id}\n\n"
            f"📋 PROJECT DETAILS:\n"
            f"   Type: {project_info.get('project_type', 'Unknown')}\n"
            f"   Scope: {project_info.get('scope', 'See conversation')[:200]}\n"
            f"   Budget: {project_info.get('budget', 'Not mentioned')}\n"
            f"   Timeline: {project_info.get('timeline', 'Not mentioned')}\n"
            f"   Urgency: {project_info.get('urgency', 'Unknown')}\n"
            f"   Messages: {project_info.get('message_count', 0)}\n\n"
            f"🤔 WHY REVIEW NEEDED:\n"
            f"   {reason}\n\n"
            f"💬 FULL CONVERSATION:\n{context}\n\n"
            f"❓ YOUR OPTIONS:\n"
            f"   1️⃣ Accept at their budget (if doable)\n"
            f"   2️⃣ Negotiate higher price\n"
            f"   3️⃣ Offer reduced scope at their budget\n"
            f"   4️⃣ Politely decline\n\n"
            f"💬 Reply to @{username} to take over conversation."
        )
        
        await client.send_message(ALERT_USERNAME, alert)
        log.info(f"⚠️ Review needed alert sent for {name}")
        
        conversation["alerted"] = True
        conversation["alert_type"] = "review"
        save_conversation(user_id, conversation)
        
    except Exception as e:
        log.error(f"Failed to send review alert: {e}")


async def send_warm_lead_alert(client: TelegramClient, user_info: dict, conversation: dict, project_info: dict):
    """
    🟡 WARM LEAD - Engaged but not ready yet
    """
    if not ALERT_USERNAME:
        return
    
    try:
        # Only send if 4+ messages and not alerted before
        if conversation.get("alerted") or project_info.get("message_count", 0) < 4:
            return
        
        name = user_info.get("name", "Unknown")
        username = user_info.get("username", "No username")
        
        last_messages = conversation["messages"][-4:]
        context = "\n".join([
            f"{'🤖' if m['role'] == 'bot' else '👤'} {m['content'][:120]}"
            for m in last_messages
        ])
        
        alert = (
            f"🟡 WARM LEAD - ENGAGED\n"
            f"{'='*40}\n\n"
            f"👤 {name} (@{username})\n"
            f"📋 {project_info.get('project_type', 'Project type unknown')}\n"
            f"💰 Budget: {project_info.get('budget', 'Not mentioned yet')}\n"
            f"💬 Messages: {project_info.get('message_count', 0)}\n\n"
            f"Recent:\n{context}\n\n"
            f"ℹ️ Lead is engaged but hasn't committed.\n"
            f"AI is nurturing the conversation."
        )
        
        await client.send_message(ALERT_USERNAME, alert)
        log.info(f"🟡 Warm lead alert sent for {name}")
        
        conversation["alerted"] = True
        conversation["alert_type"] = "warm"
        save_conversation(user_id, conversation)
        
    except Exception as e:
        log.error(f"Failed to send warm lead alert: {e}")


# ─────────────────────────────────────────
# TYPING SIMULATION
# ─────────────────────────────────────────

async def human_like_delay(message_length: int):
    """
    Simulates realistic human typing time
    """
    read_time = random.uniform(1.0, 2.5)
    typing_speed = message_length / random.uniform(35, 55)  # chars per second
    think_time = random.uniform(0.3, 1.2)
    
    total_delay = read_time + typing_speed + think_time
    total_delay = max(DM_REPLY_MIN_DELAY, min(total_delay, DM_REPLY_MAX_DELAY))
    
    await asyncio.sleep(total_delay)


# ─────────────────────────────────────────
# MAIN DM HANDLER
# ─────────────────────────────────────────

async def handle_dm(event, client: TelegramClient):
    """
    Processes incoming DM and generates AI response
    """
    try:
        sender = await event.get_sender()
        
        # Ignore non-user messages
        if not isinstance(sender, User):
            return
        
        user_id = sender.id
        username = sender.username or "no_username"
        name = f"{sender.first_name or ''} {sender.last_name or ''}".strip() or "Unknown"
        message_text = event.message.message
        
        # Ignore empty messages
        if not message_text or message_text.strip() == "":
            return
        
        log.info(f"📨 Received from {name} (@{username}): {message_text[:60]}...")
        
        # Load conversation
        conversation = get_conversation(user_id)
        conversation["name"] = name
        conversation["username"] = username
        
        # Save user message
        append_message(user_id, "user", message_text, name)
        
        # Show typing indicator
        async with client.action(user_id, 'typing'):
            # Human-like delay
            await human_like_delay(len(message_text))
            
            # Generate AI reply
            conversation = get_conversation(user_id)
            reply, lead_score, project_info = await generate_ai_reply(conversation["messages"])
            
            # Update lead score
            previous_score = conversation.get("lead_score", "cold")
            update_lead_score(user_id, lead_score)
            
            if lead_score != previous_score:
                log.info(f"📊 Score: {previous_score} → {lead_score} ({name})")
            
            # Send reply
            await client.send_message(user_id, reply)
            
            # Save bot response
            append_message(user_id, "bot", reply)
            
            log.info(f"💬 Sent to {name}: {reply[:60]}... [{lead_score}]")
            
            # Send appropriate alerts
            user_info = {
                "user_id": user_id,
                "username": username,
                "name": name
            }
            
            # COMMITTED = Highest priority
            if lead_score == "committed" and not conversation.get("alerted"):
                await send_committed_alert(client, user_info, conversation, project_info)
                
            # HOT LEAD
            elif lead_score == "hot" and not conversation.get("alerted"):
                await send_hot_lead_alert(client, user_info, conversation, project_info)
                
            # NEEDS REVIEW
            elif lead_score == "needs_review" and not conversation.get("alerted"):
                await send_review_needed_alert(client, user_info, conversation, project_info)
                
            # WARM LEAD (lighter notification)
            elif lead_score == "warm" and not conversation.get("alerted"):
                await send_warm_lead_alert(client, user_info, conversation, project_info)
                
    except Exception as e:
        log.error(f"❌ Error handling DM: {e}")
        try:
            await event.reply("Hey, give me a sec - message didn't come through properly. Can you resend?")
        except:
            pass


# ─────────────────────────────────────────
# ANALYTICS & REPORTING
# ─────────────────────────────────────────

def get_conversion_stats() -> dict:
    """
    Returns statistics about conversations and lead quality
    """
    from models import load_conversations
    
    convos = load_conversations()
    
    if not convos:
        return {
            "total_conversations": 0,
            "committed": 0,
            "hot_leads": 0,
            "warm_leads": 0,
            "cold_leads": 0,
            "needs_review": 0,
            "avg_messages_per_convo": 0,
            "conversion_rate": 0,
        }
    
    total = len(convos)
    committed = len([c for c in convos.values() if c.get("lead_score") == "committed"])
    hot = len([c for c in convos.values() if c.get("lead_score") == "hot"])
    warm = len([c for c in convos.values() if c.get("lead_score") == "warm"])
    cold = len([c for c in convos.values() if c.get("lead_score") == "cold"])
    review = len([c for c in convos.values() if c.get("lead_score") == "needs_review"])
    
    total_messages = sum(len(c.get("messages", [])) for c in convos.values())
    avg_messages = total_messages / total if total > 0 else 0
    
    return {
        "total_conversations": total,
        "committed": committed,
        "hot_leads": hot,
        "warm_leads": warm,
        "cold_leads": cold,
        "needs_review": review,
        "avg_messages_per_convo": round(avg_messages, 1),
        "conversion_rate": round((committed / total * 100), 1) if total > 0 else 0,
    }


def print_stats():
    """
    Prints current conversion statistics
    """
    stats = get_conversion_stats()
    
    print("\n" + "="*50)
    print("📊 CONVERSION STATS")
    print("="*50)
    print(f"Total conversations: {stats['total_conversations']}")
    print(f"🎉 COMMITTED:        {stats['committed']} (Projects secured!)")
    print(f"🔥 Hot leads:        {stats['hot_leads']}")
    print(f"🟡 Warm leads:       {stats['warm_leads']}")
    print(f"⚠️  Needs review:     {stats['needs_review']}")
    print(f"❄️  Cold leads:       {stats['cold_leads']}")
    print(f"💬 Avg messages:     {stats['avg_messages_per_convo']}")
    print(f"📈 Conversion rate:  {stats['conversion_rate']}%")
    print("="*50 + "\n")


def review_conversations(filter_by: str = "all"):
    """
    Print conversations for manual review
    """
    from models import load_conversations
    
    convos = load_conversations()
    
    if not convos:
        print("No conversations yet.")
        return
    
    filtered = convos
    if filter_by != "all":
        filtered = {k: v for k, v in convos.items() if v.get("lead_score") == filter_by}
    
    print(f"\n📋 {len(filtered)} conversations (filter: {filter_by})")
    print("="*60)
    
    for user_id, convo in filtered.items():
        name = convo.get("name", "Unknown")
        username = convo.get("username", "no_username")
        score = convo.get("lead_score", "unknown")
        msg_count = len(convo.get("messages", []))
        last_active = convo.get("last_active", "Unknown")
        
        score_emoji = {
            "committed": "🎉",
            "hot": "🔥",
            "warm": "🟡",
            "cold": "❄️",
            "needs_review": "⚠️"
        }.get(score, "❓")
        
        print(f"\n{score_emoji} {name} (@{username})")
        print(f"   Score: {score.upper()}")
        print(f"   Messages: {msg_count}")
        print(f"   Last: {last_active}")
        
        messages = convo.get("messages", [])[-2:]
        for msg in messages:
            role_emoji = "🤖" if msg["role"] == "bot" else "👤"
            print(f"   {role_emoji} {msg['content'][:80]}...")
        
        print("-"*60)


# ─────────────────────────────────────────
# STANDALONE RUNNER
# ─────────────────────────────────────────

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        
        if cmd == "stats":
            print_stats()
        elif cmd == "review":
            filter_by = sys.argv[2] if len(sys.argv) > 2 else "all"
            review_conversations(filter_by)
        else:
            print("\n📖 Usage:")
            print("  python converter.py                  # Run converter daemon")
            print("  python converter.py stats            # Show statistics")
            print("  python converter.py review           # Review all conversations")
            print("  python converter.py review committed # Review secured projects")
            print("  python converter.py review hot       # Review hot leads")
            print("  python converter.py review needs_review # Review pending decisions\n")
    else: # This file is now primarily for analytics, not running the agent.
        print("This script is for analytics. To run the converter agent, use 'python main.py'")
        print_stats()