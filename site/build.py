#!/usr/bin/env python3
"""Build a static card site from data/*.json into dist/.

Default links are relative, so the same dist/ works at the site root
or under a subpath. Blog domain forwarding is handled by the user and
is out of scope for this project.

Optional: python3 build.py --base-path /ethereum
  writes root-absolute links prefixed with /ethereum, for the case
  where files themselves live under that path and no prefix is stripped.
"""

from __future__ import annotations

import argparse
import math
import html
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PAGE_SIZE = 7
SITE_TITLE = "以太坊研究日报"
SITE_LEDE = "按日收录协议、研究和生态的重要动态。"
SITE_INTRO = (
    "本页每天早上根据当天日报自动生成。系统从日报中提取关键词、要点、配图和每条来源链接，"
    "建成卡片并部署到 Cloudflare Pages。每天一张卡片，点开后按话题列出信息和链接。"
    "重点话题深入写，其他动态只简要说明影响和用法。内容覆盖自上一期以来的变化，"
    "每条都附来源和日期，不编造数据。"
)
SITE_INTRO_EMAIL_TEXT = "想建议增加来源，请发邮件到"
SITE_CONTACT_EMAIL = "jason@idoris.ai"
SITE_SOURCES = [
    "Vitalik Buterin 及按相关度筛选的 Top 100 X 账号",
    "ethereum.org 和 @ethereum",
    "Ethereum Magicians",
    "GitHub ethereum/EIPs 和 ethereum/ERCs",
    "ethresear.ch",
    "Vitalik 博客",
    "EF Blog",
    "ethereum/pm ACD 会议",
    "Week in Ethereum News",
    "L2BEAT / ETHBEAT",
    "ultrasound.money",
    "growthepie",
]


def esc(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def format_cn_date(iso: str) -> str:
    dt = datetime.strptime(iso, "%Y-%m-%d")
    return f"{dt.year}年{dt.month}月{dt.day}日"


def format_cn_month(ym: str) -> str:
    dt = datetime.strptime(ym, "%Y-%m")
    return f"{dt.year}年{dt.month}月"


def normalize_base_path(raw: str) -> str:
    path = (raw or "").strip()
    if not path or path == "/":
        return ""
    if not path.startswith("/"):
        path = "/" + path
    return path.rstrip("/")


def root_for(base: str, depth: int) -> str:
    """Prefix that points at the site root from a page `depth` directories deep.

    With a base path every link is root-absolute (/ethereum/...). Without one,
    links stay relative so the same dist/ works anywhere. depth < 0 means
    "served from an unknown path" (404.html) and uses root-absolute links.
    """
    if base:
        return f"{base}/"
    if depth < 0:
        return "/"
    return "./" if depth == 0 else "../" * depth


def load_days(data_dir: Path) -> list[dict]:
    days = []
    if not data_dir.exists():
        return days
    for path in sorted(data_dir.glob("*.json")):
        if path.name.startswith("_"):
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"skip {path.name}: invalid JSON ({exc})", file=sys.stderr)
            continue
        if not isinstance(raw, dict) or not DATE_RE.match(str(raw.get("date") or "")):
            print(f"skip {path.name}: missing or invalid date", file=sys.stderr)
            continue
        raw["_file"] = path.name
        days.append(raw)
    days.sort(key=lambda d: d["date"], reverse=True)
    return days


def item_groups(items: list) -> list[tuple[str, list]]:
    groups: list[tuple[str, list]] = []
    index: dict[str, list] = {}
    for item in items or []:
        if not isinstance(item, dict):
            continue
        topic = (item.get("topic") or "其他").strip() or "其他"
        if topic not in index:
            bucket: list = []
            index[topic] = bucket
            groups.append((topic, bucket))
        index[topic].append(item)
    return groups


def image_name(day: dict) -> str:
    image = day.get("image")
    if not isinstance(image, dict):
        return ""
    local = (image.get("local_path") or "").replace("\\", "/").lstrip("/")
    return Path(local).name if local else ""


def page_href(root: str, n: int) -> str:
    return root if n <= 1 else f"{root}page/{n}/"


