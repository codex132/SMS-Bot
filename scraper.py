"""
language: Python 3.10+
file: scraper.py
target: scrape available numbers from public free SMS sites
"""

import requests
import threading
import phonenumbers
from bs4 import BeautifulSoup
from collections import defaultdict
import urllib3
import logging

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SITES = [
    "https://receive-smss.com/",
    "https://sms24.me/numbers",
    "https://www.receivesms.co/active-numbers/",
    "https://receive-sms.cc/",
    "https://getfreesmsnumber.com/free-receive-sms-from-us",
    "https://getfreesmsnumber.com/free-receive-sms-from-uk",
    "https://getfreesmsnumber.com/free-receive-sms-from-ca",
    "https://getfreesmsnumber.com/free-receive-sms-from-au",
    "https://getfreesmsnumber.com/free-receive-sms-from-de",
    "https://getfreesmsnumber.com/free-receive-sms-from-fr",
    "https://getfreesmsnumber.com/free-receive-sms-from-se",
    "https://getfreesmsnumber.com/free-receive-sms-from-pl",
    "https://sms-online.co/receive-free-sms",
    "https://freephonenum.com/us",
    "https://freephonenum.com/ca",
    "https://smstools.online/receive-free-sms/germany/",
    "https://smstools.online/receive-free-sms/france/",
    "https://smstools.online/receive-free-sms/australia/",
    "https://www.receivesmsonline.net/",
    "https://www.freeonlinephone.org/",
    "https://receive-sms.com/",
    "https://receiveasms.com/",
    "https://hs3x.com/",
    "https://online-sms.org/",
    "https://quackr.io/temporary-numbers",
    "https://temp-number.org/",
    "https://receive-smsonline.net/",
]

# map country code → list of known number prefixes to help classify
COUNTRY_PREFIXES = {
    "US": "+1",
    "GB": "+44",
    "CA": "+1",    # CA and US share +1 — differentiated by area code below
    "AU": "+61",
    "DE": "+49",
    "FR": "+33",
    "SE": "+46",
    "PL": "+48",
    "NL": "+31",
    "BE": "+32",
    "RU": "+7",
    "UA": "+380",
    "IN": "+91",
    "VN": "+84",
    "BR": "+55",
    "MX": "+52",
}

# CA area codes to separate from US +1
CA_AREA_CODES = {
    "204","226","236","249","250","289","306","343","365","387","403","416",
    "418","431","437","438","450","506","514","519","548","579","581","587",
    "604","613","639","647","672","705","709","742","778","780","782","807",
    "819","825","867","873","902","905",
}


def classify_number(e164: str) -> str | None:
    """Return ISO country code or None if unrecognised."""
    try:
        n = phonenumbers.parse(e164)
        region = phonenumbers.region_code_for_number(n)
        return region if region else None
    except Exception:
        return None


class NumberScraper:
    def __init__(self):
        self._lock = threading.Lock()
        self._results: dict[str, list[str]] = defaultdict(list)

    def _fetch_site(self, url: str) -> str:
        try:
            r = requests.get(url, timeout=8, verify=False,
                             headers={"User-Agent": "Mozilla/5.0"})
            return r.text
        except Exception as e:
            logging.debug(f"fetch failed {url}: {e}")
            return ""

    def _extract_numbers(self, html: str) -> list[str]:
        """Use phonenumbers matcher across all country contexts."""
        found = set()
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(separator=" ")

        # scan against every country context for maximum extraction
        for region in phonenumbers.SUPPORTED_REGIONS:
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

    def _process_site(self, url: str):
        html = self._fetch_site(url)
        if not html:
            return
        numbers = self._extract_numbers(html)
        for num in numbers:
            country = classify_number(num)
            if country:
                with self._lock:
                    if num not in self._results[country]:
                        self._results[country].append(num)

    def scrape_all(self) -> dict[str, list[str]]:
        """Scrape all sites concurrently, return {country: [numbers]}."""
        self._results = defaultdict(list)
        threads = []
        for site in SITES:
            t = threading.Thread(target=self._process_site, args=(site,), daemon=True)
            t.start()
            threads.append(t)
        for t in threads:
            t.join(timeout=15)

        # deduplicate
        return {k: list(set(v)) for k, v in self._results.items()}
