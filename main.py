"""一天运行两次：早间完整版 + 午间增量。抓取 → AI 编辑 → 合并成当天的一期 → 生成网页。

用法：
  python main.py                   按当前时间自动判断早间或午间
  python main.py --mode full       强制完整版
  python main.py --mode update     强制增量
  python main.py --force           同一时段已经跑过也再跑一次
  python main.py --sample          用 sample/ 示例数据，不联网、不花钱
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).parent
DATA, DOCS = ROOT / "data", ROOT / "docs"


def load_json(p: Path, default):
    return json.loads(p.read_text()) if p.exists() else default


def wiki_image(title: str) -> str:
    """从维基百科取作品配图，取不到就返回空。"""
    if not title:
        return ""
    import requests
    try:
        r = requests.get("https://en.wikipedia.org/api/rest_v1/page/summary/" + requests.utils.quote(title.replace(" ", "_")),
                         headers={"User-Agent": "info-feed/1.0 (personal reader)"}, timeout=15)
        j = r.json()
        return (j.get("originalimage") or j.get("thumbnail") or {}).get("source", "")
    except Exception:  # noqa: BLE001
        return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", action="store_true")
    ap.add_argument("--mode", choices=["auto", "full", "update", "test"], default=os.environ.get("RUN_MODE") or "auto")
    ap.add_argument("--force", action="store_true", default=os.environ.get("FORCE_RUN") == "true")
    args = ap.parse_args()

    cfg = yaml.safe_load((ROOT / "sources.yaml").read_text())
    DATA.mkdir(exist_ok=True)
    (DOCS / "archive").mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now(ZoneInfo(cfg["settings"]["timezone"]))
    date = now.date().isoformat()
    history = load_json(DATA / "threads.json", {})

    edition = load_json(DATA / "edition.json", {})
    if edition.get("date") != date:
        edition = {"date": date, "runs": []}
    done = {r["mode"] for r in edition["runs"]}
    mode = args.mode
    if mode == "auto":
        mode = "full" if now.hour < 10 or "full" not in done else "update"
    if mode == "test":  # 只检查来源能不能抓到，不调用 AI、不改网页
        from feed.fetch import fetch_all
        _, status = fetch_all(cfg, DATA)
        for st in status:
            print(("OK  " if st["ok"] else "失败 ") + st["source"]
                  + (f' {st.get("count")}条' if st["ok"] else f' {st["error"]}'))
        return 0
    if mode in done and not args.force and not args.sample:
        print(f"今天的{'早间' if mode == 'full' else '午间'}版已经生成过，跳过")
        return 0

    if args.sample:
        items = load_json(ROOT / "sample" / "items.json", [])
        status = [{"source": "示例数据", "ok": True, "count": len(items)}]
        digest = load_json(ROOT / "sample" / "digest.json", {})
        for i, it in enumerate(items):
            it.setdefault("published", time.time() - i * 600)
        edition = {"date": date, "runs": []}
    else:
        from feed.editor import edit
        from feed.fetch import fetch_all
        from feed.signals import load_signals

        try:
            tracked, likes = load_signals()
        except Exception as ex:  # noqa: BLE001
            print(f"读取追踪/赞失败：{ex}")
            tracked, likes = [], []
        print(f"你追踪的主线 {len(tracked)} 条，赞过 {len(likes)} 条")
        cfg["threads"] = cfg.get("threads", []) + tracked
        (DATA / "user_threads.json").write_text(json.dumps(tracked, ensure_ascii=False, indent=1))
        try:
            from feed.signals import ensure_queries
            cfg["signal_queries"] = ensure_queries(tracked, likes, DATA)
            print(f"按追踪找新闻的搜索词 {len(cfg['signal_queries']['news'])} 个，按追踪和赞找视频的 {len(cfg['signal_queries']['videos'])} 个")
        except Exception as ex:  # noqa: BLE001
            print(f"生成追踪搜索词失败：{ex}")

        items, status = fetch_all(cfg, DATA)
        for st in status:
            print(("OK  " if st["ok"] else "失败 ") + st["source"]
                  + (f' {st.get("count")}条' if st["ok"] else f' {st["error"]}'))
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("错误：没有读到 ANTHROPIC_API_KEY", file=sys.stderr)
            return 1
        seen = load_json(DATA / "seen.json", {})
        cutoff = time.time() - 10 * 86400
        seen = {k: v for k, v in seen.items() if v > cutoff}
        items = [it for it in items if it["id"] not in seen]
        if not items:
            print("没有新条目")
            return 0
        art_history = load_json(DATA / "art.json", [])
        digest = edit(items, cfg, history, date, mode, likes, art_history)
        arts = digest.get("art") or []
        arts = [arts] if isinstance(arts, dict) else arts
        for art in arts:
            if art.get("work"):
                art["image"] = wiki_image(art.get("wiki", ""))
                art_history.append({"date": date, "work": art["work"], "creator": art.get("creator", "")})
        digest["art"] = [a for a in arts if a.get("work")]
        (DATA / "art.json").write_text(json.dumps(art_history[-300:], ensure_ascii=False, indent=1))
        for it in items:
            seen[it["id"]] = time.time()
        (DATA / "seen.json").write_text(json.dumps(seen))
        print(f"{mode}：条目 {len(items)}，token 用量 {digest.get('usage')}")

    run = {"mode": mode, "ts": int(time.time()), "label": now.strftime("%H:%M"),
           "digest": digest, "items": items, "status": status}
    # 早间版重跑会替换；增量每次都追加，不覆盖之前的增量
    edition["runs"] = ([r for r in edition["runs"] if r["mode"] != "full"] if mode == "full" else edition["runs"]) + [run]
    edition["runs"].sort(key=lambda r: r["ts"])
    (DATA / "edition.json").write_text(json.dumps(edition, ensure_ascii=False))

    # 主线时间线累积（同一天多次更新合并到当天）
    for t in digest.get("threads", []):
        if t.get("update"):
            h = history.get(t["id"], [])
            if h and h[-1]["date"] == date:
                h[-1]["update"] = [u for u in h[-1]["update"] if u not in t["update"]] + t["update"]
            else:
                h.append({"date": date, "update": t["update"]})
            history[t["id"]] = h[-30:]
    (DATA / "threads.json").write_text(json.dumps(history, ensure_ascii=False, indent=1))

    if args.sample:
        pass
    else:
        cfg["threads"] = [t for t in cfg["threads"] if not t.get("user")]
    cfg["threads"] += load_json(DATA / "user_threads.json", [])
    from feed.render import render

    archive = sorted((p.stem for p in (DOCS / "archive").glob("*.html") if p.stem != date), reverse=True)[:14]
    page = render(edition, cfg, history, ROOT, archive)
    (DOCS / "index.html").write_text(page)
    (DOCS / "archive" / f"{date}.html").write_text(page.replace('href="archive/', 'href="'))
    (DOCS / ".nojekyll").touch()
    print(f"已生成 docs/index.html（{date} {run['label']}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
