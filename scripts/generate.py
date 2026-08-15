#!/usr/bin/env python3
"""
FP Civic Podcast Generator

Monitors the Forest Park Civic Association RSS feed and produces, per meeting
cycle, TWO episodes:

  EP1  Meeting Recap    — from the monthly meeting minutes (section-filtered)
  EP2  Community Reports — a consolidated digest of the NCC development report,
                          the Outreach report, and Forester security/supplemental

The meeting-minutes post is the TRIGGER for a cycle (it always posts last). When a
new minutes post appears, both episodes are generated; outreach/NCC/Forester posts
are treated as digest INGREDIENTS, not standalone episodes.

Editorial behavior (what to include/skip) lives in ../editorial-guide.md and is
injected into the prompt every run — edit that file to tune coverage, no code
change needed. Every generated episode writes its source text + final script to
../transcripts/ so misses can be reviewed and fed back into the guide.
"""

from __future__ import annotations

import argparse
import asyncio
import html
import io
import json
import os
import re
import smtplib
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formatdate, parsedate_to_datetime
from pathlib import Path

import feedparser
import pdfplumber
import requests
from bs4 import BeautifulSoup

# edge_tts, groq, and pydub are imported lazily inside the functions that need
# them, so --dry-run (source resolution + transcripts) runs without audio/LLM deps.

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

