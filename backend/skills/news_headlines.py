"""
Sparkbot skill: news_headlines

Fetches current news headlines — no API key required.
Sources:
  - topic=technology / default: Hacker News top stories (official HN API)
  - topic=world / business / science / sports / health: BBC News RSS feeds
"""
import xml.etree.ElementTree as ET

import httpx

_HN_TOP = "https://hacker-news.firebaseio.com/v1/topstories.json"
_HN_ITEM = "https://hacker-news.firebaseio.com/v1/item/{}.json"

_BBC_FEEDS = {
    "world": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "business": "https://feeds.bbci.co.uk/news/business/rss.xml",
    "technology": "https://feeds.bbci.co.uk/news/technology/rss.xml",
    "science": "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml",
    "sports": "https://feeds.bbci.co.uk/sport/rss.xml",
    "health": "https://feeds.bbci.co.uk/news/health/rss.xml",
}

DEFINITION = {
    "type": "function",
    "function": {
        "name": "news_headlines",
        "description": (
            "Fetch current news headlines. Use for questions like 'what's in the news', "
            "'what happened today', 'latest tech news', 'business news', or 'sports scores'. "
            "Always call this instead of using training-data knowledge for current events."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": (
                        "News topic: 'technology' (default, Hacker News), 'world', "
                        "'business', 'science', 'sports', or 'health' (BBC RSS)"
                    ),
                },
                "count": {
                    "type": "integer",
                    "description": "Number of headlines to return (1–15, default 8)",
                },
            },
            "required": [],
        },
    },
}

POLICY = {
    "scope": "read",
    "resource": "web",
    "default_action": "allow",
    "action_type": "read",
    "high_risk": False,
    "requires_execution_gate": False,
}


async def _fetch_hn(count: int) -> str:
    async with httpx.AsyncClient(timeout=15.0) as client:
        ids_resp = await client.get(_HN_TOP)
        ids_resp.raise_for_status()
        top_ids = ids_resp.json()[:count]

        items = []
        for story_id in top_ids:
            try:
                r = await client.get(_HN_ITEM.format(story_id))
                r.raise_for_status()
                d = r.json()
                title = d.get("title", "(no title)")
                score = d.get("score", 0)
                url = d.get("url", f"https://news.ycombinator.com/item?id={story_id}")
                items.append(f"• [{title}]({url}) ▲{score}")
            except Exception:
                pass

    return "🔥 Hacker News — Top Stories:\n" + "\n".join(items)


async def _fetch_bbc(topic: str, count: int) -> str:
    feed_url = _BBC_FEEDS.get(topic, _BBC_FEEDS["world"])
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        resp = await client.get(
            feed_url,
            headers={"User-Agent": "Sparkbot/1.0 (news aggregator)"},
        )
        resp.raise_for_status()

    root = ET.fromstring(resp.text)
    ns = {"media": "http://search.yahoo.com/mrss/"}
    items = root.findall(".//item")[:count]

    lines = [f"📰 BBC News — {topic.title()} Headlines:"]
    for item in items:
        title_el = item.find("title")
        link_el = item.find("link")
        title = title_el.text.strip() if title_el is not None and title_el.text else "(no title)"
        link = link_el.text.strip() if link_el is not None and link_el.text else ""
        if link:
            lines.append(f"• [{title}]({link})")
        else:
            lines.append(f"• {title}")

    return "\n".join(lines)


async def execute(args: dict, *, user_id=None, room_id=None, session=None) -> str:
    topic = (args.get("topic") or "technology").strip().lower()
    count = max(1, min(int(args.get("count") or 8), 15))

    try:
        if topic in ("technology", "tech", "hn", "hackernews"):
            return await _fetch_hn(count)
        return await _fetch_bbc(topic, count)
    except Exception as exc:
        return f"Could not fetch news for topic '{topic}': {exc}"
