import json
import os
from datetime import datetime
from typing import Optional, List, Dict, Any, Set
from sqlalchemy import create_engine, Column, String, Integer, Text, Boolean, MetaData, Table
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.exc import OperationalError
from contextlib import contextmanager

from config import DATABASE_URL

# Use DATABASE_URL if available (for Railway), otherwise fall back to local SQLite
IS_POSTGRES = DATABASE_URL is not None

if IS_POSTGRES:
    engine = create_engine(DATABASE_URL)
else:
    # Ensure the local data directory exists for SQLite
    os.makedirs("data", exist_ok=True)
    engine = create_engine(f"sqlite:///data/agent.db")

Base = declarative_base()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ─────────────────────────────────────────
# DATABASE MODELS (SQLAlchemy)
# ─────────────────────────────────────────

class Group(Base):
    __tablename__ = "groups"
    username = Column(String, primary_key=True)
    discovered_at = Column(String, nullable=False)
    source = Column(String)
    country = Column(String)
    member_count = Column(Integer, default=0)
    category = Column(String)
    last_sent = Column(String)
    times_sent = Column(Integer, default=0)
    status = Column(String, nullable=False, default='active')
    query_used = Column(String)

class Conversation(Base):
    __tablename__ = "conversations"
    user_id = Column(Integer, primary_key=True)
    name = Column(String)
    username = Column(String)
    messages = Column(Text)  # JSON blob
    lead_score = Column(String, default='cold')
    first_contact = Column(String)
    last_active = Column(String)
    alerted = Column(Boolean, default=False)
    alert_type = Column(String)
    project_secured_at = Column(String)

class BroadcastLog(Base):
    __tablename__ = "broadcast_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    log_date = Column(String, nullable=False)
    slot = Column(String, nullable=False)
    sent = Column(Integer, default=0)
    skipped = Column(Integer, default=0)
    failed = Column(Integer, default=0)
    log_time = Column(String, nullable=False)

# ─────────────────────────────────────────
# DATABASE SETUP & UTILITIES
# ─────────────────────────────────────────

@contextmanager
def get_db_session():
    """Provide a transactional scope around a series of operations."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except:
        session.rollback()
        raise
    finally:
        session.close()

def init_database():
    """Create database tables if they don't exist."""
    if not IS_POSTGRES:
        os.makedirs("logs", exist_ok=True)

    # Ensure the .env file is actually loaded/configured
    from config import TELEGRAM_API_ID
    if not TELEGRAM_API_ID or TELEGRAM_API_ID == "your_api_id_here":
        print("⚠️ WARNING: .env file is not configured with real credentials!")

    try:
        Base.metadata.create_all(bind=engine)
        print("✅ Tables initialized successfully (or already exist).")
    except OperationalError as e:
        print(f"❌ DATABASE CONNECTION FAILED: {e}")
        print("   Please ensure your DATABASE_URL is correct in your .env file.")
        if IS_POSTGRES:
            print("   It should look like: postgresql://user:password@host:port/dbname")
        exit(1) # Exit if we can't connect to the DB

# ─────────────────────────────────────────
# GROUP MODEL
# ─────────────────────────────────────────

def get_active_groups() -> List[Dict[str, Any]]:
    """Returns only groups eligible for broadcasting."""
    with get_db_session() as session:
        groups = session.query(Group).filter(Group.status == 'active').all()
        return [g.__dict__ for g in groups]

def get_group_usernames() -> Set[str]:
    """Returns set of all known usernames for deduplication."""
    with get_db_session() as session:
        return {g.username.lower() for g in session.query(Group.username).all()}

def add_groups(new_groups: List[Dict[str, Any]]) -> int:
    """Appends new groups to the database. Skips duplicates."""
    with get_db_session() as session:
        existing_usernames = {g[0].lower() for g in session.query(Group.username).all()}
        groups_to_add = []
        
        for group_data in new_groups:
            username = group_data.get("username", "").lower().strip()
            if not username or username in existing_usernames:
                continue
            
            groups_to_add.append(Group(
                username=username,
                discovered_at=datetime.now().isoformat(),
                source=group_data.get("source", "unknown"),
                country=group_data.get("country", "unknown"),
                member_count=group_data.get("member_count", 0),
                category=group_data.get("category", "unknown"),
                status="active",
                query_used=group_data.get("query_used", "")
            ))
            existing_usernames.add(username)

        if not groups_to_add:
            return 0
            
        session.add_all(groups_to_add)
        return len(groups_to_add)

def mark_group_status(username: str, status: str):
    """Mark group as forbidden, dead, or active."""
    with get_db_session() as session:
        group = session.query(Group).filter(Group.username == username.lower()).first()
        if group:
            group.status = status

def update_group_sent(username: str):
    """Update last_sent timestamp and increment times_sent."""
    with get_db_session() as session:
        group = session.query(Group).filter(Group.username == username.lower()).first()
        if group:
            group.last_sent = datetime.now().isoformat()
            group.times_sent = (group.times_sent or 0) + 1