RSS_FEED_URL = "https://www.fpcivic.org/feed/"
DEV_REPORTS_URL = "https://www.fpcivic.org/development-reports/"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
EPISODES_DIR = PROJECT_ROOT / "episodes"
TRANSCRIPTS_DIR = PROJECT_ROOT / "transcripts"
VIDEOS_DIR = PROJECT_ROOT / "videos"
FEED_FILE = PROJECT_ROOT / "feed.xml"
STATE_FILE = PROJECT_ROOT / "state.json"
GUIDE_FILE = PROJECT_ROOT / "editorial-guide.md"
LOGO_PATH = PROJECT_ROOT / "assets" / "fpca-logo.png"  # optional; text-only card if absent
VIDEO_FONT = os.environ.get(
    "VIDEO_FONT", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")

SITE_BASE_URL = os.environ.get("SITE_BASE_URL", "https://OWNER.github.io/fpcivic-podcast")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
# Groq model. llama-3.3-70b-versatile was decommissioned 2026-08-16; replacement is
# GPT-OSS-120B (Groq's recommended successor). Override via the GROQ_MODEL env var to
# switch models without a code change (e.g. a Qwen model) if needed.
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")

# Prefix RSS enclosure URLs with OP3 (free, open-source podcast download analytics).
# Only affects the feed apps use; the website plays the raw file (tracked separately).
USE_OP3 = True
OP3_PREFIX = "https://op3.dev/e/"

VOICE_HOST = "en-US-AndrewMultilingualNeural"
VOICE_COHOST = "en-US-AvaMultilingualNeural"

# Per-host prosody so the two hosts feel like distinct people (free, via edge-tts
# rate/pitch). Host is a touch slower/warmer; cohost slightly brighter and quicker.
VOICE_PROSODY = {
    "host":   {"voice": VOICE_HOST,   "rate": "-4%", "pitch": "-2Hz"},
    "cohost": {"voice": VOICE_COHOST, "rate": "+3%", "pitch": "+3Hz"},
}

HTTP_HEADERS = {"User-Agent": "FPCivicPodcastBot/1.0 (+https://www.fpcivic.org)"}

# Input/output sizing. NOTE: on GPT-OSS-120B, Groq's free tier caps at 8,000
# tokens/minute (lower than the old llama model's 12k), counted as (input +
# max_tokens) against EACH request. So every single call must keep (input +
# max_tokens) safely under 8k (target ~6.5-7k for tokenizer variance); the two
# episode halves are spaced ~65s apart (SPACING_SECONDS) so each gets its own
# per-minute window. The editorial guide's rules (~1.8k tok, feedback log stripped)
# are injected into every call, plus the fixed role/format text.
MEETING_MAX_CHARS = 9000         # full monthly minutes are ~9k chars
DIGEST_PER_SOURCE_CHARS = 12000  # per-source cap before the combined DIGEST_MAX_CHARS cap
DIGEST_MAX_CHARS = 7500          # combined community-report sources fed to the digest call
RECAP_CONTEXT_CHARS = 2500       # of the recap fed into the digest call so it won't repeat items
MEETING_MAX_TOKENS = 2300        # ~1,200-word recap (~1,600 tok) with headroom
DIGEST_MAX_TOKENS = 2000         # digest half ~800-1,300 words
SPACING_SECONDS = 65

# Forester newsletters are mostly masthead/ads; keep only pages relevant to the
# security/supplemental content we actually want in the digest.
FORESTER_KEYWORDS = ["security", "patrol", "crime", "police", "safe", "911", "theft"]

# Pinned sources for regenerating past months as combined episodes. Going forward,
# resolve_digest_sources() discovers companion docs automatically for new meetings;
# these are pinned because old outreach posts age out of the RSS feed. Each config's
# `supersede` lists old standalone episodes now folded into the combined News episode
# (the combined episode itself upserts on the meeting post id, replacing the recap).
REGEN_CONFIGS = {
    "july": {
        "title": "Forest Park Civic Association July News",
        "slug": "forest-park-civic-association-july-2026-news",
        "minutes": {
            "id": "https://www.fpcivic.org/?p=5567",
            "title": "FOREST PARK CIVIC ASSOCIATION MEETING July Meeting",
            "link": "https://www.fpcivic.org/forest-park-civic-association-meeting-july-meeting/",
            "published": "Thu, 16 Jul 2026 00:02:10 +0000", "author": "Lou Bernard",
        },
        "sources": [
            ("NCC Report for June 2026 (summary)",
             "https://www.fpcivic.org/ncc-report-for-june-2026/"),
            ("NCC Development Committee Report — June 24, 2026 (zoning cases & votes)",
             "https://www.fpcivic.org/wordpress/wp-content/uploads/2026/06/NCC_Development_Report_20260624.pdf"),
            ("July 2026 Outreach Report",
             "https://www.fpcivic.org/july-2026-outreach-report/"),
            ("July 2026 Forester — security & supplemental items",
             "https://www.fpcivic.org/wordpress/wp-content/uploads/2026/07/07-JULY-Forester-2026-Hi-Res-1.pdf"),
        ],
        "supersede": ["https://www.fpcivic.org/?p=5567#digest",
                      "https://www.fpcivic.org/?p=5561"],  # old digest + July outreach
    },
    "june": {
        "title": "Forest Park Civic Association June News",
        "slug": "forest-park-civic-association-june-2026-news",
        "minutes": {
            "id": "https://www.fpcivic.org/?p=5527",
            "title": "FOREST PARK CIVIC ASSOCIATION MEETING June Meeting",
            "link": "https://www.fpcivic.org/forest-park-civic-association-meeting-june-meeting/",
            "published": "Thu, 11 Jun 2026 13:38:43 +0000", "author": "Lou Bernard",
        },
        "sources": [
            ("NCC Development Committee Report — May 27, 2026 (zoning cases & votes)",
             "https://www.fpcivic.org/wordpress/wp-content/uploads/2026/06/NCC_Development_Report_20260527_reva.pdf"),
            ("June 2026 Forester — security & supplemental items",
             "https://www.fpcivic.org/wordpress/wp-content/uploads/2026/07/06-JUNE-Forester-2026.pdf"),
        ],  # no June outreach report was published (404)
        "supersede": [],  # no June standalone outreach/NCC episodes exist
    },
    "may": {
        "title": "Forest Park Civic Association May News",
        "slug": "forest-park-civic-association-may-2026-news",
        "minutes": {
            "id": "https://www.fpcivic.org/?p=5501",
            "title": "FOREST PARK CIVIC ASSOCIATION MEETING May Minutes",
            "link": "https://www.fpcivic.org/forest-park-civic-association-meeting-may-minutes/",
            "published": "Sun, 17 May 2026 14:57:24 +0000", "author": "Lou Bernard",
        },
        "sources": [
            ("NCC Development Committee Report — April 29, 2026 (zoning cases & votes)",
             "https://www.fpcivic.org/wordpress/wp-content/uploads/2026/05/NCC_Development_Report_20260429.pdf"),
            ("May 2026 Outreach Report",
             "https://www.fpcivic.org/may-2026-outreach-report/"),
            ("May 2026 Forester — security & supplemental items",
             "https://www.fpcivic.org/wordpress/wp-content/uploads/2026/07/05-MAY-Forester-2026-HI-RES.pdf"),
        ],
        "supersede": ["https://www.fpcivic.org/?p=5488",   # May Outreach Report
                      "https://www.fpcivic.org/?p=5490"],  # May NCC Report
    },
    "april": {
        "title": "Forest Park Civic Association April News",
        "slug": "forest-park-civic-association-april-2026-news",
        "minutes": {
            "id": "https://www.fpcivic.org/?p=5463",
            "title": "FOREST PARK CIVIC ASSOCIATION MEETING April Minutes",
            "link": "https://www.fpcivic.org/forest-park-civic-association-meeting-april-minutes/",
            "published": "Sun, 19 Apr 2026 16:36:26 +0000", "author": "Lou Bernard",
        },
        "sources": [
            ("NCC Development Committee Report — March 25, 2026 (zoning cases & votes)",
             "https://www.fpcivic.org/wordpress/wp-content/uploads/2026/04/NCC_Development_Report_20260325.pdf"),
            ("April 2026 Outreach Report",
             "https://www.fpcivic.org/april-2026-outreach-report/"),
            ("2026 Mulch Sale — spring fundraiser announcement",
             "https://www.fpcivic.org/2026-mulch-sale-update/"),
            ("April 2026 Forester — security & supplemental items",
             "https://www.fpcivic.org/wordpress/wp-content/uploads/2026/07/04-APRIL-Forester-2026-hi-res.pdf"),
        ],
        "supersede": ["https://www.fpcivic.org/?p=5465",   # April Outreach Report
                      "https://www.fpcivic.org/?p=5415",   # NCC March Meeting Update (Mar 25 NCC)
                      "https://www.fpcivic.org/?p=5429"],  # 2026 Mulch Sale Update (folded in)
    },
    "march": {
        "title": "Forest Park Civic Association March News",
        "slug": "forest-park-civic-association-march-2026-news",
        "minutes": {
            "id": "https://www.fpcivic.org/?p=5402",
            "title": "FOREST PARK CIVIC ASSOCIATION MARCH MEETING",
            "link": "https://www.fpcivic.org/forest-park-civic-association-march-meeting/",
            "published": "Wed, 18 Mar 2026 19:21:27 +0000", "author": "Lou Bernard",
        },
        "sources": [
            ("NCC Development Committee Report — February 25, 2026 (zoning cases & votes)",
             "https://www.fpcivic.org/wordpress/wp-content/uploads/2026/03/NCC_Development_Report_20260225.pdf"),
            ("March 2026 Outreach Report",
             "https://www.fpcivic.org/march-2026-outreach-report/"),
            ("March 2026 Forester — security & supplemental items",
             "https://www.fpcivic.org/wordpress/wp-content/uploads/2026/07/02-MARCH-2026-Forester.pdf"),
        ],
        "supersede": ["https://www.fpcivic.org/?p=5407"],  # March Outreach Report
    },
}

MONTHS = {m.lower(): i for i, m in enumerate(
    ["", "January", "February", "March", "April", "May", "June",
     "July", "August", "September", "October", "November", "December"])}

# ---------------------------------------------------------------------------
# Prompt assembly (editorial guide is the source of truth for coverage)
# ---------------------------------------------------------------------------

ROLE_INTRO = (
    "You are a podcast script writer for the Forest Park Civic Association News "
    "Podcast. Two co-hosts (HOST and COHOST) BOTH present substantive content and "
    "take turns; neither is merely asking questions."
)

FORMAT_RULES = """\
Format rules (strict):
- Each line MUST start with exactly "HOST:" or "COHOST:" followed by the dialogue.
- No sound effects, music cues, stage directions, asterisks, parentheticals, or markdown.
- Use contractions and a warm, natural, conversational flow.
- Open with a short welcome; close with how residents can get involved or what's next.
Example:
HOST: Hey everyone, welcome back to the Forest Park Civic Association News Podcast!
COHOST: Big update on the development front, so let's jump right in.
"""


def load_guide() -> str:
    if GUIDE_FILE.exists():
        return GUIDE_FILE.read_text()
    return "(editorial guide file missing)"


def build_system_prompt(kind: str, guide: str, month_label: str = "") -> str:
    if kind == "meeting":
        role = ("You are writing a standalone MEETING RECAP from the FPCA meeting "
                "minutes. Apply the INCLUDE/SKIP rules in the editorial guide exactly.")
    elif kind == "combined_recap":
        role = (f"You are writing the FIRST half of ONE combined episode of the 'Forest "
                f"Park Civic Association News' podcast, covering {month_label}. Open in "
                f"exactly this spirit: a warm greeting, welcome to the show, and today's "
                f"update month — for example: \"Hey everybody, welcome to the Forest Park "
                f"Civic Association News podcast. Today we're giving you an update for "
                f"{month_label}.\" The hosts are UNNAMED narrators — never have them "
                f"introduce themselves, use names, or say 'I'm your host' / 'I'm here with "
                f"my co-host.' Then cover the MEETING RECAP sections per the editorial "
                f"guide's INCLUDE/SKIP and order rules. Do NOT sign off — at the very end, "
                f"hand off with a short transition like 'Now let's get into the community "
                f"reports.'")
    elif kind == "combined_digest":
        role = ("You are writing the SECOND half of the SAME combined episode, continuing "
                "the exact same conversation between the two hosts. Do NOT open with a new "
                "welcome, greeting, OR a transition line — the previous segment ALREADY "
                "handed off to the community reports, so do NOT re-announce it (no second "
                "'now let's move to the community reports' / 'now that we've covered the "
                "recap' line). Begin DIRECTLY with the first NCC development case. Follow "
                "the EP2 (Community Reports) structure in the guide. Do NOT re-announce any "
                "event or item the recap already covered (you'll be shown what it covered) "
                "— each announcement is said only once across the whole episode. End with a "
                "single wrap-up for the whole episode and how residents can get involved.")
    else:  # standalone digest (legacy)
        role = ("You are writing the COMMUNITY REPORTS digest, consolidating several "
                "community reports into one cohesive conversation. Follow the EP2 structure.")
    # Drop the human-only "## Feedback log" (dated notes) before injecting — it's not
    # a generation rule and it grows over time, wasting tokens against the rate limit.
    guide_rules = guide.split("## Feedback log", 1)[0].rstrip()
    return (
        f"{ROLE_INTRO}\n\n{role}\n\n"
        f"===== EDITORIAL GUIDE (authoritative — follow exactly) =====\n{guide_rules}\n\n"
        f"===== FORMAT RULES =====\n{FORMAT_RULES}"
    )


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


def load_state() -> dict:
    if STATE_FILE.exists():
        s = json.loads(STATE_FILE.read_text())
    else:
        s = {}
    s.setdefault("processed", [])
    s.setdefault("episodes", [])
    return s


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n")


def upsert_episode(state: dict, entry: dict) -> None:
    """Insert or replace an episode entry, matched by post_id."""
    for i, ep in enumerate(state["episodes"]):
        if ep["post_id"] == entry["post_id"]:
            state["episodes"][i] = entry
            return
    state["episodes"].append(entry)


def remove_episode(state: dict, post_id: str, reason: str = "") -> None:
    before = len(state["episodes"])
    state["episodes"] = [e for e in state["episodes"] if e["post_id"] != post_id]
    if len(state["episodes"]) < before:
        print(f"  Superseded episode {post_id} ({reason}); dropped from feed.")


# ---------------------------------------------------------------------------
# Fetching & extraction
# ---------------------------------------------------------------------------


def classify(title: str) -> str:
    t = title.lower()
    if "civic association" in t and ("meeting" in t or "minutes" in t):
        return "minutes"
    if "outreach" in t:
        return "outreach"
    if "ncc" in t:
        return "ncc"
    if "forester" in t:
        return "forester"
    return "other"


def fetch_new_posts(state: dict) -> list[dict]:
    feed = feedparser.parse(RSS_FEED_URL)
    processed = set(state.get("processed", []))
    new_posts = []
    for entry in feed.entries:
        post_id = entry.get("id") or entry.get("link")
        if post_id not in processed:
            new_posts.append({
                "id": post_id,
                "title": entry.get("title", "Untitled"),
                "link": entry.get("link", ""),
                "published": entry.get("published", ""),
                "author": entry.get("author", "Forest Park Civic Association"),
            })
    new_posts.reverse()  # oldest first
    return new_posts


def scrape_post_content(url: str) -> str:
    resp = requests.get(url, timeout=30, headers=HTTP_HEADERS)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    el = (soup.select_one("article .entry-content")
          or soup.select_one(".entry-content")
          or soup.select_one("article")
          or soup.select_one(".post-content")
          or soup.select_one("main"))
    if el:
        return el.get_text(separator="\n", strip=True)
    return "\n".join(p.get_text(strip=True) for p in soup.find_all("p") if p.get_text(strip=True))


def extract_pdf_text(url: str, keywords: list[str] | None = None) -> str:
    """Extract PDF text. If keywords are given, keep only pages that mention at
    least one of them (used to strip Forester masthead/ads down to the security
    content and stay under the token budget)."""
    resp = requests.get(url, timeout=60, headers=HTTP_HEADERS)
    resp.raise_for_status()
    parts = []
    with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
        for page in pdf.pages:
            txt = page.extract_text() or ""
            if keywords:
                low = txt.lower()
                if not any(k in low for k in keywords):
                    continue
            parts.append(txt)
    return "\n".join(parts)


def find_pdf_link(page_url: str, name_regex: str) -> str | None:
    """Find the first PDF link on a landing page whose URL matches name_regex."""
    resp = requests.get(page_url, timeout=30, headers=HTTP_HEADERS)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    pat = re.compile(name_regex, re.I)
    for a in soup.find_all("a", href=True):
        if a["href"].lower().endswith(".pdf") and pat.search(a["href"]):
            return a["href"]
    return None


def fetch_source_text(url: str, keywords: list[str] | None = None) -> str:
    """Extract readable text from a URL (PDF or HTML), by extension."""
    if url.lower().endswith(".pdf"):
        return extract_pdf_text(url, keywords)
    return scrape_post_content(url)


def source_posted_date(url: str) -> str:
    """Friendly posted date (e.g. 'Apr 19, 2026') for a fpcivic.org page, from its
    <time datetime> or article:published_time meta. Returns '' when unavailable
    (e.g. direct PDF links, which have no page date)."""
    if url.lower().endswith(".pdf"):
        return ""
    try:
        resp = requests.get(url, timeout=30, headers=HTTP_HEADERS)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        raw = None
        t = soup.find("time")
        if t and t.get("datetime"):
            raw = t["datetime"]
        else:
            meta = soup.find("meta", attrs={"property": "article:published_time"})
            if meta and meta.get("content"):
                raw = meta["content"]
        if raw:
            m = re.match(r"(\d{4})-(\d{2})-(\d{2})", raw)
            if m:
                from datetime import date as _date
                return _date(int(m.group(1)), int(m.group(2)), int(m.group(3))).strftime("%b %d, %Y")
    except Exception:
        pass
    return ""


def rfc_to_friendly(s: str) -> str:
    """Format an RFC-2822 date (from RSS) as 'Jul 16, 2026'; '' on failure."""
    try:
        return parsedate_to_datetime(s).strftime("%b %d, %Y")
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Date helpers & the recency resolver (for future automated cycles)
# ---------------------------------------------------------------------------


def anchor_date(post: dict) -> datetime:
    try:
        return parsedate_to_datetime(post["published"])
    except Exception:
        return datetime.now(timezone.utc)


def month_key(year: int, month: int) -> int:
    return year * 12 + month


def parse_month_year(text: str) -> tuple[int, int] | None:
    """Parse 'July 2026' / 'March, 2026' -> (year, month)."""
    m = re.search(r"([A-Za-z]+),?\s+(\d{4})", text)
    if m and m.group(1).lower() in MONTHS and MONTHS[m.group(1).lower()]:
        return int(m.group(2)), MONTHS[m.group(1).lower()]
    return None


def resolve_digest_sources(anchor: dict) -> list[tuple[str, str]]:
    """Auto-discover the NCC report, Outreach report, and Forester for a cycle by
    picking, for each type, the most recent one whose CONTENT date is on/before the
    anchor meeting. Filename/slug dates are parsed (not post dates) — see the
    July-7 Forester batch for why post-date recency is wrong. Missing sources are
    skipped with a log line rather than failing the whole episode."""
    a_date = anchor_date(anchor)
    a_mk = month_key(a_date.year, a_date.month)
    feed = feedparser.parse(RSS_FEED_URL)
    sources: list[tuple[str, str]] = []

    def newest_post(kind: str):
        best, best_mk = None, -1
        for e in feed.entries:
            if classify(e.get("title", "")) != kind:
                continue
            my = parse_month_year(e.get("title", ""))
            mk = month_key(*my) if my else month_key(anchor_date(
                {"published": e.get("published", "")}).year,
                anchor_date({"published": e.get("published", "")}).month)
            if mk <= a_mk and mk > best_mk:
                best, best_mk = e, mk
        return best

    # NCC development report PDF (parse YYYYMMDD from filenames on the reports page)
    try:
        resp = requests.get(DEV_REPORTS_URL, timeout=30, headers=HTTP_HEADERS)
        resp.raise_for_status()
        cands = {}  # date -> url (prefer revised)
        for m in re.finditer(
                r'href="([^"]*NCC_Development_Report_(\d{8})(_rev\w+)?\.pdf)"',
                resp.text, re.I):
            url, d, rev = m.group(1), m.group(2), m.group(3)
            dt = datetime(int(d[:4]), int(d[4:6]), int(d[6:8]), tzinfo=timezone.utc)
            if dt <= a_date:
                if d not in cands or rev:  # prefer the _rev version for a given date
                    cands[d] = url
        if cands:
            newest = max(cands)
            sources.append((f"NCC Development Committee Report ({newest})", cands[newest]))
        else:
            print("  Resolver: no NCC development report on/before anchor — skipped.")
    except Exception as e:
        print(f"  Resolver: NCC report lookup failed: {e}")

    # Outreach post (HTML)
    o = newest_post("outreach")
    if o:
        sources.append((o.get("title", "Outreach Report"), o.get("link", "")))
    else:
        print("  Resolver: no Outreach report on/before anchor — skipped.")

    # Forester -> find the PDF on its landing page
    f = newest_post("forester")
    if f:
        try:
            pdf = find_pdf_link(f.get("link", ""), r"forester")
            if pdf:
                sources.append((f.get("title", "Forester") + " — security & supplemental", pdf))
            else:
                print("  Resolver: Forester PDF link not found — skipped.")
        except Exception as e:
            print(f"  Resolver: Forester lookup failed: {e}")
    else:
        print("  Resolver: no Forester on/before anchor — skipped.")

    return sources


# ---------------------------------------------------------------------------
# Script generation & TTS
# ---------------------------------------------------------------------------


def generate_script(system_prompt: str, user_content: str, max_tokens: int) -> list[tuple[str, str]]:
    from groq import Groq
    client = Groq(api_key=GROQ_API_KEY)
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        temperature=0.7,
        max_tokens=max_tokens,
    )
    text = response.choices[0].message.content
    lines = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if line.startswith("HOST:"):
            lines.append(("host", line[5:].strip()))
        elif line.startswith("COHOST:"):
            lines.append(("cohost", line[7:].strip()))
    if not lines:
        raise ValueError("LLM returned no valid HOST:/COHOST: lines")
    return lines


