# Telegram Automated Freelance Lead Generation System

This is a sophisticated, multi-agent system designed to automate the entire lead generation funnel for freelance developers on Telegram. It discovers potential clients, broadcasts services, and handles initial sales conversations using AI, acting as a 24/7 automated sales representative.

---

## 🚀 Features

- **3-Agent Architecture**: Specialized agents for Discovery, Broadcasting, and Conversion.
- **Multi-Source Discovery**: Scrapes Google, Perplexity, TGStat, and Telemetr.io to find relevant groups.
- **Intelligent Keyword Rotation**: Uses a matrix of skills, intents, and formats to generate unique search queries daily, preventing stagnation.
- **Automated Group Joining**: Automatically joins newly discovered groups to prepare for broadcasting.
- **Scheduled Broadcasting**: Sends your service message to joined groups at configurable times (e.g., morning and evening).
- **AI-Powered DM Handling**: Uses `anthropic/claude-haiku-3-5` to conduct human-like conversations with potential clients who send a direct message.
- **Advanced Lead Scoring**: Automatically categorizes leads as `Cold`, `Warm`, `Hot`, `Needs Review`, or `Committed` based on conversation context.
- **Automated Alerts**: Sends detailed alerts to your personal Telegram account for high-intent leads (`Hot`, `Needs Review`, `Committed`).
- **Robust CLI**: A powerful command-line interface to run agents manually, check system status, and test configuration.
- **Persistent Database**: Uses SQLite to reliably store all discovered groups, conversation histories, and broadcast logs.
- **Deployment Ready**: Designed for deployment on platforms like Railway using session strings and persistent volumes.

---

## 🏛️ 3-Agent Architecture

The system is divided into three distinct, autonomous agents that work in concert.

### 🤖 Agent 1: Discovery
*   **Objective**: Find new Telegram groups where potential clients might be.
*   **Schedule**: Runs once daily (configurable, default: `06:00`).
*   **Process**:
    1.  Generates unique search queries based on a rotating matrix of skills and intents.
    2.  Scrapes multiple sources for Telegram group links.
    3.  Filters out low-quality or irrelevant groups.
    4.  Saves new, unique groups to the database.
    5.  Attempts to join each newly discovered group.

### 📢 Agent 2: Broadcaster
*   **Objective**: Send your pre-defined service message to relevant groups.
*   **Schedule**: Runs twice daily (configurable, default: `09:00` & `18:00`).
*   **Process**:
    1.  Fetches a list of all groups your account has successfully joined.
    2.  Cross-references this with the "active" groups in the database.
    3.  Sends the `SKILL_MESSAGE` to each valid group with human-like delays.
    4.  Handles rate limits and errors gracefully, updating group statuses (e.g., "forbidden", "dead") as needed.

### 💬 Agent 3: Converter
*   **Objective**: Convert inbound direct messages into qualified leads.
*   **Schedule**: Runs 24/7, listening for new messages.
*   **Process**:
    1.  When a new DM arrives, it loads the conversation history.
    2.  Uses a highly detailed system prompt to instruct Claude Haiku to act as "Alex," a freelance developer.
    3.  Generates a natural, human-like response to qualify the lead, asking about scope, timeline, and budget.
    4.  Scores the lead and sends an alert to your personal account if the lead is promising.

---

## 🛠️ Setup & Installation

Follow these steps to get the system running locally.

### 1. Prerequisites
- Python 3.8+
- Git

### 2. Clone the Repository
```bash
git clone <your-repository-url>
cd Telegram-Agent
```

### 3. Install Dependencies
Install all required Python packages using the `requirements.txt` file.
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Create a `.env` file in the root directory by copying the example file.
```bash
cp .env.example .env
```
Now, edit the `.env` file with your actual credentials:
```dotenv
TELEGRAM_API_ID="your_api_id"
TELEGRAM_API_HASH="your_api_hash"
TELEGRAM_PHONE="+1234567890"

# Get this from https://openrouter.ai/
OPENROUTER_API_KEY="your_openrouter_key"

# Your personal Telegram username (without the @) to receive alerts
ALERT_TELEGRAM_USERNAME="your_personal_username"

# This will be generated in the next step
TELEGRAM_SESSION_STRING=""
```

### 5. Authenticate with Telegram (Crucial First Step)
You must run the `login` command once to generate a session string. This allows the bot to log in without needing your password or 2FA code every time, which is essential for server deployment.

```bash
python main.py login
```

Follow the on-screen prompts from Telegram. After a successful login, a **session string** will be printed to your console. **Copy this entire string and paste it into your `.env` file** for the `TELEGRAM_SESSION_STRING` variable.

### 6. Test Your Configuration
Run the built-in test command to ensure all your API keys and connections are working correctly.
```bash
python main.py test
```

---

## ▶️ Usage

### Running the Full System
To start all three agents and run the system as intended, simply execute `main.py`:
```bash
python main.py
```
This will:
- Start the scheduler for the Discovery and Broadcaster agents.
- Immediately begin listening for DMs with the Converter agent.
- Perform a one-time initial discovery run if the database is empty.

### Monitoring the System
You can monitor the system's performance and status using the CLI.

**View the main dashboard:**
```bash
python main.py dashboard
```

**Check conversation analytics:**
```bash
python converter.py stats
```

**Review specific conversations:**
```bash
python converter.py review hot
python converter.py review committed
```

**Watch live logs:**
For real-time insight into the AI's conversations, tail the converter log.
```bash
tail -f logs/converter.log
```

---

## ⚙️ Configuration

Most configuration is handled in `config.py`. The most important variable to customize is `SKILL_MESSAGE`.

- **`SKILL_MESSAGE` in `config.py`**: This is the static message that Agent 2 (Broadcaster) sends to groups. **Edit this message to reflect your personal skills and services.**
- **Scheduling Times**: You can change the `MORNING_TIME`, `EVENING_TIME`, and `DISCOVERY_TIME` in your `.env` file or directly in `config.py`.
- **Keyword Matrix**: For advanced targeting, you can modify the `SKILLS`, `INTENTS`, and `COUNTRIES` lists in `config.py` to change the discovery focus.

---

## ☁️ Deployment on Railway

This project is designed to be deployed on a platform like Railway. Due to the ephemeral filesystem of such platforms, you **must** do the following:

1.  **Set Environment Variables**: Add all the variables from your `.env` file (especially `TELEGRAM_SESSION_STRING`) to the Railway project's environment variable settings.
2.  **Mount a Persistent Volume**:
    - In your Railway project, create a **Volume**.
    - Mount this volume to the path `/app/data`.
    - This is **critical** to ensure your SQLite database (`agent.db`) persists across restarts and deployments. Without this, your bot will lose all its data daily.

---

## 📖 Command Line Interface (CLI) Reference

| Command | Description |
| :--- | :--- |
| `python main.py` | Runs the full system with all agents on schedule. |
| `python main.py help` | Displays the full command reference. |
| `python main.py login` | **(Required for first use)** Authenticates with Telegram and generates a session string. |
| `python main.py test` | Tests all API keys and configurations. |
| `python main.py dashboard` | Shows a high-level overview of the system's status. |
| `python main.py discovery` | Manually triggers the Discovery agent for an immediate run. |
| `python main.py broadcast <slot>` | Manually triggers the Broadcaster agent. `slot` can be `morning` or `evening`. |
| `python converter.py stats` | Displays detailed analytics on lead conversions. |
| `python converter.py review <filter>` | Reviews conversations. `filter` can be `all`, `hot`, `warm`, `cold`, `committed`, or `needs_review`. |