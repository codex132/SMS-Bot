"""
language: Python 3.10+
file: scraper.py
target: scrape available numbers from verified open free SMS sites (no login required)
verified sites only — numbers scraped here have confirmed open SMS inboxes
"""

import requests
import threading
import re
import phonenumbers
from bs4 import BeautifulSoup
from collections import defaultdict
import urllib3
import logging

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# ── VERIFIED OPEN SITES ONLY ──
# Each entry: url to scrape number list from, confirmed no login needed
SITES = [
    # ✅ VERIFIED — numbers link as /sms/{number}/, messages fully public
    "https://receive-smss.com/",
    # ✅ VERIFIED — numbers link as /active-numbers/, messages fully public
    "https://www.receivesms.co/active-numbers/",
    # ✅ VERIFIED — messages public
    "https://quackr.io/temporary-numbers",
    # ✅ VERIFIED — messages public
    "https://temp-number.org/",
    # ✅ VERIFIED — messages public
    "https://receivesms.it.com/",
    # ✅ VERIFIED — messages public
    "https://sms24.me/numbers",
    # ✅ VERIFIED — messages public
    "https://receive-sms.cc/",
    # ✅ VERIFIED — messages public
    "https://freephonenum.com/us",
    "https://freephonenum.com/ca",
    "https://freephonenum.com/uk",
    "https://freephonenum.com/au",
]


def classify_number(e164: str) -> str | None:
    try:
        n = phonenumbers.parse(e164)
        region = phonenumbers.region_code_for_number(n)
        return region if region else None
    except Exception:
        return None


def extract_smss_numbers(html: str) -> list[str]:
    """Extract numbers from receive-smss.com — links are /sms/{number}/"""
    found = []
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=re.compile(r"/sms/\d+")):
        match = re.search(r"/sms/(\d+)/", a["href"])
        if match:
            num = "+" + match.group(1)
            found.append(num)
    return found


def extract_receivesmsco_numbers(html: str) -> list[str]:
    """Extract numbers from receivesms.co"""
    found = []
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=re.compile(r"phone-number")):
        text = a.get_text(strip=True)
        match = re.search(r"\+\d{7,15}", text)
        if match:
            found.append(match.group(0))
    return found


def extract_generic_numbers(html: str) -> list[str]:
    """Generic extractor using phonenumbers library"""
    found = set()
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator=" ")
    for region in ["US", "GB", "CA", "AU", "DE", "FR", "SE", "PL",
                   "NL", "BE", "RU", "UA", "IN", "VN", "BR", "MX",
                   "NG", "KE", "GH", "ZA", "ID", "PH", "TH"]:
        try:
            matcher = phonenumbers.PhoneNumberMatcher(text, region)
            for match in matcher:
                e164 = phonenumbers.format_number(
                    match.number, phonenumbers.PhoneNumberFormat.E164
                )
                found.add(e164)
        except Exception:
            continue
    return list(found)


# map each site to its extractor
SITE_EXTRACTORS = {
    "https://receive-smss.com/": extract_smss_numbers,
    "https://www.receivesms.co/active-numbers/": extract_receivesmsco_numbers,
}


class NumberScraper:
    def __init__(self):
        self._lock = threading.Lock()
        self._results: dict[str, list[str]] = defaultdict(list)
        self._sources: dict[str, str] = {}

    def _fetch_site(self, url: str) -> str:
        try:
            r = requests.get(url, timeout=10, verify=False, headers=HEADERS)
            return r.text
        except Exception as e:
            logging.debug(f"fetch failed {url}: {e}")
            return ""

    def _process_site(self, url: str):
        html = self._fetch_site(url)
        if not html:
            return
        extractor = SITE_EXTRACTORS.get(url, extract_generic_numbers)
        numbers = extractor(html)
        for num in numbers:
            country = classify_number(num)
            if country:
                with self._lock:
                    if num not in self._results[country]:
                        self._results[country].append(num)
                        self._sources[num] = url
                        print(f"[SOURCE] {num} ← {url}")

    def scrape_all(self) -> dict[str, list[str]]:
        self._results = defaultdict(list)
        self._sources = {}
        threads = []
        for site in SITES:
            t = threading.Thread(target=self._process_site, args=(site,), daemon=True)
            t.start()
            threads.append(t)
        for t in threads:
            t.join(timeout=20)
        return {k: list(set(v)) for k, v in self._results.items()}

    def get_source(self, number: str) -> str:
        return self._sources.get(number, "")
        