def nav_html(root: str, current: str) -> str:
    links = [("home", "目录", root), ("archive", "归档", f"{root}archive/"), ("about", "关于", f"{root}about/")]
    parts = []
    for key, label, href in links:
        cls = ' class="current"' if key == current else ""
        parts.append(f'<a href="{esc(href)}"{cls}>{label}</a>')
    return f'<nav class="site-nav" aria-label="站点导航">{"".join(parts)}</nav>'


def suggest_html() -> str:
    mail = esc(SITE_CONTACT_EMAIL)
    return (
        f'<p class="suggest">{esc(SITE_INTRO_EMAIL_TEXT)} '
        f'<a href="mailto:{mail}">{mail}</a>。</p>'
    )


def intro_block_html(include_sources: bool, about_url: str = "") -> str:
    sources = ""
    if include_sources:
        items = "".join(f"<li>{esc(s)}</li>" for s in SITE_SOURCES)
        sources = f'<h3 id="sources">研究来源</h3><ul class="source-list">{items}</ul>'
    elif about_url:
        sources = (
            f'<p class="sources-link-note">完整研究来源见'
            f'<a href="{esc(about_url)}">关于页</a>。</p>'
        )
    return (
        f'<section class="about-intro">'
        f"<h2>关于本页</h2>"
        f"<p>{esc(SITE_INTRO)}</p>"
        f"{sources}"
        f"{suggest_html()}"
        f"</section>"
    )


def footer_html(root: str) -> str:
    mail = esc(SITE_CONTACT_EMAIL)
    return (
        f'<footer class="site-footer">'
        f"<p>{esc(SITE_TITLE)}"
        f' · <a href="{esc(root)}">目录</a>'
        f' · <a href="{esc(root)}archive/">归档</a>'
        f' · <a href="{esc(root)}about/">关于</a>'
        f' · <a href="mailto:{mail}">{mail}</a></p>'
        f"</footer>"
    )


def head_html(root: str, title: str, description: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(title)}</title>
  <meta name="description" content="{esc(description)}">
  <link rel="stylesheet" href="{esc(root)}styles.css">
</head>"""


def media_block(day: dict, root: str, img_exists: bool, eager: bool = False) -> tuple[str, str, str]:
    name = image_name(day) if img_exists else ""
    image = day.get("image") if isinstance(day.get("image"), dict) else {}
    credit = (image.get("credit") or "").strip()
    source_url = (image.get("source_url") or "").strip()
    alt = f"{format_cn_date(day['date'])} 配图"
    if name:
        loading = "eager" if eager else "lazy"
        fig = (
            f'<div class="media"><img src="{esc(root)}assets/{esc(name)}" alt="{esc(alt)}" '
            f'width="1200" height="675" loading="{loading}" decoding="async"></div>'
        )
    else:
        fig = (
            f'<div class="media placeholder" aria-hidden="true">'
            f'<div class="placeholder-mark"></div>'
            f'<div class="placeholder-date">{esc(format_cn_date(day["date"]))}</div>'
            f"</div>"
        )
    return fig, credit, source_url


def render_card(day: dict, root: str, img_exists: bool, eager: bool) -> str:
    fig, _, _ = media_block(day, root, img_exists, eager)
    keywords = [str(k).strip() for k in (day.get("keywords") or []) if str(k).strip()][:5]
    tags = "".join(f"<li>{esc(k)}</li>" for k in keywords)
    badge = '<p class="badge">示例</p>' if day.get("example") else ""
    href = f"{root}days/{day['date']}/"
    summary = (day.get("summary") or "").strip()
    return f"""
<article class="card">
  <a class="card-link" href="{esc(href)}">
    {fig}
    <div class="card-body">
      {badge}
      <time datetime="{esc(day["date"])}">{esc(format_cn_date(day["date"]))}</time>
      <ul class="tags">{tags}</ul>
      <p class="summary">{esc(summary)}</p>
    </div>
  </a>
