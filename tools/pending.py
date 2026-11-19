"""定时任务每小时先跑这个：判断这一次要不要编辑。不调用任何 AI 接口，几秒就结束。

输出一行：
  FULL         今天还没有早间版；如果一小时内已经有抓取（本地助手 5:50 触发的），直接用，否则先触发抓取
  FULL_FETCH   今天还没有早间版，也没有近期抓取：先触发抓取再编
  UPDATE       有比最近一次编辑更新的抓取，而且本地要点已经好了（或已经等了 30 分钟以上）
  NONE         没事可做，直接结束（包括新抓取还在等本地要点的情况）
"""
from __future__ import annotations

import datetime as dt
import json
import time
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
TZ = ZoneInfo("Europe/Berlin")

now = dt.datetime.now(TZ)
date = now.date().isoformat()
ed_p = ROOT / "data" / "edition.json"
ed = json.loads(ed_p.read_text()) if ed_p.exists() else {}
runs = ed.get("runs", []) if ed.get("date") == date else []
raws = [p for p in (ROOT / "data" / "raw").glob(f"{date}-*.json") if p.stem.split("-")[-1].isdigit()]
ts = {p: dt.datetime.strptime(p.stem, "%Y-%m-%d-%H%M").replace(tzinfo=TZ).timestamp() for p in raws}
last = max((r["ts"] for r in runs), default=0)
new = [p for p in raws if ts[p] > last]
ready = all((ROOT / "data" / "enrich" / p.name).exists() or time.time() - ts[p] > 30 * 60 for p in new)
if not runs:
    recent = [p for p in raws if time.time() - ts[p] < 60 * 60]
    print("FULL" if recent and ready else "FULL_FETCH")
else:
    print("UPDATE" if new and ready else "NONE")
