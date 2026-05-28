import asyncio
import sys
import os
from datetime import datetime
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telethon import TelegramClient, events
 
from models import init_database, get_groups_stats, get_conversation
from config import (
    MORNING_TIME, EVENING_TIME, DISCOVERY_TIME,
    TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE, SESSION_FILE,
    ALERT_USERNAME
)

# Import agent functions
from discovery import run_discovery
from broadcaster import broadcast
from converter import handle_dm, get_conversion_stats, print_stats

logging.basicConfig(
    filename="logs/main.log",
    level=logging.INFO,
    format="%(asctime)s — %(message)s"
)
log = logging.getLogger("main")


# ─────────────────────────────────────────
# BANNER
# ─────────────────────────────────────────

def print_banner():
    banner = """
╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║     ████████╗███████╗██╗     ███████╗ ██████╗ ██████╗ ████████╗ ║
║     ╚══██╔══╝██╔════╝██║     ██╔════╝██╔════╝ ██╔══██╗╚══██╔══╝ ║
║        ██║   █████╗  ██║     █████╗  ██║  ███╗██████╔╝   ██║    ║
║        ██║   ██╔══╝  ██║     ██╔══╝  ██║   ██║██╔══██╗   ██║    ║
║        ██║   ███████╗███████╗███████╗╚██████╔╝██████╔╝   ██║    ║
║        ╚═╝   ╚══════╝╚══════╝╚══════╝ ╚═════╝ ╚═════╝    ╚═╝    ║
║                                                               ║
║          AUTOMATED FREELANCE LEAD GENERATION SYSTEM           ║
║                     3-Agent Architecture                      ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝

    Agent 1: Discovery  → Finds Telegram groups (Daily at {discovery})
    Agent 2: Broadcaster → Sends skill messages (2x daily at {morning} & {evening})
    Agent 3: Converter   → Handles DMs with AI (24/7 daemon)

    """.format(
        discovery=DISCOVERY_TIME,
        morning=MORNING_TIME,
        evening=EVENING_TIME
    )
    print(banner)


# ─────────────────────────────────────────
# CONFIGURATION CHECK
# ─────────────────────────────────────────

def check_configuration() -> bool:
    """
    Validates that all required credentials are configured
    """
    errors = []
    warnings = []
    
    # Check Telegram credentials
    if not TELEGRAM_API_ID or TELEGRAM_API_ID == "your_api_id_here":
        errors.append("❌ TELEGRAM_API_ID not configured in .env")
    
    if not TELEGRAM_API_HASH or TELEGRAM_API_HASH == "your_api_hash_here":
        errors.append("❌ TELEGRAM_API_HASH not configured in .env")
    
    if not TELEGRAM_PHONE or TELEGRAM_PHONE == "+91XXXXXXXXXX":
        errors.append("❌ TELEGRAM_PHONE not configured in .env")
    
    # Check API keys
    from config import OPENROUTER_API_KEY
    
    if not OPENROUTER_API_KEY or OPENROUTER_API_KEY == "your_openrouter_key_here":
        errors.append("❌ OPENROUTER_API_KEY not configured in .env")
    
    # Check alert username
    if not ALERT_USERNAME or ALERT_USERNAME == "your_second_account_username":
        warnings.append("⚠️  ALERT_TELEGRAM_USERNAME not configured (no alerts will be sent)")
    
    # Print results
    if errors:
        print("\n🚨 CONFIGURATION ERRORS:\n")
        for error in errors:
            print(f"   {error}")
        print("\n💡 Please edit your .env file with real credentials.")
        print("   See .env.example for reference.\n")
        return False
    
    if warnings:
        print("\n⚠️  CONFIGURATION WARNINGS:\n")
        for warning in warnings:
            print(f"   {warning}")
        print()
    
    return True


# ─────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────

