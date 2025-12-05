#!/usr/bin/env python3
"""
Fetch Debezium Atom feed, filter entries by author name(s), and inject a Markdown list
into README.md between the markers:

<!-- DEBEZIUM-POSTS:START -->
... generated content ...
<!-- DEBEZIUM-POSTS:END -->

Usage:
  python3 scripts/fetch_debezium.py \
    --feed-url "https://debezium.io/blog.atom" \
    --authors "Fiore Mario Vitale" \
    --readme README.md
"""
from __future__ import annotations
import argparse
import feedparser
import requests
from datetime import datetime
from typing import List, Optional
import sys
import re
import os

START_MARKER = "<!-- DEBEZIUM-POSTS:START -->"
END_MARKER = "<!-- DEBEZIUM-POSTS:END -->"

def fetch_feed(feed_url: str, timeout: int = 15) -> feedparser.FeedParserDict:
    resp = requests.get(feed_url, timeout=timeout, headers={"User-Agent": "mfvitale-debezium-fetcher/1.0"})
    resp.raise_for_status()
    return feedparser.parse(resp.text)

def get_entry_attr(entry, key, default=None):
    """Safely get an attribute from a feedparser entry (dict-like)."""
    if hasattr(entry, "get"):
        return entry.get(key, default)
    return getattr(entry, key, default)

def parse_datetime_tuple(parsed_tuple) -> Optional[datetime]:
    """Safely parse a time tuple (from feedparser) into a datetime object."""
    if not parsed_tuple or not isinstance(parsed_tuple, (tuple, list)):
        return None
    if len(parsed_tuple) < 6:
        return None
    try:
        return datetime(*parsed_tuple[:6])
    except (TypeError, ValueError):
        return None

def entry_date_key(entry) -> datetime:
    """Extract the publication or update date from an entry for sorting."""
    published_parsed = get_entry_attr(entry, "published_parsed")
    dt = parse_datetime_tuple(published_parsed)
    if dt:
        return dt
    updated_parsed = get_entry_attr(entry, "updated_parsed")
    dt = parse_datetime_tuple(updated_parsed)
    if dt:
        return dt
    return datetime.min

def entry_author_names(entry) -> List[str]:
    names = []
    author = get_entry_attr(entry, "author")
    if author:
        names.append(author)
    authors = get_entry_attr(entry, "authors", [])
    if authors:
        for a in authors:
            if isinstance(a, dict):
                name = a.get("name") or a.get("email") or ""
                if name:
                    names.append(name)
            else:
                names.append(str(a))
    return list(dict.fromkeys([n.strip() for n in names if n and n.strip()]))

def matches_author(entry, filters: List[str]) -> bool:
    if not filters:
        return False
    entry_names = entry_author_names(entry)
    if not entry_names:
        return False
    entry_joined = " ".join(entry_names).lower()
    for f in filters:
        if f.lower() in entry_joined:
            return True
    return False

def format_entry_md(entry) -> str:
    title = get_entry_attr(entry, "title", "Untitled").strip()
    link = get_entry_attr(entry, "link", "")
    dt = None
    published_parsed = get_entry_attr(entry, "published_parsed")
    dt = parse_datetime_tuple(published_parsed)
    if not dt:
        for k in ("updated_parsed",):
            val = get_entry_attr(entry, k)
            dt = parse_datetime_tuple(val)
            if dt:
                break
    date_str = dt.strftime("%Y-%m-%d") if dt else ""
    authors = ", ".join(entry_author_names(entry))
    if link:
        return f"- {date_str} [{title}]({link}) — {authors}"
    else:
        return f"- {date_str} {title} — {authors}"

def generate_markdown(entries, header: Optional[str] = None) -> str:
    lines = []
    if header:
        lines.append(header)
        lines.append("")
    for e in entries:
        lines.append(format_entry_md(e))
    if not entries:
        lines.append("_No matching Debezium posts found._")
    return "\n".join(lines)

def replace_block_in_file(filepath: str, start_marker: str, end_marker: str, new_block: str) -> None:
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as fh:
            content = fh.read()
    else:
        content = ""
    pattern = re.compile(
        re.escape(start_marker) + r".*?" + re.escape(end_marker),
        flags=re.DOTALL
    )
    full_block = start_marker + "\n" + new_block.strip() + "\n" + end_marker
    if pattern.search(content):
        new_content = pattern.sub(full_block, content)
    else:
        if content and not content.endswith("\n"):
            content += "\n"
        new_content = content + "\n" + full_block + "\n"
    with open(filepath, "w", encoding="utf-8") as fh:
        fh.write(new_content)

def main():
    parser = argparse.ArgumentParser(description="Fetch Debezium Atom feed and inject filtered posts into README")
    parser.add_argument("--feed-url", default="https://debezium.io/blog.atom", help="Atom feed URL")
    parser.add_argument("--authors", default="Fiore Mario Vitale", help="Comma-separated author name fragments to match (case-insensitive)")
    parser.add_argument("--readme", default="README.md", help="Path to README.md to update")
    parser.add_argument("--header", default="## Debezium posts by specified author(s)", help="Header to add before the list")
    parser.add_argument("--max", type=int, default=20, help="Max items to include")
    args = parser.parse_args()

    filters = [s.strip() for s in args.authors.split(",") if s.strip()]
    if not filters:
        print("No author filters provided; exiting.", file=sys.stderr)
        sys.exit(1)

    print(f"Fetching feed from {args.feed_url} ...")
    feed = fetch_feed(args.feed_url)
    entries = feed.entries or []
    print(f"Fetched {len(entries)} entries from feed")

    matched = [e for e in entries if matches_author(e, filters)]
    matched.sort(key=entry_date_key, reverse=True)
    matched = matched[: args.max]

    md = generate_markdown(matched, header=args.header + f" (filters: {', '.join(filters)})")
    print(f"Found {len(matched)} matching entries; updating {args.readme}")
    replace_block_in_file(args.readme, START_MARKER, END_MARKER, md)
    print("Done.")

if __name__ == "__main__":
    main()
