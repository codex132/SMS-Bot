"""
language: Python 3.10+
file: monitor.py
target: poll verified open SMS sites for incoming messages on a specific number
Each site confirmed: no login, messages publicly visible
"""

import requests
import time
import re
import logging
from bs4 import BeautifulSoup

urllib3 = __import__("urllib3")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def _strip(n: str) -> str:
    """Strip + and non-digits"""
    return re.sub(r"[^\d]", "", n)


# ── PARSERS — one per site structure ──

def _parse_receivesmss(html: str) -> list[dict]:
    """
    receive-smss.com structure:
    Message in <div> with class pattern, Sender in separate element
    Confirmed open — no login needed
    """
    messages = []
    soup = BeautifulSoup(html, "html.parser")
    # messages are in table rows or specific divs
    # structure: Message | Sender | Time columns
    rows = soup.select("table tr")
    for row in rows[1:]:
        cols = row.find_all("td")
        if len(cols) >= 3:
            msg_text = cols[0].get_text(strip=True)
            sender = cols[1].get_text(strip=True) if len(cols) > 1 else "unknown"
            if msg_text and len(msg_text) < 500:
                messages.append({
                    "sender": sender,
                    "text": msg_text,
                    "time": cols[2].get_text(strip=True) if len(cols) > 2 else "",
                })
    # fallback: grab any bold OTP codes
    if not messages:
        for bold in soup.find_all("strong"):
            text = bold.get_text(strip=True)
            if re.search(r'\b\d{4,8}\b', text):
                parent = bold.find_parent()
                full_text = parent.get_text(strip=True) if parent else text
                messages.append({"sender": "unknown", "text": full_text, "time": ""})
    return messages


def _parse_receivesmsco(html: str) -> list[dict]:
    """
    receivesms.co structure:
    Messages in .sms-list-item or table rows
    Confirmed open — no login needed
    """
    messages = []
    soup = BeautifulSoup(html, "html.parser")
    # try table rows first
    rows = soup.select("table tr, .receivesms-table tr")
    for row in rows[1:]:
        cols = row.find_all("td")
        if len(cols) >= 2:
            messages.append({
                "sender": cols[0].get_text(strip=True),
                "text": cols[-1].get_text(strip=True),
                "time": cols[1].get_text(strip=True) if len(cols) > 2 else "",
            })
    return messages


def _parse_quackr(html: str) -> list[dict]:
    """
    quackr.io structure:
    Messages in .message-item or similar
    Confirmed open — no login needed
    """
    messages = []
    soup = BeautifulSoup(html, "html.parser")
    # quackr uses specific message containers
    items = soup.select(".message-item, .sms-item, .inbox-item, article, .message")
    for item in items:
        text = item.get_text(separator=" ", strip=True)
        if text and re.search(r'\b\d{4,8}\b', text) and len(text) < 500:
            messages.append({"sender": "unknown", "text": text, "time": ""})
    if not messages:
        # fallback generic
        for line in soup.get_text(separator="\n").splitlines():
            line = line.strip()
            if re.search(r'\b\d{4,8}\b', line) and 5 < len(line) < 300:
                messages.append({"sender": "unknown", "text": line, "time": ""})
    return messages


def _parse_generic(html: str) -> list[dict]:
    """Generic fallback — grabs OTP-shaped content"""
    messages = []
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator="\n")
    for line in text.splitlines():
        line = line.strip()
        if re.search(r'\b\d{4,8}\b', line) and 5 < len(line) < 300:
            messages.append({"sender": "unknown", "text": line, "time": ""})
    return messages


# ── POLL TARGETS — only verified open sites ──
# URL format: {clean} = digits only, no +
POLL_TARGETS = [
    {
        # ✅ VERIFIED OPEN — URL: /sms/{digits}/
        "url": "https://receive-smss.com/sms/{clean}/",
        "parser": _parse_receivesmss,
    },
    {
        # ✅ VERIFIED OPEN — UK numbers endpoint
        "url": "https://www.receivesms.co/uk-phone-number/{clean}/",
        "parser": _parse_receivesmsco,
    },
    {
        # ✅ VERIFIED OPEN — US numbers endpoint
        "url": "https://www.receivesms.co/us-phone-number/{clean}/",
        "parser": _parse_receivesmsco,
    },
    {
        # ✅ VERIFIED OPEN — quackr
        "url": "https://quackr.io/temporary-numbers/{clean}",
        "parser": _parse_quackr,
    },
    {
        # ✅ VERIFIED OPEN — temp-number.org
        "url": "https://temp-number.org/numbers/{clean}",
        "parser": _parse_generic,
    },
    {
        # ✅ VERIFIED OPEN — sms24.me
        "url": "https://sms24.me/en/numbers/{clean}/",
        "parser": _parse_generic,
    },
    {
        # ✅ VERIFIED OPEN — receive-sms.cc
        "url": "https://receive-sms.cc/{clean}/",
        "parser": _parse_generic,
    },
    {
        # ✅ VERIFIED OPEN — receivesms.it.com
        "url": "https://receivesms.it.com/numbers/{clean}/",
        "parser": _parse_generic,
    },
    {
        # ✅ VERIFIED OPEN — freephonenum.com
        "url": "https://freephonenum.com/receive-sms/{clean}/",
        "parser": _parse_generic,
    },
]


class SMSMonitor:
    def _poll_once(self, number: str) -> list[dict]:
        clean = _strip(number)
        found = []
        for target in POLL_TARGETS:
            url = target["url"].replace("{clean}", clean)
            try:
                r = requests.get(url, headers=HEADERS, timeout=8, verify=False)
                if r.status_code == 200:
                    msgs = target["parser"](r.text)
                    found.extend(msgs)
            except Exception as e:
                logging.debug(f"poll failed {url}: {e}")
        # deduplicate by text
        seen = set()
        unique = []
        for m in found:
            if m["text"] not in seen and m["text"]:
                seen.add(m["text"])
                unique.append(m)
        return unique

    def wait_for_sms(self, number: str, timeout: int = 600, interval: int = 6) -> dict | None:
        """
        Poll all verified open sites for new SMS on number.
        Returns first new message or None on timeout.
        timeout: 600s (10 min)
        interval: poll every 6 seconds
        """
        deadline = time.time() + timeout
        baseline = {m["text"] for m in self._poll_once(number)}
        logging.info(f"Monitoring {number} | baseline: {len(baseline)} existing messages")

        while time.time() < deadline:
            time.sleep(interval)
            current = self._poll_once(number)
            for msg in current:
                if msg["text"] not in baseline:
                    logging.info(f"✅ New SMS on {number}: {msg['text'][:50]}")
                    return msg
        logging.info(f"⏱ Timeout monitoring {number}")
        return None
