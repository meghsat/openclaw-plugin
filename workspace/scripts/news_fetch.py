#!/usr/bin/env python3

import json
import os
import sys
import re
import ssl
import argparse
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.parse import urlparse
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

_SSL_Context = ssl.create_default_context()
REQUEST_TIMEOUT = 15

_ABBREV_PATTERN = re.compile(r"\b(AI|AGI|LLM|GPU|TPU|RAG)\b")
_KEYWORD_PATTERN = re.compile(
    r"agentic|amazon|AMD|Anthropic|artificial intelligence|"
    r"AWS|ChatGPT|chip|Claude|Codex|Cohere|Copilot|"
    r"DeepMind|DeepSeek|deep learning|diffusion|drones|"
    r"fine-tuning|gen AI|generative AI|Gemini|Google AI|"
    r"Grok|health care|Hugging Face|inference|"
    r"language model|machine learning|Meta AI|Microsoft|"
    r"multimodal|neural network|NVIDIA|open source|"
    r"OpenAI|Perplexity|Qwen|reasoning model|robotics|"
    r"training|transformer|xAI|autonomous",
    re.IGNORECASE,
)

FEEDS = [
    ("TechCrunch AI",     "https://techcrunch.com/category/artificial-intelligence/feed/"),
    ("The Verge AI",      "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"),
    ("THE DECODER",       "https://the-decoder.com/feed/"),
    ("404 Media",         "https://www.404media.co/rss/"),
    ("VentureBeat AI",    "https://venturebeat.com/category/ai/feed/"),
    ("AI TechPark",       "https://ai-techpark.com/category/ai/feed/"),
    ("Wired AI",          "https://www.wired.com/feed/tag/ai/latest/rss"),
    ("MIT Tech Review",   "https://www.technologyreview.com/feed/"),
    ("AI News",           "https://www.artificialintelligence-news.com/feed/rss/"),
    ("OpenAI Blog",       "https://openai.com/blog/rss.xml"),
    ("Hugging Face Blog", "https://huggingface.co/blog/feed.xml"),
    ("Simon Willison",    "https://simonwillison.net/atom/everything/"),
    ("SiliconANGLE",      "https://siliconangle.com/category/ai/feed/"),
    ("Ars Technica AI",   "https://feeds.arstechnica.com/arstechnica/technology-lab"),
    ("Axios AI",          "https://api.axios.com/feed/top/technology"),
    ("AIM",               "https://analyticsindiamag.com/feed/"),
    ("Bens Bites",        "https://www.bensbites.com/feed"),
    ("Futurism",          "https://futurism.com/categories/ai-artificial-intelligence/feed")
]

SEARCH_QUERIES = [
    # Breaking news & general updates
    "AI artificial intelligence latest news",
    "AGI artificial general intelligence latest developments",

    # Companies & major players
    "OpenAI Anthropic Google DeepMind AI announcements",
    "Microsoft Amazon AWS Meta xAI AI updates",

    # Models & releases
    "new AI model release launch GPT Claude Gemini",
    "open source AI model releases Hugging Face",

    # Research & progress
    "AI research breakthroughs transformer diffusion models",
    "AGI progress and milestones research",

    # Business, funding, acquisitions
    "AI startup funding venture capital generative AI",
    "AI mergers acquisitions billion deal",
    "AI company valuations and investments",

    # Policy & regulation
    "AI regulation government policy law",
    "AGI safety alignment policy updates",

    # Infrastructure & hardware
    "NVIDIA AMD AI chips GPU NPU news",
    "AI infrastructure cloud computing AWS Azure Google Cloud",
    "AI training inference optimization hardware",

    # Applications & domains
    "AI robotics autonomous systems drones",
    "AI healthcare medical applications news",

    # Trends & future outlook
    "future of AGI predictions expert opinions",
    "AI trends generative AI adoption",
]

BLOCKED_DOMAINS = {"reddit.com", "twitter.com", "x.com", "youtube.com", "github.com", "arxiv.org"}
BLOCKED_PATHS   = {"", "/technology", "/tech", "/ai", "/tech/ai"}
TAVILY_ENDPOINT = "https://api.tavily.com/search"
ATOM_NS         = "http://www.w3.org/2005/Atom"

def _load_dotenv():
    dotenv_path = os.path.join(os.path.expanduser("~"), ".openclaw", ".env")
    try:
        with open(dotenv_path) as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw or raw.startswith("#") or "=" not in raw:
                    continue
                key, _, val = raw.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = val
    except FileNotFoundError:
        pass


_load_dotenv()

@dataclass
class Article:
    title:  str
    url:    str
    source: str
    def clean_title(self) -> str:
        return self.title.replace("|", " -")

def is_matching_keywords(text: str) -> bool:
    return bool(_ABBREV_PATTERN.search(text) or _KEYWORD_PATTERN.search(text))

def get_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().lstrip("www.")
    except Exception:
        return ""

def parse_pubdate(date_str: str | None) -> datetime | None:
    if not date_str:
        return None
    cleaned = date_str.strip()
    try:
        return parsedate_to_datetime(cleaned).astimezone(timezone.utc)
    except Exception:
        pass
    try:
        iso = cleaned.rstrip("Z")
        if "T" in iso:
            return datetime.fromisoformat(iso).replace(tzinfo=timezone.utc)
    except Exception:
        pass
    return None


def _http_get(url: str, headers: dict) -> bytes | None:
    req = Request(url, headers=headers)
    try:
        with urlopen(req, timeout=REQUEST_TIMEOUT, context=_SSL_Context) as resp:
            return resp.read()
    except Exception as exc:
        print(f"  [fetch] {url}: {exc}", file=sys.stderr)
        return None


