"""AI 编辑：把当天抓到的条目交给 Claude，产出精选、主线、简讯、德语词和创作素材。"""
from __future__ import annotations

import json
import os
import re

import anthropic

MODEL = os.environ.get("CLAUDE_MODEL") or "claude-sonnet-5-5"

SYSTEM = """你是一份私人中文信息台的编辑。读者情况：
{profile}

你的任务：从今天抓到的条目里挑选、归纳、解释，产出一份适合手机碎片时间阅读的日报。
原则：
- 全部用简体中文写，人名地名首次出现可附原文。
- 不泛泛而谈：每条都要说清"发生了什么、为什么重要"，宏观新闻要落到读者的生活（for_you），实在没关系就留空，不要硬凑。
- 多方对比时，依据每家媒体的立场卡说明它强调了什么、略过了什么、用什么措辞引导读者。只根据条目里实际出现的内容判断，不要编造某家媒体的观点。
- 不同立场一视同仁地描述，不替读者下政治结论。
- 只能引用下面给出的条目，item_ids 必须是真实存在的 id。
- 只输出 JSON，不要任何其它文字。"""

SCHEMA = """输出格式（JSON）：
{
  "headline": "一句话概括今天最重要的事",
  "threads": [   // 只为今天有新进展的主线输出
    {"id": "主线id", "title": "只有 u 开头的主线需要：简短主线名", "update": ["今天的新进展，每条一句"], "background": "和之前时间线的衔接",
     "perspectives": [{"source": "媒体名", "angle": "它强调了什么、怎么框定"}],
     "outlook": "研判：接下来最可能怎么走", "signals": ["观察信号"], "for_you": "对读者意味着什么",
     "item_ids": ["..."]}
  ],
  "picks": [     // 4到6篇值得细读的精选，优先有深度、多方报道或和读者直接相关的
    {"title": "", "summary": "三到四句", "background": "来龙去脉", "for_you": "", "item_ids": ["..."]}
  ],
  "briefs": [    // 20到40条简讯，每条一两句话，覆盖各板块
    {"section": "板块名", "text": "", "item_id": "..."}
  ],
  "videos": [    // 给每个视频写一句中文看点（德语/英语视频尤其要写），最多25个
    {"item_id": "...", "hook": "一句话看点"}
  ],
  "german": [    // 从当天德语条目里挑5个实用词或表达
    {"word": "", "meaning": "", "example": "德语例句"}
  ],
  "creative": [  // 2到3个适合做视频或德语 Instagram 帖子的选题
    {"idea": "", "why": "", "item_ids": ["..."]}
  ]
}"""


def _compact(items: list[dict]) -> str:
    lines = []
    for it in items:
        if it["kind"] == "bili" and it["section"] in ("B站·影视娱乐", "B站·组织动态"):
            continue
        lines.append(json.dumps({
            "id": it["id"], "src": it["source"], "sec": it["section"], "kind": it["kind"],
            "t": it["title"], "s": it["summary"][:300],
        }, ensure_ascii=False))
    return "\n".join(lines)


def _stances(cfg: dict) -> str:
    return "\n".join(f'- {f["name"]}：{f.get("stance", "")}' for f in cfg.get("feeds", []))


def _threads(cfg: dict, history: dict) -> str:
    out = []
    for t in cfg.get("threads", []):
        past = history.get(t["id"], [])[-6:]
        timeline = "；".join(f'{p["date"]} {" / ".join(p["update"])}' for p in past) or "（还没有记录）"
        extra = f'｜读者点"追踪"时附的原始信息：{t["context"]}' if t.get("context") else ""
        kw = f'｜关键词：{", ".join(t["keywords"])}' if t.get("keywords") else ""
        out.append(f'- id={t["id"]}｜{t["title"]}{kw}｜已有时间线：{timeline}{extra}')
    return "\n".join(out)


def _parse_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start:end + 1])


UPDATE_SCHEMA = """这是午间增量更新：上午的日报已经发出，下面只有上午之后的新条目。输出格式（JSON）：
{
  "headline": "如果有比上午更重要的新事，用一句话概括；没有就留空字符串",
  "threads": [ 同上午格式，只为有新进展的主线输出，update 只写新进展 ],
  "picks": [ 0到2篇，只有真正重要或和读者直接相关时才写，格式同上 ],
  "briefs": [ 10到25条简讯，格式同上 ],
  "videos": [ 给新视频写一句中文看点，格式同上 ]
}"""


def edit(items: list[dict], cfg: dict, history: dict, date: str, mode: str = "full",
         likes: list[str] | None = None) -> dict:
    profile = os.environ.get("READER_PROFILE", "（未设置）")
    client = anthropic.Anthropic()
    user = (f"日期：{date}\n\n## 媒体立场卡\n{_stances(cfg)}\n\n## 长期主线\n{_threads(cfg, history)}\n\n"
            f"## 今天的条目（每行一个 JSON）\n{_compact(items)}\n\n"
            + (SCHEMA if mode == "full" else SCHEMA + "\n\n" + UPDATE_SCHEMA))
    with client.messages.stream(
        model=MODEL,
        max_tokens=32000,
        system=SYSTEM.format(profile=profile),
        messages=[{"role": "user", "content": user}],
    ) as stream:
        msg = stream.get_final_message()
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    digest = _parse_json(text)
    digest["usage"] = {"input": msg.usage.input_tokens, "output": msg.usage.output_tokens}
    return digest
