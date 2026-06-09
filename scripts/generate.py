#!/usr/bin/env python3
"""
FP Civic Podcast Generator

Monitors the Forest Park Civic Association RSS feed for new posts,
generates conversational podcast episodes using Podcastfy + Edge TTS,
and updates the podcast RSS feed for distribution.
"""

import json
import os
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import formatdate, parsedate_to_datetime
from pathlib import Path

import feedparser
from podcastfy.client import generate_podcast

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

RSS_FEED_URL = "https://www.fpcivic.org/feed/"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
EPISODES_DIR = PROJECT_ROOT / "episodes"
FEED_FILE = PROJECT_ROOT / "feed.xml"
STATE_FILE = PROJECT_ROOT / "state.json"

# This gets set after the GitHub Pages site is created
SITE_BASE_URL = os.environ.get(
    "SITE_BASE_URL", "https://OWNER.github.io/fpcivic-podcast"
)

PODCAST_CONFIG = {
    "word_count": 600,
    "conversation_style": ["casual", "informative", "friendly"],
    "podcast_name": "Forest Park Civic Podcast",
    "podcast_tagline": "Your neighborhood meeting minutes, as a conversation",
    "creativity": 0.7,
    "roles_person1": "host who summarizes the key points",
    "roles_person2": "curious neighbor asking follow-up questions",
    "dialogue_structure": [
        "Introduction",
        "Main Topics Covered",
        "Key Decisions and Action Items",
        "What It Means for Residents",
        "Wrap-up",
    ],
    "output_language": "English",
    "engagement_techniques": [
        "rhetorical questions",
        "real-world examples",
        "analogies",
    ],
}

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

    # Oldest first so episodes are generated in chronological order
    new_posts.reverse()
    return new_posts


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
    print(f"Generating podcast for: {post['title']}")
    print(f"  URL: {post['link']}")

    try:
        audio_file = generate_podcast(
            urls=[post["link"]],
            tts_model="edge",
            conversation_config=PODCAST_CONFIG,
        )
    except Exception as e:
        print(f"  ERROR generating podcast: {e}", file=sys.stderr)
        return None

    if not audio_file or not Path(audio_file).exists():
        print("  ERROR: No audio file produced.", file=sys.stderr)
        return None

    # Move to episodes directory with a clean filename
    slug = slugify(post["title"])
    dest = EPISODES_DIR / f"{slug}.mp3"
    shutil.move(str(audio_file), str(dest))
    print(f"  Saved: {dest.name}")
    return dest


# ---------------------------------------------------------------------------
# Podcast RSS feed generation
# ---------------------------------------------------------------------------


def rfc2822_now() -> str:
    return formatdate(timeval=None, localtime=False, usegmt=True)


def post_pub_date(post: dict) -> str:
    """Convert post's published date to RFC 2822, or use now."""
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
    ET.SubElement(channel, "title").text = "Forest Park Civic Podcast"
    ET.SubElement(channel, "link").text = "https://www.fpcivic.org"
    ET.SubElement(
        channel, "description"
    ).text = (
        "Automated conversational podcast of Forest Park Civic Association "
        "meeting minutes and community updates. Powered by AI."
    )
    ET.SubElement(channel, "language").text = "en-us"
    ET.SubElement(channel, "lastBuildDate").text = rfc2822_now()
    ET.SubElement(channel, "generator").text = "fpcivic-podcast (Podcastfy + Edge TTS)"

    # iTunes tags (needed for podcast directories)
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

    # Atom self-link
    atom_link = ET.SubElement(
        channel, "{http://www.w3.org/2005/Atom}link"
    )
    atom_link.set("href", f"{SITE_BASE_URL}/feed.xml")
    atom_link.set("rel", "self")
    atom_link.set("type", "application/rss+xml")

    # Episodes (newest first)
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
            item,
            "{http://www.itunes.com/dtds/podcast-1.0.dtd}author",
        ).text = ep.get("author", "Forest Park Civic Association")
        ET.SubElement(
            item,
            "{http://www.itunes.com/dtds/podcast-1.0.dtd}summary",
        ).text = f"AI-generated conversational recap of: {ep['title']}"

    tree = ET.ElementTree(rss)
    ET.indent(tree, space="  ")
    tree.write(str(FEED_FILE), encoding="unicode", xml_declaration=True)
    # Add newline at end
    with open(FEED_FILE, "a") as f:
        f.write("\n")

    print(f"Feed updated: {len(episodes)} total episodes")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    EPISODES_DIR.mkdir(exist_ok=True)
    state = load_state()

    new_posts = fetch_new_posts(state)
    if not new_posts:
        print("No new posts found.")
        build_feed(state)  # Ensure feed.xml exists even with no new posts
        return

    print(f"Found {len(new_posts)} new post(s)")

    if "episodes" not in state:
        state["episodes"] = []

    for post in new_posts:
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

        # Mark as processed even if generation failed (to avoid retrying bad posts)
        state["processed"].append(post["id"])
        save_state(state)

    build_feed(state)
    print("Done!")


if __name__ == "__main__":
    main()
