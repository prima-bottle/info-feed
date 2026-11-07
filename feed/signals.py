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