SUMMARY_SYSTEM = (
    "Summarize this community-news podcast transcript as ONE line of comma-separated "
    "SPECIFIC topics and events actually discussed. Name the real content (e.g. 'dog "
    "licensing, May 16 garage sale, cars stolen while left running') — NOT section names "
    "like 'NCC update', 'outreach report', or 'new business'. Max 200 characters, no "
    "trailing period. Output only the summary line.")


def generate_summary(script_text: str) -> str:
    """A one-line, <=200-char, content-focused summary for the website. Best-effort:
    returns '' if the LLM call fails (e.g. rate limit) so it never blocks an episode."""
    try:
        from groq import Groq
        resp = Groq(api_key=GROQ_API_KEY).chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "system", "content": SUMMARY_SYSTEM},
                      {"role": "user", "content": script_text[:8000]}],
            temperature=0.3, max_tokens=120)
        return resp.choices[0].message.content.strip().strip('"')[:200]
    except Exception as e:
        print(f"  WARN: summary generation failed: {e}", file=sys.stderr)
        return ""


async def _synth(text: str, speaker: str, path: str) -> bool:
    """Synthesize one line with per-host prosody and retries. Returns True on
    success. A single line that can't be synthesized is skipped rather than
    aborting the whole episode."""
    import edge_tts
    p = VOICE_PROSODY[speaker]
    for attempt in range(3):
        try:
            await edge_tts.Communicate(
                text, p["voice"], rate=p["rate"], pitch=p["pitch"]).save(path)
            if os.path.exists(path) and os.path.getsize(path) > 0:
                return True
        except Exception as e:
            if attempt == 2:
                print(f"  WARN: TTS failed after retries: {e}", file=sys.stderr)
        await asyncio.sleep(2)
    return False


