#!/usr/bin/env python3
"""
Cache-aware news context provider for OpenClaw.

Runs news_fetch.py and caches the result for CACHE_TTL_MINUTES.
On a cache hit the cached output is returned instantly, saving the
network round-trips and keeping context injection fast.

Usage:
    python news_context.py [--ttl MINUTES] [--force]

Options:
    --ttl MINUTES   Cache lifetime in minutes (default: 30)
    --force         Bypass cache and always fetch fresh news
"""

import os
import sys
import subprocess
import time
import argparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TMP_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "tmp")
CACHE_FILE = os.path.join(TMP_DIR, "news_cache.txt")
CACHE_TS_FILE = CACHE_FILE + ".ts"
NEWS_SCRIPT = os.path.join(SCRIPT_DIR, "news_fetch.py")


def is_cache_fresh(ttl_minutes: int) -> bool:
    if not os.path.exists(CACHE_FILE) or not os.path.exists(CACHE_TS_FILE):
        return False
    try:
        with open(CACHE_TS_FILE) as f:
            ts = float(f.read().strip())
        age_minutes = (time.time() - ts) / 60.0
        return age_minutes < ttl_minutes
    except Exception:
        return False


def read_cache() -> str:
    with open(CACHE_FILE, encoding="utf-8") as f:
        return f.read()


def save_cache(content: str) -> None:
    os.makedirs(TMP_DIR, exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        f.write(content)
    with open(CACHE_TS_FILE, "w") as f:
        f.write(str(time.time()))


def fetch_fresh() -> str:
    result = subprocess.run(
        [sys.executable, NEWS_SCRIPT],
        capture_output=True,
        text=True,
        timeout=90,
    )
    return result.stdout


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ttl", type=int, default=30, help="Cache TTL in minutes")
    parser.add_argument("--force", action="store_true", help="Bypass cache")
    args = parser.parse_args()

    if not args.force and is_cache_fresh(args.ttl):
        print(read_cache(), end="")
        return

    content = fetch_fresh()
    if content.strip():
        save_cache(content)
    print(content, end="")


if __name__ == "__main__":
    main()
