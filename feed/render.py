"""把 AI 编辑结果和原始条目渲染成手机网页。"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

WEEKDAYS = "一二三四五六日"


def render(digest: dict, items: list[dict], status: list[dict], cfg: dict,
           history: dict, date: str, root: Path, archive: list[str]) -> str:
    env = Environment(loader=FileSystemLoader(root / "templates"),
                      autoescape=select_autoescape(["html"]))
    by_id = {it["id"]: it for it in items}
    titles = {t["id"]: t["title"] for t in cfg.get("threads", [])}

    threads = []
    for t in digest.get("threads", []):
        if t.get("id") not in titles:
            continue
        past = [p for p in history.get(t["id"], []) if p["date"] != date][-5:]
        threads.append({**t, "title": titles[t["id"]], "past": past})

    seen, sections = set(), []
    for b in digest.get("briefs", []):
        if b.get("section") and b["section"] not in seen:
            seen.add(b["section"])
            sections.append(b["section"])

    hooks = {v["item_id"]: v.get("hook", "") for v in digest.get("videos", [])}
    vids = [it for it in items if it["kind"] in ("video", "bili")]
    vids.sort(key=lambda x: (x["id"] not in hooks, -x["published"]))
    groups: dict[str, list] = {}
    for v in vids:
        groups.setdefault(v["section"], []).append(v)
    shorts = sorted([it for it in items if it["kind"] == "short"], key=lambda x: -x["published"])

    d = dt.date.fromisoformat(date)
    return env.get_template("page.html").render(
        d=digest, date=date, date_label=f"{d.month}月{d.day}日 周{WEEKDAYS[d.weekday()]}",
        items=by_id, threads=threads, brief_sections=sections,
        video_groups=list(groups.items()), shorts=shorts[:12], hooks=hooks,
        status=status, ok_count=sum(s["ok"] for s in status),
        fail_count=sum(not s["ok"] for s in status), archive=archive,
    )