def _speakable(text: str) -> bool:
    return any(c.isalnum() for c in text)


# Also consume a lead-in preposition/verb ("...website at <url>") so removing the
# address doesn't leave a dangling "at"/"to".
_URL_RE = re.compile(r"(?:\b(?:at|on|via|visit|see|go to|to)\s+)?(?:https?://|www\.)\S+", re.I)
_EMAIL_RE = re.compile(r"(?:\b(?:at|to|via|email)\s+)?[\w.+-]+@[\w-]+\.[\w.-]+", re.I)


def normalize_for_speech(text: str) -> str:
    """Make a line TTS-friendly: drop URLs/emails (unreadable aloud) and spell
    civic service numbers like 311 as 'three-one-one'. Belt-and-suspenders with
    the editorial guide, which also tells the model not to write these."""
    text = _URL_RE.sub("", text)
    text = _EMAIL_RE.sub("", text)
    # strip NCC application/case reference codes and PIDs (unlistenable)
    text = re.sub(r"\bapplication\s*#?\s*[A-Z]{2,3}\d{2}-\d{2,}\b", "", text, flags=re.I)
    text = re.sub(r"#?\b[A-Z]{2,3}\d{2}-\d{2,}\b", "", text)
    text = re.sub(r"\bPID\s*[\d-]+", "", text, flags=re.I)
    # NOTE: "I'm your host"/self-intros are handled at the prompt level (the intro is
    # written fresh each run) — a regex here would leave broken mid-sentence fragments.
    # tidy leftovers from a removed URL/email (e.g. "...on their website at ." )
    text = re.sub(r"\b(?:at|visit|via)\s*([.,;:])", r"\1", text, flags=re.I)
    text = re.sub(r"\(\s*\)", "", text)            # empty parens
    text = re.sub(r"\s+([.,;:!?])", r"\1", text)   # space before punctuation
    text = re.sub(r"\s{2,}", " ", text).strip()
    # Numbers & wording for natural narration (documented in the editorial guide):
    text = re.sub(r"\b311\b", "three-one-one", text)
    text = re.sub(r"\b614\b", "six-one-four", text)                 # Columbus area code
    text = re.sub(r"\b(?:R[Tt]|Route|Rte)\.?\s*161\b", "Route one-sixty-one", text, flags=re.I)
    text = re.sub(r"\b161\b", "one-sixty-one", text)                # SR-161 (smooth, no pause)
    text = re.sub(r"\bBZA\s+(variances?)\b", r"zoning \1", text, flags=re.I)
    text = re.sub(r"\bC-?2\s+district\b", "commercial district", text, flags=re.I)
    text = re.sub(r"security and supplemental", "supplemental security", text, flags=re.I)
    return text


