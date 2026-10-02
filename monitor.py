"""
language: Python 3.10+
file: monitor.py
target: poll verified open SMS sites — no login required
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
    return re.sub(r"[^\d]", "", n)


def _parse_receivesmss(html: str) -> list[dict]:
    """
    receive-smss.com individual number page.
    OTPs are in <strong> tags. Sender is in separate link.
    Confirmed open — no login for any number.
    """
    messages = []
    soup = BeautifulSoup(html, "html.parser")

    # each message block — look for elements containing bold OTP codes
    # structure: message text with <strong>CODE</strong>, sender as link
    seen = set()

    # try to find message containers
    for container in soup.select(".message, .sms-message, .msg, article, .single-message"):
        text = container.get_text(separator=" ", strip=True)
        if text and len(text) < 500 and text not in seen:
            sender_tag = container.find("a")
            sender = sender_tag.get_text(strip=True) if sender_tag else "unknown"
            messages.append({"sender": sender, "text": text, "time": ""})
            seen.add(text)

    # fallback: grab full paragraph text containing bold OTP codes
    if not messages:
        for bold in soup.find_all("strong"):
            code = bold.get_text(strip=True)
            if re.search(r'\b\d{4,8}\b', code):
                parent = bold.find_parent(["p", "div", "td", "li"])
                full_text = parent.get_text(separator=" ", strip=True) if parent else code
                if full_text not in seen and len(full_text) < 500:
                    messages.append({"sender": "unknown", "text": full_text, "time": ""})
                    seen.add(full_text)

    # second fallback: any text line with OTP pattern
    if not messages:
        text_content = soup.get_text(separator="\n")
        for line in text_content.splitlines():
            line = line.strip()
            if re.search(r'\b\d{4,8}\b', line) and 10 < len(line) < 300:
                if line not in seen:
                    messages.append({"sender": "unknown", "text": line, "time": ""})
                    seen.add(line)

    return messages


def _parse_receivesmsco(html: str) -> list[dict]:
    """receivesms.co — table structure, confirmed open"""
    messages = []
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("table tr, .receivesms-table tr")
    for row in rows[1:]:
        cols = row.find_all("td")
        if len(cols) >= 2:
            text = cols[-1].get_text(strip=True)
            if text and len(text) < 500:
                messages.append({
                    "sender": cols[0].get_text(strip=True),
                    "text": text,
                    "time": cols[1].get_text(strip=True) if len(cols) > 2 else "",
                })
    return messages


def _parse_generic(html: str) -> list[dict]:
    """Generic fallback — OTP pattern scan"""
    messages = []
    seen = set()
    soup = BeautifulSoup(html, "html.parser")

    # try bold tags first
    for bold in soup.find_all("strong"):
        code = bold.get_text(strip=True)
        if re.search(r'\b\d{4,8}\b', code):
            parent = bold.find_parent(["p", "div", "td", "li"])
            full_text = parent.get_text(separator=" ", strip=True) if parent else code
            if full_text not in seen and len(full_text) < 500:
                messages.append({"sender": "unknown", "text": full_text, "time": ""})
                seen.add(full_text)

    # fallback line scan
    if not messages:
        for line in soup.get_text(separator="\n").splitlines():
            line = line.strip()
            if re.search(r'\b\d{4,8}\b', line) and 10 < len(line) < 300:
                if line not in seen:
                    messages.append({"sender": "unknown", "text": line, "time": ""})
                    seen.add(line)
    return messages


# ── VERIFIED OPEN POLL TARGETS — no login required ──
POLL_TARGETS = [
    {
        # ✅ OPEN — confirmed Facebook/WhatsApp OTPs land here
        "url": "https://receive-smss.com/sms/{clean}/",
        "parser": _parse_receivesmss,
    },
    {
        # ✅ OPEN — UK numbers endpoint
        "url": "https://www.receivesms.co/uk-phone-number/{clean}/",
        "parser": _parse_receivesmsco,
    },
    {
        # ✅ OPEN — US numbers endpoint
        "url": "https://www.receivesms.co/us-phone-number/{clean}/",
        "parser": _parse_receivesmsco,
    },
    {
        # ✅ OPEN — Germany endpoint
        "url": "https://www.receivesms.co/germany-phone-number/{clean}/",
        "parser": _parse_receivesmsco,
    },
    {
        # ✅ OPEN — quackr
        "url": "https://quackr.io/temporary-numbers/{clean}",
        "parser": _parse_generic,
    },
    {
        # ✅ OPEN — temp-number.org
        "url": "https://temp-number.org/numbers/{clean}",
        "parser": _parse_generic,
    },
    {
        # ✅ OPEN — sms24.me
        "url": "https://sms24.me/en/numbers/{clean}/",
        "parser": _parse_generic,
    },
    {
        # ✅ OPEN — receivesms.it.com
        "url": "https://receivesms.it.com/numbers/{clean}/",
        "parser": _parse_generic,
    },
    {
        # ✅ OPEN — receivesms.me (fast, confirmed working)
        "url": "https://receivesms.me/number/{clean}",
        "parser": _parse_generic,
    },
    {
        # ✅ OPEN — receive-sms.cc
        "url": "https://receive-sms.cc/{clean}/",
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
            if m["text"] and m["text"] not in seen:
                seen.add(m["text"])
                unique.append(m)
        return unique

    def wait_for_sms(self, number: str, timeout: int = 600, interval: int = 6) -> dict | None:
        deadline = time.time() + timeout
        baseline = {m["text"] for m in self._poll_once(number)}
        logging.info(f"Monitoring {number} | baseline: {len(baseline)} messages")

        while time.time() < deadline:
            time.sleep(interval)
            current = self._poll_once(number)
            for msg in current:
                if msg["text"] not in baseline:
                    logging.info(f"✅ New SMS on {number}: {msg['text'][:60]}")
                    return msg
        logging.info(f"⏱ Timeout on {number}")
        return None