</article>
"""


def pager_html(root: str, page: int, total: int) -> str:
    if total <= 1:
        return ""
    parts = []
    if page > 1:
        parts.append(f'<a class="prev" rel="prev" href="{esc(page_href(root, page - 1))}">上一页</a>')
    else:
        parts.append('<span class="prev disabled">上一页</span>')
    shown = sorted({1, total, page - 2, page - 1, page, page + 1, page + 2})
    last = 0
    for n in shown:
        if n < 1 or n > total:
            continue
        if last and n - last > 1:
            parts.append('<span class="gap">…</span>')
        if n == page:
            parts.append(f'<span class="current" aria-current="page">{n}</span>')
        else:
            parts.append(f'<a href="{esc(page_href(root, n))}">{n}</a>')
        last = n
    if page < total:
        parts.append(f'<a class="next" rel="next" href="{esc(page_href(root, page + 1))}">下一页</a>')
    else:
        parts.append('<span class="next disabled">下一页</span>')
    return f'<nav class="pager" aria-label="分页">{"".join(parts)}</nav>'


def render_index_page(days: list[dict], page: int, total: int, root: str, existing: set[str], total_days: int) -> str:
    if days:
        cards = [render_card(d, root, image_name(d) in existing, eager=(page == 1 and i == 0)) for i, d in enumerate(days)]
        main = f'<section class="card-list" aria-label="日报列表">{"".join(cards)}</section>'
    else:
        main = (
            '<section class="empty">'
            "<h2>暂无日报</h2>"
            "<p>把当天的数据文件放进 data 目录后重新构建即可。</p>"
            "</section>"
        )
    if page == 1:
        intro = intro_block_html(include_sources=False, about_url=f"{root}about/")
        status = ""
        title = SITE_TITLE
    else:
        intro = ""
        first, last = days[0]["date"], days[-1]["date"]
        status = (
            f'<p class="page-status">第 {page} / {total} 页 · '
            f"{esc(format_cn_date(last))} 至 {esc(format_cn_date(first))}</p>"
        )
        title = f"第 {page} 页 · {SITE_TITLE}"
    count_note = f'<p class="page-status">共 {total_days} 天，每页 {PAGE_SIZE} 天。更早的日报见分页或<a href="{esc(root)}archive/">按月归档</a>。</p>' if page == 1 and total > 1 else ""
    return f"""{head_html(root, title, SITE_LEDE)}
<body>
  <header class="site-header">
    {nav_html(root, "home")}
    <p class="eyebrow">Ethereum Research Digest</p>
    <h1>{esc(SITE_TITLE)}</h1>
    <p class="lede">{esc(SITE_LEDE)}</p>
  </header>
  {intro}
  <main>
    {status}{count_note}
    {main}
    {pager_html(root, page, total)}
  </main>
  {footer_html(root)}
</body>
</html>
"""


def render_archive(days: list[dict], root: str) -> str:
    months: dict[str, list[dict]] = {}
    for d in days:
        months.setdefault(d["date"][:7], []).append(d)
    sections = []
    for ym in sorted(months, reverse=True):
        rows = []
        for d in months[ym]:
            kws = "、".join(str(k).strip() for k in (d.get("keywords") or [])[:5] if str(k).strip())
            rows.append(
                f'<li><a class="day" href="{esc(root)}days/{esc(d["date"])}/">{esc(format_cn_date(d["date"]))}</a>'
                f'<span class="kw">{esc(kws)}</span></li>'
            )
        sections.append(
            f'<section class="archive-month" id="m{esc(ym)}"><h2>{esc(format_cn_month(ym))}'
            f'<span class="count">{len(months[ym])} 天</span></h2>'
            f'<ul class="archive-list">{"".join(rows)}</ul></section>'
        )
    body = "".join(sections) or "<p>暂无日报。</p>"
    return f"""{head_html(root, f"归档 · {SITE_TITLE}", "按月浏览全部日报。")}
<body>
  <header class="site-header">
    {nav_html(root, "archive")}
    <p class="eyebrow">Ethereum Research Digest</p>
    <h1>按月归档</h1>
    <p class="lede">共 {len(days)} 天日报，按月份倒序排列。</p>
  </header>
  <main class="archive-main">
    {body}
  </main>
  {footer_html(root)}
