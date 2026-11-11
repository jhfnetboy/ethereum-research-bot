# 以太坊研究日报站点

把每天的日报做成卡片式静态页：首页按日期倒序，一天一张卡片；点进去是当天的收集页，按话题列出条目和来源链接。

页面默认使用相对路径。如需把同一套文件挂在子路径下，可以用 `--base-path` 生成带前缀的绝对路径。

## 目录

- `data/YYYY-MM-DD.json`：一天一份数据
- `assets/`：从新闻来源下载的配图（本地保存，并在 JSON 里记录出处）
- `templates/day.json`：数据模板
- `build.py`：读取 `data/*.json`，生成 `dist/` 纯静态 HTML 和 CSS
- `ingest.py`：从 `../reports/YYYY-MM-DD.md` 生成 JSON，可选下载配图
- 首页和关于页的介绍文案写在 `build.py` 的模板常量里，每次构建都会生成

日报 Markdown 在上一级目录 `../reports/`。

## 数据格式

`data/YYYY-MM-DD.json` 字段：

```json
{
  "date": "2026-11-11",
  "keywords": ["关键词一", "关键词二", "关键词三"],
  "summary": "两三句关键信息。",
  "image": {
    "local_path": "assets/2026-11-11.jpg",
    "source_url": "https://example.com/article",
    "credit": "来源媒体或作者"
  },
  "items": [
    {
      "topic": "话题名称",
      "title": "条目标题",
      "note": "一句说明。",
      "url": "https://source.example/path",
      "date": "2026-11-11"
    }
  ]
}
```

说明：

- `keywords` 建议 3 到 5 个，首页卡片会显示。
- `summary` 是卡片上的关键信息，写两三句即可。
- `image` 可省略。没有配图时，构建脚本用简洁占位样式，不会编造或生成假图。
- `image.local_path` 相对站点根目录，通常是 `assets/` 下的文件。
- `image.source_url` 和 `image.credit` 必须记录真实出处。
- `items` 会按 `topic` 分组出现在详情页。
- 文件名以 `_` 开头的 JSON 会被构建脚本忽略。

## 从当天 reports 生成 JSON

建议的 Markdown 形状（字段都可以缺，解析器会尽量识别）：

```markdown
# 以太坊研究日报 2026-11-11

关键词：Fusaka、PeerDAS、Based Rollup

摘要：
两三句关键信息。

配图来源：https://example.com/article
配图版权：媒体或作者名称

## 话题名称

- [条目标题](https://source.example/path)
  一句说明。
```

也支持 YAML front matter（`date`、`keywords`、`summary`、`image.source_url`、`image.credit`）。

在 `site/` 目录下运行：

```bash
python3 ingest.py --report ../reports/2026-11-11.md --fetch-image
```

`--fetch-image` 会访问「配图来源」页面（或条目里的第一个链接），抓取 `og:image` 或直接的图片地址，保存到 `assets/YYYY-MM-DD.ext`，并写入 `local_path`、`source_url`、`credit`。找不到配图就跳过，不要手工补假图。

## 构建

零依赖，只需 Python 3：

```bash
python3 build.py
```

输出在 `dist/`。常用参数：

```bash
python3 build.py --base-path /ethereum
```

不传 `--base-path` 时使用相对路径，这是默认也是推荐的方式。

本地预览：

```bash
python3 -m http.server 8765 --directory dist
```

然后打开 `http://127.0.0.1:8765/`。介绍文案在首页顶部，完整研究来源在 `about/` 关于页，首页有明显入口。

## 页面结构（分页与归档）

- `/`：最近 7 天，按日期倒序，一天一张卡片；顶部是「关于」简介。
- `/page/2/`、`/page/3/` …：更早的日报，每页 7 天，底部有上一页、下一页和页码。`/page/1/` 301 跳回首页（`_redirects`）。
- `/archive/`：按月归档（YYYY年M月，附天数），列出全部日期。
- `/days/YYYY-MM-DD/`：当天收集页，按话题分组，底部有前一天、后一天链接。
- `/about/`：研究来源与联系方式（jason@idoris.ai）。

每页条数由 `build.py` 的 `PAGE_SIZE = 7` 控制。纯静态，不需要数据库。按 365 天估算：约 788 个文件、约 22 MiB（配图经 `ingest.py` 压缩到宽 1200、JPEG 质量 78），本地构建不到 1 秒，远低于 Cloudflare Pages 的 20,000 文件和单文件 25 MiB 限制。

## 部署目标

- GitHub 仓库：`https://github.com/jhfnetboy/ethereum-research-bot`（公开）
- Pages 项目名：`ethereum-research-bot`
- 目标地址：`https://ethereum-research-bot.pages.dev/`
- 顺序：先提交并 push 到 GitHub，push 成功后再用 wrangler 把同一个 commit 部署到 Pages。不使用 Cloudflare Git 集成，也不把 Cloudflare token 放进 GitHub secrets。
- 只发布真实日报数据，不要发布示例数据。

一键发布（在仓库根目录或任意目录运行）：

```bash
bash site/publish.sh "日报 2026-11-12"
bash site/publish.sh --no-deploy "只推 GitHub"
```

脚本会：构建 `dist/`，检查暂存内容里没有 `.env`、密钥或被排除的目录，提交，push 到 `main` 并核对远端 SHA，然后执行
`npx wrangler pages deploy dist --project-name ethereum-research-bot --branch main --commit-hash <SHA>`。
`CLOUDFLARE_API_TOKEN` 只从环境变量读取。

git 目录默认在 `/home/box/git/ethereum-research-bot.git`（工作区所在的挂载盘不允许创建 `.git`），可用环境变量 `GIT_DIR` 覆盖。哪些文件进仓库由根目录 `.gitignore` 白名单决定：只有 `site/`（不含 `dist/`、`docs/`、`workers/`）和 `reports/`。

- 博客 `blog.mushroom.cv/ethereum` 的转发由用户自行处理，本项目不涉及。不要在本项目中创建 Worker 或 route，也不要改动博客。
