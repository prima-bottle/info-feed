"""读取你在网页上点的"追踪"和"赞"。

点按钮时会打开一个预填好的 GitHub Issue，提交后就存在仓库的 Issues 里：
  标题以「追踪：」开头 → 变成一条新主线，以后每次推送接着写后续
  标题以「赞：」开头   → 同类话题以后更优先入选
想停止追踪或取消赞，在 GitHub 上把那个 Issue 关掉（Close）就行。
"""
from __future__ import annotations

import os

import requests

TRACK, LIKE = "追踪：", "赞："
MAX_TRACKED, MAX_LIKES = 10, 40


def load_signals() -> tuple[list[dict], list[str]]:
    repo, token = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_TOKEN")
    if not repo:
        return [], []
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    issues = []
    for page in (1, 2):
        r = requests.get(f"https://api.github.com/repos/{repo}/issues",
                         params={"state": "open", "per_page": 100, "page": page},
                         headers=headers, timeout=20)
        r.raise_for_status()
        batch = [i for i in r.json() if "pull_request" not in i]
        issues += batch
        if len(batch) < 100:
            break

    owner = repo.split("/")[0].lower()
    issues = [i for i in issues if (i.get("user") or {}).get("login", "").lower() == owner]
    tracked, likes = [], []
    for i in sorted(issues, key=lambda x: x["number"]):
        title = (i.get("title") or "").strip()
        body = (i.get("body") or "").strip()[:800]
        if title.startswith(TRACK):
            tracked.append({"id": f"u{i['number']}", "title": title[len(TRACK):].strip()[:60],
                            "keywords": [], "context": body, "user": True})
        elif title.startswith(LIKE):
            likes.append(title[len(LIKE):].strip() + (f"（{body[:200]}）" if body else ""))
    return tracked[-MAX_TRACKED:], likes[-MAX_LIKES:]


def ensure_queries(tracked: list[dict], likes: list[str], data_dir) -> dict:
    """给每条追踪和每个赞生成搜索词（新闻 + 视频），结果缓存，只为新出现的条目调用一次 AI。"""
    import hashlib
    import json
    from pathlib import Path

    cache_file = Path(data_dir) / "signal_queries.json"
    cache = json.loads(cache_file.read_text()) if cache_file.exists() else {}
    want = {t["id"]: f'{t["title"]}｜{t.get("context", "")[:300]}' for t in tracked}
    for x in likes:
        want["l" + hashlib.sha1(x.encode()).hexdigest()[:8]] = x[:300]
    missing = {k: v for k, v in want.items() if k not in cache}
    if missing:
        import anthropic
        prompt = ("下面是读者在新闻页上点了「追踪」或「赞」的条目。为每条生成搜索词，用来之后自动去找后续新闻和相关视频。\n"
                  "要求：news 给 2 个新闻搜索词，3到6个词的关键词式短语，用最可能有报道的语言（德国的事用德语，中国的事用中文，国际的事用英语）；"
                  "video 给 1 个 YouTube 搜索词，偏解读或纪录片。lang 只能是 de、en、zh。\n"
                  '只输出 JSON：{"条目id": {"news": [{"q": "...", "lang": "de"}], "video": {"q": "...", "lang": "de"}}}\n\n'
                  + "\n".join(f"- {k}：{v}" for k, v in missing.items()))
        msg = anthropic.Anthropic().messages.create(
            model=os.environ.get("CLAUDE_SMALL_MODEL") or "claude-haiku-5-5", max_tokens=4000,
            messages=[{"role": "user", "content": prompt}])
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        from feed.editor import _parse_json
        try:
            cache.update({k: v for k, v in _parse_json(text).items() if k in missing})
        except Exception:  # noqa: BLE001
            pass
    cache = {k: v for k, v in cache.items() if k in want}
    cache_file.write_text(json.dumps(cache, ensure_ascii=False, indent=1))
    titles = {t["id"]: t["title"] for t in tracked}
    news = [{"thread": k, "title": titles[k], **q} for k, v in cache.items() if k in titles for q in v.get("news", [])[:2]]
    videos = [v["video"] for v in cache.values() if isinstance(v.get("video"), dict) and v["video"].get("q")]
    return {"news": news, "videos": videos}
