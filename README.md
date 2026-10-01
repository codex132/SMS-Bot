# Free Virtual Number Telegram Bot

Pulls available numbers from 20+ public free SMS sites and delivers OTPs to users via Telegram.

---

## Setup

### 1. Get a Bot Token
- Open Telegram → search `@BotFather`
- Send `/newbot` → follow prompts → copy the token

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Set your token
Open `bot.py` line 18:
```python
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
```
Replace with your actual token.

### 4. Run
```bash
python bot.py
```

---

## Bot Commands

| Command | Action |
|---|---|
| `/start` | Show country picker |
| `/numbers` | Same as start |
| `/status` | Show pool size and status |

---

## How It Works

1. **Scraper** (`scraper.py`) — hits 25+ public free SMS sites simultaneously using threads, extracts numbers using the `phonenumbers` library, classifies by country code
2. **Monitor** (`monitor.py`) — polls multiple site endpoints for a specific number, detects new messages by diffing against a baseline snapshot
3. **Bot** (`bot.py`) — Telegram interface via aiogram 3.x, country buttons, number selection, background monitoring task per user request

Pool refreshes every 30 minutes automatically.

---

## Notes

- **WhatsApp success rate: ~15-30%** — these shared public numbers are known to WhatsApp. Some work, many are flagged. Rotate aggressively.
- Numbers are public/shared — multiple users may be monitoring the same number simultaneously
- No database required — runs stateless
- Deploy on any VPS, Raspberry Pi, or keep running locally

---

## Extend It

- Add more sites to `POLL_TARGETS` in `monitor.py`
- Add more countries to the keyboard in `bot.py`
- Wire in SQLite to track which user claimed which number
- Add a `/history` command to show past received OTPs