def get_groups_stats() -> Dict[str, Any]:
    """Retrieves statistics about the groups in the database."""
    stats = {"total": 0, "active": 0, "forbidden": 0, "dead": 0, "by_country": {}, "by_source": {}}
    try:
        with get_db_session() as session:
            stats['total'] = session.query(Group).count()
            
            status_counts = session.query(Group.status, func.count(Group.status)).group_by(Group.status).all()
            for status, count in status_counts:
                stats[status] = count

            country_counts = session.query(Group.country, func.count(Group.country)).group_by(Group.country).order_by(func.count(Group.country).desc()).all()
            stats['by_country'] = {country: count for country, count in country_counts}

            source_counts = session.query(Group.source, func.count(Group.source)).group_by(Group.source).order_by(func.count(Group.source).desc()).all()
            stats['by_source'] = {source: count for source, count in source_counts}
    except Exception:
        # Return zero stats if DB is empty or there's an error
        return stats
    return stats

# ─────────────────────────────────────────
# CONVERSATION MODEL — Agent 3
# ─────────────────────────────────────────

def load_conversations() -> Dict[str, Any]:
    """Loads all conversations from the database."""
    with get_db_session() as session:
        convos = {}
        for convo_obj in session.query(Conversation).all():
            convo = convo_obj.__dict__
            convo.pop('_sa_instance_state', None) # Clean up SQLAlchemy state
            convo['messages'] = json.loads(convo.get('messages', '[]'))
            convos[str(convo['user_id'])] = convo
        return convos

def get_conversation(user_id: int) -> Dict[str, Any]:
    """Retrieves a single conversation or returns a new one."""
    with get_db_session() as session:
        convo_obj = session.query(Conversation).filter(Conversation.user_id == user_id).first()
        if convo_obj:
            convo = convo_obj.__dict__
            convo.pop('_sa_instance_state', None)
            convo['messages'] = json.loads(convo.get('messages', '[]'))
            return convo
        else:
            return {
                "user_id": user_id, "name": "Unknown", "messages": [],
                "lead_score": "cold", "first_contact": datetime.now().isoformat(),
                "last_active": datetime.now().isoformat(), "alerted": False
            }

def save_conversation(user_id: int, convo_data: Dict[str, Any]):
    """Saves a conversation to the database (insert or update)."""
    with get_db_session() as session:
        convo_obj = session.query(Conversation).filter(Conversation.user_id == user_id).first()
        if not convo_obj:
            convo_obj = Conversation(user_id=user_id)
            session.add(convo_obj)
        
        convo_obj.name = convo_data.get('name')
        convo_obj.username = convo_data.get('username')
        convo_obj.messages = json.dumps(convo_data.get('messages', []))
        convo_obj.lead_score = convo_data.get('lead_score', 'cold')
        convo_obj.first_contact = convo_data.get('first_contact', datetime.now().isoformat())
        convo_obj.last_active = datetime.now().isoformat()
        convo_obj.alerted = convo_data.get('alerted', False)
        convo_obj.alert_type = convo_data.get('alert_type')
        convo_obj.project_secured_at = convo_data.get('project_secured_at')

def append_message(user_id: int, role: str, content: str, name: str = ""):
    """Appends a message to a conversation."""
    convo = get_conversation(user_id)
    if name:
        convo["name"] = name
    
    convo["messages"].append({
        "role": role, "content": content, "timestamp": datetime.now().isoformat()
    })
    convo["messages"] = convo["messages"][-20:] # Keep last 20 messages
    save_conversation(user_id, convo)

def update_lead_score(user_id: int, score: str):
    """Updates only the lead score for a conversation."""
    with get_db_session() as session:
        convo = session.query(Conversation).filter(Conversation.user_id == user_id).first()
        if convo:
            convo.lead_score = score
            convo.last_active = datetime.now().isoformat()

def get_hot_leads() -> List[Dict[str, Any]]:
    """Retrieves all conversations marked as 'hot'."""
    with get_db_session() as session:
        leads = session.query(Conversation).filter(Conversation.lead_score == 'hot').all()
        return [l.__dict__ for l in leads]

# ─────────────────────────────────────────
# SENT LOG MODEL — Agent 2
# ─────────────────────────────────────────

def log_broadcast(slot: str, sent: int, skipped: int, failed: int):
    """Logs the result of a broadcast run to the database."""
    with get_db_session() as session:
        log_entry = BroadcastLog(
            log_date=datetime.now().strftime("%Y-%m-%d"),
            slot=slot,
            sent=sent,
            skipped=skipped,
            failed=failed,
            log_time=datetime.now().strftime("%H:%M")
        )
        session.add(log_entry)

def get_broadcast_stats() -> Dict[str, Any]:
    """Retrieves statistics about past broadcasts."""
    stats = {'total_broadcasts': 0, 'total_messages_sent': 0, 'log': []}
    try:
        with get_db_session() as session:
            stats['total_broadcasts'] = session.query(func.count(func.distinct(BroadcastLog.log_date))).scalar() or 0
            stats['total_messages_sent'] = session.query(func.sum(BroadcastLog.sent)).scalar() or 0
            
            logs = session.query(BroadcastLog).order_by(BroadcastLog.id.desc()).limit(10).all()
            stats['log'] = [l.__dict__ for l in logs]
    except Exception:
        return stats
    return stats