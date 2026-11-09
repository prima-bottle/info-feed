"""抓取 RSS 和 YouTube。任何一个来源失败都不影响其它来源。"""
from __future__ import annotations

import calendar
import hashlib
import html
import json
import re
import os
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
    if kind in ("video", "short") and parsed.feed.get("title") and not source.get("name_fixed"):
        source = {**source, "name": parsed.feed["title"]}
    now, out = time.time(), []
    for e in parsed.entries[: max_items * 3]:
        ts = _ts(e)
        if ts and now - ts > max_age_h * 3600:
            continue
        link = e.get("link", "")
        title, src_name = e.get("title", ""), source["name"]
        if "news.google.com" in url:
            pub = (e.get("source") or {}).get("title", "")
            if pub and title.endswith(" - " + pub):
                title = title[: -len(pub) - 3]
            if pub and (source.get("section", "").startswith("地方") or source["name"] in ("中国劳动与民生", "珠三角动态", "长三角动态")):
                src_name = pub
        out.append({
            "id": hashlib.sha1((link or e.get("title", "")).encode()).hexdigest()[:10],
            "kind": kind,
            "source": src_name,
            "section": source["section"],
            "stance": source.get("stance", ""),
            "title": _clean(title, 200),
            "summary": _clean(e.get("summary", "")),
            "link": link,
            "image": _image(e),
            "published": ts or now,
        })
        if len(out) >= max_items:
            break
    return out


def _channel_from(page: str) -> str | None:
    m = re.search(r'"(?:channelId|externalId|browseId)":"(UC[\w-]{22})"', page)
    return m.group(1) if m else None


def resolve_youtube(ch: dict, cache: dict) -> str | None:
    """依次尝试：直接给的 channel_id → @账号名 → 按名字搜索。结果缓存。"""
    key = ch.get("channel_id") or ch.get("handle") or ch.get("search")
    if ch.get("channel_id"):
        return ch["channel_id"]
    if key in cache:
        return cache[key]
    cid = None
    api_key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    if api_key and ch.get("handle"):
        try:
            r = requests.get("https://www.googleapis.com/youtube/v3/channels",
                             params={"part": "id", "forHandle": ch["handle"], "key": api_key}, timeout=TIMEOUT)
            items_ = r.json().get("items") or []
            cid = items_[0]["id"] if items_ else None
        except Exception:  # noqa: BLE001
            cid = None
    if not cid and ch.get("handle"):
        try:
            cid = _channel_from(_get(f"https://www.youtube.com/{ch['handle']}").decode("utf-8", "ignore"))
        except Exception:  # noqa: BLE001
            cid = None
    if not cid:
        q = requests.utils.quote(ch.get("search") or ch.get("name") or ch["handle"].lstrip("@"))
        page = _get(f"https://www.youtube.com/results?search_query={q}&sp=EgIQAg%253D%253D").decode("utf-8", "ignore")
        cid = _channel_from(page)
    if cid:
        cache[key] = cid
    return cid


_YT_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                             "(KHTML, like Gecko) Chrome/130.0 Safari/537.36",
               "Accept-Language": "en-US,en;q=0.8", "Cookie": "CONSENT=YES+1; SOCS=CAI"}
_AGO = {"second": 1, "minute": 60, "hour": 3600, "day": 86400, "week": 604800, "month": 2592000, "year": 31536000}


