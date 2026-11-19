# 信息台本地助手（在你自己的电脑上运行）

用 LM Studio 里的本地模型做体力活：给每条新闻打相关度分、翻译标题、打开原网页抓全文写中文要点，
推到 GitHub 给 Claude 编辑时用。不花订阅或 API 额度。

## 第一次设置（大约 15 分钟）

1. 安装 [Python](https://www.python.org/downloads/)（安装时勾选 "Add python.exe to PATH"）、
   [Git](https://git-scm.com/download/win) 和 [GitHub CLI](https://cli.github.com/)。
2. 打开"命令提示符"，依次运行：
   ```
   gh auth login
   cd %USERPROFILE%\Documents
   gh repo clone prima-bottle/info-feed
   cd info-feed
   pip install -r local\requirements.txt
   ```
   `gh auth login` 选 GitHub.com → HTTPS → 用浏览器登录；之后 git 推送也会用这个登录。
3. 打开 LM Studio：加载一个模型（8GB 显存推荐 Qwen3 8B 或同级别的 Q4 量化版），
   左边点 Developer → 打开 "Start Server"（默认地址 http://localhost:1234）。

## 每天使用

双击 `local\start.bat`，窗口开着就行。它每 3 分钟检查一次：
- GitHub 抓到新内容 → 打分、抓全文、写要点 → 推送（一批大约 10–20 分钟，看模型速度）；
- 5:50 和 11:50 自动触发一次抓取，所以早间版和午间版都能用上全文要点。

电脑关着也没关系：Claude 会照常编，只是没有全文要点。

## 可调的设置

第一次运行后会生成 `local\config.json`：
- `model`：留空就用 LM Studio 当前加载的模型；
- `max_fulltext`：每批最多抓多少篇全文（默认 50，嫌慢就调小）；
- `min_score_fulltext`：相关度几分以上才抓全文（0–3，默认 2）；
- `fetch_times`：自动抓取的时间，不想要就改成 `[]`。
