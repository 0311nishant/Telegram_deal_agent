import json
import os
import sqlite3
from datetime import datetime
from typing import Optional, List, Dict, Any, Set
from config import DATABASE_FILE


# ─────────────────────────────────────────
# DATABASE SETUP & UTILITIES
# ─────────────────────────────────────────

def _db_connect() -> sqlite3.Connection:
    """Establish a connection to the SQLite database."""
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row  # Makes rows accessible by column name
    return conn

def init_database():
    """Create database tables if they don't exist."""
    os.makedirs("data", exist_ok=True)
    os.makedirs("logs", exist_ok=True)

    # Ensure the .env file is actually loaded/configured
    from config import TELEGRAM_API_ID
    if not TELEGRAM_API_ID or TELEGRAM_API_ID == "your_api_id_here":
        print("⚠️ WARNING: .env file is not configured with real credentials!")

    conn = _db_connect()
    cursor = conn.cursor()

    # Groups table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS groups (
        username TEXT PRIMARY KEY,
        discovered_at TEXT NOT NULL,
        source TEXT,
        country TEXT,
        member_count INTEGER DEFAULT 0,
        category TEXT,
        last_sent TEXT,
        times_sent INTEGER DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'active',
        query_used TEXT
    )
    """)
    print("✅ Table 'groups' initialized.")

    # Conversations table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS conversations (
        user_id INTEGER PRIMARY KEY,
        name TEXT,
        username TEXT,
        messages TEXT, -- JSON blob
        lead_score TEXT DEFAULT 'cold',
        first_contact TEXT,
        last_active TEXT,
        alerted BOOLEAN DEFAULT 0,
        alert_type TEXT,
        project_secured_at TEXT
    )
    """)
    print("✅ Table 'conversations' initialized.")

    # Broadcast logs table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS broadcast_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        log_date TEXT NOT NULL,
        slot TEXT NOT NULL,
        sent INTEGER DEFAULT 0,
        skipped INTEGER DEFAULT 0,
        failed INTEGER DEFAULT 0,
        log_time TEXT NOT NULL
    )
    """)
    print("✅ Table 'broadcast_logs' initialized.")

    conn.commit()
    conn.close()


# ─────────────────────────────────────────
# GROUP MODEL
# ─────────────────────────────────────────

def get_active_groups() -> List[Dict[str, Any]]:
    """Returns only groups eligible for broadcasting."""
    conn = _db_connect()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM groups WHERE status = 'active'")
    groups = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return groups

def get_group_usernames() -> Set[str]:
    """Returns set of all known usernames for deduplication."""
    conn = _db_connect()
    cursor = conn.cursor()
    cursor.execute("SELECT username FROM groups")
    usernames = {row['username'].lower() for row in cursor.fetchall()}
    conn.close()
    return usernames

def add_groups(new_groups: List[Dict[str, Any]]) -> int:
    """
    Appends new groups to the database.
    Skips duplicates. Returns count of actually added groups.
    """
    existing_usernames = get_group_usernames()
    groups_to_add = []

    for group in new_groups:
        username = group.get("username", "").lower().strip()
        if not username or username in existing_usernames:
            continue
        
        groups_to_add.append((
            username,
            datetime.now().isoformat(),
            group.get("source", "unknown"),
            group.get("country", "unknown"),
            group.get("member_count", 0),
            group.get("category", "unknown"),
            "active",
            group.get("query_used", "")
        ))
        existing_usernames.add(username) # Avoid adding duplicates from the same batch

    if not groups_to_add:
        return 0

    conn = _db_connect()
    cursor = conn.cursor()
    cursor.executemany("""
    INSERT INTO groups (username, discovered_at, source, country, member_count, category, status, query_used)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, groups_to_add)
    conn.commit()
    added_count = cursor.rowcount
    conn.close()
    return added_count

def mark_group_status(username: str, status: str):
    """Mark group as forbidden, dead, or active."""
    conn = _db_connect()
    cursor = conn.cursor()
    cursor.execute("UPDATE groups SET status = ? WHERE username = ?", (status, username.lower()))
    conn.commit()
    conn.close()

