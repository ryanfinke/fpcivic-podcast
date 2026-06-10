#!/usr/bin/env python3
"""
FP Civic Podcast Generator

Monitors the Forest Park Civic Association RSS feed for new posts,
generates conversational podcast episodes using Gemini + Edge TTS,
and updates the podcast RSS feed for distribution.
"""

import asyncio
import json
import os
import re
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import formatdate, parsedate_to_datetime
from pathlib import Path

import edge_tts
import feedparser
import requests
from bs4 import BeautifulSoup
from groq import Groq
from pydub import AudioSegment

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

RSS_FEED_URL = "https://www.fpcivic.org/feed/"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
EPISODES_DIR = PROJECT_ROOT / "episodes"
FEED_FILE = PROJECT_ROOT / "feed.xml"
STATE_FILE = PROJECT_ROOT / "state.json"

SITE_BASE_URL = os.environ.get(
    "SITE_BASE_URL", "https://OWNER.github.io/fpcivic-podcast"
)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

# Edge TTS voices
VOICE_HOST = "en-US-AndrewMultilingualNeural"
VOICE_GUEST = "en-US-AvaMultilingualNeural"

SYSTEM_PROMPT = """\
You are a podcast script writer. Given the text content of a civic association \
blog post, write a natural two-person conversational podcast script about it.

The hosts are:
- HOST: A friendly, knowledgeable narrator who summarizes the key points
- GUEST: A curious neighbor who asks follow-up questions and reacts naturally

Guidelines:
- Keep it casual, warm, and informative — like two neighbors chatting
- Cover the main topics, key decisions, and what it means for residents
- About 400-600 words total
- Do NOT use sound effects, music cues, or stage directions
- Do NOT use asterisks, parenthetical actions, or markdown formatting
- Each line must start with exactly "HOST:" or "GUEST:" followed by their dialogue
- Make it sound natural — use contractions, filler words occasionally, reactions
- End with a brief wrap-up

Example format:
HOST: Hey everyone, welcome back to the Forest Park Civic Association News Podcast!
GUEST: So what happened at the latest meeting?
HOST: Well, there were a few big items on the agenda...
"""


# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"processed": []}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n")


# ---------------------------------------------------------------------------
# RSS feed parsing
# ---------------------------------------------------------------------------


def fetch_new_posts(state: dict) -> list[dict]:
    """Return list of posts not yet processed, oldest first."""
    feed = feedparser.parse(RSS_FEED_URL)
    processed_ids = set(state.get("processed", []))
    new_posts = []

    for entry in feed.entries:
        post_id = entry.get("id") or entry.get("link")
        if post_id not in processed_ids:
            new_posts.append(
                {
                    "id": post_id,
                    "title": entry.get("title", "Untitled"),
                    "link": entry.get("link", ""),
                    "published": entry.get("published", ""),
                    "author": entry.get("author", "Forest Park Civic Association"),
                    "summary": entry.get("summary", ""),
                }
            )

    new_posts.reverse()
    return new_posts


# ---------------------------------------------------------------------------
# Web scraping
# ---------------------------------------------------------------------------


def scrape_post_content(url: str) -> str:
    """Fetch and extract the main text content from a blog post URL."""
    resp = requests.get(url, timeout=30, headers={"User-Agent": "FPCivicPodcastBot/1.0"})
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # Try common WordPress content selectors
    content_el = (
        soup.select_one("article .entry-content")
        or soup.select_one(".entry-content")
        or soup.select_one("article")
        or soup.select_one(".post-content")
        or soup.select_one("main")
    )

    if content_el:
        return content_el.get_text(separator="\n", strip=True)

    # Fallback: get all paragraph text
    paragraphs = soup.find_all("p")
    return "\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))


# ---------------------------------------------------------------------------
# Script generation with Groq (Llama)
# ---------------------------------------------------------------------------