def _scrape_channel(cid: str, src: dict, max_items: int, age_days: int) -> list[dict]:
    """RSS 不可用时的备用方案：直接读频道的视频页。"""
    page = requests.get(f"https://www.youtube.com/channel/{cid}/videos?hl=en&gl=US",
                        headers=_YT_HEADERS, timeout=TIMEOUT).text
    m = re.search(r'"channelMetadataRenderer":\{"title":"((?:[^"\\]|\\.)*)"', page)
    name = json.loads(f'"{m.group(1)}"') if m else src["name"]
    now, out, seen = time.time(), [], set()
    for vm in re.finditer(r'"videoRenderer":\{"videoId":"([\w-]{11})"', page):
        vid = vm.group(1)
        if vid in seen:
            continue
        seen.add(vid)
        chunk = page[vm.end(): vm.end() + 6000]
        t = re.search(r'"title":\{"runs":\[\{"text":"((?:[^"\\]|\\.)*)"', chunk)
        ago = re.search(r'"publishedTimeText":\{"simpleText":"(?:Streamed )?(\d+) (second|minute|hour|day|week|month|year)s? ago"', chunk)
        ts = now - int(ago.group(1)) * _AGO[ago.group(2)] if ago else now - 86400 * 30
        if now - ts > age_days * 86400:
            continue
        link = f"https://www.youtube.com/watch?v={vid}"
        out.append({"id": hashlib.sha1(link.encode()).hexdigest()[:10], "kind": "video", "source": name,
                    "section": src["section"], "stance": src.get("stance", ""),
                    "title": _clean(json.loads(f'"{t.group(1)}"') if t else "", 200), "summary": "",
                    "link": link, "image": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg", "published": ts})
        if len(out) >= max_items:
            break
    if not out and "videoRenderer" not in page:
        raise RuntimeError("频道页没有读到视频")
    return out


def _api_playlist(pid: str, src: dict, kind: str, max_items: int, age_days: int, key: str) -> list[dict]:
    """YouTube Data API：读取一个播放列表（上传列表 UU… 或短视频列表 UUSH…）。每次调用消耗 1 点配额。"""
    r = requests.get("https://www.googleapis.com/youtube/v3/playlistItems",
                     params={"part": "snippet,contentDetails", "playlistId": pid,
                             "maxResults": min(max_items * 2, 50), "key": key}, timeout=TIMEOUT)
    if r.status_code == 404:
        return []
    r.raise_for_status()
    now, out = time.time(), []
    for it in r.json().get("items", []):
        sn, cd = it.get("snippet", {}), it.get("contentDetails", {})
        vid = cd.get("videoId") or sn.get("resourceId", {}).get("videoId")
        if not vid or sn.get("title") in ("Private video", "Deleted video"):
            continue
        published = cd.get("videoPublishedAt") or sn.get("publishedAt") or ""
        try:
            ts = calendar.timegm(time.strptime(published[:19], "%Y-%m-%dT%H:%M:%S"))
        except ValueError:
            ts = now
        if now - ts > age_days * 86400:
            continue
        link = f"https://www.youtube.com/watch?v={vid}" if kind == "video" else f"https://www.youtube.com/shorts/{vid}"
        thumbs = sn.get("thumbnails", {})
        img = (thumbs.get("high") or thumbs.get("medium") or thumbs.get("default") or {}).get("url", "")
        out.append({"id": hashlib.sha1(f"https://www.youtube.com/watch?v={vid}".encode()).hexdigest()[:10],
                    "kind": kind, "source": sn.get("channelTitle") or src["name"],
                    "section": src["section"], "stance": src.get("stance", ""),
                    "title": _clean(sn.get("title", ""), 200), "summary": _clean(sn.get("description", ""), 300),
                    "link": link, "image": img, "published": ts})
        if len(out) >= max_items:
            break
    return out


def youtube_videos(cid: str, src: dict, max_items: int, age_days: int) -> list[dict]:
    """有 YOUTUBE_API_KEY 时用官方 API（最稳）；否则依次尝试 RSS 和频道页。"""
    key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    if key:
        return _api_playlist("UU" + cid[2:], src, "video", max_items, age_days, key)
    errors = []
    for url in (f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}",
                f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}",
                f"https://www.youtube.com/feeds/videos.xml?playlist_id=UU{cid[2:]}"):
        try:
            return parse_feed(url, src, "video", max_items, age_days * 24)
        except Exception as ex:  # noqa: BLE001
            errors.append(str(ex)[:40])
            time.sleep(1.5)
    try:
        return _scrape_channel(cid, src, max_items, age_days)
    except Exception as ex:  # noqa: BLE001
        raise RuntimeError("YouTube 拦截了服务器请求（需要设置 YOUTUBE_API_KEY）：" + str(ex)[:60]) from ex


