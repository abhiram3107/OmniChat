"""
Domain-restricted crawler using requests + trafilatura. Respects allowed domain.
"""
import os, time, urllib.parse, requests
from bs4 import BeautifulSoup
import trafilatura
from typing import List, Dict

ALLOWED_DOMAIN = os.getenv("ALLOWED_DOMAIN", "https://example.com")
# Default base derived from env; can be overridden per-crawl.
_base = urllib.parse.urlparse(ALLOWED_DOMAIN).netloc

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


def same_domain(url: str) -> bool:
    """Allow exact host or any subdomain of the base (e.g., www.)"""
    try:
        netloc = urllib.parse.urlparse(url).netloc.split(":")[0].lower()
        base = (_base or "").split(":")[0].lower()
        if not netloc or not base:
            return False
        return netloc == base or netloc.endswith("." + base)
    except Exception:
        return False


def normalize(url: str) -> str:
    return urllib.parse.urljoin(ALLOWED_DOMAIN, url)


def extract_links(html: str, base_url: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        url = urllib.parse.urljoin(base_url, a["href"])
        if same_domain(url):
            links.append(url.split("#")[0])
    return list(dict.fromkeys(links))


def fetch(url: str) -> Dict[str, str]:
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    html = r.text
    text = trafilatura.extract(html) or ""
    return {"url": url, "html": html, "text": text}


def crawl(start_url: str, max_pages: int = 50) -> List[Dict[str, str]]:
    # Override the allowed base for this crawl so links are domain-restricted
    global _base
    try:
        _base = urllib.parse.urlparse(start_url).netloc or _base
    except Exception:
        pass
    seen, q, out = set(), [start_url], []
    while q and len(out) < max_pages:
        url = q.pop(0)
        if url in seen:
            continue
        seen.add(url)
        try:
            page = fetch(url)
            out.append(page)
            links = extract_links(page["html"], url)
            for l in links:
                if l not in seen and same_domain(l):
                    q.append(l)
            time.sleep(0.2)
        except Exception:
            continue
    return out
