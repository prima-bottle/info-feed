"""每天运行一次：抓取 → AI 编辑 → 生成网页。

用法：
  python main.py            正式运行（需要环境变量 ANTHROPIC_API_KEY）
  python main.py --sample   用 sample/ 里的示例数据，不联网、不花钱
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", action="store_true")
    args = ap.parse_args()

    cfg = yaml.safe_load((ROOT / "sources.yaml").read_text())
    DATA.mkdir(exist_ok=True)
    (DOCS / "archive").mkdir(parents=True, exist_ok=True)
    date = dt.datetime.now(ZoneInfo(cfg["settings"]["timezone"])).date().isoformat()
    history = load_json(DATA / "threads.json", {})

    if args.sample:
        items = load_json(ROOT / "sample" / "items.json", [])
        status = [{"source": "示例数据", "ok": True, "count": len(items)},
                  {"source": "Stadt Münster", "ok": False, "error": "示例：抓取失败时会显示在这里"}]
        digest = load_json(ROOT / "sample" / "digest.json", {})
        now = time.time()
        for i, it in enumerate(items):
            it.setdefault("published", now - i * 600)
    else:
        from feed.editor import edit
        from feed.fetch import fetch_all

        items, status = fetch_all(cfg, DATA)
        for st in status:
            print(("OK  " if st["ok"] else "失败 ") + st["source"] + (f' {st.get("count")}条' if st["ok"] else f' {st["error"]}'))
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("错误：没有读到 ANTHROPIC_API_KEY，请检查仓库 Settings → Secrets and variables → Actions 里的名字是否完全一致", file=sys.stderr)
            return 1
        seen = load_json(DATA / "seen.json", {})
        cutoff = time.time() - 7 * 86400
        seen = {k: v for k, v in seen.items() if v > cutoff}
        items = [it for it in items if it["id"] not in seen]
        if not items:
            print("今天没有新条目", file=sys.stderr)
            return 0
        digest = edit(items, cfg, history, date)
        for it in items:
            seen[it["id"]] = time.time()
        (DATA / "seen.json").write_text(json.dumps(seen))
        print(f"条目 {len(items)}，token 用量 {digest.get('usage')}")

    # 主线时间线累积
    for t in digest.get("threads", []):
        if t.get("update"):
            h = [p for p in history.get(t["id"], []) if p["date"] != date]
            h.append({"date": date, "update": t["update"]})
            history[t["id"]] = h[-30:]
    (DATA / "threads.json").write_text(json.dumps(history, ensure_ascii=False, indent=1))

    from feed.render import render

    archive = sorted((p.stem for p in (DOCS / "archive").glob("*.html") if p.stem != date), reverse=True)[:14]
    page = render(digest, items, status, cfg, history, date, ROOT, archive)
    (DOCS / "index.html").write_text(page)
    (DOCS / "archive" / f"{date}.html").write_text(page.replace('href="archive/', 'href="'))
    (DOCS / ".nojekyll").touch()
    print(f"已生成 docs/index.html（{date}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
