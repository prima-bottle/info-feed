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
- 地方新闻权重低：「明斯特」板块最多2条简讯，只选影响日常生活的（交通、住房、安全、停工停运）；「地方·」开头的板块合计最多6条简讯，只选社会运动、工人与工会、住房租户、左翼政治相关的，其它地方琐事一律不选。地方新闻一般不进精选，除非是大规模罢工或抗议。
- 「中国·政策」：讲清楚出台了什么文件或部署、政策导向往哪个方向走（收紧还是放松、扶持谁、限制谁）、会影响哪些人；官方定调和独立分析（财新、NPC Observer 等）有差别时要点出来。
- 「中国·社会」：优先劳动者、住房、教育、青年就业、社会事件，写清楚事件本身和背后的结构性问题；官方媒体和独立媒体的说法不同时并列给出。
- 「香港」：同一件事尽量对照建制（大公文汇、RTHK）和独立或境外（HKFP、法广）的说法；关注立法与政治案件、经济民生、社会运动空间的变化。
- 「珠三角」「长三角」：关注地方政策（产业、楼市、就业、外贸）、工厂与劳工、地方人事变动；讲清楚是哪个城市、哪个层级出台、对普通打工者和中小企业意味着什么。两地有可比的政策时可以放在一起对照。各最多5条简讯。
- 带 "thread" 字段的条目是专门为读者追踪的主线搜来的后续报道：只要和主线有关，就一定要写进那条主线的 update；确实无关的忽略。读者追踪的主线有新进展时，优先放进精选。
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
  "videos": [    // 给每个视频写一句中文看点（德语/英语视频尤其要写），最多40个；「推荐·」开头的是按兴趣搜来的，标题党或质量明显差的不写看点
    {"item_id": "...", "hook": "一句话看点"}
  ],
  "german": [    // 从当天德语条目里挑5个实用词或表达
    {"word": "", "meaning": "", "example": "德语例句"}
  ],
  "art": [ {     // 每期4件作品精读（数组，4个对象，字段如下），从创作者的思路出发，服务于读者用 AI 工具做海报和文化符号
    "work": "作品名（中文 + 原名）", "creator": "作者", "year": "年代",
    "wiki": "这件作品或作者在英文维基百科的条目标题，用于配图，不确定就留空",
    "brief": "创作时要解决的问题：谁委托、给谁看、在什么场合、要达到什么效果",
    "decisions": ["创作者的关键决定，每条讲一个：构图/色彩/字体/符号/媒介，以及为什么这么选"],
    "symbols": "用了哪些符号，是怎么借用、改造或反转的",
    "takeaway": ["读者做海报时可以直接借用的手法，具体到可操作"],
    "ai_prompt": "用 AI 图像工具做类似效果的英文提示词示例（写风格、构图、色彩、质感，不要写作者姓名）",
    "ai_tips": "AI 容易做错的地方和修正办法，比如文字、符号变形、风格太甜",
    "item_ids": ["如果和今天「艺术」板块的某条有关，写它的 id，否则空数组"]
  } ],
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
            "id": it["id"], "src": it["source"], **({"thread": it["thread"]} if it.get("thread") else {}), "sec": it["section"], "kind": it["kind"],
            "t": it["title"], "s": it["summary"][:300], **({"img": 1} if it.get("image") else {}),
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
    body = text[start:end + 1]
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        # 模型偶尔会在中文里写没转义的引号，用 json_repair 修一下
        from json_repair import repair_json
        return json.loads(repair_json(body))


UPDATE_SCHEMA = """这是午间增量更新：上午的日报已经发出，下面只有上午之后的新条目。输出格式（JSON）：
{
  "headline": "如果有比上午更重要的新事，用一句话概括；没有就留空字符串",
  "threads": [ 同上午格式，只为有新进展的主线输出，update 只写新进展 ],
  "picks": [ 0到2篇，只有真正重要或和读者直接相关时才写，格式同上 ],
  "briefs": [ 10到25条简讯，格式同上 ],
  "videos": [ 给新视频写一句中文看点，格式同上 ]
}
午间版不要输出 art、german、creative。"""


def _art(cfg: dict, art_history: list[dict], date: str) -> str:
    import datetime as _dt
    themes = cfg.get("art_themes") or []
    if not themes:
        return ""
    week = _dt.date.fromisoformat(date).isocalendar()[1]
    done = "；".join(f'{a["work"]}（{a["creator"]}）' for a in art_history[-40:]) or "无"
    return (f"## 艺术赏析\n本周主题：{themes[week % len(themes)]}\n"
            f"已经讲过的作品（不要重复）：{done}\n"
            "挑4件真实存在、资料可靠的作品，都围绕本周主题但角度不同：不同年代或地区，至少一件当代作品（可以来自今天「艺术」板块），4件之间最好能互相对照。"
            "读者是做政治与文化内容的创作者，用 AI 工具做海报和文化符号，讲解要从创作者的决策出发，少讲艺术史八卦。\n\n")


def edit(items: list[dict], cfg: dict, history: dict, date: str, mode: str = "full",
         likes: list[str] | None = None, art_history: list[dict] | None = None) -> dict:
    profile = os.environ.get("READER_PROFILE", "（未设置）")
    client = anthropic.Anthropic()
    user = (f"日期：{date}\n\n## 媒体立场卡\n{_stances(cfg)}\n\n## 长期主线\n{_threads(cfg, history)}\n\n"
            f"## 今天的条目（每行一个 JSON）\n{_compact(items)}\n\n"
            + (SCHEMA if mode == "full" else SCHEMA + "\n\n" + UPDATE_SCHEMA))
    with client.messages.stream(
        model=MODEL,
        max_tokens=48000,
        system=SYSTEM.format(profile=profile),
        messages=[{"role": "user", "content": user}],
    ) as stream:
        msg = stream.get_final_message()
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    digest = _parse_json(text)
    digest["usage"] = {"input": msg.usage.input_tokens, "output": msg.usage.output_tokens}
    return digest
