#!/usr/bin/env python3
"""Fetch Terms of Service and Privacy Policy pages from sources.txt.

Parses a markdown-style source list, downloads each URL,
extracts readable text, and stores it under pages/<company>/<slug>.txt
for version-control tracking.
"""

import argparse
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

SOURCES_FILE = "sources.txt"
OUTPUT_DIR = Path("pages")
REQUEST_TIMEOUT = 30
DELAY_BETWEEN_REQUESTS = 1.0

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


def parse_sources(path: str) -> list[tuple[str, str]]:
    """Parse sources.txt into a list of (company, url) tuples.

    Lines starting with '#' or '##' set the current company name.
    Non-empty lines that look like URLs are collected under that company.
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
            if line.startswith("http://") or line.startswith("https://"):
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


def fetch_page(url: str) -> str:
    """Download a URL and return its extracted text content."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    }
    resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return extract_text(resp.text)


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


def main() -> int:
    """Entry point: parse sources, fetch pages, write output."""
    parser = argparse.ArgumentParser(
        description="Fetch TOS/privacy pages listed in sources.txt."
    )
    parser.add_argument(
        "-s",
        "--sources",
        default=SOURCES_FILE,
        help=f"Path to the sources file (default: {SOURCES_FILE})",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=str(OUTPUT_DIR),
        help=f"Output directory (default: {OUTPUT_DIR})",
    )
    parser.add_argument(
        "-d",
        "--delay",
        type=float,
        default=DELAY_BETWEEN_REQUESTS,
        help=f"Seconds between requests (default: {DELAY_BETWEEN_REQUESTS})",
    )
    args = parser.parse_args()

    sources_path = args.sources
    output_dir = Path(args.output)

    entries = parse_sources(sources_path)
    if not entries:
        print(f"No URLs found in {sources_path}", file=sys.stderr)
        return 1

    print(f"Found {len(entries)} URLs from {sources_path}")

    succeeded = 0
    failed = 0

    for company, url in entries:
        company_dir = output_dir / slugify_company(company)
        company_dir.mkdir(parents=True, exist_ok=True)
        filename = url_to_filename(url)
        dest = company_dir / filename

        try:
            text = fetch_page(url)
            dest.write_text(text, encoding="utf-8")
            print(f"  OK  {dest}")
            succeeded += 1
        except requests.RequestException as exc:
            print(f" FAIL {url} — {exc}", file=sys.stderr)
            failed += 1

        time.sleep(args.delay)

    print(f"\nDone: {succeeded} succeeded, {failed} failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