def generate_script(title: str, content: str) -> list[tuple[str, str]]:
    """Use Groq to generate a conversational podcast script.
    Returns list of (speaker, text) tuples."""
    client = Groq(api_key=GROQ_API_KEY)

    prompt = f"Blog post title: {title}\n\nBlog post content:\n{content[:8000]}"

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
        max_tokens=2048,
    )

    script_text = response.choices[0].message.content
    lines = []

    for line in script_text.strip().split("\n"):
        line = line.strip()
        if line.startswith("HOST:"):
            lines.append(("host", line[5:].strip()))
        elif line.startswith("GUEST:"):
            lines.append(("guest", line[6:].strip()))

    if not lines:
        raise ValueError("LLM returned no valid HOST:/GUEST: lines")

    return lines


# ---------------------------------------------------------------------------
# TTS with edge-tts
# ---------------------------------------------------------------------------


async def synthesize_line(text: str, voice: str, output_path: str) -> None:
    """Generate speech for a single line using edge-tts."""
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)


async def generate_audio(script: list[tuple[str, str]], output_path: Path) -> None:
    """Convert a script to a single MP3 file with alternating voices."""
    combined = AudioSegment.empty()
    pause = AudioSegment.silent(duration=400)  # 400ms pause between lines

    with tempfile.TemporaryDirectory() as tmpdir:
        for i, (speaker, text) in enumerate(script):
            voice = VOICE_HOST if speaker == "host" else VOICE_GUEST
            tmp_file = os.path.join(tmpdir, f"line_{i:03d}.mp3")

            print(f"  TTS [{speaker}]: {text[:60]}...")
            await synthesize_line(text, voice, tmp_file)

            segment = AudioSegment.from_mp3(tmp_file)
            combined += segment + pause

        combined.export(str(output_path), format="mp3", bitrate="128k")


# ---------------------------------------------------------------------------
# Podcast generation
# ---------------------------------------------------------------------------


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text[:80].strip("-")


def generate_episode(post: dict) -> Path | None:
    """Generate a podcast episode for a single post. Returns the mp3 path."""
    print(f"\nGenerating podcast for: {post['title']}")
    print(f"  URL: {post['link']}")

    # Step 1: Scrape the post content
    try:
        content = scrape_post_content(post["link"])
        if not content or len(content) < 50:
            print("  SKIP: Post content too short", file=sys.stderr)
            return None
        print(f"  Scraped {len(content)} characters")
    except Exception as e:
        print(f"  ERROR scraping: {e}", file=sys.stderr)
        return None

    # Step 2: Generate conversational script with Gemini
    try:
        script = generate_script(post["title"], content)
        print(f"  Generated script: {len(script)} lines")
    except Exception as e:
        print(f"  ERROR generating script: {e}", file=sys.stderr)
        return None

    # Step 3: Convert script to audio with edge-tts
    slug = slugify(post["title"])
    dest = EPISODES_DIR / f"{slug}.mp3"

    try:
        asyncio.run(generate_audio(script, dest))
        print(f"  Saved: {dest.name} ({dest.stat().st_size / 1024:.0f} KB)")
    except Exception as e:
        print(f"  ERROR generating audio: {e}", file=sys.stderr)
        if dest.exists():
            dest.unlink()
        return None

    return dest


# ---------------------------------------------------------------------------
# Podcast RSS feed generation
# ---------------------------------------------------------------------------


def rfc2822_now() -> str:
    return formatdate(timeval=None, localtime=False, usegmt=True)


def post_pub_date(post: dict) -> str:
    if post.get("published"):
        try:
            dt = parsedate_to_datetime(post["published"])
            return formatdate(dt.timestamp(), localtime=False, usegmt=True)
        except Exception:
            pass
    return rfc2822_now()


def get_file_size(path: Path) -> int:
    return path.stat().st_size if path.exists() else 0


