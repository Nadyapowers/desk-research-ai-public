"""Collector: visits every active source once, saves new materials, exits."""

import html
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import db

SERVICE = "collector"
MAX_PER_SOURCE = None  # None: take everything the feed gives; repeats are dropped by the database for free
MAX_AGE_DAYS = 14  # older materials are not saved: there is no archive at this stage
MAX_TEXT = 1500
TG_TITLE = 120
TEXT_FIELDS = ("description", "full-text", "encoded")  # feeds keep the article text in different fields
ATOM = "{http://www.w3.org/2005/Atom}"


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "food-at-work-news/0.1"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def read_hn(url):
    for hit in json.loads(fetch(url))["hits"]:
        link = (
            hit.get("url") or f"https://news.ycombinator.com/item?id={hit['objectID']}"
        )
        yield {
            "url": link,
            "title": hit["title"],
            "text": hit.get("story_text") or "",
            "published_at": hit["created_at"],
        }


def read_arxiv(url):
    root = ET.fromstring(fetch(url))
    for entry in root.iter(f"{ATOM}entry"):
        yield {
            "url": entry.findtext(f"{ATOM}id"),
            "title": " ".join(entry.findtext(f"{ATOM}title").split()),
            "text": " ".join(entry.findtext(f"{ATOM}summary").split())[:1500],
            "published_at": entry.findtext(f"{ATOM}published"),
        }


def local_name(element):
    # some feeds declare a namespace, then tags look like {http://...}item
    return element.tag.rsplit("}", 1)[-1]


def plain_text(value):
    # feeds often put HTML into the description
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", value or "")).split())


def parse_date(value):
    try:
        return parsedate_to_datetime(value).isoformat()
    except (TypeError, ValueError):
        return None


def read_rss(url):
    root = ET.fromstring(fetch(url))
    for item in root.iter():
        if local_name(item) != "item":
            continue
        fields = {local_name(child): child.text for child in item}
        link, title = (fields.get("link") or "").strip(), (fields.get("title") or "").strip()
        if not link or not title:
            continue
        texts = [plain_text(fields.get(name)) for name in TEXT_FIELDS]
        yield {
            "url": link,
            "title": plain_text(title),
            "text": max(texts, key=len)[:MAX_TEXT],
            "published_at": parse_date(fields.get("pubDate")),
        }


def read_tg(url):
    # open channels have a web page t.me/s/<channel> with the latest posts, no Telegram account needed
    page = fetch(url).decode("utf-8", "replace")
    for post in re.split(r'(?=data-post=")', page)[1:]:
        path = re.match(r'data-post="([^"]+)"', post).group(1)
        body = re.search(r'tgme_widget_message_text js-message_text[^>]*>(.*?)</div>', post, re.S)
        date = re.search(r'<time[^>]*datetime="([^"]+)"', post)
        text = plain_text(re.sub(r"<br\s*/?>", " ", body.group(1))) if body else ""
        if not text:
            continue  # a photo or a video without a caption
        yield {
            "url": f"https://t.me/{path}",
            "title": text[:TG_TITLE],  # posts have no title
            "text": text[:MAX_TEXT],
            "published_at": date.group(1) if date else None,
        }


READERS = {"hn": read_hn, "arxiv": read_arxiv, "rss": read_rss, "tg": read_tg}


def is_fresh(published_at):
    # a material without a date is kept: better to look at it once than to lose it
    if not published_at:
        return True
    moment = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment >= datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)


def main():
    conn = db.connect()
    db.init_schema(conn)
    run_id = db.start_run(conn, SERVICE)
    total_new = 0
    try:
        sources = conn.execute(
            "SELECT id, name, kind, url FROM sources WHERE active"
        ).fetchall()
        for source_id, name, kind, url in sources:
            try:
                items = list(READERS[kind](url))[:MAX_PER_SOURCE]
                items = [item for item in items if is_fresh(item["published_at"])]
            except Exception as error:
                # one broken source does not stop the run
                db.log(SERVICE, f"источник «{name}» недоступен: {error}")
                continue
            new = 0
            for item in items:
                row = conn.execute(
                    """INSERT INTO materials (source_id, run_id, url, title, text, published_at)
                       VALUES (%s, %s, %s, %s, %s, %s)
                       ON CONFLICT (url) DO NOTHING RETURNING id""",
                    (
                        source_id,
                        run_id,
                        item["url"],
                        item["title"],
                        item["text"],
                        item["published_at"],
                    ),
                ).fetchone()
                new += row is not None
            total_new += new
            db.progress_run(
                conn,
                SERVICE,
                run_id,
                total_new,
                f"{name}: взял {len(items)}, новых {new}",
            )
        db.finish_run(
            conn, SERVICE, run_id, total_new, f"новых материалов в базе: {total_new}"
        )
    except Exception as error:
        db.fail_run(conn, SERVICE, run_id, error)
        raise


if __name__ == "__main__":
    main()