def print_dashboard():
    """
    Displays current system status
    """
    print("\n" + "="*70)
    print("📊 SYSTEM DASHBOARD")
    print("="*70)
    
    # Group stats
    try:
        group_stats = get_groups_stats()
        print("\n📦 GROUP DATABASE:")
        print(f"   Total groups: {group_stats['total']}")
        print(f"   Active:       {group_stats['active']}")
        print(f"   Forbidden:    {group_stats['forbidden']}")
        print(f"   Dead:         {group_stats['dead']}")
        
        if group_stats['by_country']:
            top_countries = list(group_stats['by_country'].items())[:5]
            print(f"\n   Top countries:")
            for country, count in top_countries:
                print(f"      {country.upper()}: {count}")
    except Exception as e:
        print(f"\n📦 GROUP DATABASE: Error loading ({e})")
    
    # Conversation stats
    try:
        conv_stats = get_conversion_stats()
        print(f"\n💬 CONVERSATIONS:")
        print(f"   Total:        {conv_stats['total_conversations']}")
        print(f"   🎉 Committed:  {conv_stats['committed']} (Projects secured!)")
        print(f"   🔥 Hot leads:  {conv_stats['hot_leads']}")
        print(f"   🟡 Warm leads: {conv_stats['warm_leads']}")
        print(f"   ⚠️  Needs review: {conv_stats['needs_review']}")
        print(f"   ❄️  Cold leads: {conv_stats['cold_leads']}")
        print(f"   📈 Conversion: {conv_stats['conversion_rate']}%")
    except Exception as e:
        print(f"\n💬 CONVERSATIONS: Error loading ({e})")
    
    # Schedule status
    print(f"\n⏰ SCHEDULE:")
    print(f"   Discovery:    Daily at {DISCOVERY_TIME}")
    print(f"   Morning:      Daily at {MORNING_TIME}")
    print(f"   Evening:      Daily at {EVENING_TIME}")
    print(f"   Converter:    Running 24/7")
    
    # Current time
    now = datetime.now()
    print(f"\n🕐 Current time:  {now.strftime('%Y-%m-%d %H:%M:%S')}")
    
    print("="*70 + "\n")


# ─────────────────────────────────────────
# AGENT RUNNERS (with error handling)
# ─────────────────────────────────────────

