"""在你自己电脑上运行的本地助手：用 LM Studio 里的本地模型做"体力活"，结果推到 GitHub，
给 Claude 的定时任务编辑时用。不花任何订阅或 API 额度。

它做三件事：
1. 每当 GitHub 抓到一批新的原始条目（data/raw/日期-时间.json），给每条打相关度分（0–3），
   并把外文标题翻成中文；
2. 对相关度高的文章，从你电脑直接打开原网页抓全文（云端连不上大多数新闻网站，你的电脑可以），
   用中文写三到五句要点；
3. 到了设定的时间（默认 5:50 和 11:50）自动触发一次抓取，让早间版和午间版用上全文要点。

结果写到 data/enrich/同名.json，然后 git push。Claude 编辑时会自动读进去。

用法（在仓库根目录）：
  python local/worker.py            一直运行，每 3 分钟检查一次
  python local/worker.py --once     只检查一次（测试用）
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
import time
import traceback
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
CFG_PATH = Path(__file__).with_name("config.json")
DEFAULT_CFG = {
    "lmstudio_url": "http://localhost:1234/v1",
    "model": "",                      # 留空：用 LM Studio 当前加载的第一个模型
    "max_fulltext": 50,               # 每批最多抓多少篇全文
    "min_score_fulltext": 2,          # 相关度达到几分才抓全文
    "fetch_times": ["05:50", "11:50"],  # 自动触发抓取的时间（柏林时间），不要就留空列表
    "poll_minutes": 3,
    "repo": "prima-bottle/info-feed",
}
READER = ("读者是住在德国明斯特的中国人，机电学徒，关心：劳工与工会、罢工、德国和欧洲的左翼运动与社会运动、住房、移民、"
          "中国政治与社会、香港、珠三角和长三角、中美欧关系与战争、AI 技术和本地部署、艺术与设计。"
          "不关心：体育比赛、名人八卦、犯罪猎奇、股市日常涨跌、促销软文。")


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def load_cfg() -> dict:
    cfg = dict(DEFAULT_CFG)
    if CFG_PATH.exists():
        cfg.update(json.loads(CFG_PATH.read_text(encoding="utf-8")))
    else:
        CFG_PATH.write_text(json.dumps(DEFAULT_CFG, ensure_ascii=False, indent=2), encoding="utf-8")
    return cfg


def git(*args: str, check: bool = True) -> str:
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} 失败：{r.stderr.strip()}")
    return r.stdout


# ---------- 本地模型 ----------

class LLM:
    def __init__(self, cfg: dict):
        self.url = cfg["lmstudio_url"].rstrip("/")
        self.model = cfg["model"] or self._first_model()

    def _first_model(self) -> str:
        r = requests.get(self.url + "/models", timeout=10)
        r.raise_for_status()
        ms = [m["id"] for m in r.json().get("data", []) if "embed" not in m["id"].lower()]
        if not ms:
            raise RuntimeError("LM Studio 里没有加载模型")
        return ms[0]

    def chat(self, prompt: str, max_tokens: int = 800) -> str:
        r = requests.post(self.url + "/chat/completions", timeout=600, json={
            "model": self.model, "temperature": 0.2, "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}]})
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"] or ""
        return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()  # 去掉推理模型的思考过程


def score_batch(llm: LLM, items: list[dict]) -> dict[str, dict]:
    lines = "\n".join(f'{it["id"]} | {it["source"]} | {it["title"][:140]}' for it in items)
    prompt = (f"{READER}\n\n给下面每条新闻按对这位读者的价值打分：3=很重要且相关，2=值得一看，1=一般，0=不相关或琐事。"
              "同时把标题翻译成简洁的中文（已经是中文就照抄）。\n"
              "每行只输出：id|分数|中文标题，不要输出别的。\n\n" + lines)
    out = llm.chat(prompt, max_tokens=60 * len(items) + 200)
    res = {}
    for line in out.splitlines():
        m = re.match(r"\s*([0-9a-f]{10})\s*\|\s*([0-3])\s*\|\s*(.+)", line)
        if m:
            res[m.group(1)] = {"score": int(m.group(2)), "zh_title": m.group(3).strip()}
    return res


# ---------- 全文 ----------

def resolve_link(url: str) -> str:
    if "news.google.com" in url:
        try:
            from googlenewsdecoder import gnewsdecoder
            r = gnewsdecoder(url, interval=1)
            if r.get("status"):
                return r["decoded_url"]
        except Exception:  # noqa: BLE001
            pass
    return url


def fulltext(url: str) -> str:
    import trafilatura
    html = trafilatura.fetch_url(resolve_link(url))
    if not html:
        return ""
    return trafilatura.extract(html, include_comments=False, include_tables=False) or ""


def gist(llm: LLM, it: dict, text: str) -> str:
    prompt = ("用简体中文写三到五句话，概括这篇文章的要点：发生了什么、谁做了什么或说了什么、关键数字和日期。"
              "只根据原文，不评论、不推测，不要加标题或列表符号。\n\n"
              f"标题：{it['title']}\n来源：{it['source']}\n正文：\n{text[:7000]}")
    return llm.chat(prompt, max_tokens=500)


# ---------- 主流程 ----------

def enrich_file(llm: LLM, cfg: dict, raw: Path, out: Path) -> None:
    items = [it for it in json.loads(raw.read_text(encoding="utf-8")).get("items", []) if it.get("kind") == "article"]
    log(f"{raw.name}：{len(items)} 条，开始打分（模型 {llm.model}）")
    res: dict[str, dict] = {}
    for i in range(0, len(items), 25):
        try:
            res.update(score_batch(llm, items[i:i + 25]))
        except Exception as ex:  # noqa: BLE001
            log(f"打分出错：{ex}")
    # 追踪主线搜来的条目一律保留
    for it in items:
        if it.get("thread") and it["id"] in res:
            res[it["id"]]["score"] = max(res[it["id"]]["score"], 2)
    picks = sorted((it for it in items if res.get(it["id"], {}).get("score", 0) >= cfg["min_score_fulltext"]),
                   key=lambda it: -res[it["id"]]["score"])[: cfg["max_fulltext"]]
    log(f"打分完成 {len(res)} 条，抓全文 {len(picks)} 篇")
    done = 0
    for it in picks:
        try:
            text = fulltext(it["link"])
            if len(text) < 400:
                continue
            res[it["id"]]["gist"] = gist(llm, it, text)
            done += 1
        except Exception as ex:  # noqa: BLE001
            log(f"全文失败 {it['source']}：{str(ex)[:80]}")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"model": llm.model, "done": int(time.time()), "items": res}, ensure_ascii=False, indent=0),
                   encoding="utf-8")
    log(f"写好 {out.name}：全文要点 {done} 篇")


def maybe_trigger_fetch(cfg: dict, state: dict) -> None:
    now = dt.datetime.now()
    for t in cfg["fetch_times"]:
        key = now.strftime("%Y-%m-%d ") + t
        h, m = map(int, t.split(":"))
        target = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if key not in state["fired"] and target <= now < target + dt.timedelta(minutes=30):
            r = subprocess.run(["gh", "workflow", "run", "daily.yml", "-R", cfg["repo"], "-f", "mode=fetch", "-f", "force=true"],
                               capture_output=True, text=True)
            state["fired"].append(key)
            log(f"触发抓取 {t}：{'成功' if r.returncode == 0 else '失败 ' + r.stderr.strip()[:120]}")


def tick(cfg: dict, state: dict) -> None:
    maybe_trigger_fetch(cfg, state)
    git("pull", "--rebase", "-q")
    today = dt.date.today().isoformat()
    raws = sorted(p for p in (ROOT / "data" / "raw").glob(f"{today}-*.json") if p.stem.split("-")[-1].isdigit())
    todo = [p for p in raws if not (ROOT / "data" / "enrich" / p.name).exists()]
    if not todo:
        return
    llm = LLM(cfg)
    for raw in todo:
        enrich_file(llm, cfg, raw, ROOT / "data" / "enrich" / raw.name)
    git("add", "data/enrich")
    git("commit", "-q", "-m", f"本地要点 {today}", check=False)
    for _ in range(3):
        try:
            git("pull", "--rebase", "-q")
            git("push", "-q")
            log("已推送")
            return
        except RuntimeError as ex:
            log(str(ex))
            time.sleep(10)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args()
    cfg = load_cfg()
    state = {"fired": []}
    log("本地助手启动。保持这个窗口开着；LM Studio 要开着本地服务器（Developer → Start Server）")
    while True:
        try:
            tick(cfg, state)
        except requests.ConnectionError:
            log("连不上 LM Studio：请打开 LM Studio 的本地服务器")
        except Exception:  # noqa: BLE001
            traceback.print_exc()
        if args.once:
            break
        time.sleep(cfg["poll_minutes"] * 60)


if __name__ == "__main__":
    sys.exit(main())
