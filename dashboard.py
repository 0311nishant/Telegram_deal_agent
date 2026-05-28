from flask import Flask, render_template
import sqlite3
import pandas as pd
import json

DATABASE_FILE = "data/database.db"

app = Flask(__name__)

def get_db_connection():
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    conn = get_db_connection()
    
    # Group stats
    groups_df = pd.read_sql_query("SELECT * FROM groups", conn)
    group_stats = {
        "total": len(groups_df),
        "active": len(groups_df[groups_df['status'] == 'active']),
        "dead": len(groups_df[groups_df['status'] == 'dead']),
        "contacted": len(groups_df[groups_df['status'] == 'contacted']),
    }

    # Conversation stats
    convos_df = pd.read_sql_query("SELECT * FROM conversations", conn)
    convo_stats = {
        "total": len(convos_df),
        "cold": len(convos_df[convos_df['lead_score'] == 'cold']),
        "warm": len(convos_df[convos_df['lead_score'] == 'warm']),
        "hot": len(convos_df[convos_df['lead_score'] == 'hot']),
        "secured": len(convos_df[convos_df['project_secured_at'].notna()]),
    }
    
    # Broadcast logs
    broadcast_logs_df = pd.read_sql_query("SELECT * FROM broadcast_logs ORDER BY log_date DESC, log_time DESC LIMIT 20", conn)

    # Detailed tables
    groups_table = groups_df.to_html(classes='table table-striped', index=False, border=0)
    convos_table = convos_df.to_html(classes='table table-striped', index=False, border=0)
    logs_table = broadcast_logs_df.to_html(classes='table table-striped', index=False, border=0)

    conn.close()
    
    return render_template('index.html', 
                           group_stats=group_stats,
                           convo_stats=convo_stats,
                           groups_table=groups_table,
                           convos_table=convos_table,
                           logs_table=logs_table)

def run_dashboard():
    app.run(debug=True, port=5001)