def fetch_all(cfg: dict, data_dir: Path) -> tuple[list[dict], list[dict]]:
    s = cfg["settings"]
    items, status = [], []

    for f in cfg.get("feeds", []):
        if f.get("enabled", True) is False:
            continue
        try:
            got = parse_feed(f["url"], f, "article", f.get("max", s["max_items_per_source"]), s["max_age_hours"])
            items += got
            status.append({"source": f["name"], "ok": True, "count": len(got)})
        except Exception as ex:  # noqa: BLE001
            status.append({"source": f["name"], "ok": False, "error": str(ex)[:120]})

    cache_file = data_dir / "youtube_ids.json"
    cache = json.loads(cache_file.read_text()) if cache_file.exists() else {}
    shorts_groups = set(cfg.get("shorts_from", []))
    for ch in cfg.get("youtube", []):
        label = ch.get("name") or ch.get("handle", "").lstrip("@") or ch.get("search")
        src = {"name": label, "section": ch["section"], "stance": ch.get("note", "")}
        try:
            cid = resolve_youtube(ch, cache)
            if not cid:
                raise ValueError("找不到频道 ID")
            got = youtube_videos(cid, src, s.get("videos_per_channel", 5), s.get("video_age_days", 10))
            if ch["section"] in shorts_groups:
                try:
                    key = os.environ.get("YOUTUBE_API_KEY", "").strip()
                    shorts = (_api_playlist("UUSH" + cid[2:], src, "short", 6, s.get("video_age_days", 10), key) if key
                              else parse_feed(f"https://www.youtube.com/feeds/videos.xml?playlist_id=UUSH{cid[2:]}",
                                              src, "short", 6, s.get("video_age_days", 10) * 24))
                    ids = {x["id"] for x in shorts}
                    got = [x for x in got if x["id"] not in ids] + shorts
                except Exception:  # noqa: BLE001
                    pass
            items += got
            status.append({"source": label, "ok": True, "count": len(got)})
        except Exception as ex:  # noqa: BLE001
            status.append({"source": label, "ok": False, "error": str(ex)[:120]})
    cache_file.write_text(json.dumps(cache, ensure_ascii=False, indent=1))

    b = cfg.get("bilibili", {})
    sess = os.environ.get("BILI_SESSDATA", "").strip()
    if b.get("enabled") and sess:
        try:
            got = fetch_bilibili(b, sess, s.get("video_age_days", 10))
            items += got
            status.append({"source": "B站关注动态", "ok": True, "count": len(got)})
        except Exception as ex:  # noqa: BLE001
            status.append({"source": "B站关注动态", "ok": False, "error": str(ex)[:160]})
    elif b.get("enabled"):
        status.append({"source": "B站关注动态", "ok": False, "error": "没有设置 BILI_SESSDATA"})

    return items, status


def fetch_bilibili(b: dict, sessdata: str, age_days: int) -> list[dict]:
    """读取账号的"关注动态"里的视频，按 sources.yaml 里的分组归类。"""
    groups = {u["name"]: u["group"] for u in b.get("ups", [])}
    headers = {"User-Agent": UA.replace("personal news reader", "Windows NT 10.0; Win64; x64"),
               "Referer": "https://t.bilibili.com/", "Origin": "https://t.bilibili.com",
               "Cookie": f"SESSDATA={sessdata}"}
    cutoff, out, offset = time.time() - age_days * 86400, [], ""
    for _ in range(b.get("pages", 4)):
        r = requests.get("https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/all",
                         params={"type": "video", "offset": offset, "timezone_offset": -60},
                         headers=headers, timeout=TIMEOUT)
        r.raise_for_status()
        j = r.json()
        if j.get("code") != 0:
            raise RuntimeError(f'B站返回 code={j.get("code")} {j.get("message")}')
        data, stop = j["data"], False
        for it in data.get("items", []):
            mod = it.get("modules", {})
            author = mod.get("module_author", {})
            ts = int(author.get("pub_ts") or 0)
            if ts and ts < cutoff:
                stop = True
                continue
            arc = (mod.get("module_dynamic", {}).get("major") or {}).get("archive")
            if not arc:
                continue
            name = author.get("name", "")
            link = arc.get("jump_url", "")
            link = "https:" + link if link.startswith("//") else link
            cover = arc.get("cover", "")
            out.append({
                "id": hashlib.sha1(arc.get("bvid", link).encode()).hexdigest()[:10],
                "kind": "bili", "source": name,
                "section": "B站·" + groups.get(name, "其他"), "stance": "",
                "title": _clean(arc.get("title", ""), 200), "summary": _clean(arc.get("desc", ""), 300),
                "link": link, "image": ("https:" + cover) if cover.startswith("//") else cover,
                "published": ts or time.time(),
            })
        offset = data.get("offset", "")
        if stop or not data.get("has_more"):
            break
    return out
