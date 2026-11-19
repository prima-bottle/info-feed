"""定时任务每小时先跑这个：判断这一次要不要编辑。不调用任何 AI 接口，几秒就结束。

输出一行：
  FULL    今天还没有早间版，需要抓取并编完整版
  UPDATE  有比最近一次编辑更新的抓取（网页上点了 ⤓），需要编增量
  NONE    没事可做，直接结束
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
TZ = ZoneInfo("Europe/Berlin")

now = dt.datetime.now(TZ)
date = now.date().isoformat()
ed_p = ROOT / "data" / "edition.json"
ed = json.loads(ed_p.read_text()) if ed_p.exists() else {}
runs = ed.get("runs", []) if ed.get("date") == date else []
if not runs:
    print("FULL")
else:
    last = max(r["ts"] for r in runs)
    raws = [p for p in (ROOT / "data" / "raw").glob(f"{date}-*.json") if p.stem.split("-")[-1].isdigit()]
    newest = max((dt.datetime.strptime(p.stem, "%Y-%m-%d-%H%M").replace(tzinfo=TZ).timestamp() for p in raws), default=0)
    print("UPDATE" if newest > last else "NONE")
