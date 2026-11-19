"""手动编辑模式第一步：把今天抓到、还没用过的原始条目，连同主线时间线、立场卡、艺术主题和输出格式，
整理成一份编辑材料，交给对话里的 Claude（或定时任务里的 Claude）写 digest。不调用任何 AI 接口。

  python tools/prepare_edit.py [full|update] > brief.txt
输出最后一行会写明用到的 raw 文件，发布时把它传给 manual_publish.py。
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from feed.editor import SCHEMA, UPDATE_SCHEMA, _art, _compact, _stances, _threads  # noqa: E402

DATA = ROOT / "data"
PROFILE = ("住在德国明斯特的中国人，机电一体化学徒（明年转去大众埃姆登），懂德语、粤语；关注劳工与工会、德国和欧洲的左翼运动、"
           "中国政治与社会、香港、AI 和本地部署、艺术与视觉创作；在做左翼 YouTube 频道、德语 Instagram 和历史纪录片。")


def load(p: Path, default):
    return json.loads(p.read_text()) if p.exists() else default


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "full"
    cfg = yaml.safe_load((ROOT / "sources.yaml").read_text())
    now = dt.datetime.now(ZoneInfo(cfg["settings"]["timezone"]))
    date = now.date().isoformat()
    seen = load(DATA / "seen.json", {})
    raws = sorted((DATA / "raw").glob(f"{date}-*.json"))
    if not raws:
        sys.exit("今天还没有抓取过：先触发 fetch 模式")
    items, ids = [], set()
    for p in raws:  # 合并今天所有抓取，去重、去掉已经编过的
        for it in load(p, {}).get("items", []):
            if it["id"] not in seen and it["id"] not in ids:
                ids.add(it["id"])
                items.append(it)
    merged = DATA / "raw" / f"{date}-merged.json"
    merged.write_text(json.dumps({"items": items, "status": load(raws[-1], {}).get("status", [])}, ensure_ascii=False))
    cfg["threads"] = [t for t in cfg.get("threads", []) if not t.get("user")] + load(DATA / "user_threads.json", [])
    out = (f"# 编辑材料 {date}（{'早间完整版' if mode == 'full' else '增量更新'}）\n\n"
           f"## 读者\n{PROFILE}\n\n## 媒体立场卡\n{_stances(cfg)}\n\n"
           f"## 长期主线（id 以 u 开头的是读者自己点了追踪的，优先找后续）\n{_threads(cfg, load(DATA / 'threads.json', {}))}\n\n"
           + _art(cfg, load(DATA / "art.json", []), date)
           + f"## 今天的条目（{len(items)} 条，每行一个 JSON）\n{_compact(items)}\n\n"
           + (SCHEMA if mode == "full" else SCHEMA + "\n\n" + UPDATE_SCHEMA)
           + f"\n\nRAW_FILE={merged.relative_to(ROOT)}\n")
    print(out)


if __name__ == "__main__":
    main()
