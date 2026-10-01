"""
language: Python 3.10+
file: monitor.py
target: poll free SMS sites for incoming messages on a specific number
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


# ── site parsers ──

def _parse_receivesmss(html: str) -> list[dict]:
    messages = []
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("table tr")
    for row in rows[1:]:
        cols = row.find_all("td")
        if len(cols) >= 3:
            messages.append({
                "sender": cols[0].get_text(strip=True),
                "text": cols[2].get_text(strip=True),
                "time": cols[1].get_text(strip=True),
            })
    return messages


def _parse_receivesmsco(html: str) -> list[dict]:
    messages = []
    soup = BeautifulSoup(html, "html.parser")
    blocks = soup.select(".sms-list-item, .receivesms-table tr")
    for block in blocks:
        cols = block.find_all("td")
        if len(cols) >= 2:
            messages.append({
                "sender": cols[0].get_text(strip=True),
                "text": cols[-1].get_text(strip=True),
                "time": "",
            })
    return messages


def _parse_generic(html: str) -> list[dict]:
    messages = []
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator="\n")
    for line in text.splitlines():
        line = line.strip()
        if re.search(r'\b\d{4,8}\b', line) and len(line) < 300:
            messages.append({"sender": "unknown", "text": line, "time": ""})
    return messages


POLL_TARGETS = [
    {
        "url": "https://receive-smss.com/sms/{clean}/",
        "parser": _parse_receivesmss,
    },
    {
        "url": "https://www.receivesms.co/uk-phone-number/{clean}/",
        "parser": _parse_receivesmsco,
    },
    {
        "url": "https://www.receivesms.co/us-phone-number/{clean}/",
        "parser": _parse_receivesmsco,
    },
    {
        "url": "https://sms24.me/en/numbers/{clean}/",
        "parser": _parse_generic,
    },
    {
        "url": "https://receive-sms.cc/{clean}/",
        "parser": _parse_generic,
    },
    {
        "url": "https://quackr.io/temporary-numbers/{clean}",
        "parser": _parse_generic,
    },
    {
        "url": "https://temp-number.org/numbers/{clean}",
        "parser": _parse_generic,
    },
    {
        "url": "https://onlinesim.io/virtual-phone-numbers/{clean}",
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
                msgs = target["parser"](r.text)
                found.extend(msgs)
            except Exception as e:
                logging.debug(f"poll failed {url}: {e}")
        return found

    def wait_for_sms(self, number: str, timeout: int = 600, interval: int = 6) -> dict | None:
        """
        Poll for new SMS on number.
        Returns first new message dict or None on timeout.
        timeout: seconds to wait (default 10 min)
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
                    logging.info(f"New SMS on {number}: {msg}")
                    return msg
        return None
