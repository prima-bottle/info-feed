"""抓取 RSS 和 YouTube。任何一个来源失败都不影响其它来源。"""
from __future__ import annotations

import calendar
import hashlib
import html
import json
import re
import time
from pathlib import Path

import feedparser
import requests

UA = "Mozilla/5.0 (personal news reader)"
TIMEOUT = 20


def _clean(text: str, limit: int = 600) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(re.sub(r"\s+", " ", text)).strip()
    return text[:limit]


def _image(entry) -> str:
    for key in ("media_thumbnail", "media_content"):
        for m in entry.get(key, []) or []:
            if m.get("url"):
                return m["url"]
    for enc in entry.get("enclosures", []) or []:
        if enc.get("type", "").startswith("image") and enc.get("href"):
            return enc["href"]
    m = re.search(r'<img[^>]+src="([^"]+)"', entry.get("summary", "") or "")
    return m.group(1) if m else ""


def _ts(entry) -> float | None:
    for key in ("published_parsed", "updated_parsed"):
        if entry.get(key):
            return calendar.timegm(entry[key])
    return None


def _get(url: str) -> bytes:
    r = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.content


def parse_feed(url: str, source: dict, kind: str, max_items: int, max_age_h: float) -> list[dict]:
    parsed = feedparser.parse(_get(url))
    now, out = time.time(), []
    for e in parsed.entries[: max_items * 3]:
        ts = _ts(e)
        if ts and now - ts > max_age_h * 3600:
            continue
        link = e.get("link", "")
        out.append({
            "id": hashlib.sha1((link or e.get("title", "")).encode()).hexdigest()[:10],
            "kind": kind,
            "source": source["name"],
            "section": source["section"],
            "stance": source.get("stance", ""),
            "title": _clean(e.get("title", ""), 200),
            "summary": _clean(e.get("summary", "")),
            "link": link,
            "image": _image(e),
            "published": ts or now,
        })
        if len(out) >= max_items:
            break
    return out


def resolve_youtube(handle: str, cache: dict) -> str | None:
    if handle in cache:
        return cache[handle]
    page = _get(f"https://www.youtube.com/{handle}").decode("utf-8", "ignore")
    m = re.search(r'"(?:channelId|externalId)":"(UC[\w-]{22})"', page)
    if m:
        cache[handle] = m.group(1)
    return cache.get(handle)


def fetch_all(cfg: dict, data_dir: Path) -> tuple[list[dict], list[dict]]:
    s = cfg["settings"]
    items, status = [], []

    for f in cfg.get("feeds", []):
        if f.get("enabled", True) is False:
            continue
        try:
            got = parse_feed(f["url"], f, "article", s["max_items_per_source"], s["max_age_hours"])
            items += got
            status.append({"source": f["name"], "ok": True, "count": len(got)})
        except Exception as ex:  # noqa: BLE001
            status.append({"source": f["name"], "ok": False, "error": str(ex)[:120]})

    cache_file = data_dir / "youtube_ids.json"
    cache = json.loads(cache_file.read_text()) if cache_file.exists() else {}
    shorts_groups = set(cfg.get("shorts_from", []))
    for ch in cfg.get("youtube", []):
        src = {"name": ch.get("name") or ch["handle"].lstrip("@"),
               "section": ch["section"], "stance": ch.get("note", "")}
        try:
            cid = resolve_youtube(ch["handle"], cache)
            if not cid:
                raise ValueError("找不到频道 ID")
            got = parse_feed(f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}",
                             src, "video", 4, 24 * 7)
            if ch["section"] in shorts_groups:
                try:
                    shorts = parse_feed(
                        f"https://www.youtube.com/feeds/videos.xml?playlist_id=UUSH{cid[2:]}",
                        src, "short", 6, 24 * 3)
                    ids = {x["id"] for x in shorts}
                    got = [x for x in got if x["id"] not in ids] + shorts
                except Exception:  # noqa: BLE001
                    pass
            items += got
            status.append({"source": ch["handle"], "ok": True, "count": len(got)})
        except Exception as ex:  # noqa: BLE001
            status.append({"source": ch["handle"], "ok": False, "error": str(ex)[:120]})
    cache_file.write_text(json.dumps(cache, ensure_ascii=False, indent=1))

    b = cfg.get("bilibili", {})
    if b.get("enabled"):
        for up in b.get("ups", []):
            if not up.get("uid"):
                continue
            src = {"name": up["name"], "section": "B站·" + up["group"], "stance": ""}
            try:
                got = parse_feed(f'{b["rsshub"]}/bilibili/user/video/{up["uid"]}',
                                 src, "bili", 3, 24 * 7)
                items += got
                status.append({"source": up["name"], "ok": True, "count": len(got)})
            except Exception as ex:  # noqa: BLE001
                status.append({"source": up["name"], "ok": False, "error": str(ex)[:120]})

    return items, status
