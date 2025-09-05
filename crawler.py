"""
Domain-restricted crawler with robust text extraction.
"""
import os, time, urllib.parse, requests
from bs4 import BeautifulSoup
import trafilatura
from typing import List, Dict, Optional

# Try readability-lxml; fall back gracefully if not installed
try:
    from readability import Document  # provided by readability-lxml
except Exception:
    Document = None

ALLOWED_DOMAIN = os.getenv("ALLOWED_DOMAIN", "https://example.com")
RENDER_JS = os.getenv("RENDER_JS", "0").lower() in ("1", "true", "yes")
_base = urllib.parse.urlparse(ALLOWED_DOMAIN).netloc

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit(537.36) (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

_session = requests.Session()
_session.headers.update(HEADERS)

def same_domain(url: str) -> bool:
    try:
        netloc = urllib.parse.urlparse(url).netloc.split(":")[0].lower()
        base = (_base or "").split(":")[0].lower()
        return bool(netloc) and bool(base) and (netloc == base or netloc.endswith("." + base))
    except Exception:
        return False

def _visible_text_from_bs(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "template", "nav", "footer", "header", "svg"]):
        tag.extract()
    text = soup.get_text(separator=" ")
    return " ".join(text.split())

def extract_text(html: str, url: str) -> str:
    # 1) trafilatura
    txt = trafilatura.extract(html, include_tables=True) or ""
    if txt.strip():
        return " ".join(txt.split())

    # 2) readability-lxml (if available)
    if Document is not None:
        try:
            doc = Document(html)
            main_html = doc.summary(html_partial=True)
            if main_html:
                soup = BeautifulSoup(main_html, "html.parser")
                text = " ".join(soup.get_text(separator=" ").split())
                if text.strip():
                    return text
        except Exception:
            pass

    # 3) BeautifulSoup fallback
    return _visible_text_from_bs(html)

def extract_links(html: str, base_url: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        url = urllib.parse.urljoin(base_url, a["href"]).split("#")[0]
        if same_domain(url):
            links.append(url)
    return list(dict.fromkeys(links))

def fetch(url: str) -> Dict[str, str]:
    html: Optional[str] = None
    if RENDER_JS:
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(user_agent=HEADERS["User-Agent"])
                page.goto(url, wait_until="networkidle", timeout=30000)
                html = page.content()
                browser.close()
        except Exception:
            html = None

    if html is None:
        r = _session.get(url, timeout=20, allow_redirects=True)
        r.raise_for_status()
        if "text/html" not in (r.headers.get("Content-Type", "") or ""):
            return {"url": url, "html": "", "text": ""}
        html = r.text

    return {"url": url, "html": html, "text": extract_text(html, url) if html else ""}

def crawl(start_url: str, max_pages: int = 50) -> List[Dict[str, str]]:
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
            if page.get("html"):
                for l in extract_links(page["html"], url):
                    if l not in seen and same_domain(l):
                        q.append(l)
            time.sleep(0.2)
        except Exception:
            continue
    return out