</body>
</html>
"""


def render_day(day: dict, root: str, img_exists: bool, newer: dict | None, older: dict | None) -> str:
    fig, credit, source_url = media_block(day, root, img_exists, eager=True)
    keywords = [str(k).strip() for k in (day.get("keywords") or []) if str(k).strip()][:5]
    tags = "".join(f"<li>{esc(k)}</li>" for k in keywords)
    badge = '<p class="badge">示例</p>' if day.get("example") else ""
    summary = (day.get("summary") or "").strip()
    groups_html = []
    for topic, items in item_groups(day.get("items") or []):
        entries = []
        for item in items:
            title = (item.get("title") or "").strip() or "未命名条目"
            note = (item.get("note") or "").strip()
            url = (item.get("url") or "").strip()
            item_date = (item.get("date") or day["date"]).strip()
            title_html = (
                f'<h3><a href="{esc(url)}" rel="noopener noreferrer">{esc(title)}</a></h3>'
                if url
                else f"<h3>{esc(title)}</h3>"
            )
            note_html = f"<p class=\"note\">{esc(note)}</p>" if note else ""
            meta_bits = []
            if url:
                meta_bits.append(
                    f'<a class="source" href="{esc(url)}" rel="noopener noreferrer">{esc(url)}</a>'
                )
            if item_date:
                meta_bits.append(f'<time datetime="{esc(item_date)}">{esc(item_date)}</time>')
            meta_html = f'<p class="meta">{" ".join(meta_bits)}</p>' if meta_bits else ""
            entries.append(f'<article class="item">{title_html}{note_html}{meta_html}</article>')
        groups_html.append(
            f'<section class="topic"><h2>{esc(topic)}</h2>{"".join(entries)}</section>'
        )
    topics = "".join(groups_html) or '<p class="empty-items">这一天还没有收录条目。</p>'
    credit_html = ""
    if credit or source_url:
        label = esc(credit or "配图来源")
        if source_url:
            credit_html = (
                f'<p class="credit">配图来源：'
                f'<a href="{esc(source_url)}" rel="noopener noreferrer">{label}</a></p>'
            )
        else:
            credit_html = f'<p class="credit">配图来源：{label}</p>'
    left = (
        f'<a rel="prev" href="{esc(root)}days/{esc(older["date"])}/">← {esc(format_cn_date(older["date"]))}</a>'
        if older else "<span></span>"
    )
    right = (
        f'<a rel="next" href="{esc(root)}days/{esc(newer["date"])}/">{esc(format_cn_date(newer["date"]))} →</a>'
        if newer else "<span></span>"
    )
    day_nav = f'<nav class="day-nav" aria-label="前后日报">{left}{right}</nav>'
    title = f"{format_cn_date(day['date'])} · {SITE_TITLE}"
    return f"""{head_html(root, title, summary or SITE_LEDE)}
<body>
  <header class="day-header">
    {nav_html(root, "day")}
    <a class="back" href="{esc(root)}">返回目录</a>
    {badge}
    <p class="eyebrow">Ethereum Research Digest</p>
    <time datetime="{esc(day["date"])}">{esc(format_cn_date(day["date"]))}</time>
    <h1>{esc(SITE_TITLE)}</h1>
    <ul class="tags">{tags}</ul>
    <p class="lede">{esc(summary)}</p>
  </header>
  <figure class="hero">
    {fig}
    {credit_html}
  </figure>
  <main class="day-main">
    {topics}
    {day_nav}
  </main>
  {footer_html(root)}
</body>
</html>
"""


def render_404(root: str) -> str:
    return f"""{head_html(root, f"页面不存在 · {SITE_TITLE}", SITE_LEDE)}
<body>
  <main class="empty">
    {nav_html(root, "")}
    <h1>页面不存在</h1>
    <p>这条地址没有对应的日报。</p>
    <p><a href="{esc(root)}">回到首页</a> · <a href="{esc(root)}archive/">归档</a> · <a href="{esc(root)}about/">关于</a></p>
  </main>
</body>
</html>
"""


def render_about(root: str) -> str:
    intro = intro_block_html(include_sources=True)
    return f"""{head_html(root, f"关于 · {SITE_TITLE}", SITE_INTRO)}
<body>
  <header class="site-header">
    {nav_html(root, "about")}
    <p class="eyebrow">Ethereum Research Digest</p>
    <h1>关于本页</h1>
    <p class="lede">{esc(SITE_LEDE)}</p>
  </header>
  <main class="about-page">
    {intro}
  </main>
  {footer_html(root)}
