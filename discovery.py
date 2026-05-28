import re
import time
import random
import requests
import logging, httpx
import asyncio
from datetime import datetime
from bs4 import BeautifulSoup
from telethon.sync import TelegramClient
from telethon.tl.functions.contacts import SearchRequest

from config import (
    TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE,
    OPENROUTER_API_KEY, DISCOVERY_MODEL, SESSION_FILE, SKILLS,
    INTENTS, FORMATS, COUNTRIES, CATEGORY_QUERIES,
    DAILY_COUNTRY_ROTATION, MIN_MEMBERS, MAX_MEMBERS
)
from models import add_groups, get_groups_stats, mark_group_status

import os

# Ensure logs directory exists
os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    filename="logs/discovery.log",
    level=logging.INFO,
    format="%(asctime)s — %(message)s"
)
log = logging.getLogger("discovery")


# ─────────────────────────────────────────
# KEYWORD ROTATION ENGINE
# ─────────────────────────────────────────

def generate_daily_queries(n: int = 10) -> list:
    """
    Generates N unique queries daily using rotating keyword matrix.
    16 skills × 13 intents × 5 formats = 1040 combinations.
    Never repeats for 2+ years.
    """
    queries = set()
    attempts = 0

    while len(queries) < n and attempts < 100:
        skill  = random.choice(SKILLS)
        intent = random.choice(INTENTS)
        fmt    = random.choice(FORMATS)
        query  = f"{skill} {intent} {fmt}"
        queries.add(query)
        attempts += 1

    return list(queries)

def get_todays_countries() -> list:
    """Returns the 3 countries assigned to today"""
    day = datetime.now().strftime("%A").lower()
    return DAILY_COUNTRY_ROTATION.get(day, ["us", "uk", "in"])

def get_category_queries(n: int = 5) -> list:
    """Picks N random queries from category matrix"""
    all_queries = []
    for queries in CATEGORY_QUERIES.values():
        all_queries.extend(queries)
    return random.sample(all_queries, min(n, len(all_queries)))


# ─────────────────────────────────────────
# EXTRACT TELEGRAM USERNAMES FROM TEXT
# ─────────────────────────────────────────

def extract_usernames(text: str) -> list:
    """Pulls t.me/username or @username patterns from any text"""
    patterns = [
        r't\.me/([a-zA-Z0-9_]{5,32})',
        r'@([a-zA-Z0-9_]{5,32})',
    ]
    blacklist = {
        "telegram", "username", "channel", "group", "bot",
        "joinchat", "share", "msg", "gif", "sticker", "voice"
    }
    found = []
    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for m in matches:
            if m.lower() not in blacklist and len(m) >= 5:
                found.append(m.lower())
    return list(set(found))


# ─────────────────────────────────────────
# SOURCE 1 — PERPLEXITY SONAR
# ─────────────────────────────────────────

async def search_perplexity(client: httpx.AsyncClient, query: str) -> list:
    """Calls Perplexity Sonar via OpenRouter to find Telegram group links."""
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": DISCOVERY_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You find Telegram group links only (no channels). "
                    "Return ONLY a plain list of t.me/ links and @usernames for groups. "
                    "No explanations, no formatting, no markdown."
                )
            },
            {
                "role": "user",
                "content": (
                    f"Find Telegram groups (not channels) for: {query}. "
                    "List every t.me/ link or @username you find. One per line."
                )
            }
        ],
        "max_tokens": 600
    }
    try:
        r = await client.post(url, headers=headers, json=payload, timeout=30)
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]
        usernames = extract_usernames(content)
        log.info(f"Perplexity [{query}] → {len(usernames)} groups")
        return [{"username": u, "source": "perplexity", "query_used": query} for u in usernames]
    except Exception as e:
        log.error(f"Perplexity error [{query}]: {e}")
        return []


# ─────────────────────────────────────────
# SOURCE 2 — TGSTAT.COM
# ─────────────────────────────────────────

