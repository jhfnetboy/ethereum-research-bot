# 以太坊研究日报站点

把每天的日报做成卡片式静态页：首页按日期倒序，一天一张卡片；点进去是当天的收集页，按话题列出条目和来源链接。

站点是中英双语：中文是默认语言，在根路径 `/`；英文版在 `/en/` 下，结构完全相同。每页都有语言切换。

页面默认使用相对路径。如需把同一套文件挂在子路径下，可以用 `--base-path` 生成带前缀的绝对路径。

## 目录

- `data/YYYY-MM-DD.json`：一天一份数据
- `assets/`：从新闻来源下载的配图（本地保存，并在 JSON 里记录出处）
- `templates/day.json`：数据模板
- `build.py`：读取 `data/*.json`，生成 `dist/` 纯静态 HTML 和 CSS
- `ingest.py`：从 `../reports/YYYY-MM-DD.md` 生成 JSON，可选下载配图
- 首页和关于页的介绍文案写在 `build.py` 的模板常量里，每次构建都会生成

日报 Markdown 在上一级目录 `../reports/`（中文）和 `../reports/en/`（英文）。

## 数据格式

`data/YYYY-MM-DD.json` 字段（`_en` 是英文版字段，缺省时英文页回退到中文）：

```json
{
  "date": "2026-11-11",
  "keywords": ["关键词一", "关键词二", "关键词三"],
  "keywords_en": ["keyword one", "keyword two", "keyword three"],
  "summary": "两三句关键信息。",
  "summary_en": "Two or three sentences in natural English.",
  "image": {
    "local_path": "assets/2026-11-11.jpg",
    "source_url": "https://example.com/article",
    "credit": "来源媒体或作者",
    "credit_en": "Source outlet or author (optional)"
  },
  "items": [
    {
      "topic": "话题名称",
      "topic_en": "Topic name",
      "title": "条目标题",
      "title_en": "Item title",
      "note": "一句说明。",
      "note_en": "One-sentence note.",
      "url": "https://source.example/path",
      "date": "2026-11-11"
    }
  ]
}
```

说明：

- `keywords` / `keywords_en` 建议 3 到 5 个，首页卡片会显示，详情页标题会同时带两种语言的日期和前 3 个关键词。
- `summary` / `summary_en` 是卡片上的关键信息，也用作各语言页面的 meta description 和 Open Graph 描述。
- `url` 和 `date` 只有一份，两种语言共用，保证链接和日期完全一致。
- `image` 可省略。没有配图，或 `local_path` 指向的文件不存在时，构建脚本统一兜底为站点默认图 `assets/default.jpg`（品牌图，不冒充新闻配图），配图来源显示为“默认配图”。
- `image.local_path` 相对站点根目录，通常是 `assets/` 下的文件。
- `image.source_url` 和 `image.credit` 必须记录真实出处。
- `items` 会按 `topic`（英文页按 `topic_en`）分组出现在详情页。
- 文件名以 `_` 开头的 JSON 会被构建脚本忽略。

## 从当天 reports 生成双语 JSON

每天写两份 Markdown，事实相同、链接相同：

- 中文：`../reports/YYYY-MM-DD.md`
- 英文：`../reports/en/YYYY-MM-DD.md`（自然英文表达，不增加中文版没有的事实，不用 em dash）

中文形状：

```markdown
# 以太坊日报 2026-11-11

关键词：Fusaka、PeerDAS、Based Rollup

摘要：两三句关键信息。

配图来源：https://example.com/article
配图版权：媒体或作者名称

## 今日要点
1. ...

## 重点话题
### 1. 话题名称
- [条目标题](https://source.example/path) 一句说明。

## 其他动态
- [条目标题](https://source.example/path) 一句说明。

来源说明：……
```

英文形状对应：`Keywords:`、`Summary:`、`Image source:`、`Image credit:`，标题用 `## Highlights`、`## Key topics`、`## Other updates`、`## Community`，结尾 `Source notes:`。

在 `site/` 目录下运行：

```bash
python3 ingest.py --report ../reports/2026-11-11.md --fetch-image
```

如果 `../reports/en/2026-11-11.md` 存在，会自动合并成 `_en` 字段：条目按 URL（同一 URL 多次出现时按出现顺序）配对，日期和链接始终取中文版。英文缺条目或多出条目会在 stderr 列出并以退出码 2 结束，方便发现漏译。

只补英文、不重新解析中文（例如中文 JSON 是手工整理的）：

```bash
python3 ingest.py --en-only --en-report ../reports/en/2026-11-11.md --date 2026-11-11
```

