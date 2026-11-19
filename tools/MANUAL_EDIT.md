# 手动编辑流程（API 额度用完时，由对话或定时任务里的 Claude 完成）

1. 抓取：GitHub Actions 的 daily.yml 用 fetch 模式只抓原始条目，存到 `data/raw/日期-时间.json`。
   需要新抓时：
   `echo '{"ref":"main","inputs":{"mode":"fetch","force":"true"}}' | gh api -X POST repos/prima-bottle/info-feed/actions/workflows/daily.yml/dispatches --input -`
   然后 `git pull`，等 `data/raw/` 里出现今天的新文件（通常 2–4 分钟）。
2. 整理材料：`python tools/prepare_edit.py full > brief.txt`（当天已有早间版就用 `update`）。
   它会合并今天所有抓取、去掉编过的，写出 `data/raw/日期-merged.json`，最后一行是 RAW_FILE。
3. 写 digest：按 brief.txt 里的规则和 JSON 格式写一份 digest.json。
   - item_ids / item_id 只能用 brief 里出现过的 id；写完用脚本核对。
   - 只根据条目标题和摘要写，不要编造细节；拿不准的写"据报道"或不写。
   - 艺术 10 件，每件都要填 `wiki`（英文维基条目标题）和 `en`（英文作品名 + 作者），页面靠它们配图；不要和已讲过的重复。
   - 简讯 20–40 条；精选 4–6 篇；主线只写有新进展的。
4. 发布：`python tools/manual_publish.py <RAW_FILE> digest.json full|update`
5. 提交推送：`git add docs data && git commit -m "日期 手动编辑版" && git pull --rebase && git push`
