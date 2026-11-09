"""把当天的一期（可能有早间、午间两次运行）合并渲染成手机网页。"""
from __future__ import annotations

import datetime as dt
import hashlib
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

WEEKDAYS = "一二三四五六日"


def _key(prefix: str, *parts) -> str:
    return prefix + hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()[:10]


def merge(edition: dict, cfg: dict, history: dict) -> dict:
    """较新的运行排在前面；每个元素带上 ts（来自哪次运行）和 key（用于记录已读）。"""
    date = edition["date"]
    runs = sorted(edition["runs"], key=lambda r: -r["ts"])
    titles = {t["id"]: t["title"] for t in cfg.get("threads", [])}
    m = {"art": None, "headline": "", "picks": [], "briefs": [], "german": [], "creative": [],
         "hooks": {}, "items": {}, "threads": {}, "status": runs[0]["status"] if runs else []}

    for r in runs:
        d, ts = r["digest"], r["ts"]
        for it in r["items"]:
            m["items"].setdefault(it["id"], {**it, "ts": ts})
        if not m["headline"] and d.get("headline"):
            m["headline"] = d["headline"]
        for p in d.get("picks", []):
            m["picks"].append({**p, "ts": ts, "key": _key("p", date, p.get("title"))})
        for b in d.get("briefs", []):
            m["briefs"].append({**b, "ts": ts, "key": _key("b", b.get("item_id"), b.get("text"))})
        for v in d.get("videos", []):
            m["hooks"].setdefault(v.get("item_id"), v.get("hook", ""))
        if not m["art"] and (d.get("art") or {}).get("work"):
            m["art"] = {**d["art"], "key": _key("art", date)}
        m["german"] += d.get("german", [])
        m["creative"] += d.get("creative", [])
        for t in d.get("threads", []):
            if t.get("id") not in titles:
                continue
            cur = m["threads"].get(t["id"])
            if cur is None:
                title = t.get("title") if t["id"].startswith("u") and t.get("title") else titles[t["id"]]
                m["threads"][t["id"]] = {**t, "title": title, "ts": ts, "user": t["id"].startswith("u"),
                                         "update": list(t.get("update", [])),
                                         "item_ids": list(t.get("item_ids", []))}
            else:  # 较早的运行：补充今天更早的进展
                cur["update"] += [u for u in t.get("update", []) if u not in cur["update"]]
                cur["item_ids"] += [i for i in t.get("item_ids", []) if i not in cur["item_ids"]]

    threads = []
    for t in m["threads"].values():
        t["past"] = [p for p in history.get(t["id"], []) if p["date"] != date][-5:]
        t["key"] = _key("t", date, t["id"], len(t["update"]))
        threads.append(t)
    threads.sort(key=lambda t: -t["ts"])
    m["threads"] = threads
    return m


def render(edition: dict, cfg: dict, history: dict, root: Path, archive: list[str]) -> str:
    env = Environment(loader=FileSystemLoader(root / "templates"),
                      autoescape=select_autoescape(["html"]))
    m = merge(edition, cfg, history)
    items = m["items"]

    seen, sections = set(), []
    for b in m["briefs"]:
        if b.get("section") and b["section"] not in seen:
            seen.add(b["section"])
            sections.append(b["section"])

    folded = set("B站·" + g for g in cfg.get("bilibili", {}).get("folded_groups", []))
    hooks = m["hooks"]
    vids = [it for it in items.values() if it["kind"] in ("video", "bili")]
    # 推荐视频里，AI 认为是标题党、没写看点的不显示
    vids = [v for v in vids if not v["section"].startswith("推荐·") or v["id"] in hooks]
    vids.sort(key=lambda x: (-x["ts"], x["id"] not in hooks, -x["published"]))
    groups: dict[str, list] = {}
    for v in vids:
        groups.setdefault(v["section"], []).append(v)
    order = sorted(groups, key=lambda g: (g in folded, g.startswith("推荐·"), g.startswith("B站·其他")))
    video_groups = [(g, groups[g], g in folded) for g in order]
    shorts = sorted([it for it in items.values() if it["kind"] == "short"], key=lambda x: -x["published"])

    runs = sorted(edition["runs"], key=lambda r: r["ts"])
    d = dt.date.fromisoformat(edition["date"])
    run_label = " · ".join(("早间 " if r["mode"] == "full" else "更新 ") + r["label"] for r in runs)
    status = m["status"]
    return env.get_template("page.html").render(
        m=m, date=edition["date"], date_label=f"{d.month}月{d.day}日 周{WEEKDAYS[d.weekday()]}",
        run_label=run_label, latest_ts=runs[-1]["ts"] if runs else 0,
        items=items, threads=m["threads"], brief_sections=sections,
        video_groups=video_groups, shorts=shorts[:12], hooks=hooks,
        status=status, ok_count=sum(s["ok"] for s in status),
        fail_count=sum(not s["ok"] for s in status), archive=archive,
    )