`--fetch-image` 会访问「配图来源」页面（或条目里的第一个链接），抓取 `og:image` 或直接的图片地址，压缩后保存到 `assets/YYYY-MM-DD.jpg`，并写入 `local_path`、`source_url`、`credit`。找不到配图就跳过，不要手工补假图。不带 `--fetch-image` 重跑时会保留已下载的配图。

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

## 页面结构（双语、分页与归档）

中文在根路径，英文在 `/en/` 下，结构一致：

| 页面 | 中文 | 英文 |
|---|---|---|
| 首页（最近 7 天，顶部有关于简介） | `/` | `/en/` |
| 更早的日报，每页 7 天 | `/page/2/` … | `/en/page/2/` … |
| 按月归档 | `/archive/` | `/en/archive/` |
| 当天详情 | `/days/YYYY-MM-DD/` | `/en/days/YYYY-MM-DD/` |
| 关于（来源与 jason@idoris.ai） | `/about/` | `/en/about/` |

- `/page/1/` 和 `/en/page/1/` 301 跳回各自首页（`_redirects`）。
- 每页：`<html lang>` 为 `zh-CN` 或 `en`；`canonical` 指向本页；`hreflang` 互指 `zh-CN`、`en`，`x-default` 指向中文；Open Graph 和 Twitter 卡片用本语言的标题和描述，`og:locale` 与 `og:locale:alternate` 互指；详情页带 `og:image` 和 `article:published_time`。
- 标题双语：首页「以太坊研究日报 | Ethereum Research Daily」，详情页含两种语言的日期和关键词。
- 根目录生成 `sitemap.xml`（每个页面的两种语言，附 `xhtml:link` 互指）和 `robots.txt`。公开地址用 `--site-url` 指定，默认 `https://ethereum-research-bot.pages.dev`。

每页条数由 `build.py` 的 `PAGE_SIZE = 7` 控制。纯静态，不需要数据库。按 365 天估算：双语约 1,210 个文件、约 31 MiB（配图两种语言共用，经 `ingest.py` 压缩到宽 1200、JPEG 质量 78），远低于 Cloudflare Pages 的 20,000 文件和单文件 25 MiB 限制。

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

脚本会：把源文件单向镜像到本地构建目录，在那里构建 `dist/`，检查暂存内容里没有 `.env`、密钥或被排除的目录，提交，push 到 `main` 并核对远端 SHA，然后执行
`npx wrangler pages deploy dist --project-name ethereum-research-bot --branch main --commit-hash <SHA>`。
`CLOUDFLARE_API_TOKEN` 只从环境变量读取。

### 在本地目录构建（避免挂载盘卡住）

源文件的权威版本在 store 目录（`site/` 和 `reports/` 所在的挂载盘）。直接在挂载盘上运行 `build.py` 会因为大量小文件写入而卡住，所以 `publish.sh` 每次都这样做：

1. 清空本地构建目录 `BUILD_ROOT`（默认 `/home/box/build/ethereum-research-bot`），再从 store 单向复制 `.gitignore`、`site/`（不含 `dist/`、`docs/`、`workers/`、`__pycache__/`）和 `reports/`。复制有超时（`COPY_TIMEOUT`，默认 300 秒），卡住会直接失败而不是无限等待。
2. 以 `BUILD_ROOT` 作为 git 工作区（`GIT_WORK_TREE`），在 `BUILD_ROOT/site` 里构建，`dist/` 只写在本地。
3. 在本地做 secret 检查、提交、push、核对远端 SHA，再从本地 `dist/` 部署。

因为每次运行都先清空再从 store 复制，提交进 git 的内容就是 store 当时的内容；本地目录只是一次性副本，不要在里面改文件，改了也会在下次运行时被覆盖。脚本从不写回 store。提交后若工作区不干净会在 push 前中止。

日常流程（包括每天 8:30 的日报例行任务）不变：先把当天 Markdown 写进 store 的 `reports/` 和 `reports/en/`，在 store 的 `site/` 下运行 `ingest.py` 生成 JSON 和配图，然后运行：

```bash
bash /cursor/stores/<store-id>/ethereum-research/site/publish.sh "日报 YYYY-MM-DD"
```

不需要手动复制或在 store 里运行 `build.py`。若要换本地目录，设置 `BUILD_ROOT`；它不能是 store 目录本身或其子目录。

git 目录默认在 `/home/box/git/ethereum-research-bot.git`（工作区所在的挂载盘不允许创建 `.git`），可用环境变量 `GIT_DIR` 覆盖。哪些文件进仓库由根目录 `.gitignore` 白名单决定：只有 `site/`（不含 `dist/`、`docs/`、`workers/`）和 `reports/`。

- 博客 `blog.mushroom.cv/ethereum` 的转发由用户自行处理，本项目不涉及。不要在本项目中创建 Worker 或 route，也不要改动博客。