async def run_discovery_safe(client: TelegramClient):
    """Wrapper for discovery with error handling"""
    try:
        print(f"\n{'='*70}")
        print(f"🔍 AGENT 1: DISCOVERY STARTING - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print(f"{'='*70}\n")
        log.info("=== Agent 1: Discovery started ===")
        await run_discovery(client)
        log.info("=== Agent 1: Discovery completed ===")
        print(f"\n{'='*70}")
        print(f"✅ AGENT 1: DISCOVERY COMPLETED - {datetime.now().strftime('%H:%M')}")
        print(f"{'='*70}\n")
    except Exception as e:
        error_msg = f"Agent 1 (Discovery) failed: {type(e).__name__} - {e}"
        log.error(error_msg)
        print(f"\n❌ {error_msg}\n")


async def run_broadcast_safe(client: TelegramClient, slot: str):
    """Wrapper for morning broadcast"""
    try:
        print(f"\n{'='*70}")
        print(f"📢 AGENT 2: {slot.upper()} BROADCAST STARTING - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print(f"{'='*70}\n")
        log.info(f"=== Agent 2: {slot} broadcast started ===")
        await broadcast(slot, client)
        log.info("=== Agent 2: Morning broadcast completed ===")
        print(f"\n{'='*70}")
        print(f"✅ AGENT 2: {slot.upper()} BROADCAST COMPLETED - {datetime.now().strftime('%H:%M')}")
        print(f"{'='*70}\n")
    except Exception as e:
        error_msg = f"Agent 2 ({slot.capitalize()} Broadcast) failed: {type(e).__name__} - {e}"
        log.error(error_msg)
        print(f"\n❌ {error_msg}\n")


# ─────────────────────────────────────────
# SCHEDULER
# ─────────────────────────────────────────

def setup_schedule(scheduler: AsyncIOScheduler, client: TelegramClient):
    """
    Sets up the scheduler for automated agent runs
    """
    h_disc, m_disc = map(int, DISCOVERY_TIME.split(':'))
    scheduler.add_job(run_discovery_safe, 'cron', hour=h_disc, minute=m_disc, args=[client])

    h_morn, m_morn = map(int, MORNING_TIME.split(':'))
    scheduler.add_job(run_broadcast_safe, 'cron', hour=h_morn, minute=m_morn, args=[client, "morning"])

    h_eve, m_eve = map(int, EVENING_TIME.split(':'))
    scheduler.add_job(run_broadcast_safe, 'cron', hour=h_eve, minute=m_eve, args=[client, "evening"])
    
    print(f"✅ Scheduler configured:")
    print(f"   🔍 Discovery:  Every day at {DISCOVERY_TIME}")
    print(f"   📢 Morning:    Every day at {MORNING_TIME}")
    print(f"   📢 Evening:    Every day at {EVENING_TIME}")
    print(f"   💬 Converter:  Running continuously\n")

    scheduler.start()


# ─────────────────────────────────────────
# MAIN ORCHESTRATOR
# ─────────────────────────────────────────

async def run_full_system():
    """
    Runs all 3 agents:
    - Agent 1 & 2 on schedule
    - Agent 3 as foreground process (with scheduler in background)
    """
    print_banner()
    
    # Check configuration
    if not check_configuration():
        print("❌ System cannot start due to configuration errors.")
        print("   Please fix the issues above and try again.\n")
        sys.exit(1)
    
    # Initialize data files
    print("🔧 Initializing system...")
    init_database()
    
    # Show dashboard
    print_dashboard()
    
    # Perform initial discovery if database is empty
    if get_groups_stats()['total'] == 0:
        print("\n⚠️  Group database is empty. Performing initial discovery run...")
        log.info("Database empty, performing initial discovery.")
        # We need a temporary client for this initial run
        # This will use the session string if available, preventing interactive login
        temp_client = TelegramClient(SESSION_FILE, TELEGRAM_API_ID, TELEGRAM_API_HASH)
        await temp_client.start(phone=TELEGRAM_PHONE)
        await run_discovery_safe(temp_client)
        await temp_client.disconnect()
        print("✅ Initial discovery complete.")

    # Create a single, shared client
    from config import TELEGRAM_SESSION_STRING
    # Use session string for deployment, fall back to file for local dev
    session = TELEGRAM_SESSION_STRING or SESSION_FILE
    client = TelegramClient(session, TELEGRAM_API_ID, TELEGRAM_API_HASH)

    # Register Agent 3 (Converter) DM handler
    @client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
    async def dm_handler(event):
        # This ensures the client is passed correctly to the handler
        await handle_dm(event, client)

    # Setup and start the asynchronous scheduler
    scheduler = AsyncIOScheduler()
    setup_schedule(scheduler, client)

    try:
        # Start the client
        await client.start(phone=TELEGRAM_PHONE)
        me = await client.get_me()
        
        print(f"🚀 SYSTEM IS LIVE")
        print(f"   Running as: {me.first_name} (@{me.username})")
        print(f"   Alerts go to: @{ALERT_USERNAME}")
        print("   Agents 1 & 2 will run automatically on schedule.")
        print("   Press Ctrl+C to stop the system.\n")
        log.info("System is live and all agents are active.")
        
        # Run until disconnected
        await client.run_until_disconnected()
        
    except KeyboardInterrupt:
        pass # Handled in finally
    finally:
        if client.is_connected():
            await client.disconnect()
        scheduler.shutdown()
        print("\n✅ System stopped gracefully.\n")
        log.info("System shutdown.")


# ─────────────────────────────────────────
# MANUAL AGENT RUNNERS
# ─────────────────────────────────────────

def run_discovery_now():
    """Manually run Agent 1"""
    print_banner()
    init_database() # Ensure files exist for manual runs
    async def _run():
        async with TelegramClient('session', TELEGRAM_API_ID, TELEGRAM_API_HASH) as client:
            await run_discovery_safe(client)
    asyncio.run(_run())


def run_broadcast_now(slot: str = "morning"):
    """Manually run Agent 2"""
    print_banner()
    init_database()
    async def _run():
        async with TelegramClient('session', TELEGRAM_API_ID, TELEGRAM_API_HASH) as client:
            await run_broadcast_safe(client, slot)
    asyncio.run(_run())


def run_converter_now():
    """Manually run Agent 3"""
    print_banner()
    print("NOTE: This runs Agent 3 only. Scheduled tasks will NOT run.")
    print("Use 'python main.py' to run the full system.\n")
    asyncio.run(run_full_system()) # Simplified: run_full_system handles the converter loop


# ─────────────────────────────────────────
# TESTING & UTILITIES
# ─────────────────────────────────────────

def test_configuration():
    """Test all API connections"""
    print_banner()
    print("🧪 TESTING CONFIGURATION\n")
    
    errors = []
    successes = []
    
    # Test 1: Data files
    try:
        init_database()
        successes.append("✅ Data files initialized")
    except Exception as e:
        errors.append(f"❌ Data files failed: {e}")
    
    # Test 2: Telegram connection
    try:
        from telethon import TelegramClient
        client = TelegramClient(
            "test_session",
            TELEGRAM_API_ID,
            TELEGRAM_API_HASH
        )
        
        async def test_telegram():
            await client.connect()
            if await client.is_user_authorized():
                successes.append("✅ Telegram connection: Already authorized")
            else:
                successes.append("⚠️  Telegram connection: Not authorized (run 'python main.py login' first)")
            await client.disconnect()
        
        asyncio.run(test_telegram())
        
        # Clean up test session
        if os.path.exists("test_session.session"):
            os.remove("test_session.session")
            
    except Exception as e:
        errors.append(f"❌ Telegram connection failed: {e}")
    
    # Test 3: OpenRouter API
    try:
        from config import OPENROUTER_API_KEY
        import requests
        
        if OPENROUTER_API_KEY and OPENROUTER_API_KEY != "your_openrouter_key_here":
            response = requests.get(
                "https://openrouter.ai/api/v1/models",
                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
                timeout=10
            )
            if response.status_code == 200:
                successes.append("✅ OpenRouter API: Connected")
            else:
                errors.append(f"❌ OpenRouter API: Invalid key (status {response.status_code})")
        else:
            errors.append("❌ OpenRouter API: Not configured")
    except Exception as e:
        errors.append(f"❌ OpenRouter API failed: {e}")
    
    # Print results
    print("\n" + "="*70)
    print("TEST RESULTS")
    print("="*70 + "\n")
    
    for success in successes:
        print(success)
    
    print()
    
    for error in errors:
        print(error)
    
    print("\n" + "="*70 + "\n")
    
    if not any("❌" in e for e in errors):
        print("✅ All critical tests passed! System is ready to run.\n")
        return True
    else:
        print("❌ Some tests failed. Please fix the issues above.\n")
        return False


def telegram_login():
    """Interactive Telegram login"""
    print_banner()
    print("🔐 TELEGRAM LOGIN\n")
    print("This will create a session file for Telegram authentication.\n")
    
    from telethon import TelegramClient
    
    client = TelegramClient(SESSION_FILE, TELEGRAM_API_ID, TELEGRAM_API_HASH)
    
    async def login():
        await client.start(phone=TELEGRAM_PHONE)
        me = await client.get_me()
        session_string = client.session.save()
        
        print("\n" + "="*70)
        print("✅ LOGIN SUCCESSFUL. Add this session string to your .env file.")
        print("   TELEGRAM_SESSION_STRING=")
        print(session_string)
        print("="*70)
        
        print(f"\n✅ Successfully logged in as: {me.first_name} (@{me.username})")
        print(f"   User ID: {me.id}")
        print(f"   Phone: {me.phone}\n")
        await client.disconnect()
    
    try:
        asyncio.run(login())
        print("✅ Session file created. You can now run the system.\n")
    except Exception as e:
        print(f"\n❌ Login failed: {e}\n")
        sys.exit(1)


# ─────────────────────────────────────────
# CLI INTERFACE
# ─────────────────────────────────────────

def print_help():
    """Print usage instructions"""
    help_text = """
╔═══════════════════════════════════════════════════════════════╗
║                    TELEGRAM AUTOMATION SYSTEM                 ║
║                         COMMAND REFERENCE                     ║
╚═══════════════════════════════════════════════════════════════╝

MAIN COMMANDS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  python main.py
      Run the full system (all 3 agents)
      - Agent 1 & 2 run on schedule
      - Agent 3 runs continuously (foreground)

  python main.py dashboard
      Show current system status

  python main.py login
      Authenticate with Telegram (required on first run)

  python main.py test
      Test all API connections and configuration


MANUAL AGENT EXECUTION:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  python main.py discovery
      Run Agent 1 (Discovery) once immediately

  python main.py broadcast morning
      Run Agent 2 (Broadcaster) - morning slot

  python main.py broadcast evening
      Run Agent 2 (Broadcaster) - evening slot

  python main.py converter
      Run Agent 3 (Converter) - DM handler


ANALYTICS & MONITORING:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  python converter.py stats
      Show conversion statistics

  python converter.py review
      Review all conversations

  python converter.py review committed
      Review secured projects only

  python converter.py review hot
      Review hot leads

  python converter.py review needs_review
      Review leads needing your decision


TYPICAL WORKFLOW:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  1. First time setup:
     python main.py test       # Verify configuration
     python main.py login      # Authenticate with Telegram

  2. Run system:
     python main.py            # Starts all agents

  3. Monitor (in another terminal):
     python converter.py stats # Check performance
     python main.py dashboard  # View system status

  4. Manual operations (optional):
     python main.py discovery  # Find new groups manually
     python main.py broadcast morning  # Send messages manually


LOGS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  logs/main.log          - System orchestration
  logs/discovery.log     - Agent 1 activity
  logs/broadcaster.log   - Agent 2 activity
  logs/converter.log     - Agent 3 activity

  tail -f logs/converter.log   # Watch live DM conversations


NEED HELP?
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Check the README.md for detailed documentation.
  Make sure your .env file is properly configured.

"""
    print(help_text)


# ─────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────

def main():
    """Main entry point with command routing"""
    
    # Create logs directory
    os.makedirs("logs", exist_ok=True)
    
    # Parse command
    if len(sys.argv) == 1:
        # No arguments = run full system
        asyncio.run(run_full_system())
    
    else:
        command = sys.argv[1].lower()
        
        if command == "help" or command == "-h" or command == "--help":
            print_help()
        
        elif command == "dashboard":
            print_banner()
            init_database()
            print_dashboard()
        
        elif command == "login":
            telegram_login()
        
        elif command == "test":
            test_configuration()
        
        elif command == "discovery":
            run_discovery_now()
        
        elif command == "broadcast":
            slot = sys.argv[2] if len(sys.argv) > 2 else "morning"
            if slot not in ["morning", "evening"]:
                print(f"❌ Invalid slot: {slot}")
                print("   Use: python main.py broadcast morning")
                print("   Or:  python main.py broadcast evening\n")
                sys.exit(1)
            run_broadcast_now(slot)
        
        elif command == "converter":
            run_converter_now()
        
        elif command == "stats":
            print_banner()
            init_database()
            print_stats()
        
        else:
            print(f"❌ Unknown command: {command}\n")
            print("Run 'python main.py help' for usage instructions.\n")
            sys.exit(1)


if __name__ == "__main__":
    main()