def _entries_rss2(root: ET.Element, cutoff: datetime, source: str) -> list[Article]:
    articles = []
    for item in root.findall(".//item"):
        title_el = item.find("title")
        link_el  = item.find("link")
        pub_el   = item.find("pubDate")
        if title_el is None or link_el is None:
            continue
        title = (title_el.text or "").strip()
        link  = (link_el.text or "").strip()
        if not title or not link:
            continue
        pub = parse_pubdate(pub_el.text if pub_el is not None else None)
        if pub and pub < cutoff:
            continue
        if is_matching_keywords(title):
            articles.append(Article(title, link, source))
    return articles


def _entries_atom(root: ET.Element, cutoff: datetime, source: str) -> list[Article]:
    articles = []
    ns = ATOM_NS
    pfx = f"{{{ns}}}"
    for entry in root.findall(f".//{pfx}entry"):
        title_el = entry.find(f"{pfx}title")
        link_el  = entry.find(f"{pfx}link")
        pub_el   = entry.find(f"{pfx}updated") or entry.find(f"{pfx}published")
        if title_el is None:
            continue
        title = (title_el.text or "").strip()
        link  = link_el.get("href", "") if link_el is not None else ""
        if not title or not link:
            continue
        pub = parse_pubdate(pub_el.text if pub_el is not None else None)
        if pub and pub < cutoff:
            continue
        if is_matching_keywords(title):
            articles.append(Article(title, link, source))
    return articles


def fetch_feed(name: str, url: str, cutoff: datetime) -> list[Article]:
    raw = _http_get(url, {"User-Agent": "OpenClaw-NewsBot/1.0"})
    if raw is None:
        return []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        print(f"  [RSS] {name}: parse error — {exc}", file=sys.stderr)
        return []
    return _entries_rss2(root, cutoff, name) + _entries_atom(root, cutoff, name)


def _tavily_search(query: str, api_key: str, per_query: int) -> list[dict]:
    body = json.dumps({
        "query":               query,
        "search_depth":        "basic",
        "max_results":         per_query,
        "include_answer":      False,
        "include_raw_content": False,
        "days":                2,
    }).encode("utf-8")

    req = Request(TAVILY_ENDPOINT, data=body, headers={
        "Content-Type":  "application/json",
        "Authorization": f"Bearer {api_key}",
        "User-Agent":    "OpenClaw-NewsBot/1.0",
    })

    try:
        with urlopen(req, timeout=REQUEST_TIMEOUT, context=_SSL_Context) as resp:
            return json.loads(resp.read().decode("utf-8")).get("results", [])
    except HTTPError as exc:
        msg = {401: "Invalid TAVILY_API_KEY", 429: "Rate limit reached"}.get(exc.code, f"HTTP {exc.code}")
        print(f"  [Tavily] {msg}", file=sys.stderr)
    except Exception as exc:
        print(f"  [Tavily] Error: {exc}", file=sys.stderr)
    return []


def _is_valid_result(url: str, seen: set[str]) -> bool:
    if not url or url in seen:
        return False
    if get_domain(url) in BLOCKED_DOMAINS:
        return False
    path = urlparse(url).path.rstrip("/")
    return path not in BLOCKED_PATHS


def fetch_tavily(api_key: str, max_queries: int = 3, per_query: int = 5) -> list[Article]:
    seen: set[str] = set()
    articles: list[Article] = []

    for query in SEARCH_QUERIES[:max_queries]:
        for hit in _tavily_search(query, api_key, per_query):
            url   = hit.get("url", "")
            title = hit.get("title", "").strip()
            if not title or not _is_valid_result(url, seen):
                continue
            seen.add(url)
            domain = get_domain(url)
            articles.append(Article(title, url, f"Tavily/{domain}" if domain else "Tavily"))

    return articles


def main():
    parser = argparse.ArgumentParser(description="Fetch AI news from RSS + Tavily")
    parser.add_argument("--max-rss",    type=int, default=5,
                        help="Max RSS articles (default: 10)")
    parser.add_argument("--max-tavily", type=int, default=5,
                        help="Max Tavily articles (default: 10)")
    parser.add_argument("--hours",      type=int, default=48,
                        help="Recency window in hours (default: 48)")
    args = parser.parse_args()

    cutoff   = datetime.now(timezone.utc) - timedelta(hours=args.hours)
    seen_urls: set[str] = set()
    collected: list[Article] = []

    print("Fetching RSS feeds...", file=sys.stderr)
    rss_count = 0
    for name, feed_url in FEEDS:
        for article in fetch_feed(name, feed_url, cutoff):
            if article.url not in seen_urls and rss_count < args.max_rss:
                seen_urls.add(article.url)
                collected.append(article)
                rss_count += 1
    print(f"  RSS total: {rss_count}", file=sys.stderr)

    tavily_key   = os.environ.get("TAVILY_API_KEY", "")
    tavily_count = 0
    if tavily_key:
        print("Fetching Tavily web search...", file=sys.stderr)
        for article in fetch_tavily(tavily_key):
            if article.url not in seen_urls and tavily_count < args.max_tavily:
                seen_urls.add(article.url)
                collected.append(article)
                tavily_count += 1
        print(f"  Tavily total: {tavily_count}", file=sys.stderr)
    else:
        print("  Tavily: skipped (TAVILY_API_KEY not set)", file=sys.stderr)

    if not collected:
        print("No articles found.")
        return

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"=== AI NEWS FEED — {now_str} ===")
    print(f"Sources: {rss_count} RSS + {tavily_count} Tavily  |  Total: {len(collected)}\n")

    for idx, article in enumerate(collected, 1):
        print(f"{idx}. {article.clean_title()}")
        print(f"   Source: {article.source}")
        print(f"   URL: {article.url}")
        print()


if __name__ == "__main__":
    main()
