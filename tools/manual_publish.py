"""API 额度不够时的手动发布：GitHub 用 fetch 模式抓好原始条目，对话里的 Claude 写好 digest，
再用这个脚本合成当天一期并生成网页。不调用任何 AI 接口。

  python tools/manual_publish.py data/raw/2026-11-17-0631.json digest.json full
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import time
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from feed.render import render  # noqa: E402

DATA, DOCS = ROOT / "data", ROOT / "docs"


def load(p: Path, default):
    return json.loads(p.read_text()) if p.exists() else default


def main() -> None:
    raw_path, digest_path, mode = sys.argv[1], sys.argv[2], (sys.argv[3] if len(sys.argv) > 3 else "full")
    cfg = yaml.safe_load((ROOT / "sources.yaml").read_text())
    now = dt.datetime.now(ZoneInfo(cfg["settings"]["timezone"]))
    date = now.date().isoformat()
    raw = load(Path(raw_path), {})
    digest = load(Path(digest_path), {})
    items, status = raw.get("items", []), raw.get("status", [])
    used = set()
    for k in ("picks", "threads", "creative"):
        for x in digest.get(k, []):
            used.update(x.get("item_ids") or [])
    used.update(b.get("item_id") for b in digest.get("briefs", []))
    # 只保留被引用的条目和视频，页面更轻
    items = [it for it in items if it["id"] in used or it["kind"] in ("video", "short", "bili")]

    edition = load(DATA / "edition.json", {})
    if edition.get("date") != date:
        edition = {"date": date, "runs": []}
    run = {"mode": mode, "ts": int(time.time()), "label": now.strftime("%H:%M") + " 手动",
           "digest": digest, "items": items, "status": status}
    edition["runs"] = ([r for r in edition["runs"] if r["mode"] != "full"] if mode == "full" else edition["runs"]) + [run]
    edition["runs"].sort(key=lambda r: r["ts"])
    (DATA / "edition.json").write_text(json.dumps(edition, ensure_ascii=False))

    history = load(DATA / "threads.json", {})
    for t in digest.get("threads", []):
        if t.get("update"):
            h = history.get(t["id"], [])
            if h and h[-1]["date"] == date:
                h[-1]["update"] = [u for u in h[-1]["update"] if u not in t["update"]] + t["update"]
            else:
                h.append({"date": date, "update": t["update"]})
            history[t["id"]] = h[-30:]
    (DATA / "threads.json").write_text(json.dumps(history, ensure_ascii=False, indent=1))

    art_hist = load(DATA / "art.json", [])
    for a in digest.get("art") or []:
        if a.get("work"):
            art_hist.append({"date": date, "work": a["work"], "creator": a.get("creator", "")})
    (DATA / "art.json").write_text(json.dumps(art_hist[-300:], ensure_ascii=False, indent=1))

    links = {it["id"]: {"source": it["source"], "link": it["link"]} for it in items}
    aw = digest.get("aiwork") or {}
    if aw.get("items"):
        aw_hist = load(DATA / "aiwork.json", [])
        aw_hist += [{"date": date, **{k: x.get(k, "") for k in ("kind", "area", "title", "what", "use")},
                     "links": [links[i] for i in x.get("item_ids", []) if i in links]} for x in aw["items"] if x.get("title")]
        (DATA / "aiwork.json").write_text(json.dumps(aw_hist[-500:], ensure_ascii=False, indent=1))
    les = digest.get("lesson") or {}
    if les.get("title"):
        course = load(DATA / "aicourse.json", [])
        course.append({"date": date, **{k: les.get(k) for k in ("no", "title", "concept", "how", "for_you", "pitfalls", "try")},
                       "links": [links[i] for i in les.get("item_ids", []) if i in links]})
        (DATA / "aicourse.json").write_text(json.dumps(course, ensure_ascii=False, indent=1))
    seen = load(DATA / "seen.json", {})
    for it in raw.get("items", []):
        seen[it["id"]] = time.time()
    (DATA / "seen.json").write_text(json.dumps(seen))

    cfg["threads"] = [t for t in cfg.get("threads", []) if not t.get("user")] + load(DATA / "user_threads.json", [])
    archive = sorted((p.stem for p in (DOCS / "archive").glob("*.html") if p.stem != date), reverse=True)[:14]
    page = render(edition, cfg, history, ROOT, archive)
    (DOCS / "index.html").write_text(page)
    (DOCS / "archive" / f"{date}.html").write_text(page.replace('href="archive/', 'href="'))
    print(f"已生成 {date} {run['label']}，引用条目 {len(items)}")


if __name__ == "__main__":
    main()
