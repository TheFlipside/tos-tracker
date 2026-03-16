#!/usr/bin/env python3
"""Fetch Terms of Service and Privacy Policy pages from sources.txt.

Parses a markdown-style source list, downloads each URL, extracts
readable text, and stores it under pages/<company>/<slug>.txt for
version-control tracking.

Uses Playwright (headless browser) by default for JS-heavy sites.
Falls back to plain HTTP (requests) when the browser is blocked
(e.g. Amazon detects automation but allows regular HTTP clients).
"""

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

SOURCES_FILE = "sources.txt"
OUTPUT_DIR = Path("pages")
PAGE_TIMEOUT_MS = 30_000
NAVIGATION_WAIT_MS = 3000
HTTP_TIMEOUT = 30

# Minimum body length (chars) to consider a fetch successful.
# Catches error pages / CAPTCHA stubs that return 200.
MIN_CONTENT_LENGTH = 200

# Common boilerplate tags to strip before extracting text.
STRIP_TAGS = [
    "nav",
    "header",
    "footer",
    "script",
    "style",
    "noscript",
    "svg",
    "img",
    "iframe",
]

HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}


def parse_sources(path: str) -> list[tuple[str, str]]:
    """Parse sources.txt into a list of (company, url) tuples.

    Lines starting with '#' or '##' set the current company name.
    Non-empty lines that look like URLs are collected under
    that company.
    """
    entries: list[tuple[str, str]] = []
    current_company = "unknown"

    with open(path, encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line:
                continue
            heading = re.match(r"^#{1,3}\s+(.+)$", line)
            if heading:
                current_company = heading.group(1).strip()
                continue
            if line.startswith(("http://", "https://")):
                entries.append((current_company, line))

    return entries


def url_to_filename(url: str) -> str:
    """Derive a filesystem-safe filename from a URL path."""
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    if parsed.query:
        path = f"{path}_{parsed.query}"
    if not path:
        path = "index"
    # Replace path separators and unsafe chars with underscores.
    safe = re.sub(r"[^a-zA-Z0-9._-]", "_", path)
    # Collapse repeated underscores.
    safe = re.sub(r"_+", "_", safe).strip("_")
    return f"{safe}.txt"


def extract_text(html: str) -> str:
    """Strip HTML and return clean, readable text."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(STRIP_TAGS):
        tag.decompose()
    text = soup.get_text(separator="\n")
    # Collapse blank lines and strip trailing whitespace per line.
    lines = [line.rstrip() for line in text.splitlines()]
    cleaned = re.sub(r"\n{3,}", "\n\n", "\n".join(lines))
    return cleaned.strip() + "\n"


def slugify_company(name: str) -> str:
    """Convert a company name to a directory-safe slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


def _fetch_http(url: str) -> str:
    """Fetch a URL via plain HTTP and return extracted text."""
    resp = requests.get(url, headers=HTTP_HEADERS, timeout=HTTP_TIMEOUT)
    resp.raise_for_status()
    return extract_text(resp.text)


def _fetch_browser(page, url: str, wait_ms: int) -> str:
    """Fetch a URL via Playwright and return extracted text."""
    page.goto(url, wait_until="networkidle")
    page.wait_for_timeout(wait_ms)
    return extract_text(page.content())


def _is_stub(text: str) -> bool:
    """Return True if the text looks like an error stub."""
    return len(text.strip()) < MIN_CONTENT_LENGTH


def _fetch_one(page, url: str, dest: Path, wait_ms: int) -> bool:
    """Fetch a URL with browser, falling back to HTTP.

    Returns True on success, False on failure.
    """
    text = ""

    # Try Playwright first (handles JS-rendered sites).
    try:
        text = _fetch_browser(page, url, wait_ms)
    except PlaywrightError as exc:
        msg = str(exc).splitlines()[0]
        print(f"  WARN browser failed: {msg}", file=sys.stderr)

    # Fall back to plain HTTP if browser got blocked / stub.
    if _is_stub(text):
        try:
            text = _fetch_http(url)
        except requests.RequestException as exc:
            print(f" FAIL {url} — {exc}", file=sys.stderr)
            return False

    if _is_stub(text):
        print(f" FAIL {url} — content too short", file=sys.stderr)
        return False

    dest.write_text(text, encoding="utf-8")
    print(f"  OK  {dest}")
    return True


def _make_browser_context(pw):
    """Create a Playwright browser and context."""
    browser = pw.chromium.launch(headless=True)
    context = browser.new_context(
        locale="en-US",
        user_agent=HTTP_HEADERS["User-Agent"],
    )
    return browser, context


def fetch_all(
    entries: list[tuple[str, str]],
    output_dir: Path,
    wait_ms: int,
) -> tuple[int, int]:
    """Fetch every URL with browser + HTTP fallback.

    Returns (succeeded, failed) counts.
    """
    succeeded = 0
    failed = 0

    with sync_playwright() as pw:
        browser, context = _make_browser_context(pw)
        page = context.new_page()
        page.set_default_timeout(PAGE_TIMEOUT_MS)

        for company, url in entries:
            company_dir = output_dir / slugify_company(company)
            company_dir.mkdir(parents=True, exist_ok=True)
            dest = company_dir / url_to_filename(url)

            if _fetch_one(page, url, dest, wait_ms):
                succeeded += 1
            else:
                failed += 1

        browser.close()

    return succeeded, failed


def main() -> int:
    """Entry point: parse sources, fetch pages, write output."""
    parser = argparse.ArgumentParser(
        description="Fetch TOS/privacy pages from sources.txt."
    )
    parser.add_argument(
        "-s",
        "--sources",
        default=SOURCES_FILE,
        help=f"Sources file (default: {SOURCES_FILE})",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=str(OUTPUT_DIR),
        help=f"Output directory (default: {OUTPUT_DIR})",
    )
    parser.add_argument(
        "-w",
        "--wait",
        type=int,
        default=NAVIGATION_WAIT_MS,
        help=f"Extra wait after load, ms (default: {NAVIGATION_WAIT_MS})",
    )
    args = parser.parse_args()

    sources_path = args.sources
    output_dir = Path(args.output)

    entries = parse_sources(sources_path)
    if not entries:
        print(
            f"No URLs found in {sources_path}",
            file=sys.stderr,
        )
        return 1

    print(f"Found {len(entries)} URLs from {sources_path}")
    succeeded, failed = fetch_all(entries, output_dir, args.wait)
    print(f"\nDone: {succeeded} succeeded, {failed} failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