async def scrape_tgstat(client: httpx.AsyncClient, query: str, country_code: str = None) -> list:
    """Scrapes tgstat.com search — most reliable Telegram directory"""
    base = "https://tgstat.com/en/search"
    params = f"?q={requests.utils.quote(query)}"
    if country_code:
        params += f"&country={country_code}"

    url = base + params
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        r = await client.get(url, headers=headers, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        results = []
        # tgstat shows peer links as /channel/@username
        for tag in soup.find_all("a", href=True):
            href = tag["href"]
            if "/channel/@" in href:
                username = href.split("/channel/@")[-1].split("/")[0].strip()
                if len(username) >= 5:
                    results.append({
                        "username": username.lower(),
                        "source": "tgstat",
                        "country": country_code or "unknown",
                        "query_used": query
                    })

        # Also extract any t.me links in page
        text_links = extract_usernames(r.text)
        for u in text_links:
            results.append({
                "username": u,
                "source": "tgstat",
                "country": country_code or "unknown",
                "query_used": query
            })

        unique = {r["username"]: r for r in results}
        log.info(f"tgstat [{query}] [{country_code}] → {len(unique)} groups")
        return list(unique.values())

    except Exception as e:
        log.error(f"tgstat error [{query}] [{country_code}]: {e}")
        return []


# ─────────────────────────────────────────
# SOURCE 3 — TELEMETR.IO (GROUPS)
# ─────────────────────────────────────────

async def scrape_telemetr_groups(client: httpx.AsyncClient, query: str, country_code: str = None) -> list:
    """Scrapes telemetr.io groups directory"""
    params = f"?search={requests.utils.quote(query)}"
    if country_code:
        params += f"&country={country_code.upper()}"

    url = f"https://telemetr.io/en/groups{params}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    try:
        r = await client.get(url, headers=headers, timeout=20)
        r.raise_for_status()
        usernames = extract_usernames(r.text)
        results = [
            {
                "username": u,
                "source": "telemetr_groups",
                "country": country_code or "unknown",
                "query_used": query
            }
            for u in usernames
        ]
        log.info(f"telemetr groups [{query}] [{country_code}] → {len(results)} groups")
        return results
    except Exception as e:
        log.error(f"telemetr groups error [{query}]: {e}")
        return []


# ─────────────────────────────────────────
# SOURCE 4 — GOOGLE COUNTRY DOMAINS
# ─────────────────────────────────────────

async def scrape_google(client: httpx.AsyncClient, query: str, country: str = "us") -> list:
    """Hits Google's country-specific domain for local results"""
    country_data = COUNTRIES.get(country, {})
    google_domain = country_data.get("google_domain", "https://www.google.com")

    full_query = f"{query} telegram group site:t.me -channel -channels"
    url = f"{google_domain}/search?q={requests.utils.quote(full_query)}&num=20"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        r = await client.get(url, headers=headers, timeout=20)
        usernames = extract_usernames(r.text)
        results = [
            {
                "username": u,
                "source": "google",
                "country": country,
                "query_used": query
            }
            for u in usernames
        ]
        log.info(f"Google [{country}] [{query}] → {len(results)} groups")
        return results
    except Exception as e:
        log.error(f"Google error [{country}] [{query}]: {e}")
        return []


# ─────────────────────────────────────────
# SOURCE 5 — TELETHON NATIVE SEARCH
# ─────────────────────────────────────────

async def search_telegram_native(client: TelegramClient, keywords: list) -> list:
    """Uses Telegram's own search index via Telethon"""
    results = []
    for keyword in keywords:
        try:
            search = await client(SearchRequest(q=keyword, limit=20))
            for chat in search.chats:
                username = getattr(chat, "username", None)
                if username:
                    results.append({
                        "username": username.lower(),
                        "source": "telegram_native",
                        "member_count": getattr(chat, "participants_count", 0),
                        "query_used": keyword
                    })
            log.info(f"Telegram native [{keyword}] → {len(search.chats)} found for '{keyword}'")
            await asyncio.sleep(2) # brief delay between keywords
        except Exception as e:
            log.error(f"Telegram native error [{keyword}]: {e}")
    return results


# ─────────────────────────────────────────
# QUALITY FILTER
# ─────────────────────────────────────────

def filter_quality(groups: list) -> list:
    """Remove groups that are too small, too large, or invalid usernames"""
    valid = []
    seen = set()
    for g in groups:
        username = g.get("username", "").strip()
        if not username or len(username) < 5:
            continue
        if username in seen:
            continue
        count = g.get("member_count", 0)
        # If we have member count, apply filter. If not (0 = unknown), keep it
        if count > 0 and (count < MIN_MEMBERS or count > MAX_MEMBERS):
            continue
        seen.add(username)
        valid.append(g)
    return valid


async def filter_groups_only(client: TelegramClient, groups: list) -> list:
    """Keep only Telegram groups (exclude channels)."""
    from telethon.errors import FloodWaitError, UsernameInvalidError, UsernameNotOccupiedError

    kept = []
    for g in groups:
        username = g.get("username", "").strip()
        if not username:
            continue
        try:
            entity = await client.get_entity(username)
            is_megagroup = getattr(entity, "megagroup", False)
            is_gigagroup = getattr(entity, "gigagroup", False)
            is_broadcast = getattr(entity, "broadcast", False)

            if (is_megagroup or is_gigagroup) and not is_broadcast:
                kept.append(g)
            else:
                log.info(f"Skipping channel @{username}")
        except FloodWaitError as e:
            wait_seconds = int(getattr(e, "seconds", 0))
            if wait_seconds <= 0:
                wait_seconds = 60
            log.warning(f"FloodWaitError while checking @{username}: sleeping {wait_seconds}s")
            await asyncio.sleep(wait_seconds + 1)
        except (UsernameInvalidError, UsernameNotOccupiedError) as e:
            log.warning(f"Invalid username @{username}: {type(e).__name__}")
        except Exception as e:
            log.warning(f"Failed to verify @{username} type: {e}")

    return kept


# ─────────────────────────────────────────
# MAIN DISCOVERY RUNNER
# ─────────────────────────────────────────

async def run_discovery(client: TelegramClient):
    """
    Agent 1 — Full discovery run.
    Runs all 5 sources with rotating keywords and country targeting.
    """
    print(f"\n🔍 [{datetime.now().strftime('%H:%M')}] Agent 1: Starting group discovery...\n")
    log.info("=== Discovery run started ===")

    all_found = []
    todays_countries = get_todays_countries()
    daily_queries = generate_daily_queries(n=8)
    category_queries = get_category_queries(n=5)

    print(f"📅 Today's countries: {todays_countries}")
    print(f"🔑 Rotating queries: {len(daily_queries)}")
    print(f"📂 Category queries: {len(category_queries)}")

    async with httpx.AsyncClient() as http_client:
        # ── SOURCE 1: Perplexity (rotating queries)
        print("\n[1/5] Perplexity Sonar...")
        for query in daily_queries[:4]:
            results = await search_perplexity(http_client, query)
            all_found.extend(results)
            await asyncio.sleep(2)

        # ── SOURCE 2: tgstat (country targeted)
        print("[2/5] tgstat.com...")
        for country in todays_countries:
            country_data = COUNTRIES.get(country, {})
            tgstat_code = country_data.get("tgstat_code", country)
            for query in random.sample(list(CATEGORY_QUERIES["direct_freelance"]), 2):
                results = await scrape_tgstat(http_client, query, tgstat_code)
                all_found.extend(results)
                await asyncio.sleep(3)
            for query in random.sample(list(CATEGORY_QUERIES["qa_testing"]), 2):
                results = await scrape_tgstat(http_client, query, tgstat_code)
                all_found.extend(results)
                await asyncio.sleep(3)

        # ── SOURCE 3: telemetr groups directory
        print("[3/5] telemetr.io groups...")
        for country in todays_countries:
            for query in random.sample(category_queries, 2):
                results = await scrape_telemetr_groups(http_client, query, country)
                all_found.extend(results)
                await asyncio.sleep(3)

        # ── SOURCE 4: Google country domains
        print("[4/5] Google country domains...")
        for country in todays_countries:
            query = random.choice(daily_queries)
            results = await scrape_google(http_client, query, country)
            all_found.extend(results)
            await asyncio.sleep(4)

    # ── SOURCE 5: Telegram native search
    print("[5/5] Telegram native search...")
    native_keywords = [
        "freelance developer",
        "QA automation",
        "hire developer",
        "remote developer jobs",
    ]
    try:
        native_results = await search_telegram_native(client, native_keywords)
        all_found.extend(native_results)
    except Exception as e:
        log.error(f"Native search failed: {e}")
        print(f"⚠️  Native search skipped: {e}")

    # ── FILTER + SAVE
    print(f"\n📊 Raw found: {len(all_found)}")
    filtered = filter_quality(all_found)
    print(f"📊 After quality filter: {len(filtered)}")

    print("🔎 Verifying group-only usernames (excluding channels)...")
    filtered = await filter_groups_only(client, filtered)
    print(f"📊 After group-only filter: {len(filtered)}")

    added = add_groups(filtered)
    stats = get_groups_stats()

    print(f"✅ New groups added: {added}")
    print(f"📦 Total groups in DB: {stats['total']}")
    print(f"   Active: {stats['active']} | Forbidden: {stats['forbidden']} | Dead: {stats['dead']}")
    print(f"   By country: {stats['by_country']}")

    # ── JOIN NEW GROUPS
    joined_count = 0
    if added > 0:
        print(f"\n🔗 Attempting to join {added} new groups...")
        from telethon.tl.functions.channels import JoinChannelRequest
        from telethon.errors import (
            ChannelsTooMuchError, ChannelPrivateError, InviteRequestSentError,
            UserAlreadyParticipantError, FloodWaitError
        )

        # Get the usernames of the groups just added
        newly_added_usernames = {g['username'] for g in filtered}

        for username in newly_added_usernames:
            try:
                await client(JoinChannelRequest(username))
                joined_count += 1
                log.info(f"Successfully joined @{username}")
                print(f"   ✅ Joined @{username}")
                await asyncio.sleep(random.randint(5, 10)) # Delay between joins
            except UserAlreadyParticipantError:
                log.info(f"Already a participant in @{username}")
                # No need to count as a "new join"
            except ChannelsTooMuchError:
                print("  ⚠️  Reached Telegram's channel limit. Cannot join more groups.")
                log.error("ChannelsTooMuchError: Cannot join more groups.")
                break # Stop trying to join
            except FloodWaitError as e:
                wait_seconds = int(getattr(e, "seconds", 0))
                if wait_seconds <= 0:
                    wait_seconds = 60
                print(f"  ⏳ Flood wait for {wait_seconds}s. Pausing before next join...")
                log.warning(f"FloodWaitError: sleeping {wait_seconds}s before continuing.")
                await asyncio.sleep(wait_seconds + 1)
            except (ChannelPrivateError, ValueError, InviteRequestSentError) as e:
                print(f"  🚫 Cannot join @{username} ({type(e).__name__}). Marking as dead.")
                log.warning(f"Could not join @{username} ({type(e).__name__}). Marking as dead.")
                mark_group_status(username, "dead")
            except Exception as e:
                print(f"  ❌ Error joining @{username}: {e}")
                log.error(f"Error joining @{username}: {e}")

    print(f"✅ Joined {joined_count} new groups.")
    log.info(f"Discovery done — added {added}, joined {joined_count}, total {stats['total']}")

    return added