#!/usr/bin/env python3
"""Build a bilingual static card site from data/*.json into dist/.

Chinese is the default language at the site root (/). English pages live
under /en/ with the same structure. Every page links to its counterpart
(language switch, hreflang), and the build writes sitemap.xml and robots.txt.

Default links are relative, so the same dist/ works at the site root or under
a subpath. Absolute URLs (canonical, hreflang, Open Graph, sitemap) use
--site-url. Blog domain forwarding is handled by the user and is out of scope.

Optional: python3 build.py --base-path /ethereum
"""

from __future__ import annotations

import argparse
import html
import json
import math
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PAGE_SIZE = 7
DEFAULT_SITE_URL = "https://ethereum-research-bot.pages.dev"
SITE_CONTACT_EMAIL = "jason@idoris.ai"
LANG_ORDER = ("zh", "en")

STRINGS = {
    "zh": {
        "html_lang": "zh-CN",
        "hreflang": "zh-CN",
        "og_locale": "zh_CN",
        "prefix": "",
        "site_title": "以太坊研究日报",
        "brand": "以太坊研究日报 | Ethereum Research Daily",
        "brand_short": "以太坊研究日报 Ethereum Research Daily",
        "eyebrow": "Ethereum Research Daily",
        "lede": "按日收录以太坊协议、研究和生态的重要动态。",
        "intro": (
            "本页每天早上根据当天日报自动生成。系统从日报中提取关键词、要点、配图和每条来源链接，"
            "建成卡片并部署到 Cloudflare Pages。每天一张卡片，点开后按话题列出信息和链接。"
            "重点话题深入写，其他动态只简要说明影响和用法。内容覆盖自上一期以来的变化，"
            "每条都附来源和日期，不编造数据。"
        ),
        "email_text": "想建议增加来源，请发邮件到",
        "sentence_end": "。",
        "sources_title": "研究来源",
        "sources": [
            "Vitalik Buterin 及按相关度筛选的 Top 100 X 账号",
            "ethereum.org 和 @ethereum",
            "Ethereum Magicians",
            "GitHub ethereum/EIPs 和 ethereum/ERCs",
            "ethresear.ch",
            "Vitalik 博客",
            "EF Blog",
            "ethereum/pm ACD 会议",
            "Week in Ethereum News（及其后继 Ethereal news）",
            "L2BEAT / ETHBEAT",
            "ultrasound.money",
            "growthepie",
        ],
        "about_heading": "关于本站",
        "sources_link_pre": "完整研究来源见",
        "sources_link": "关于本站",
        "nav_label": "站点导航",
        "nav_home": "目录",
        "nav_archive": "归档",
        "nav_about": "关于",
        "switch_label": "English",
        "switch_title": "Read this page in English",
        "list_label": "日报列表",
        "empty_title": "暂无日报",
        "empty_text": "把当天的数据文件放进 data 目录后重新构建即可。",
        "pager_label": "分页",
        "prev": "上一页",
        "next": "下一页",
        "page_status": "第 {page} / {total} 页 · {start} 至 {end}",
        "page_title": "第 {page} 页",
        "count_note": "共 {days} 天，每页 {size} 天。更早的日报见分页或<a href=\"{href}\">按月归档</a>。",
        "archive_title": "按月归档",
        "archive_lede": "共 {days} 天日报，按月份倒序排列。",
        "archive_desc": "按月浏览以太坊研究日报的全部日期和关键词。",
        "archive_count": "{n} 天",
        "archive_empty": "暂无日报。",
        "back": "返回目录",
        "image_alt": "{date} 配图",
        "credit_label": "配图来源：",
        "default_credit": "默认配图（当日无可用真实配图）",
        "credit_fallback": "配图来源",
        "untitled": "未命名条目",
        "other_topic": "其他",
        "no_items": "这一天还没有收录条目。",
        "day_nav_label": "前后日报",
        "kw_sep": "、",
        "example": "示例",
        "article_entry_pre": "专题文章：",
        "research_heading": "我的账户研究",
        "research_zh": "中文版",
        "research_en": "English",
        "research_label": "账户研究文章链接",
        "archive_jump": "跳到月份",
        "article_kicker": "专题",
        "article_back": "返回目录",
        "cite_day": "日报",
        "cite_src": "原文",
        "diagram_title": "理想以太坊账户的组件结构图（状态截至 2026-11-11）",
        "diagram_desc": "从用户往下分六层：钱包与交互、交易格式、验证与签名、执行 nonce 与付费、权限恢复与委托安全、隐私与抗审查。每层列出对应标准，实线框为已上线、在用或已排期，虚线框为候选或提议中。",
        "checked": "2026-11-11 核对",
    },
    "en": {
        "html_lang": "en",
        "hreflang": "en",
        "og_locale": "en_US",
        "prefix": "en/",
        "site_title": "Ethereum Research Daily",
        "brand": "Ethereum Research Daily",
        "brand_short": "Ethereum Research Daily",
        "eyebrow": "Ethereum Research Daily",
        "lede": "A daily record of what changed in Ethereum protocol work, research and the ecosystem.",
        "intro": (
            "This site is rebuilt every morning from that day's report. The pipeline pulls out the keywords, "
            "highlights, an image and every source link, turns them into a card and deploys it to Cloudflare Pages. "
            "There is one card per day; open it to see the items and links grouped by topic. Priority topics get "
            "in-depth coverage, and everything else is a short note on what it means for users and how to use it. "
            "Each issue covers what changed since the previous one, every item carries its source and date, "
            "and nothing is made up."
        ),
        "email_text": "To suggest a source, email",
        "sentence_end": ".",
        "sources_title": "Sources",
        "sources": [
            "Vitalik Buterin and a relevance-ranked list of the top 100 X accounts",
            "ethereum.org and @ethereum",
            "Ethereum Magicians",
            "GitHub ethereum/EIPs and ethereum/ERCs",
            "ethresear.ch",
            "Vitalik's blog",
            "EF Blog",
            "ethereum/pm All Core Devs calls",
            "Week in Ethereum News (and its successor, Ethereal news)",
            "L2BEAT / ETHBEAT",
            "ultrasound.money",
            "growthepie",
        ],
        "about_heading": "About this site",
        "sources_link_pre": "The full list of sources is on the ",
        "sources_link": "About this site page",
        "nav_label": "Site navigation",
        "nav_home": "Home",
        "nav_archive": "Archive",
        "nav_about": "About",
        "switch_label": "中文",
        "switch_title": "Read the Chinese version",
        "list_label": "Daily reports",
        "empty_title": "No reports yet",
        "empty_text": "Add a day's data file to the data directory and rebuild.",
        "pager_label": "Pagination",
        "prev": "Previous",
        "next": "Next",
        "page_status": "Page {page} of {total} · {start} to {end}",
        "page_title": "Page {page}",
        "count_note": "{days} days in total, {size} per page. Older reports are on the following pages and in the <a href=\"{href}\">monthly archive</a>.",
        "archive_title": "Monthly archive",
        "archive_lede": "{days} daily reports, newest month first.",
        "archive_desc": "Browse every Ethereum Research Daily report by month, with its keywords.",
        "archive_count": "{n} days",
        "archive_empty": "No reports yet.",
        "back": "Back to all reports",
        "image_alt": "Image for {date}",
        "credit_label": "Image: ",
        "default_credit": "Default image (no real image available for this day)",
        "credit_fallback": "Image source",
        "untitled": "Untitled item",
        "other_topic": "Other",
        "no_items": "No items have been recorded for this day yet.",
        "day_nav_label": "Previous and next reports",
        "kw_sep": ", ",
        "example": "Example",
        "article_entry_pre": "Feature article: ",
        "research_heading": "My account research",
        "research_zh": "Chinese",
        "research_en": "English",
        "research_label": "Account research article links",
        "archive_jump": "Jump to month",
        "article_kicker": "Feature",
        "article_back": "Back to all reports",
        "cite_day": "daily",
        "cite_src": "source",
        "diagram_title": "Component diagram of the ideal Ethereum account (status as of 2026-11-11)",
        "diagram_desc": "Six layers below the user: wallet, transaction format, signatures, nonces and fees, keys and delegation, privacy and anti-censorship. Each layer lists its standards; solid boxes are live, in use, or Scheduled for Inclusion, dashed boxes are candidates or proposals.",
        "checked": "checked 2026-11-11",
    },
}