def build_feed(state: dict) -> None:
    """Regenerate the podcast RSS feed XML from state."""
    episodes = state.get("episodes", [])

    rss = ET.Element("rss", version="2.0")
    rss.set("xmlns:itunes", "http://www.itunes.com/dtds/podcast-1.0.dtd")
    rss.set("xmlns:atom", "http://www.w3.org/2005/Atom")

    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "Forest Park Civic Association News Podcast"
    ET.SubElement(channel, "link").text = "https://www.fpcivic.org"
    ET.SubElement(
        channel, "description"
    ).text = (
        "Automated conversational podcast of Forest Park Civic Association "
        "meeting minutes and community updates. Powered by AI."
    )
    ET.SubElement(channel, "language").text = "en-us"
    ET.SubElement(channel, "lastBuildDate").text = rfc2822_now()
    ET.SubElement(channel, "generator").text = "fpcivic-podcast (Gemini + Edge TTS)"

    ET.SubElement(channel, "{http://www.itunes.com/dtds/podcast-1.0.dtd}author").text = (
        "Forest Park Civic Association"
    )
    ET.SubElement(
        channel, "{http://www.itunes.com/dtds/podcast-1.0.dtd}summary"
    ).text = (
        "AI-generated conversational recaps of Forest Park Civic Association meetings."
    )
    cat = ET.SubElement(
        channel, "{http://www.itunes.com/dtds/podcast-1.0.dtd}category"
    )
    cat.set("text", "Government")
    ET.SubElement(
        channel, "{http://www.itunes.com/dtds/podcast-1.0.dtd}explicit"
    ).text = "no"

    atom_link = ET.SubElement(
        channel, "{http://www.w3.org/2005/Atom}link"
    )
    atom_link.set("href", f"{SITE_BASE_URL}/feed.xml")
    atom_link.set("rel", "self")
    atom_link.set("type", "application/rss+xml")

    for ep in reversed(episodes):
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = ep["title"]
        ET.SubElement(item, "link").text = ep["source_link"]
        ET.SubElement(
            item, "description"
        ).text = f"AI-generated podcast of: {ep['title']}"
        ET.SubElement(item, "pubDate").text = ep["pub_date"]
        ET.SubElement(item, "guid", isPermaLink="false").text = ep["post_id"]

        enclosure = ET.SubElement(item, "enclosure")
        enclosure.set("url", f"{SITE_BASE_URL}/episodes/{ep['filename']}")
        enclosure.set("length", str(ep.get("file_size", 0)))
        enclosure.set("type", "audio/mpeg")

        ET.SubElement(
            item, "{http://www.itunes.com/dtds/podcast-1.0.dtd}author",
        ).text = ep.get("author", "Forest Park Civic Association")
        ET.SubElement(
            item, "{http://www.itunes.com/dtds/podcast-1.0.dtd}summary",
        ).text = f"AI-generated conversational recap of: {ep['title']}"

    tree = ET.ElementTree(rss)
    ET.indent(tree, space="  ")
    tree.write(str(FEED_FILE), encoding="unicode", xml_declaration=True)
    with open(FEED_FILE, "a") as f:
        f.write("\n")

    print(f"Feed updated: {len(episodes)} total episodes")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    if not GROQ_API_KEY:
        print("ERROR: GROQ_API_KEY environment variable is required", file=sys.stderr)
        sys.exit(1)

    EPISODES_DIR.mkdir(exist_ok=True)
    state = load_state()

    new_posts = fetch_new_posts(state)
    if not new_posts:
        print("No new posts found.")
        build_feed(state)
        return

    print(f"Found {len(new_posts)} new post(s)")

    if "episodes" not in state:
        state["episodes"] = []

    for i, post in enumerate(new_posts):
        if i > 0:
            print("  Waiting 5s to avoid rate limits...")
            time.sleep(5)
        episode_path = generate_episode(post)

        if episode_path:
            state["episodes"].append(
                {
                    "post_id": post["id"],
                    "title": post["title"],
                    "source_link": post["link"],
                    "filename": episode_path.name,
                    "pub_date": post_pub_date(post),
                    "author": post["author"],
                    "file_size": get_file_size(episode_path),
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                }
            )

        # Mark as processed even if generation failed
        state["processed"].append(post["id"])
        save_state(state)

    build_feed(state)
    print("Done!")


if __name__ == "__main__":
    main()
