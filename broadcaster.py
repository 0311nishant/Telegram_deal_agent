import asyncio
import random
import logging
from datetime import datetime
from telethon import TelegramClient
from telethon.errors import (
    FloodWaitError,
    ChatWriteForbiddenError,
    UserBannedInChannelError,
    ChannelPrivateError,
    UsernameNotOccupiedError,
    UsernameInvalidError,
)

from config import (
    TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE,
    SKILL_MESSAGE, SESSION_FILE,
    MIN_DELAY_BETWEEN_GROUPS, MAX_DELAY_BETWEEN_GROUPS
)
from models import (
    get_active_groups, mark_group_status, update_group_sent,
    log_broadcast
)

logging.basicConfig(
    filename="logs/broadcaster.log",
    level=logging.INFO,
    format="%(asctime)s — %(message)s"
)
log = logging.getLogger("broadcaster")


async def broadcast(slot: str, client: TelegramClient):
    """
    Agent 2 — Sends fixed SKILL_MESSAGE to all active, joined groups.
    Rate limited with human-like delays to avoid flood detection.
    slot: "morning" or "evening"
    """
    print(f"\n📢 [{datetime.now().strftime('%H:%M')}] Agent 2: {slot.upper()} broadcast starting...\n")
    log.info(f"=== {slot.upper()} broadcast started ===")

    # Get all *active* discovered group usernames from our DB to use as a filter
    active_groups_from_db = get_active_groups()
    if not active_groups_from_db:
        print("⚠️  No active groups in database. Run Agent 1 first.")
        log.warning("No active groups found in DB")
        return
    active_usernames_db = {g['username'].lower() for g in active_groups_from_db}

    # Get all groups the bot has actually joined and filter them
    print("📡 Checking all joined groups against database...")
    groups = []
    async for dialog in client.iter_dialogs():
        if (dialog.is_group or dialog.is_channel) and not dialog.is_user:
            username = getattr(dialog.entity, 'username', None)
            if username and username.lower() in active_usernames_db:
                groups.append(dialog.entity)

    if not groups:
        print("⚠️  No discovered groups have been joined yet. Run Agent 1 to find and join groups.")
        log.warning("No joined groups match the discovered groups in DB")
        return

    print(f"📋 Found {len(groups)} joined groups to message.\n")

    sent = skipped = failed = 0

    try:
        for i, group_entity in enumerate(groups):
            username = group_entity.username

            try:
                await client.send_message(username, SKILL_MESSAGE)
                update_group_sent(username)
                sent += 1
                print(f"  [{i+1}/{len(groups)}] ✅ Sent → @{username}")
                log.info(f"Sent → @{username}")

                # Human-like random delay between sends
                delay = random.randint(MIN_DELAY_BETWEEN_GROUPS, MAX_DELAY_BETWEEN_GROUPS)
                print(f"  ⏳ Waiting {delay}s...")
                await asyncio.sleep(delay)

            except FloodWaitError as e:
                wait = e.seconds + 30
                print(f"  ⚠️  Flood wait: sleeping {wait}s")
                log.warning(f"FloodWait {wait}s after @{username}")
                await asyncio.sleep(wait)
                # Retry once after flood wait
                try:
                    await client.send_message(username, SKILL_MESSAGE)
                    update_group_sent(username)
                    sent += 1
                    print(f"  [{i+1}/{len(groups)}] ✅ Retry sent after flood wait → @{username}")
                except Exception:
                    failed += 1

            except ChatWriteForbiddenError:
                print(f"  🚫 Write forbidden → @{username}")
                mark_group_status(username, "forbidden")
                log.info(f"Marked forbidden: @{username}")
                skipped += 1

            except UserBannedInChannelError:
                print(f"  🚫 Banned in channel → @{username}")
                mark_group_status(username, "forbidden")
                skipped += 1

            except ChannelPrivateError:
                print(f"  🔒 Private channel → @{username}")
                mark_group_status(username, "dead")
                skipped += 1

            except (UsernameNotOccupiedError, UsernameInvalidError):
                print(f"  ❌ Username not found → @{username}")
                mark_group_status(username, "dead")
                log.info(f"Marked dead: @{username}")
                failed += 1

            except Exception as e:
                print(f"  ❌ Error on @{username}: {e}")
                log.error(f"Error @{username}: {e}")
                failed += 1
                await asyncio.sleep(60)

    log_broadcast(slot, sent, skipped, failed)

    summary = (
        f"\n📊 {slot.capitalize()} broadcast complete\n"
        f"   ✅ Sent:    {sent}\n"
        f"   ⏭️  Skipped: {skipped}\n"
        f"   ❌ Failed:  {failed}\n"
        f"   📦 Total:   {len(groups)}\n"
    )
    print(summary)
    log.info(summary)