def update_group_sent(username: str):
    """Update last_sent timestamp and increment times_sent."""
    conn = _db_connect()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE groups
    SET last_sent = ?, times_sent = times_sent + 1
    WHERE username = ?
    """, (datetime.now().isoformat(), username.lower()))
    conn.commit()
    conn.close()

def get_groups_stats() -> Dict[str, Any]:
    """Retrieves statistics about the groups in the database."""
    conn = _db_connect()
    cursor = conn.cursor()

    stats = {}
    try:
        cursor.execute("SELECT COUNT(*) FROM groups")
        stats['total'] = cursor.fetchone()[0]

        cursor.execute("SELECT status, COUNT(*) FROM groups GROUP BY status")
        status_counts = {row['status']: row[1] for row in cursor.fetchall()}
        stats['active'] = status_counts.get('active', 0)
        stats['forbidden'] = status_counts.get('forbidden', 0)
        stats['dead'] = status_counts.get('dead', 0)

        cursor.execute("SELECT country, COUNT(*) as count FROM groups GROUP BY country ORDER BY count DESC")
        stats['by_country'] = {row['country']: row['count'] for row in cursor.fetchall()}

        cursor.execute("SELECT source, COUNT(*) as count FROM groups GROUP BY source ORDER BY count DESC")
        stats['by_source'] = {row['source']: row['count'] for row in cursor.fetchall()}
    except sqlite3.OperationalError as e:
        # This can happen if the DB was just created and is empty
        print(f"Database might be empty, returning zero stats. Error: {e}")
        return {"total": 0, "active": 0, "forbidden": 0, "dead": 0, "by_country": {}, "by_source": {}}
    finally:
        conn.close()
    
    return stats


# ─────────────────────────────────────────
# CONVERSATION MODEL — Agent 3
# ─────────────────────────────────────────

def load_conversations() -> Dict[str, Any]:
    """Loads all conversations from the database."""
    conn = _db_connect()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM conversations")
    convos = {}
    for row in cursor.fetchall():
        convo = dict(row)
        convo['messages'] = json.loads(convo.get('messages', '[]'))
        convos[str(row['user_id'])] = convo
    conn.close()
    return convos

def get_conversation(user_id: int) -> Dict[str, Any]:
    """Retrieves a single conversation or returns a new one."""
    conn = _db_connect()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM conversations WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()

    if row:
        convo = dict(row)
        convo['messages'] = json.loads(convo.get('messages', '[]'))
        return convo
    else:
        return {
            "user_id": user_id,
            "name": "Unknown",
            "messages": [],
            "lead_score": "cold",
            "first_contact": datetime.now().isoformat(),
            "last_active": datetime.now().isoformat(),
            "alerted": False
        }

def save_conversation(user_id: int, convo: Dict[str, Any]):
    """Saves a conversation to the database (insert or update)."""
    conn = _db_connect()
    cursor = conn.cursor()
    
    convo['last_active'] = datetime.now().isoformat()
    messages_json = json.dumps(convo.get('messages', []))

    cursor.execute("""
    INSERT OR REPLACE INTO conversations (
        user_id, name, username, messages, lead_score, first_contact,
        last_active, alerted, alert_type, project_secured_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        convo.get('name'),
        convo.get('username'),
        messages_json,
        convo.get('lead_score', 'cold'),
        convo.get('first_contact', datetime.now().isoformat()),
        convo.get('last_active'),
        convo.get('alerted', False),
        convo.get('alert_type'),
        convo.get('project_secured_at')
    ))
    conn.commit()
    conn.close()

def append_message(user_id: int, role: str, content: str, name: str = ""):
    """Appends a message to a conversation."""
    convo = get_conversation(user_id)
    if name:
        convo["name"] = name
    
    convo["messages"].append({
        "role": role,
        "content": content,
        "timestamp": datetime.now().isoformat()
    })
    # Keep last 20 messages only
    convo["messages"] = convo["messages"][-20:]
    
    save_conversation(user_id, convo)

def update_lead_score(user_id: int, score: str):
    """Updates only the lead score for a conversation."""
    conn = _db_connect()
    cursor = conn.cursor()
    cursor.execute("UPDATE conversations SET lead_score = ?, last_active = ? WHERE user_id = ?",
                   (score, datetime.now().isoformat(), user_id))
    conn.commit()
    conn.close()

def get_hot_leads() -> List[Dict[str, Any]]:
    """Retrieves all conversations marked as 'hot'."""
    conn = _db_connect()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM conversations WHERE lead_score = 'hot'")
    leads = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return leads


# ─────────────────────────────────────────
# SENT LOG MODEL — Agent 2
# ─────────────────────────────────────────

def log_broadcast(slot: str, sent: int, skipped: int, failed: int):
    """Logs the result of a broadcast run to the database."""
    conn = _db_connect()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO broadcast_logs (log_date, slot, sent, skipped, failed, log_time)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (
        datetime.now().strftime("%Y-%m-%d"),
        slot,
        sent,
        skipped,
        failed,
        datetime.now().strftime("%H:%M")
    ))
    conn.commit()
    conn.close()

def get_broadcast_stats() -> Dict[str, Any]:
    """Retrieves statistics about past broadcasts."""
    conn = _db_connect()
    cursor = conn.cursor()

    stats = {}
    cursor.execute("SELECT COUNT(DISTINCT log_date) FROM broadcast_logs")
    stats['total_broadcasts'] = cursor.fetchone()[0]

    cursor.execute("SELECT SUM(sent) FROM broadcast_logs")
    total_sent = cursor.fetchone()[0]
    stats['total_messages_sent'] = total_sent if total_sent is not None else 0

    cursor.execute("SELECT * FROM broadcast_logs ORDER BY id DESC LIMIT 10")
    stats['log'] = [dict(row) for row in cursor.fetchall()]

    conn.close()
    return stats