ARTICLES = {
    "ideal-account": {
        "published": "2026-11-11",
        "zh": {
            "title": "理想的以太坊账户：功能、标准与评估",
            "lede": "基于本站一年日报（2025-11-12 至 2026-11-11）的资料，梳理一个具备关键功能的以太坊账户该如何构建、各组件遵守哪些标准，以及如何评估它的安全与隐私。",
            "keywords": ["账户抽象", "EIP-8141", "EIP-7702", "ERC-4337", "EIP-8250", "EIP-8272", "隐私", "后量子"],
        },
        "en": {
            "title": "The ideal Ethereum account: features, standards and how to evaluate them",
            "lede": "Drawing on a year of this site's daily reports (2025-11-12 to 2026-11-11), we lay out how to build an Ethereum account with every key feature, which standards each component follows, and how to judge its security and privacy.",
            "keywords": ["account abstraction", "EIP-8141", "EIP-7702", "ERC-4337", "EIP-8250", "EIP-8272", "privacy", "post-quantum"],
        },
    },
}

EN_MONTHS = ["January", "February", "March", "April", "May", "June", "July",
             "August", "September", "October", "November", "December"]


def esc(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def fmt_date(iso: str, lang: str) -> str:
    dt = datetime.strptime(iso, "%Y-%m-%d")
    if lang == "en":
        return f"{EN_MONTHS[dt.month - 1]} {dt.day}, {dt.year}"
    return f"{dt.year}年{dt.month}月{dt.day}日"


def fmt_month(ym: str, lang: str) -> str:
    dt = datetime.strptime(ym, "%Y-%m")
    if lang == "en":
        return f"{EN_MONTHS[dt.month - 1]} {dt.year}"
    return f"{dt.year}年{dt.month}月"


def tr(obj: dict, key: str, lang: str, default=""):
    """Field in the requested language, falling back to the Chinese field."""
    if not isinstance(obj, dict):
        return default
    if lang == "en":
        val = obj.get(f"{key}_en")
        if val:
            return val
    val = obj.get(key)
    return val if val else default


def day_keywords(day: dict, lang: str, limit: int = 5) -> list[str]:
    raw = tr(day, "keywords", lang, []) or []
    return [str(k).strip() for k in raw if str(k).strip()][:limit]


def normalize_base_path(raw: str) -> str:
    path = (raw or "").strip()
    if not path or path == "/":
        return ""
    if not path.startswith("/"):
        path = "/" + path
    return path.rstrip("/")


class Ctx:
    """Where a page sits: its language, its path inside the language tree,
    and how to reach the site root and the language root from it."""

    def __init__(self, lang: str, path: str, base: str, site_url: str):
        self.lang = lang
        self.s = STRINGS[lang]
        self.path = path  # e.g. "", "page/2/", "days/2026-11-10/"
        self.base = base
        self.site_url = site_url.rstrip("/") + base
        depth = path.count("/") + (1 if lang == "en" else 0)
        if base:
            self.root = f"{base}/"
        elif depth < 0:
            self.root = "/"
        else:
            self.root = "./" if depth == 0 else "../" * depth
        self.lroot = self.root + self.s["prefix"]

    def href(self, path: str) -> str:
        return self.lroot + path

    def other_href(self, lang: str) -> str:
        return self.root + STRINGS[lang]["prefix"] + self.path

    def abs_url(self, lang: str | None = None, path: str | None = None) -> str:
        lang = lang or self.lang
        path = self.path if path is None else path
        return f"{self.site_url}/{STRINGS[lang]['prefix']}{path}"


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


def item_groups(items: list, lang: str) -> list[tuple[str, list]]:
    groups: list[tuple[str, list]] = []
    index: dict[str, list] = {}
    other = STRINGS[lang]["other_topic"]
    for item in items or []:
        if not isinstance(item, dict):
            continue
        topic = (tr(item, "topic", lang) or other).strip() or other
        if topic not in index:
            bucket: list = []
            index[topic] = bucket
            groups.append((topic, bucket))
        index[topic].append(item)
    return groups


DEFAULT_IMAGE = "default.jpg"


def image_name(day: dict) -> str:
    if day.get("_default_image"):
        return DEFAULT_IMAGE
    image = day.get("image")
    if not isinstance(image, dict):
        return ""
    local = (image.get("local_path") or "").replace("\\", "/").lstrip("/")
    return Path(local).name if local else ""


def page_path(n: int) -> str:
    return "" if n <= 1 else f"page/{n}/"


def nav_html(c: Ctx, current: str) -> str:
    s = c.s
    links = [("home", s["nav_home"], c.href("")), ("archive", s["nav_archive"], c.href("archive/")),
             ("about", s["nav_about"], c.href("about/"))]
    parts = []
    for key, label, href in links:
        cls = ' class="current"' if key == current else ""
        parts.append(f'<a href="{esc(href)}"{cls}>{esc(label)}</a>')
    other = "en" if c.lang == "zh" else "zh"
    parts.append(
        f'<a class="lang-switch" href="{esc(c.other_href(other))}" hreflang="{STRINGS[other]["hreflang"]}" '
        f'lang="{STRINGS[other]["html_lang"]}" title="{esc(s["switch_title"])}">{esc(s["switch_label"])}</a>'
    )
    return f'<nav class="site-nav" aria-label="{esc(s["nav_label"])}">{"".join(parts)}</nav>'


def suggest_html(c: Ctx) -> str:
    mail = esc(SITE_CONTACT_EMAIL)
    return f'<p class="suggest">{esc(c.s["email_text"])} <a href="mailto:{mail}">{mail}</a>{c.s["sentence_end"]}</p>'


def intro_block_html(c: Ctx, include_sources: bool) -> str:
    s = c.s
    if include_sources:
        items = "".join(f"<li>{esc(x)}</li>" for x in s["sources"])
        sources = f'<h3 id="sources">{esc(s["sources_title"])}</h3><ul class="source-list">{items}</ul>'
    else:
        sources = (
            f'<p class="sources-link-note">{esc(s["sources_link_pre"])}'
            f'<a href="{esc(c.href("about/"))}">{esc(s["sources_link"])}</a>{s["sentence_end"]}</p>'
        )
    main = (
        f'<h2>{esc(s["about_heading"])}</h2>'
        f"<p>{esc(s['intro'])}</p>{article_entry_html(c)}{sources}{suggest_html(c)}"
    )
    if include_sources:
        return f'<section class="about-intro">{main}</section>'
    return (
        f'<section class="about-intro has-aside"><div class="about-main">{main}</div>'
        f"{research_aside_html(c)}</section>"
    )


def research_aside_html(c: Ctx) -> str:
    s = c.s
    items = []
    for slug, meta in ARTICLES.items():
        links = []
        for lang, label in (("zh", s["research_zh"]), ("en", STRINGS["zh"]["research_en"])):
            path = f'/{STRINGS[lang]["prefix"]}{slug}/'
            href = c.root + STRINGS[lang]["prefix"] + slug + "/"
            cur = ' aria-current="true"' if lang == c.lang else ""
            links.append(
                f'<a class="research-link" href="{esc(href)}" hreflang="{STRINGS[lang]["hreflang"]}" '
                f'lang="{STRINGS[lang]["html_lang"]}"{cur}><span class="rl-lang">{esc(label)}</span>'
                f'<span class="rl-path">{esc(path)}</span></a>'
            )
        items.append(
            f'<p class="research-title">{esc(meta[c.lang]["title"])}</p>'
            f'<div class="research-links">{"".join(links)}</div>'
        )
    return (
        f'<aside class="research-aside" aria-label="{esc(s["research_label"])}">'
        f'<h2>{esc(s["research_heading"])}</h2>{"".join(items)}</aside>'
    )


def article_entry_html(c: Ctx) -> str:
    links = "".join(
        f'<a href="{esc(c.href(slug + "/"))}">{esc(meta[c.lang]["title"])}</a>' for slug, meta in ARTICLES.items()
    )
    return f'<p class="article-entry">{esc(c.s["article_entry_pre"])}{links}{c.s["sentence_end"]}</p>'


def footer_html(c: Ctx) -> str:
    s = c.s
    mail = esc(SITE_CONTACT_EMAIL)
    other = "en" if c.lang == "zh" else "zh"
    return (
        f'<footer class="site-footer"><p>{esc(s["site_title"])}'
        f' · <a href="{esc(c.href(""))}">{esc(s["nav_home"])}</a>'
        f' · <a href="{esc(c.href("archive/"))}">{esc(s["nav_archive"])}</a>'
        f' · <a href="{esc(c.href("about/"))}">{esc(s["nav_about"])}</a>'
        f' · <a href="{esc(c.other_href(other))}" hreflang="{STRINGS[other]["hreflang"]}">{esc(s["switch_label"])}</a>'
        f' · <a href="mailto:{mail}">{mail}</a></p></footer>'
    )


def head_html(c: Ctx, title: str, description: str, *, og_type: str = "website",
              image_abs: str = "", keywords: list[str] | None = None, published: str = "") -> str:
    s = c.s
    desc = re.sub(r"\s+", " ", description or s["lede"]).strip()
    if len(desc) > 300:
        desc = desc[:297].rstrip() + "..."
    alternates = "".join(
        f'\n  <link rel="alternate" hreflang="{STRINGS[l]["hreflang"]}" href="{esc(c.abs_url(l))}">'
        for l in LANG_ORDER
    )
    alternates += f'\n  <link rel="alternate" hreflang="x-default" href="{esc(c.abs_url("zh"))}">'
    other = "en" if c.lang == "zh" else "zh"
    og = [
        f'<meta property="og:type" content="{og_type}">',
        f'<meta property="og:site_name" content="{esc(s["brand"])}">',
        f'<meta property="og:title" content="{esc(title)}">',
        f'<meta property="og:description" content="{esc(desc)}">',
        f'<meta property="og:url" content="{esc(c.abs_url())}">',
        f'<meta property="og:locale" content="{s["og_locale"]}">',
        f'<meta property="og:locale:alternate" content="{STRINGS[other]["og_locale"]}">',
        f'<meta name="twitter:card" content="{"summary_large_image" if image_abs else "summary"}">',
        f'<meta name="twitter:title" content="{esc(title)}">',
        f'<meta name="twitter:description" content="{esc(desc)}">',
    ]
    if image_abs:
        og.append(f'<meta property="og:image" content="{esc(image_abs)}">')
        og.append(f'<meta name="twitter:image" content="{esc(image_abs)}">')
    if published:
        og.append(f'<meta property="article:published_time" content="{esc(published)}">')
    kw = f'\n  <meta name="keywords" content="{esc(", ".join(keywords))}">' if keywords else ""
    og_html = "".join(f"\n  {x}" for x in og)
    return f"""<!DOCTYPE html>
<html lang="{s['html_lang']}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(title)}</title>
  <meta name="description" content="{esc(desc)}">{kw}
  <link rel="canonical" href="{esc(c.abs_url())}">{alternates}{og_html}
  <link rel="sitemap" type="application/xml" href="{esc(c.root)}sitemap.xml">
  <link rel="stylesheet" href="{esc(c.root)}styles.css">
</head>"""


def image_abs(c: Ctx, day: dict | None, existing: set[str]) -> str:
    if not day:
        return ""
    name = image_name(day)
    return f"{c.site_url}/assets/{name}" if name and name in existing else ""


def media_block(c: Ctx, day: dict, img_exists: bool, eager: bool = False) -> tuple[str, str, str]:
    name = image_name(day) if img_exists else ""
    image = day.get("image") if isinstance(day.get("image"), dict) else {}
    credit = (tr(image, "credit", c.lang) or "").strip()
    source_url = (image.get("source_url") or "").strip()
    if day.get("_default_image"):
        credit, source_url = c.s["default_credit"], ""
    alt = c.s["image_alt"].format(date=fmt_date(day["date"], c.lang))
    if name:
        loading = "eager" if eager else "lazy"
        fig = (
            f'<div class="media"><img src="{esc(c.root)}assets/{esc(name)}" alt="{esc(alt)}" '
            f'width="1200" height="675" loading="{loading}" decoding="async"></div>'
        )
    else:
        fig = (
            f'<div class="media placeholder" aria-hidden="true"><div class="placeholder-mark"></div>'
            f'<div class="placeholder-date">{esc(fmt_date(day["date"], c.lang))}</div></div>'
        )
    return fig, credit, source_url


def render_card(c: Ctx, day: dict, img_exists: bool, eager: bool) -> str:
    fig, _, _ = media_block(c, day, img_exists, eager)
    tags = "".join(f"<li>{esc(k)}</li>" for k in day_keywords(day, c.lang))
    badge = f'<p class="badge">{esc(c.s["example"])}</p>' if day.get("example") else ""
    summary = (tr(day, "summary", c.lang) or "").strip()
    return f"""
<article class="card">
  <a class="card-link" href="{esc(c.href("days/" + day["date"] + "/"))}">
    {fig}
    <div class="card-body">
      {badge}
      <time datetime="{esc(day["date"])}">{esc(fmt_date(day["date"], c.lang))}</time>
      <ul class="tags">{tags}</ul>
      <p class="summary">{esc(summary)}</p>
    </div>
  </a>
</article>
"""


def pager_html(c: Ctx, page: int, total: int) -> str:
    if total <= 1:
        return ""
    s = c.s
    parts = []
    if page > 1:
        parts.append(f'<a class="prev" rel="prev" href="{esc(c.href(page_path(page - 1)))}">{esc(s["prev"])}</a>')
    else:
        parts.append(f'<span class="prev disabled">{esc(s["prev"])}</span>')
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
            parts.append(f'<a href="{esc(c.href(page_path(n)))}">{n}</a>')
        last = n
    if page < total:
        parts.append(f'<a class="next" rel="next" href="{esc(c.href(page_path(page + 1)))}">{esc(s["next"])}</a>')
    else:
        parts.append(f'<span class="next disabled">{esc(s["next"])}</span>')
    return f'<nav class="pager" aria-label="{esc(s["pager_label"])}">{"".join(parts)}</nav>'


def render_index_page(c: Ctx, days: list[dict], page: int, total: int, existing: set[str], total_days: int) -> str:
    s = c.s
    if days:
        cards = [render_card(c, d, image_name(d) in existing, eager=(page == 1 and i == 0)) for i, d in enumerate(days)]
        main = f'<section class="card-list" aria-label="{esc(s["list_label"])}">{"".join(cards)}</section>'
    else:
        main = f'<section class="empty"><h2>{esc(s["empty_title"])}</h2><p>{esc(s["empty_text"])}</p></section>'
    if page == 1:
        intro = intro_block_html(c, include_sources=False)
        status = ""
        title = s["brand"]
        desc = f'{s["lede"]} {s["intro"]}'
    else:
        intro = ""
        first, last = days[0]["date"], days[-1]["date"]
        span = s["page_status"].format(page=page, total=total, start=fmt_date(last, c.lang), end=fmt_date(first, c.lang))
        status = f'<p class="page-status">{esc(span)}</p>'
        title = f'{s["page_title"].format(page=page)} · {s["brand"]}'
        desc = f'{s["site_title"]}: {span}.'
    count_note = (
        f'<p class="page-status">{s["count_note"].format(days=total_days, size=PAGE_SIZE, href=esc(c.href("archive/")))}</p>'
        if page == 1 and total > 1 else ""
    )
    kws = []
    for d in days[:3]:
        kws += day_keywords(d, c.lang, 3)
    return f"""{head_html(c, title, desc, image_abs=image_abs(c, days[0] if days else None, existing), keywords=kws)}
<body>
  <header class="site-header">
    {nav_html(c, "home")}
    <p class="eyebrow">{esc(s["eyebrow"])}</p>
    <h1>{esc(s["site_title"])}</h1>
    <p class="lede">{esc(s["lede"])}</p>
  </header>
  {intro}
  <main>
    {status}{count_note}
    {main}
    {pager_html(c, page, total)}
  </main>
  {footer_html(c)}
</body>
</html>
"""


def render_archive(c: Ctx, days: list[dict]) -> str:
    s = c.s
    months: dict[str, list[dict]] = {}
    for d in days:
        months.setdefault(d["date"][:7], []).append(d)
    sections = []
    for ym in sorted(months, reverse=True):
        rows = []
        for d in months[ym]:
            kws = s["kw_sep"].join(day_keywords(d, c.lang))
            rows.append(
                f'<li><a class="day" href="{esc(c.href("days/" + d["date"] + "/"))}">{esc(fmt_date(d["date"], c.lang))}</a>'
                f'<span class="kw">{esc(kws)}</span></li>'
            )
        sections.append(
            f'<section class="archive-month" id="m{esc(ym)}"><h2>{esc(fmt_month(ym, c.lang))}'
            f'<span class="count">{esc(s["archive_count"].format(n=len(months[ym])))}</span></h2>'
            f'<ul class="archive-list">{"".join(rows)}</ul></section>'
        )
    body = "".join(sections) or f"<p>{esc(s['archive_empty'])}</p>"
    if months:
        chips = "".join(
            f'<a href="#m{esc(ym)}">{esc(fmt_month(ym, c.lang))}</a>' for ym in sorted(months, reverse=True)
        )
        body = f'<nav class="archive-jump" aria-label="{esc(s["archive_jump"])}">{chips}</nav>' + body
    return f"""{head_html(c, f'{s["archive_title"]} · {s["brand"]}', s["archive_desc"])}
<body>
  <header class="site-header">
    {nav_html(c, "archive")}
    <p class="eyebrow">{esc(s["eyebrow"])}</p>
    <h1>{esc(s["archive_title"])}</h1>
    <p class="lede">{esc(s["archive_lede"].format(days=len(days)))}</p>
  </header>
  <main class="archive-main">
    {body}
  </main>
  {footer_html(c)}
</body>
</html>
"""


def day_title(day: dict, lang: str) -> str:
    """Title that carries the date and keywords in both languages."""
    other = "en" if lang == "zh" else "zh"
    sep = STRINGS[lang]["kw_sep"]
    osep = STRINGS[other]["kw_sep"]
    first = f'{fmt_date(day["date"], lang)} {sep.join(day_keywords(day, lang, 3))}'
    # Keep the other language's keywords whole: dropping the ones shared with
    # this language removed meeting codes such as "ACDE #246" from the second half.
    other_kw = day_keywords(day, other, 3)
    second = f'{fmt_date(day["date"], other)} {osep.join(other_kw)}'.strip()
    return f"{first} · {second} | {STRINGS[lang]['brand_short']}"


def render_day(c: Ctx, day: dict, img_exists: bool, newer: dict | None, older: dict | None, existing: set[str]) -> str:
    s = c.s
    fig, credit, source_url = media_block(c, day, img_exists, eager=True)
    kw = day_keywords(day, c.lang)
    tags = "".join(f"<li>{esc(k)}</li>" for k in kw)
    badge = f'<p class="badge">{esc(s["example"])}</p>' if day.get("example") else ""
    summary = (tr(day, "summary", c.lang) or "").strip()
    groups_html = []
    for topic, items in item_groups(day.get("items") or [], c.lang):
        entries = []
        for item in items:
            title = (tr(item, "title", c.lang) or "").strip() or s["untitled"]
            note = (tr(item, "note", c.lang) or "").strip()
            url = (item.get("url") or "").strip()
            item_date = (item.get("date") or day["date"]).strip()
            title_html = (
                f'<h3><a href="{esc(url)}" rel="noopener noreferrer">{esc(title)}</a></h3>' if url else f"<h3>{esc(title)}</h3>"
            )
            note_html = f'<p class="note">{esc(note)}</p>' if note else ""
            meta_bits = []
            if url:
                meta_bits.append(f'<a class="source" href="{esc(url)}" rel="noopener noreferrer">{esc(url)}</a>')
            if item_date:
                meta_bits.append(f'<time datetime="{esc(item_date)}">{esc(item_date)}</time>')
            meta_html = f'<p class="meta">{" ".join(meta_bits)}</p>' if meta_bits else ""
            entries.append(f'<article class="item">{title_html}{note_html}{meta_html}</article>')
        groups_html.append(f'<section class="topic"><h2>{esc(topic)}</h2>{"".join(entries)}</section>')
    topics = "".join(groups_html) or f'<p class="empty-items">{esc(s["no_items"])}</p>'
    credit_html = ""
    if credit or source_url:
        label = esc(credit or s["credit_fallback"])
        inner = f'<a href="{esc(source_url)}" rel="noopener noreferrer">{label}</a>' if source_url else label
        credit_html = f'<p class="credit">{esc(s["credit_label"])}{inner}</p>'
    left = (
        f'<a rel="prev" href="{esc(c.href("days/" + older["date"] + "/"))}">← {esc(fmt_date(older["date"], c.lang))}</a>'
        if older else "<span></span>"
    )
    right = (
        f'<a rel="next" href="{esc(c.href("days/" + newer["date"] + "/"))}">{esc(fmt_date(newer["date"], c.lang))} →</a>'
        if newer else "<span></span>"
    )
    day_nav = f'<nav class="day-nav" aria-label="{esc(s["day_nav_label"])}">{left}{right}</nav>'
    other = "en" if c.lang == "zh" else "zh"
    all_kw = kw + [k for k in day_keywords(day, other) if k not in kw]
    head = head_html(c, day_title(day, c.lang), summary or s["lede"], og_type="article",
                     image_abs=image_abs(c, day, existing), keywords=all_kw, published=day["date"])
    return f"""{head}
<body>
  <header class="day-header">
    {nav_html(c, "day")}
    <a class="back" href="{esc(c.href(""))}">{esc(s["back"])}</a>
    {badge}
    <p class="eyebrow">{esc(s["eyebrow"])}</p>
    <time datetime="{esc(day["date"])}">{esc(fmt_date(day["date"], c.lang))}</time>
    <h1>{esc(s["site_title"])}</h1>
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
  {footer_html(c)}
</body>
</html>
"""


def render_about(c: Ctx) -> str:
    s = c.s
    return f"""{head_html(c, f'{s["about_heading"]} · {s["brand"]}', s["intro"])}
<body>
  <header class="site-header">
    {nav_html(c, "about")}
    <p class="eyebrow">{esc(s["eyebrow"])}</p>
    <h1>{esc(s["about_heading"])}</h1>
    <p class="lede">{esc(s["lede"])}</p>
  </header>
  <main class="about-page">
    {intro_block_html(c, include_sources=True)}
  </main>
  {footer_html(c)}
</body>
</html>
"""


SVG_LAYERS = [
    # (zh band, en band, [(label, zh desc, en desc, style)])  style: s=live, in use or SFI, d=candidate/proposed
    ("钱包与交互", "Wallet layer", [
        ("ERC-7730", "可读签名", "Clear signing", "s"),
        ("EIP-5792", "批量调用接口", "Batch call API", "s"),
        ("EIP-7906", "交易断言", "Assertions", "d"),
        ("ERC-7930 / 7828", "跨链地址", "Interop addresses", "d"),
    ]),
    ("交易格式", "Transaction format", [
        ("EIP-8141", "帧交易，L1", "Frames, L1", "s"),
        ("ERC-4337 / 7562", "UserOp 与 bundler", "UserOps, bundlers", "s"),
        ("EIP-7702", "EOA 委托", "EOA delegation", "s"),
        ("8130 AA tx type", "拆出的交易类型，PR 未合并", "Split out, PR unmerged", "d"),
    ]),
    ("验证与签名", "Signatures", [
        ("EIP-7951", "P256，passkey", "P256, passkeys", "s"),
        ("ERC-7913", "非地址公钥", "Non-address keys", "s"),
        ("ERC-1271", "合约签名", "Contract signatures", "s"),
        ("EIP-8288", "后量子签名聚合", "PQ aggregation", "d"),
    ]),
    ("执行、nonce 与付费", "Nonces and fees", [
        ("EIP-8250", "keyed nonce 并发", "Keyed nonces", "d"),
        ("4337 paymaster", "代付 gas", "Sponsored gas", "s"),
        ("8141 payer", "付款方帧", "Payer frame", "s"),
        ("ERC-7579 / 8286", "模块化账户", "Modular accounts", "d"),
    ]),
    ("权限、恢复与委托安全", "Keys and delegation", [
        ("EIP-8130", "Keystore 与 actor", "Keystore, actors", "d"),
        ("ERC-8403 / 8231", "授权方与后量子公钥", "Authorities, PQ keys", "d"),
        ("EIP-8476 / 8477", "关闭或限时委托", "Opt-out, expiry", "d"),
        ("EIP-8425", "量子冻结与恢复", "Quantum freeze", "d"),
        ("EIP-8151 / 8298", "停用旧密钥", "Retire old key", "d"),
    ]),
    ("隐私与抗审查", "Privacy, anti-censorship", [
        ("ERC-5564 / 6538", "隐身地址", "Stealth addresses", "s"),
        ("ERC-8441", "后量子隐身地址", "PQ stealth", "d"),
        ("EIP-8272", "recent roots", "Recent roots", "d"),
        ("FOCIL EIP-7805", "包含列表", "Inclusion lists", "s"),
    ]),
]


def article_svg(lang: str) -> str:
    zh = lang == "zh"
    W, band_h, gap, top, left_w = 960, 74, 14, 40, 200
    H = top + len(SVG_LAYERS) * (band_h + gap) + 56
    out = [f'<svg class="arch" viewBox="0 0 {W} {H}" role="img" aria-labelledby="arch-title" aria-describedby="arch-desc" xmlns="http://www.w3.org/2000/svg">',
           f'<title id="arch-title">{esc(STRINGS[lang]["diagram_title"])}</title>',
           f'<desc id="arch-desc">{esc(STRINGS[lang]["diagram_desc"])}</desc>',
           '<defs><marker id="arr" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
           '<path d="M0 0L10 5L0 10z" fill="#5c564d"/></marker></defs>',
           f'<text x="{W/2}" y="24" text-anchor="middle" class="arch-h">{esc("用户" if zh else "User")}</text>']
    for i, (bz, be, boxes) in enumerate(SVG_LAYERS):
        y = top + i * (band_h + gap)
        out.append(f'<rect x="8" y="{y}" width="{W-16}" height="{band_h}" rx="12" class="arch-band"/>')
        out.append(f'<text x="22" y="{y + band_h/2 + 5}" class="arch-band-t">{esc(bz if zh else be)}</text>')
        n = len(boxes)
        bw = (W - left_w - 24 - (n - 1) * 10) / n
        for j, (lab, dz, de, st) in enumerate(boxes):
            x = left_w + j * (bw + 10)
            cls = {"s": "arch-box", "d": "arch-box dashed"}[st]
            out.append(f'<rect x="{x:.0f}" y="{y+10}" width="{bw:.0f}" height="{band_h-20}" rx="8" class="{cls}"/>')
            out.append(f'<text x="{x+bw/2:.0f}" y="{y+32}" text-anchor="middle" class="arch-l">{esc(lab)}</text>')
            out.append(f'<text x="{x+bw/2:.0f}" y="{y+50}" text-anchor="middle" class="arch-d">{esc(dz if zh else de)}</text>')
        if i < len(SVG_LAYERS) - 1:
            out.append(f'<line x1="{W/2}" y1="{y+band_h}" x2="{W/2}" y2="{y+band_h+gap}" stroke="#5c564d" marker-end="url(#arr)"/>')
    out.append(f'<line x1="{W/2}" y1="30" x2="{W/2}" y2="{top}" stroke="#5c564d" marker-end="url(#arr)"/>')
    ly = H - 22
    leg = [("arch-box", "实线：已上线、在用或已排期（SFI）" if zh else "Solid: live, in use, or Scheduled for Inclusion (SFI)"),
           ("arch-box dashed", "虚线：候选（CFI）或提议中" if zh else "Dashed: candidate (CFI) or proposed")]
    for k, (cls, t) in enumerate(leg):
        x = 24 + k * 460
        out.append(f'<rect x="{x}" y="{ly-12}" width="26" height="16" rx="4" class="{cls}"/>')
        out.append(f'<text x="{x+34}" y="{ly+1}" class="arch-d" text-anchor="start">{esc(t)}</text>')
    out.append("</svg>")
    return f'<figure class="arch-fig">{"".join(out)}</figure>'


CITE_RE = re.compile(r"\{\{c:([^}]*)\}\}")
REF_RE = re.compile(r"\{\{r:([^|}]+)\|([^}]+)\}\}")


def render_article_body(c: Ctx, raw: str, day_dates: set[str]) -> str:
    s = c.s

    def cite(m: re.Match) -> str:
        parts = [p.strip() for p in m.group(1).split("|") if p.strip()]
        date, urls = parts[0], parts[1:]
        if date not in day_dates:
            raise SystemExit(f"article cites a day that does not exist: {date}")
        bits = [f'<a href="{esc(c.href(f"days/{date}/"))}">{esc(s["cite_day"])} {esc(date)}</a>']
        for k, u in enumerate(urls, 1):
            label = s["cite_src"] if len(urls) == 1 else f'{s["cite_src"]} {k}'
            bits.append(f'<a href="{esc(u)}" rel="noopener noreferrer">{esc(label)}</a>')
        o, cl = ("（", "）") if c.lang == "zh" else ("(", ")")
        return f'<span class="cite">{o}{" · ".join(bits)}{cl}</span>'

    def ref(m: re.Match) -> str:
        u, label = m.group(1).strip(), m.group(2).strip()
        o, cl = ("（", "）") if c.lang == "zh" else ("(", ")")
        sep = "：" if c.lang == "zh" else ": "
        return f'<span class="cite">{o}{esc(s["checked"])}{sep}<a href="{esc(u)}" rel="noopener noreferrer">{esc(label)}</a>{cl}</span>'

    body = REF_RE.sub(ref, CITE_RE.sub(cite, raw))
    if "{{" in body.replace("{{svg}}", ""):
        raise SystemExit("unrendered macro left in article body")
    return body.replace("{{svg}}", article_svg(c.lang))


def render_article(c: Ctx, slug: str, raw: str, day_dates: set[str]) -> str:
    s = c.s
    meta = ARTICLES[slug]
    m = meta[c.lang]
    body = render_article_body(c, raw, day_dates)
    pub = meta["published"]
    return f"""{head_html(c, f'{m["title"]} · {s["brand"]}', m["lede"], og_type="article", keywords=m["keywords"], published=pub)}
<body>
  <header class="site-header">
    {nav_html(c, "")}
    <p class="eyebrow">{esc(s["article_kicker"])} · {esc(s["eyebrow"])}</p>
    <h1>{esc(m["title"])}</h1>
    <p class="lede">{esc(m["lede"])}</p>
    <p class="article-date"><time datetime="{esc(pub)}">{esc(fmt_date(pub, c.lang))}</time></p>
  </header>
  <main class="article-page">
    <article class="article-body">
{body}
    </article>
    <p class="article-back"><a href="{esc(c.href("about/"))}">{esc(s["about_heading"])}</a> · <a href="{esc(c.href(""))}">{esc(s["article_back"])}</a></p>
  </main>
  {footer_html(c)}
</body>
</html>
"""


def render_404(base: str) -> str:
    root = f"{base}/" if base else "/"
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex">
  <title>页面不存在 · Page not found | 以太坊研究日报 Ethereum Research Daily</title>
  <link rel="stylesheet" href="{root}styles.css">
</head>
<body>
  <main class="empty">
    <h1>页面不存在</h1>
    <p>这条地址没有对应的日报。<a href="{root}">回到首页</a> · <a href="{root}archive/">归档</a> · <a href="{root}about/">关于</a></p>
    <h2 lang="en">Page not found</h2>
    <p lang="en">There is no report at this address. <a href="{root}en/">Home</a> · <a href="{root}en/archive/">Archive</a> · <a href="{root}en/about/">About</a></p>
  </main>
</body>
</html>
"""


def render_sitemap(site_url: str, paths: list[tuple[str, str]]) -> str:
    def loc(lang: str, path: str) -> str:
        return f"{site_url}/{STRINGS[lang]['prefix']}{path}"

    rows = []
    for path, lastmod in paths:
        alts = "".join(
            f'\n    <xhtml:link rel="alternate" hreflang="{STRINGS[l]["hreflang"]}" href="{esc(loc(l, path))}"/>'
            for l in LANG_ORDER
        ) + f'\n    <xhtml:link rel="alternate" hreflang="x-default" href="{esc(loc("zh", path))}"/>'
        lm = f"\n    <lastmod>{lastmod}</lastmod>" if lastmod else ""
        for lang in LANG_ORDER:
            rows.append(f"  <url>\n    <loc>{esc(loc(lang, path))}</loc>{lm}{alts}\n  </url>")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">\n'
        + "\n".join(rows) + "\n</urlset>\n"
    )


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
.archive-main {
  width: min(1080px, calc(100% - 2rem));
  margin: 0.4rem auto 0;
  padding: 0 0 3rem;
  display: grid;
  gap: 1.4rem;
}
.archive-jump {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
  margin: 0 0 0.4rem;
}
.archive-jump a {
  padding: 0.2rem 0.75rem;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: var(--paper);
  color: var(--ink);
  text-decoration: none;
  font-size: 0.88rem;
}
.archive-jump a:hover { border-color: var(--accent); color: var(--accent); }
.archive-month {
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  padding: 1.3rem 1.6rem 1.4rem;
  scroll-margin-top: 1rem;
}
.archive-month h2 {
  font-family: var(--serif);
  font-size: 1.45rem;
  margin: 0 0 0.6rem;
  padding-bottom: 0.5rem;
  border-bottom: 1px solid var(--line);
}
.archive-month h2 .count { font-family: var(--sans); font-size: 0.9rem; color: var(--muted); margin-left: 0.6rem; font-weight: 400; }
.archive-list { list-style: none; margin: 0; padding: 0; display: grid; }
.archive-list li {
  display: grid;
  grid-template-columns: 11rem minmax(0, 1fr);
  gap: 1rem;
  align-items: baseline;
  padding: 0.55rem 0.6rem;
  border-bottom: 1px solid color-mix(in srgb, var(--line) 55%, transparent);
  border-radius: 8px;
}
.archive-list li:last-child { border-bottom: 0; }
.archive-list li:hover { background: color-mix(in srgb, var(--accent) 6%, transparent); }
.archive-list a.day { font-family: var(--serif); font-weight: 600; white-space: nowrap; }
.archive-list .kw { color: var(--muted); font-size: 0.92rem; }
.day-nav { display: flex; justify-content: space-between; gap: 1rem; padding: 0 0 2rem; font-size: 0.95rem; }
@media (max-width: 600px) {
  .archive-list li { grid-template-columns: 1fr; gap: 0.1rem; padding: 0.55rem 0.2rem; }
  .archive-month { padding: 1rem 1rem 1.1rem; }
}
"""

EXTRA_STYLES = """
.page-status { text-align: center; margin-left: auto; margin-right: auto; max-width: 46rem; padding: 0 1rem; }
.site-nav { flex-wrap: wrap; align-items: baseline; }
.site-nav a.lang-switch { margin-left: auto; border: 1px solid var(--line); border-radius: 999px; padding: 0 0.7rem; }
.site-nav a.lang-switch:hover { border-color: var(--accent); }

.article-page { width: min(920px, calc(100% - 2rem)); margin: 0 auto 3rem; }
.article-body { background: var(--paper); border: 1px solid var(--line); border-radius: var(--radius); box-shadow: var(--shadow); padding: 1.4rem 1.6rem 1.8rem; }
.article-body h2 { font-family: var(--serif); font-size: 1.35rem; margin: 2rem 0 0.8rem; }
.article-body h2:first-of-type { margin-top: 1rem; }
.article-body h3 { font-size: 1.08rem; margin: 1.4rem 0 0.6rem; }
.article-body li { margin: 0.35rem 0; }
.article-note { color: var(--muted); font-size: 0.92rem; margin: 0; }
.cite { color: var(--muted); font-size: 0.82rem; white-space: normal; }
.cite a { color: var(--muted); }
.cite a:hover { color: var(--accent); }
.table-wrap { overflow-x: auto; margin: 0.8rem 0 1.2rem; }
.article-body table { border-collapse: collapse; width: 100%; font-size: 0.92rem; min-width: 640px; }
.article-body th, .article-body td { border: 1px solid var(--line); padding: 0.5rem 0.6rem; vertical-align: top; text-align: left; }
.article-body th { background: var(--tag); }
.arch-fig { margin: 1rem 0 1.4rem; overflow-x: auto; }
.arch { width: 100%; min-width: 640px; height: auto; font-family: var(--sans); }
.arch-band { fill: #f6f2e8; stroke: var(--line); }
.arch-band-t { font-size: 14px; font-weight: 600; fill: var(--ink); }
.arch-box { fill: var(--accent-soft); stroke: var(--accent); stroke-width: 1.4; }
.arch-box.dashed { fill: #fffcf6; stroke-dasharray: 6 4; }
.arch-l { font-size: 13px; font-weight: 600; fill: var(--ink); }
.arch-d { font-size: 11.5px; fill: var(--muted); }
.arch-h { font-size: 13px; fill: var(--muted); }
.article-date { color: var(--muted); font-size: 0.9rem; margin: 0.3rem 0 0; }
.article-back { margin-top: 1.4rem; }
.about-intro .article-entry { margin-top: 0.85rem; font-weight: 600; }
.about-intro.has-aside {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(15rem, 19rem);
  gap: 1.6rem;
  align-items: start;
}
.research-aside {
  border: 1px solid var(--line);
  border-radius: 12px;
  background: color-mix(in srgb, var(--accent) 5%, var(--paper));
  padding: 1rem 1.1rem 1.1rem;
}
.about-intro .research-aside h2 { font-size: 1.1rem; margin: 0 0 0.45rem; }
.about-intro .research-title { font-size: 0.92rem; color: var(--muted); margin: 0 0 0.75rem; }
.research-links { display: grid; gap: 0.5rem; }
.research-link {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 0.8rem;
  padding: 0.5rem 0.8rem;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--paper);
  color: var(--ink);
  text-decoration: none;
}
.research-link:hover { border-color: var(--accent); color: var(--accent); }
.research-link[aria-current] { border-color: var(--accent); }
.research-link .rl-lang { font-weight: 600; }
.research-link .rl-path { font-size: 0.85rem; color: var(--muted); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
@media (max-width: 800px) {
  .about-intro.has-aside { grid-template-columns: 1fr; gap: 1.1rem; }
}
html[lang="en"] body { font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans CJK SC", sans-serif; }
"""


def copy_images(days: list[dict], site_root: Path, dist_assets: Path) -> set[str]:
    """Copy each day's image; a day with no usable image falls back to assets/default.jpg."""
    dist_assets.mkdir(parents=True, exist_ok=True)
    present: set[str] = set()
    default_src = site_root / "assets" / DEFAULT_IMAGE
    for day in days:
        if not _copy_day_image(day, site_root, dist_assets, present) and default_src.is_file():
            day["_default_image"] = True
    if any(d.get("_default_image") for d in days):
        shutil.copyfile(default_src, dist_assets / DEFAULT_IMAGE)
        present.add(DEFAULT_IMAGE)
    return present


def _copy_day_image(day: dict, site_root: Path, dist_assets: Path, present: set[str]) -> bool:
    image = day.get("image") if isinstance(day.get("image"), dict) else None
    local = ((image or {}).get("local_path") or "").replace("\\", "/").lstrip("/")
    if not local:
        return False
    src = site_root / local
    if not src.is_file():
        alt = site_root / "assets" / Path(local).name
        src = alt if alt.is_file() else src
    if not src.is_file():
        print(f"warning: image not found for {day['date']}: {local}, using default", file=sys.stderr)
        return False
    shutil.copyfile(src, dist_assets / src.name)
    present.add(src.name)
    return True


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> int:
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Build the bilingual Ethereum daily digest static site.")
    parser.add_argument("--data-dir", default=str(here / "data"))
    parser.add_argument("--out-dir", default=str(here / "dist"))
    parser.add_argument("--base-path", default="",
                        help="Optional root-absolute prefix such as /ethereum. Leave empty (default) for relative links.")
    parser.add_argument("--site-url", default=DEFAULT_SITE_URL,
                        help="Public origin used for canonical, hreflang, Open Graph and sitemap URLs.")
    args = parser.parse_args()

    data_dir, out_dir = Path(args.data_dir), Path(args.out_dir)
    base = normalize_base_path(args.base_path)
    site_url = args.site_url.rstrip("/")
    days = load_days(data_dir)

    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    existing = copy_images(days, here, out_dir / "assets")
    write(out_dir / "styles.css", STYLES.strip() + "\n" + EXTRA_STYLES.strip() + "\n")

    total_pages = max(1, math.ceil(len(days) / PAGE_SIZE))
    missing_en = [d["date"] for d in days if not d.get("summary_en")]
    sitemap_paths: list[tuple[str, str]] = []
    newest = days[0]["date"] if days else ""

    for lang in LANG_ORDER:
        lang_dir = out_dir / STRINGS[lang]["prefix"]
        for page in range(1, total_pages + 1):
            chunk = days[(page - 1) * PAGE_SIZE: page * PAGE_SIZE]
            c = Ctx(lang, page_path(page), base, site_url)
            write(lang_dir / page_path(page) / "index.html",
                  render_index_page(c, chunk, page, total_pages, existing, len(days)))
            if lang == "zh":
                sitemap_paths.append((page_path(page), chunk[0]["date"] if chunk else newest))
        write(lang_dir / "archive" / "index.html", render_archive(Ctx(lang, "archive/", base, site_url), days))
        write(lang_dir / "about" / "index.html", render_about(Ctx(lang, "about/", base, site_url)))
        for i, day in enumerate(days):
            newer = days[i - 1] if i > 0 else None
            older = days[i + 1] if i + 1 < len(days) else None
            path = f"days/{day['date']}/"
            write(lang_dir / path / "index.html",
                  render_day(Ctx(lang, path, base, site_url), day, image_name(day) in existing, newer, older, existing))
            if lang == "zh":
                sitemap_paths.append((path, day["date"]))
    day_dates = {d["date"] for d in days}
    for lang in LANG_ORDER:
        lang_dir = out_dir / STRINGS[lang]["prefix"]
        for slug in ARTICLES:
            raw = (here / "articles" / f"{slug}.{lang}.html").read_text(encoding="utf-8")
            write(lang_dir / slug / "index.html",
                  render_article(Ctx(lang, f"{slug}/", base, site_url), slug, raw, day_dates))
    sitemap_paths[1:1] = [("archive/", newest), ("about/", "")] + [(f"{slug}/", m["published"]) for slug, m in ARTICLES.items()]

    write(out_dir / "404.html", render_404(base))
    write(out_dir / "_redirects", "/page/1 / 301\n/page/1/ / 301\n/en/page/1 /en/ 301\n/en/page/1/ /en/ 301\n/en /en/ 301\n")
    public = site_url + base
    write(out_dir / "sitemap.xml", render_sitemap(public, sitemap_paths))
    write(out_dir / "robots.txt", f"User-agent: *\nAllow: /\n\nSitemap: {public}/sitemap.xml\n")

    files = sum(1 for p in out_dir.rglob("*") if p.is_file())
    size = sum(p.stat().st_size for p in out_dir.rglob("*") if p.is_file())
    print(f"built {len(days)} day(s) x {len(LANG_ORDER)} languages, {total_pages} index page(s) each, "
          f"{files} file(s), {size / 1024:.0f} KiB -> {out_dir}")
    print(f"base path: {base or 'relative links'}; site url: {public}")
    if missing_en:
        print(f"warning: no English summary for {len(missing_en)} day(s): {', '.join(missing_en[:10])}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