</body>
</html>
"""


STYLES = """
:root {
  --bg: #f1eee6;
  --bg-deep: #e7e2d6;
  --paper: #fffcf6;
  --ink: #1c1915;
  --muted: #5c564d;
  --line: #d8d1c4;
  --accent: #143f33;
  --accent-soft: #d9ece4;
  --tag: #ece7dc;
  --tag-ink: #2a3d35;
  --shadow: 0 16px 40px rgba(40, 32, 18, 0.08);
  --radius: 18px;
  --sans: "Noto Sans CJK SC", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", ui-sans-serif, system-ui, sans-serif;
  --serif: "Noto Serif CJK SC", "Songti SC", "STSong", "SimSun", "Times New Roman", serif;
}
* { box-sizing: border-box; }
html { color-scheme: light; }
body {
  margin: 0;
  min-height: 100vh;
  background:
    radial-gradient(1200px 500px at 10% -10%, #fbf8f0 0%, transparent 60%),
    linear-gradient(180deg, var(--bg) 0%, var(--bg-deep) 100%);
  color: var(--ink);
  font-family: var(--sans);
  font-size: 16px;
  line-height: 1.7;
}
a { color: var(--accent); text-decoration-thickness: 1px; text-underline-offset: 0.18em; }
a:hover { color: #0b2b22; }
img { max-width: 100%; display: block; }
.site-header, .day-header, .day-main, .site-footer, .empty, .card-list, .about-intro, .about-page {
  width: min(1080px, calc(100% - 2rem));
  margin-left: auto;
  margin-right: auto;
}
.site-nav {
  display: flex;
  gap: 1.1rem;
  margin: 0 0 1.2rem;
  font-size: 0.92rem;
}
.site-nav a { color: var(--muted); text-decoration: none; }
.site-nav a:hover, .site-nav a.current { color: var(--accent); }
.site-nav a.current { font-weight: 600; }
.about-intro {
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  padding: 1.25rem 1.4rem 1.35rem;
  margin-bottom: 1.8rem;
}
.about-page .about-intro { margin-top: 0; box-shadow: none; background: transparent; border: 0; padding: 0 0 2.5rem; }
.about-intro h2 { font-family: var(--serif); font-size: 1.3rem; margin: 0 0 0.7rem; }
.about-page .about-intro h2 { display: none; }
.about-intro h3 { font-size: 1rem; margin: 1rem 0 0.45rem; }
.about-intro p { margin: 0; max-width: 46rem; }
.about-intro .sources-link-note, .about-intro .suggest { margin-top: 0.85rem; }
.source-list {
  margin: 0;
  padding-left: 1.15rem;
  max-width: 40rem;
}
.source-list li { margin: 0.2rem 0; }
.site-header, .day-header { padding: 2.6rem 0 1.4rem; }
.eyebrow {
  margin: 0 0 0.6rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  font-size: 0.72rem;
  color: var(--muted);
}
.site-header h1, .day-header h1, .day-header time {
  font-family: var(--serif);
  font-weight: 650;
  letter-spacing: 0.02em;
  line-height: 1.25;
  margin: 0;
}
.site-header h1 { font-size: clamp(2rem, 5vw, 3.1rem); }
.day-header time {
  display: block;
  font-size: clamp(2rem, 5vw, 3rem);
  margin: 0.2rem 0 0.4rem;
}
.day-header h1 {
  font-size: 1rem;
  font-family: var(--sans);
  font-weight: 600;
  color: var(--muted);
}
.lede, .summary {
  color: var(--ink);
  max-width: 40rem;
}
.lede { margin: 0.85rem 0 0; font-size: 1.05rem; }
.card-list {
  display: grid;
  gap: 1.4rem;
  padding: 0.4rem 0 3rem;
}
.card {
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  overflow: hidden;
}
.card-link {
  display: grid;
  grid-template-columns: minmax(0, 0.9fr) minmax(0, 1.15fr);
  color: inherit;
  text-decoration: none;
  min-height: 240px;
}
.card-link:hover { color: inherit; }
.card-link:hover .summary { color: var(--accent); }
.media {
  min-height: 220px;
  background: #d9e3dc;
  overflow: hidden;
}
.media img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  aspect-ratio: 16 / 9;
}
.placeholder {
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  gap: 0.8rem;
  padding: 1.2rem;
  background:
    linear-gradient(160deg, #1c3f35 0%, #31574b 42%, #c9b498 100%);
  color: #f6f1e8;
}
.placeholder-mark {
  width: 42px;
  height: 42px;
  border: 2px solid rgba(255, 252, 246, 0.75);
  border-radius: 10px;
  transform: rotate(12deg);
  position: relative;
}
.placeholder-mark::after {
  content: "";
  position: absolute;
  inset: 8px;
  border: 2px solid rgba(255, 252, 246, 0.55);
}
.placeholder-date {
  font-family: var(--serif);
  font-size: 1.25rem;
}
.card-body { padding: 1.25rem 1.35rem 1.4rem; display: flex; flex-direction: column; gap: 0.7rem; }
.card-body time {
  font-family: var(--serif);
  font-size: 1.55rem;
  line-height: 1.2;
}
.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  list-style: none;
  padding: 0;
  margin: 0;
}
.tags li {
  background: var(--tag);
  color: var(--tag-ink);
  border-radius: 999px;
  padding: 0.15rem 0.7rem;
  font-size: 0.82rem;
}
.summary { margin: 0; color: var(--muted); }
.badge {
  align-self: flex-start;
  margin: 0;
  background: var(--accent-soft);
  color: var(--accent);
  font-size: 0.75rem;
  padding: 0.1rem 0.55rem;
  border-radius: 999px;
}
.day-header .back {
  display: inline-block;
  margin-bottom: 1rem;
  color: var(--muted);
}
.hero {
  width: min(1080px, calc(100% - 2rem));
  margin: 0 auto 2rem;
}
.hero .media, .hero img {
  border-radius: 18px;
  width: 100%;
  aspect-ratio: 16 / 9;
  object-fit: cover;
}
.hero .placeholder { min-height: 240px; border-radius: 18px; }
.credit { margin: 0.6rem 0 0; color: var(--muted); font-size: 0.88rem; }
.day-main { padding-bottom: 3rem; display: grid; gap: 2rem; }
.topic h2 {
  font-family: var(--serif);
  font-size: 1.5rem;
  margin: 0 0 0.9rem;
  padding-bottom: 0.45rem;
  border-bottom: 1px solid var(--line);
}
.item + .item { margin-top: 1.15rem; }
.item h3 { margin: 0 0 0.3rem; font-size: 1.08rem; }
.item .note { margin: 0 0 0.35rem; color: var(--ink); }
.item .meta { margin: 0; color: var(--muted); font-size: 0.88rem; word-break: break-all; }
.item .meta time { margin-left: 0.8rem; }
.empty { padding: 3rem 0 5rem; }
.empty h1, .empty h2 { font-family: var(--serif); margin-bottom: 0.6rem; }
.site-footer {
  padding: 0 0 2.5rem;
  color: var(--muted);
  font-size: 0.9rem;
}
@media (max-width: 800px) {
  .card-link { grid-template-columns: 1fr; min-height: 0; }
  .media img, .hero img, .hero .media { aspect-ratio: 16 / 9; min-height: 0; }
  .card-body time { font-size: 1.35rem; }
}
@media (prefers-reduced-motion: reduce) {
  * { scroll-behavior: auto !important; }
}

.site-nav a + a { margin-left: 0.2rem; }
.page-status { margin: 0 0 1rem; color: var(--muted); font-size: 0.95rem; }
.pager {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: 0.45rem;
  padding: 0 0 3rem;
}
.pager a, .pager span {
  display: inline-block;
  min-width: 2.3rem;
  text-align: center;
  padding: 0.35rem 0.75rem;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: var(--paper);
  color: var(--ink);
  text-decoration: none;
  font-size: 0.92rem;
}
.pager a:hover { border-color: var(--accent); color: var(--accent); }
.pager .current { background: var(--accent); border-color: var(--accent); color: #fffcf6; }
.pager .disabled { color: var(--line); }
.pager .gap { border: 0; background: transparent; min-width: 0; padding: 0.35rem 0.2rem; }
.archive-main { padding-bottom: 3rem; display: grid; gap: 2rem; }
.archive-month h2 {
  font-family: var(--serif);
  font-size: 1.45rem;
  margin: 0 0 0.8rem;
  padding-bottom: 0.4rem;
  border-bottom: 1px solid var(--line);
}
.archive-month h2 .count { font-family: var(--sans); font-size: 0.9rem; color: var(--muted); margin-left: 0.6rem; font-weight: 400; }
.archive-list { list-style: none; margin: 0; padding: 0; display: grid; gap: 0.7rem; }
.archive-list li { display: grid; grid-template-columns: 7.5rem minmax(0, 1fr); gap: 0.8rem; align-items: baseline; }
.archive-list a.day { font-family: var(--serif); font-weight: 600; }
.archive-list .kw { color: var(--muted); font-size: 0.92rem; }
.day-nav { display: flex; justify-content: space-between; gap: 1rem; padding: 0 0 2rem; font-size: 0.95rem; }
@media (max-width: 600px) { .archive-list li { grid-template-columns: 1fr; gap: 0.1rem; } }
"""


def copy_images(days: list[dict], site_root: Path, dist_assets: Path) -> set[str]:
    dist_assets.mkdir(parents=True, exist_ok=True)
    present: set[str] = set()
    for day in days:
        image = day.get("image") if isinstance(day.get("image"), dict) else None
        if not image:
            continue
        local = (image.get("local_path") or "").replace("\\", "/").lstrip("/")
        if not local:
            continue
        src = site_root / local
        if not src.is_file():
            alt = site_root / "assets" / Path(local).name
            src = alt if alt.is_file() else src
        if not src.is_file():
            print(f"warning: image not found for {day['date']}: {local}", file=sys.stderr)
            continue
        dest = dist_assets / src.name
        shutil.copyfile(src, dest)
        present.add(src.name)
    return present


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> int:
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Build the Ethereum daily digest static site.")
    parser.add_argument("--data-dir", default=str(here / "data"))
    parser.add_argument("--out-dir", default=str(here / "dist"))
    parser.add_argument(
        "--base-path",
        default="",
        help="Optional root-absolute prefix such as /ethereum. Leave empty (default) to use relative links.",
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    out_dir = Path(args.out_dir)
    base = normalize_base_path(args.base_path)

    days = load_days(data_dir)

    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    existing = copy_images(days, here, out_dir / "assets")
    write(out_dir / "styles.css", STYLES.strip() + "\n")

    total_pages = max(1, math.ceil(len(days) / PAGE_SIZE))
    for page in range(1, total_pages + 1):
        chunk = days[(page - 1) * PAGE_SIZE : page * PAGE_SIZE]
        if page == 1:
            write(out_dir / "index.html", render_index_page(chunk, 1, total_pages, root_for(base, 0), existing, len(days)))
        else:
            write(
                out_dir / "page" / str(page) / "index.html",
                render_index_page(chunk, page, total_pages, root_for(base, 2), existing, len(days)),
            )
    write(out_dir / "archive" / "index.html", render_archive(days, root_for(base, 1)))
    write(out_dir / "about" / "index.html", render_about(root_for(base, 1)))
    write(out_dir / "404.html", render_404(root_for(base, -1)))
    write(
        out_dir / "_redirects",
        "/page/1 / 301\n/page/1/ / 301\n",
    )
    for i, day in enumerate(days):
        newer = days[i - 1] if i > 0 else None
        older = days[i + 1] if i + 1 < len(days) else None
        write(
            out_dir / "days" / day["date"] / "index.html",
            render_day(day, root_for(base, 2), image_name(day) in existing, newer, older),
        )

    files = sum(1 for p in out_dir.rglob("*") if p.is_file())
    size = sum(p.stat().st_size for p in out_dir.rglob("*") if p.is_file())
    print(f"built {len(days)} day(s), {total_pages} index page(s), {files} file(s), {size / 1024:.0f} KiB -> {out_dir}")
    print(f"base path: {base or 'relative links'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