def clean_script(script: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Apply speech normalization and drop lines that end up empty/unspeakable."""
    out = []
    for speaker, text in script:
        t = normalize_for_speech(text)
        if t and _speakable(t):
            out.append((speaker, t))
    return out


def _pause_after(text: str) -> int:
    """Vary the gap between turns so the exchange has natural rhythm: snappy after
    short reactions and questions, a longer beat after a full point."""
    words = len(text.split())
    if text.rstrip().endswith("?") or words <= 7:
        return 220   # quick back-and-forth
    if words >= 45:
        return 520   # a beat to let a big point land
    return 380


async def _build_audio(script: list[tuple[str, str]], out_path: Path) -> None:
    from pydub import AudioSegment
    combined = AudioSegment.empty()
    rendered = 0
    with tempfile.TemporaryDirectory() as tmp:
        for i, (speaker, text) in enumerate(script):
            if not _speakable(text):
                continue  # skip empty/punctuation-only lines (edge-tts returns no audio)
            f = os.path.join(tmp, f"line_{i:03d}.mp3")
            print(f"  TTS [{speaker}]: {text[:60]}...")
            if await _synth(text, speaker, f):
                combined += AudioSegment.from_mp3(f) + AudioSegment.silent(
                    duration=_pause_after(text))
                rendered += 1
            else:
                print(f"  WARN: skipped line {i} (no audio)", file=sys.stderr)
    if rendered == 0:
        raise RuntimeError("no lines produced audio")
    combined.export(str(out_path), format="mp3", bitrate="128k")


def script_to_text(script: list[tuple[str, str]]) -> str:
    return "\n".join(f"{'HOST' if s == 'host' else 'COHOST'}: {t}" for s, t in script)


# ---------------------------------------------------------------------------
# Facebook video (audiogram) + caption
# ---------------------------------------------------------------------------


def _dt_escape(text: str) -> str:
    """Escape a string for use inside an ffmpeg drawtext text='...' value."""
    return (text.replace("\\", "\\\\").replace(":", "\\:")
                .replace("'", "’").replace("%", "\\%"))


def make_video(mp3_path: Path, out_path: Path, month_label: str) -> None:
    """Render a 1280x720 MP4 for Facebook: the FPCA logo (if present) or a text
    title card, the month/year, and an animated waveform driven by the audio."""
    W, H = 1280, 720
    bg, accent = "0x123f2a", "0x8BC34A"  # dark FPCA green + light green
    has_logo = LOGO_PATH.exists()
    fc = [f"color=c={bg}:s={W}x{H}:r=25[bg]"]
    inputs = ["-i", str(mp3_path)]

    if has_logo:
        inputs += ["-i", str(LOGO_PATH)]
        fc.append("[1:v]scale=760:-1[lg]")
        fc.append("[bg][lg]overlay=x=(W-w)/2:y=90[base]")
        base, subtitle_y = "base", 360   # logo already shows the org name
        text_lines = [("News Podcast", 52, "white", subtitle_y),
                      (month_label, 44, accent, subtitle_y + 78)]
    else:
        base, title_y = "bg", 200
        text_lines = [("Forest Park Civic Association", 54, "white", title_y),
                      ("News Podcast", 54, "white", title_y + 68),
                      (month_label, 44, accent, title_y + 150)]

    fc.append(f"[0:a]showwaves=s=1120x180:mode=cline:rate=25:colors={accent}[wv]")
    fc.append(f"[{base}][wv]overlay=x=(W-w)/2:y=500:shortest=1[bw]")
    draw = ",".join(
        f"drawtext=fontfile={VIDEO_FONT}:text='{_dt_escape(t)}':fontcolor={c}"
        f":fontsize={sz}:x=(w-text_w)/2:y={y}"
        for (t, sz, c, y) in text_lines)
    fc.append(f"[bw]{draw}[v]")

    cmd = (["ffmpeg", "-y"] + inputs +
           ["-filter_complex", ";".join(fc), "-map", "[v]", "-map", "0:a",
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-r", "25",
            "-c:a", "aac", "-b:a", "192k", "-shortest", str(out_path)])
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError("ffmpeg: " + e.stderr.decode("utf-8", "ignore")[-600:])


def facebook_caption(month_label: str, summary: str, site_url: str) -> str:
    cap = f"\U0001F399️ The {month_label} Forest Park Civic Association News podcast is out!"
    s = (summary or "").strip().rstrip(".")
    if s:
        cap += f"\n\nThis month: {s}."
    cap += f"\n\n\U0001F3A7 Listen to every episode: {site_url}"
    cap += "\n\n#ForestPark #Columbus"
    return cap


# ---------------------------------------------------------------------------
# Transcripts
# ---------------------------------------------------------------------------


def save_transcript(slug: str, title: str, kind: str,
                    sources: list[tuple[str, str, str]], script_text: str | None) -> None:
    """sources = list of (label, url, extracted_text)."""
    TRANSCRIPTS_DIR.mkdir(exist_ok=True)
    lines = [f"# {title}", "",
             f"- Episode type: {kind}",
             f"- Generated: {datetime.now(timezone.utc).isoformat()}",
             "- Sources:"]
    for label, url, _ in sources:
        lines.append(f"  - {label} — {url}")
    lines += ["", "---", "", "## Generated script", ""]
    lines.append(script_text if script_text else "_(dry-run: no script generated)_")
    lines += ["", "---", "", "## Source input (fed to the model)", ""]
    for label, url, text in sources:
        lines += [f"### {label}", f"<{url}>", "", "```", text, "```", ""]
    (TRANSCRIPTS_DIR / f"{slug}.md").write_text("\n".join(lines))
    print(f"  Transcript: transcripts/{slug}.md")


def parse_script_from_transcript(slug: str) -> list[tuple[str, str]]:
    """Recover (speaker, text) lines from a saved transcript's '## Generated script'
    section — used to re-render audio from an existing script without an LLM call."""
    path = TRANSCRIPTS_DIR / f"{slug}.md"
    if not path.exists() or "## Generated script" not in path.read_text():
        return []
    block = path.read_text().split("## Generated script", 1)[1].split("## Source input", 1)[0]
    lines = []
    for line in block.splitlines():
        line = line.strip()
        if line.startswith("HOST:"):
            lines.append(("host", line[5:].strip()))
        elif line.startswith("COHOST:"):
            lines.append(("cohost", line[7:].strip()))
    return lines


def send_notification_email(title: str, sources: list[tuple[str, str, str]],
                            transcript_text: str, video_url: str | None = None,
                            fb_caption: str | None = None) -> None:
    """Email Ryan when an episode is generated: a link to the site, a bulleted list
    of source links, the full transcript (for admin awareness + QA), and — when
    provided — the Facebook video download link + a ready-to-paste caption. Requires
    SMTP_USER / SMTP_PASS env (GitHub secrets); skips gracefully if unset."""
    to_addr = os.environ.get("NOTIFY_EMAIL_TO", "ryan.finke@gmail.com")
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    from_addr = os.environ.get("NOTIFY_EMAIL_FROM", smtp_user)
    if not (smtp_user and smtp_pass):
        print(">>> EMAIL NOTIFICATION: skipped (SMTP_USER/SMTP_PASS not configured)")
        return

    site = SITE_BASE_URL.rstrip("/") + "/index.html"

    def _txt(label, url, date):
        return f"- {label}: {url}" + (f" (posted {date})" if date else "")

    def _html(label, url, date):
        suffix = f" (posted {html.escape(date)})" if date else ""
        return f'<li><a href="{html.escape(url)}">{html.escape(label)}</a>{suffix}</li>'

    src_txt = "\n".join(_txt(*s) for s in sources) or "- (none)"
    src_html = "\n".join(_html(*s) for s in sources) or "<li>(none)</li>"

    fb_txt = ""
    fb_html = ""
    if video_url or fb_caption:
        fb_txt = "\n=== Post to Facebook ===\n"
        if video_url:
            fb_txt += f"Download the video: {video_url}\n"
        if fb_caption:
            fb_txt += f"\nCaption (copy-paste):\n{fb_caption}\n"
        fb_txt += "\n"
        fb_html = "<hr><p><strong>Post to Facebook</strong></p>"
        if video_url:
            fb_html += (f'<p><a href="{html.escape(video_url)}">Download the video (.mp4)</a></p>')
        if fb_caption:
            fb_html += ('<p>Caption (copy-paste):</p>'
                        f'<pre style="white-space:pre-wrap;font-family:inherit;'
                        f'background:#f5f5f5;padding:10px;border-radius:6px">'
                        f'{html.escape(fb_caption)}</pre>')

    text_body = (f"A new episode was generated: {title}\n\n"
                 f"Listen / all episodes:\n{site}\n\n"
                 f"Sources used to produce it:\n{src_txt}\n"
                 f"{fb_txt}"
                 f"\n--- Full transcript ---\n\n{transcript_text}\n")
    html_body = (f"<html><body>"
                 f"<p>A new episode was generated: <strong>{html.escape(title)}</strong></p>"
                 f'<p><a href="{html.escape(site)}">Listen / all episodes</a></p>'
                 f"<p><strong>Sources used to produce it:</strong></p><ul>{src_html}</ul>"
                 f"{fb_html}"
                 f"<hr><p><strong>Full transcript</strong></p>"
                 f'<pre style="white-space:pre-wrap;font-family:inherit">'
                 f"{html.escape(transcript_text)}</pre></body></html>")

    msg = EmailMessage()
    msg["Subject"] = f"New FPCA podcast episode: {title}"
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")
    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as s:
            s.starttls()
            s.login(smtp_user, smtp_pass)
            s.send_message(msg)
        print(f">>> EMAIL NOTIFICATION: sent to {to_addr}")
    except Exception as e:
        print(f">>> EMAIL NOTIFICATION: FAILED — {e}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Slug / date helpers
# ---------------------------------------------------------------------------


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text[:80].strip("-")


def cycle_label(post: dict) -> str:
    d = anchor_date(post)
    return d.strftime("%B %Y")


def month_name(post: dict) -> str:
    return anchor_date(post).strftime("%B")


def rfc2822_now() -> str:
    return formatdate(timeval=None, localtime=False, usegmt=True)


def post_pub_date(post: dict) -> str:
    if post.get("published"):
        try:
            return formatdate(parsedate_to_datetime(post["published"]).timestamp(),
                              localtime=False, usegmt=True)
        except Exception:
            pass
    return rfc2822_now()


# ---------------------------------------------------------------------------
# Episode builders
# ---------------------------------------------------------------------------


def make_meeting_episode(post: dict, state: dict, guide: str, dry_run: bool,
                         slug: str | None = None, title: str | None = None) -> None:
    title = title or f"{cycle_label(post)} Meeting Recap"
    slug = slug or slugify(title)
    print(f"\n[EP1] Meeting Recap: {title}")
    try:
        content = scrape_post_content(post["link"])
    except Exception as e:
        print(f"  ERROR scraping minutes: {e}", file=sys.stderr)
        return
    if len(content) < 50:
        print("  SKIP: minutes content too short", file=sys.stderr)
        return
    print(f"  Scraped {len(content)} chars of minutes")
    sources = [("Meeting minutes", post["link"], content)]

    if dry_run:
        save_transcript(slug, title, "EP1 Meeting Recap", sources, None)
        return

    system = build_system_prompt("meeting", guide)
    user = f"Meeting minutes title: {post['title']}\n\nMinutes content:\n{content[:MEETING_MAX_CHARS]}"
    try:
        script = clean_script(generate_script(system, user, MEETING_MAX_TOKENS))
    except Exception as e:
        print(f"  ERROR generating script: {e}", file=sys.stderr)
        return
    dest = EPISODES_DIR / f"{slug}.mp3"
    try:
        asyncio.run(_build_audio(script, dest))
    except Exception as e:
        print(f"  ERROR building audio: {e}", file=sys.stderr)
        if dest.exists():
            dest.unlink()
        return
    save_transcript(slug, title, "EP1 Meeting Recap", sources, script_to_text(script))
    upsert_episode(state, {
        "post_id": post["id"], "title": title, "source_link": post["link"],
        "filename": dest.name, "pub_date": post_pub_date(post),
        "author": post.get("author", "Forest Park Civic Association"),
        "file_size": dest.stat().st_size,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    })
    print(f"  Saved: {dest.name} ({dest.stat().st_size/1024:.0f} KB)")
    send_notification_email(
        title, [(l, u, rfc_to_friendly(post.get("published", ""))) for l, u, _ in sources],
        script_to_text(script))


def fetch_digest_sources(source_urls: list[tuple[str, str]]) -> list[tuple[str, str, str]]:
    """Fetch each (label, url) community-report source. Forester sources are
    keyword-filtered to their security content. Returns (label, url, text[:cap]);
    sources that fail or are empty are skipped with a log line, not fatal."""
    resolved = []
    for label, url in source_urls:
        try:
            kw = FORESTER_KEYWORDS if "forester" in label.lower() else None
            text = fetch_source_text(url, kw)
            if text and len(text) >= 50:
                resolved.append((label, url, text[:DIGEST_PER_SOURCE_CHARS]))
                print(f"  + {label}: {len(text)} chars")
            else:
                print(f"  - {label}: too short/empty — skipped ({url})")
        except Exception as e:
            print(f"  - {label}: fetch failed — skipped ({e})")
    return resolved


def make_combined_episode(minutes_post: dict, source_urls: list[tuple[str, str]],
                          state: dict, guide: str, dry_run: bool,
                          title: str, slug: str, post_id: str) -> bool:
    """One episode = meeting recap (part 1) + community reports (part 2), stitched
    into a single MP3. Two LLM calls (spaced for the rate limit): the first opens
    the show and hands off; the second continues straight into the reports and
    wraps up. Keeps each half's proven depth while reading as one conversation.
    Returns True only if the episode was fully created (callers gate cleanup on it)."""
    print(f"\n[NEWS] {title}")
    try:
        minutes = scrape_post_content(minutes_post["link"])
    except Exception as e:
        print(f"  ERROR scraping minutes: {e}", file=sys.stderr)
        return False
    if len(minutes) < 50:
        print("  SKIP: minutes content too short", file=sys.stderr)
        return False
    print(f"  Scraped {len(minutes)} chars of minutes")
    digest = fetch_digest_sources(source_urls)
    all_sources = [("Meeting minutes", minutes_post["link"], minutes)] + digest

    if dry_run:
        save_transcript(slug, title, "Combined News", all_sources, None)
        return True

    recap_sys = build_system_prompt("combined_recap", guide, month_label=cycle_label(minutes_post))
    recap_user = (f"Meeting minutes title: {minutes_post['title']}\n\n"
                  f"Minutes content:\n{minutes[:MEETING_MAX_CHARS]}")
    combined_src = ""
    for label, _, text in digest:
        combined_src += f"===== SOURCE: {label} =====\n{text}\n\n"
    combined_src = combined_src[:DIGEST_MAX_CHARS]
    digest_sys = build_system_prompt("combined_digest", guide)
    try:
        part1 = clean_script(generate_script(recap_sys, recap_user, MEETING_MAX_TOKENS))
        part2 = []
        if digest:
            # Feed the recap into the digest call so it doesn't re-announce items that
            # already appeared in the meeting recap (e.g. the Beautification Contest,
            # garage sales, events that show up in both the minutes and a report).
            recap_text = script_to_text(part1)[:RECAP_CONTEXT_CHARS]
            digest_user = (
                "Continue the same episode with the community reports. Lead with the "
                "NCC development report — go through each case ONE AT A TIME, referring "
                "to them as 'case one', 'case two', etc. (never read the reference codes) "
                "— then Outreach, then any community announcements in the sources (e.g. "
                "fundraisers/sales), then Forester supplemental security. Ignore the "
                "Forester masthead/ads/directory.\n\n"
                "CRITICAL: the meeting-recap half (shown below) ALREADY announced some "
                "items. Do NOT announce any of them a second time — say each event/"
                "announcement only ONCE across the whole episode. Only mention a "
                "recap item again if a report adds genuinely new, substantive detail.\n\n"
                "===== ALREADY COVERED IN THE RECAP (do not repeat) =====\n" + recap_text +
                "\n\n===== COMMUNITY REPORT SOURCES =====\n" + combined_src)
            print(f"  (waiting {SPACING_SECONDS}s for the token-rate window)")
            time.sleep(SPACING_SECONDS)
            part2 = clean_script(generate_script(digest_sys, digest_user, DIGEST_MAX_TOKENS))
    except Exception as e:
        print(f"  ERROR generating script: {e}", file=sys.stderr)
        return False
    script = part1 + part2
    if not script:
        print("  ERROR: empty script", file=sys.stderr)
        return False
    dest = EPISODES_DIR / f"{slug}.mp3"
    try:
        asyncio.run(_build_audio(script, dest))
    except Exception as e:
        print(f"  ERROR building audio: {e}", file=sys.stderr)
        if dest.exists():
            dest.unlink()
        return False
    script_text = script_to_text(script)
    save_transcript(slug, title, "Combined News", all_sources, script_text)
    summary = generate_summary(script_text)
    month_label = cycle_label(minutes_post)
    upsert_episode(state, {
        "post_id": post_id, "title": title, "source_link": minutes_post["link"],
        "web_title": f"{month_label} FPCA News",
        "summary": summary,
        "filename": dest.name, "pub_date": post_pub_date(minutes_post),
        "author": minutes_post.get("author", "Forest Park Civic Association"),
        "file_size": dest.stat().st_size,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "digest_sources": [{"label": l, "url": u} for l, u, _ in digest],
    })
    print(f"  Saved: {dest.name} ({dest.stat().st_size/1024:.0f} KB, {len(script)} lines)")

    # Facebook video (audiogram) + ready-to-post caption
    video_url = None
    try:
        VIDEOS_DIR.mkdir(exist_ok=True)
        video_dest = VIDEOS_DIR / f"{slug}.mp4"
        make_video(dest, video_dest, month_label)
        video_url = f"{SITE_BASE_URL}/videos/{video_dest.name}"
        print(f"  Video: {video_dest.name} ({video_dest.stat().st_size/1024/1024:.1f} MB)")
    except Exception as e:
        print(f"  WARN: video generation failed: {e}", file=sys.stderr)
    fb_caption = facebook_caption(month_label, summary, SITE_BASE_URL.rstrip("/") + "/index.html")

    email_sources = [("Meeting minutes", minutes_post["link"],
                      rfc_to_friendly(minutes_post.get("published", "")))]
    email_sources += [(l, u, source_posted_date(u)) for l, u, _ in digest]
    send_notification_email(title, email_sources, script_text,
                            video_url=video_url, fb_caption=fb_caption)
    return True


def make_standalone_episode(post: dict, state: dict, guide: str, dry_run: bool) -> None:
    """Preserve old per-post behavior for unclassified ('other') posts."""
    print(f"\n[STANDALONE] {post['title']}")
    make_meeting_episode(post, state, guide, dry_run,
                         slug=slugify(post["title"]), title=post["title"])


# ---------------------------------------------------------------------------
# Feed
# ---------------------------------------------------------------------------


def build_feed(state: dict) -> None:
    episodes = state.get("episodes", [])
    rss = ET.Element("rss", version="2.0")
    rss.set("xmlns:itunes", "http://www.itunes.com/dtds/podcast-1.0.dtd")
    rss.set("xmlns:atom", "http://www.w3.org/2005/Atom")
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "Forest Park Civic Association News Podcast"
    ET.SubElement(channel, "link").text = "https://www.fpcivic.org"
    ET.SubElement(channel, "description").text = (
        "Automated conversational podcast of Forest Park Civic Association meeting "
        "recaps and community reports. Powered by AI.")
    ET.SubElement(channel, "language").text = "en-us"
    ET.SubElement(channel, "lastBuildDate").text = rfc2822_now()
    ET.SubElement(channel, "generator").text = "fpcivic-podcast (Groq + Edge TTS)"
    ET.SubElement(channel, "{http://www.itunes.com/dtds/podcast-1.0.dtd}author").text = (
        "Forest Park Civic Association")
    ET.SubElement(channel, "{http://www.itunes.com/dtds/podcast-1.0.dtd}summary").text = (
        "AI-generated conversational recaps of Forest Park Civic Association meetings.")
    cat = ET.SubElement(channel, "{http://www.itunes.com/dtds/podcast-1.0.dtd}category")
    cat.set("text", "Government")
    ET.SubElement(channel, "{http://www.itunes.com/dtds/podcast-1.0.dtd}explicit").text = "no"
    atom = ET.SubElement(channel, "{http://www.w3.org/2005/Atom}link")
    atom.set("href", f"{SITE_BASE_URL}/feed.xml")
    atom.set("rel", "self")
    atom.set("type", "application/rss+xml")

    for ep in reversed(episodes):
        disp_title = ep.get("web_title") or ep["title"]
        summary = ep.get("summary") or f"AI-generated conversational recap of: {disp_title}"
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = disp_title
        ET.SubElement(item, "link").text = ep["source_link"]
        ET.SubElement(item, "description").text = summary
        ET.SubElement(item, "pubDate").text = ep["pub_date"]
        ET.SubElement(item, "guid", isPermaLink="false").text = ep["post_id"]
        enc = ET.SubElement(item, "enclosure")
        mp3_url = f"{SITE_BASE_URL}/episodes/{ep['filename']}"
        enc.set("url", (OP3_PREFIX + mp3_url) if USE_OP3 else mp3_url)
        enc.set("length", str(ep.get("file_size", 0)))
        enc.set("type", "audio/mpeg")
        ET.SubElement(item, "{http://www.itunes.com/dtds/podcast-1.0.dtd}author").text = (
            ep.get("author", "Forest Park Civic Association"))
        ET.SubElement(item, "{http://www.itunes.com/dtds/podcast-1.0.dtd}summary").text = summary

    tree = ET.ElementTree(rss)
    ET.indent(tree, space="  ")
    tree.write(str(FEED_FILE), encoding="unicode", xml_declaration=True)
    with open(FEED_FILE, "a") as f:
        f.write("\n")
    print(f"Feed updated: {len(episodes)} total episodes")


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


def regenerate_months(keys: list[str], state: dict, guide: str, dry_run: bool) -> None:
    for i, key in enumerate(keys):
        cfg = REGEN_CONFIGS.get(key)
        if not cfg:
            print(f"Unknown month '{key}' — choices: {', '.join(REGEN_CONFIGS)}", file=sys.stderr)
            continue
        print(f"\n=== Regenerating {cfg['title']} (pinned sources) ===")
        if i > 0 and not dry_run:
            print(f"  (waiting {SPACING_SECONDS}s between months for the token-rate window)")
            time.sleep(SPACING_SECONDS)
        ok = make_combined_episode(
            cfg["minutes"], cfg["sources"], state, guide, dry_run,
            title=cfg["title"], slug=cfg["slug"], post_id=cfg["minutes"]["id"])
        # Only fold in / drop old artifacts if the combined episode actually built,
        # so a failed run can't leave a month with nothing.
        if ok and not dry_run:
            for pid in cfg["supersede"]:
                remove_episode(state, pid, reason="merged into combined News episode")


def reaudio_months(keys: list[str], state: dict, dry_run: bool) -> None:
    """Re-render an episode's AUDIO from its existing transcript script — applies the
    current speech normalizations (pronunciation/wording), no LLM call, no email. The
    transcript/script CONTENT is unchanged, so script-level issues (e.g. a redundant
    transition or a repeated street name) are NOT fixed here — only a full regen does."""
    for key in keys:
        cfg = REGEN_CONFIGS.get(key)
        if not cfg:
            print(f"Unknown month '{key}' — choices: {', '.join(REGEN_CONFIGS)}", file=sys.stderr)
            continue
        slug = cfg["slug"]
        script = clean_script(parse_script_from_transcript(slug))
        if not script:
            print(f"  No transcript script found for {slug} — skipping.", file=sys.stderr)
            continue
        print(f"\n[REAUDIO] {cfg['title']} — {len(script)} lines from existing transcript "
              f"(applying current speech normalizations; no LLM)")
        if dry_run:
            continue
        dest = EPISODES_DIR / f"{slug}.mp3"
        try:
            asyncio.run(_build_audio(script, dest))
        except Exception as e:
            print(f"  ERROR building audio: {e}", file=sys.stderr)
            continue
        for ep in state["episodes"]:
            if ep["post_id"] == cfg["minutes"]["id"] or ep.get("filename") == f"{slug}.mp3":
                ep["file_size"] = dest.stat().st_size
                ep["generated_at"] = datetime.now(timezone.utc).isoformat()
                break
        print(f"  Re-rendered: {dest.name} ({dest.stat().st_size/1024:.0f} KB)")


def make_videos_for(keys: list[str], state: dict) -> None:
    """Backfill: render the Facebook MP4 (title card + waveform) from each month's
    EXISTING audio — no audio change, no LLM. Logs a ready-to-post caption too."""
    VIDEOS_DIR.mkdir(exist_ok=True)
    by_slug = {e.get("filename", "").rsplit(".", 1)[0]: e for e in state.get("episodes", [])}
    site = SITE_BASE_URL.rstrip("/") + "/index.html"
    for key in keys:
        cfg = REGEN_CONFIGS.get(key)
        if not cfg:
            print(f"Unknown month '{key}' — choices: {', '.join(REGEN_CONFIGS)}", file=sys.stderr)
            continue
        slug = cfg["slug"]
        mp3 = EPISODES_DIR / f"{slug}.mp3"
        if not mp3.exists():
            print(f"  No audio for {slug} — skipping.", file=sys.stderr)
            continue
        month_label = cycle_label(cfg["minutes"])
        out = VIDEOS_DIR / f"{slug}.mp4"
        print(f"\n[VIDEO] {cfg['title']} -> {out.name}")
        try:
            make_video(mp3, out, month_label)
            print(f"  Saved: {out.name} ({out.stat().st_size/1024/1024:.1f} MB)")
        except Exception as e:
            print(f"  ERROR: video generation failed: {e}", file=sys.stderr)
            continue
        cap = facebook_caption(month_label, by_slug.get(slug, {}).get("summary", ""), site)
        print("  --- Facebook caption ---")
        for line in cap.splitlines():
            print("   | " + line)


def send_email_for(keys: list[str], state: dict) -> None:
    """Re-send the notification email for existing episode(s) — the site link, source
    list (with posted dates), the Facebook video link + caption, and the transcript.
    No LLM/TTS; useful to preview the video/post content."""
    by_slug = {e.get("filename", "").rsplit(".", 1)[0]: e for e in state.get("episodes", [])}
    site = SITE_BASE_URL.rstrip("/") + "/index.html"
    for key in keys:
        cfg = REGEN_CONFIGS.get(key)
        if not cfg:
            print(f"Unknown month '{key}' — choices: {', '.join(REGEN_CONFIGS)}", file=sys.stderr)
            continue
        slug = cfg["slug"]
        ep = by_slug.get(slug)
        if not ep:
            print(f"  No episode in state for {slug} — skipping.", file=sys.stderr)
            continue
        month_label = cycle_label(cfg["minutes"])
        email_sources = [("Meeting minutes", cfg["minutes"]["link"],
                          rfc_to_friendly(cfg["minutes"].get("published", "")))]
        for ds in ep.get("digest_sources", []):
            email_sources.append((ds["label"], ds["url"], source_posted_date(ds["url"])))
        script_text = script_to_text(parse_script_from_transcript(slug))
        video_url = (f"{SITE_BASE_URL}/videos/{slug}.mp4"
                     if (VIDEOS_DIR / f"{slug}.mp4").exists() else None)
        fb_caption = facebook_caption(month_label, ep.get("summary", ""), site)
        print(f"\n[EMAIL] Re-sending notification for {ep.get('title', slug)}")
        send_notification_email(ep.get("title", cfg["title"]), email_sources, script_text,
                                video_url=video_url, fb_caption=fb_caption)


def run_cron(state: dict, guide: str, dry_run: bool) -> None:
    new_posts = fetch_new_posts(state)
    if not new_posts:
        print("No new posts found.")
        return
    print(f"Found {len(new_posts)} new post(s)")
    for i, post in enumerate(new_posts):
        if i > 0:
            time.sleep(5)
        kind = classify(post["title"])
        print(f"\n> {post['title']}  [{kind}]")
        if kind == "minutes":
            sources = resolve_digest_sources(post)
            make_combined_episode(
                post, sources, state, guide, dry_run,
                title=f"Forest Park Civic Association {month_name(post)} News",
                slug=slugify(f"forest-park-civic-association-{cycle_label(post)}-news"),
                post_id=post["id"])
        elif kind in ("outreach", "ncc", "forester"):
            print(f"  Ingredient ({kind}) — folded into the combined episode, no standalone.")
        else:
            make_standalone_episode(post, state, guide, dry_run)
        if not dry_run:
            state["processed"].append(post["id"])
            save_state(state)


def main() -> None:
    ap = argparse.ArgumentParser(description="FP Civic Podcast generator")
    ap.add_argument("--regenerate-months", default="",
                    help="Comma-separated months to regenerate as combined episodes from "
                         "pinned sources (e.g. 'may,june,july')")
    ap.add_argument("--reaudio", default="",
                    help="Comma-separated months to re-render AUDIO ONLY from the existing "
                         "transcript (applies current speech normalizations; no LLM, no email)")
    ap.add_argument("--make-videos", default="",
                    help="Comma-separated months to (re)build the Facebook MP4 from existing "
                         "audio (no LLM); e.g. 'march,april,may,june,july'")
    ap.add_argument("--send-email", default="",
                    help="Comma-separated months to re-send the notification email (video link "
                         "+ caption + sources + transcript) for existing episodes")
    ap.add_argument("--dry-run", action="store_true",
                    help="Resolve/scrape/extract sources and write transcripts, but "
                         "skip all LLM and TTS calls (no API key needed)")
    args = ap.parse_args()

    if (not args.dry_run and not args.reaudio and not args.make_videos
            and not args.send_email and not GROQ_API_KEY):
        print("ERROR: GROQ_API_KEY is required (or use --dry-run)", file=sys.stderr)
        sys.exit(1)

    EPISODES_DIR.mkdir(exist_ok=True)
    TRANSCRIPTS_DIR.mkdir(exist_ok=True)  # so the workflow's `git add transcripts/` never errors
    guide = load_guide()
    state = load_state()

    if args.send_email:
        send_email_for([m.strip().lower() for m in args.send_email.split(",") if m.strip()],
                       state)
    elif args.make_videos:
        make_videos_for([m.strip().lower() for m in args.make_videos.split(",") if m.strip()],
                        state)
    elif args.reaudio:
        reaudio_months([m.strip().lower() for m in args.reaudio.split(",") if m.strip()],
                       state, args.dry_run)
    elif args.regenerate_months:
        keys = [m.strip().lower() for m in args.regenerate_months.split(",") if m.strip()]
        regenerate_months(keys, state, guide, args.dry_run)
    else:
        run_cron(state, guide, args.dry_run)

    if not args.dry_run:
        save_state(state)
        build_feed(state)
    print("Done!")


if __name__ == "__main__":
    main()
