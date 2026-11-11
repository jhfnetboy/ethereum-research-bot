#!/usr/bin/env python3
"""Turn a reports/YYYY-MM-DD.md file into site/data/YYYY-MM-DD.json.

Recommended Markdown shape (flexible, most fields are optional):

    # 以太坊研究日报 2026-11-11

    关键词：Fusaka、PeerDAS、Based Rollup

    摘要：
    两三句关键信息。

    配图来源：https://example.com/article
    配图版权：媒体或作者名称

    ## 话题名称

    - [条目标题](https://source.example/path)
      一句说明。

YAML front matter is also accepted:

    ---
    date: 2026-11-11
    keywords: [Fusaka, PeerDAS]
    summary: |
      两三句关键信息。
    image:
      source_url: https://example.com/article
      credit: 媒体名称
    ---

Use --fetch-image to download an og:image (or a direct image URL) into
site/assets/ and record local_path, source_url, and credit.
Never invent an image; if none is found, image is omitted and the
site build uses a placeholder style.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
USER_AGENT = "ethereum-research-digest/1.0 (local ingest; +https://ethereum-research-bot.pages.dev)"
MAX_IMAGE_BYTES = 6 * 1024 * 1024


def parse_front_matter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    raw = text[3:end].strip()
    body = text[end + 4 :].lstrip("\n")
    data: dict = {}
    current = None
    list_key = None
    image: dict = {}
    in_image = False
    summary_lines: list[str] = []
    in_summary = False
    for line in raw.splitlines():
        if in_summary:
            if line.startswith("  ") or line.startswith("\t") or line.strip() == "":
                summary_lines.append(line.strip())
                continue
            in_summary = False
            data["summary"] = "\n".join(x for x in summary_lines if x).strip()
        m = re.match(r"^([A-Za-z0-9_]+):\s*(.*)$", line)
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip()
        if key == "summary" and (val == "|" or val == ">" or val == ""):
            in_summary = True
            summary_lines = []
            continue
        if key == "image" and val == "":
            in_image = True
            continue
        if in_image and line.startswith("  "):
            im = re.match(r"^\s+([A-Za-z0-9_]+):\s*(.*)$", line)
            if im:
                image[im.group(1)] = im.group(2).strip().strip("\"'")
            continue
        in_image = False
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            data[key] = [x.strip().strip("\"'") for x in inner.split(",") if x.strip()]
        else:
            data[key] = val.strip("\"'")
    if in_summary and summary_lines:
        data["summary"] = "\n".join(x for x in summary_lines if x).strip()
    if image:
        data["image"] = image
    return data, body


def first_date(*candidates: str, filename: str = "") -> str | None:
    for value in candidates:
        if not value:
            continue
        m = DATE_RE.search(value)
        if m:
            return m.group(1)
    m = DATE_RE.search(filename)
    return m.group(1) if m else None


def split_keywords(raw: str) -> list[str]:
    parts = re.split(r"[,，、;；]+", raw)
    return [p.strip().lstrip("#") for p in parts if p.strip()]


def labeled_block(lines: list[str], start: int, prefixes: tuple[str, ...]) -> tuple[str, int] | None:
    line = lines[start].strip()
    for prefix in prefixes:
        if line.startswith(prefix):
            rest = line[len(prefix) :].strip()
            if rest:
                return rest, start
            collected = []
            j = start + 1
            while j < len(lines) and lines[j].strip() and not re.match(r"^#{1,3}\s", lines[j]) and "：" not in lines[j][:8] and ":" not in lines[j][:12]:
                collected.append(lines[j].strip())
                j += 1
            return "\n".join(collected).strip(), j - 1
    return None


def _clean_heading(text: str) -> str:
    text = re.sub(r"^#+\s*", "", text).strip()
    text = re.sub(r"^\d+\.\s*", "", text).strip()
    return text


def _plain(text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    return re.sub(r"\s+", " ", text).strip()


def _note_from_line(line: str, title: str) -> str:
    """Turn a bullet line into a short note: drop the bullet marker, and drop
    the item's own title when the line starts with it."""
    note = _plain(re.sub(r"^\s*(?:[-*+]|\d+\.)\s+", "", line))
    if note.startswith(title):
        note = note[len(title):]
    note = re.sub(r"^[\s:：,，;；。]+", "", note).strip()
    return "" if note == title else note


def parse_digest_style(body: str, date: str) -> tuple[str, list[dict]]:
    """Parse reports that use 今日要点 / 重点话题 / 其他动态 headings."""
    body = re.split(r"\n来源说明：", body, maxsplit=1)[0]
    summary_parts: list[str] = []
    items: list[dict] = []
    topic = ""
    in_points = False
    for line in body.splitlines():
        if line.startswith("## "):
            heading = _clean_heading(line)
            in_points = heading == "今日要点"
            if heading in {"今日要点", "重点话题"}:
                topic = ""
            elif heading.startswith("以太坊日报") or heading.startswith("以太坊研究日报"):
                topic = ""
                in_points = False
            else:
                topic = heading
                in_points = False
            continue
        if line.startswith("### "):
            topic = _clean_heading(line)
            in_points = False
            continue
        if in_points:
            m = re.match(r"^\d+\.\s*(.+)$", line.strip())
            if m:
                summary_parts.append(_plain(m.group(1)))
            continue
        if not topic:
            continue
        for link in re.finditer(r"\[([^\]]+)\]\((https?://[^)]+)\)", line):
            title, url = link.group(1).strip(), link.group(2).strip()
            item_date = date
            dm = re.search(r"(20\d{2}-\d{2}-\d{2})", title + " " + line)
            if dm:
                item_date = dm.group(1)
            note = _note_from_line(line, title)
            items.append({
                "topic": topic or "其他",
                "title": title,
                "note": note,
                "url": url,
                "date": item_date,
            })
    summary = " ".join(summary_parts[:3]).strip()
    return summary, items


def parse_markdown(text: str, filename: str = "") -> dict:
    fm, body = parse_front_matter(text)
    lines = body.splitlines()
    title = ""
    keywords: list[str] = list(fm.get("keywords") or [])
    summary = (fm.get("summary") or "").strip()
    image = dict(fm.get("image") or {})
    items: list[dict] = []
    topic = ""
    i = 0
    pending_item = None

    def flush_pending():
        nonlocal pending_item
        if pending_item:
            items.append(pending_item)
            pending_item = None

    while i < len(lines):
        raw = lines[i]
        stripped = raw.strip()

        if stripped.startswith("# ") and not title:
            title = stripped[2:].strip()
            i += 1
            continue

        hit = labeled_block(lines, i, ("关键词：", "关键词:", "Keywords:", "keywords:"))
        if hit and not keywords:
            keywords = split_keywords(hit[0])
            i = hit[1] + 1
            continue

        hit = labeled_block(lines, i, ("摘要：", "摘要:", "Summary:", "summary:"))
        if hit and not summary:
            summary = hit[0]
            i = hit[1] + 1
            continue

        hit = labeled_block(lines, i, ("配图来源：", "配图来源:", "配图：", "配图:", "image:", "Image:"))
        if hit and not image.get("source_url"):
            image["source_url"] = hit[0].strip()
            i = hit[1] + 1
            continue

        hit = labeled_block(lines, i, ("配图版权：", "配图版权:", "配图出处：", "配图出处:", "credit:", "Credit:"))
        if hit and not image.get("credit"):
            image["credit"] = hit[0].strip()
            i = hit[1] + 1
            continue

        heading = re.match(r"^(#{2,3})\s+(.+)$", stripped)
        if heading:
            flush_pending()
            level, text_h = len(heading.group(1)), heading.group(2).strip()
            if level == 2:
                topic = text_h
            else:
                pending_item = {"topic": topic or "其他", "title": text_h, "note": "", "url": "", "date": ""}
            i += 1
            continue

        bullet = re.match(r"^[-*+]\s+(.+)$", stripped)
        if bullet:
            flush_pending()
            content = bullet.group(1).strip()
            link = re.match(r"^\[([^\]]+)\]\(([^)]+)\)\s*(.*)$", content)
            if link:
                pending_item = {
                    "topic": topic or "其他",
                    "title": link.group(1).strip(),
                    "note": link.group(3).strip(),
                    "url": link.group(2).strip(),
                    "date": "",
                }
            else:
                url_only = re.match(r"^(https?://\S+)\s*(.*)$", content)
                if url_only:
                    pending_item = {
                        "topic": topic or "其他",
                        "title": url_only.group(2).strip() or url_only.group(1),
                        "note": "",
                        "url": url_only.group(1),
                        "date": "",
                    }
                else:
                    pending_item = {
                        "topic": topic or "其他",
                        "title": content,
                        "note": "",
                        "url": "",
                        "date": "",
                    }
            i += 1
            continue

        url_m = re.match(r"^(https?://\S+)\s*$", stripped)
        if url_m and pending_item and not pending_item.get("url"):
            pending_item["url"] = url_m.group(1)
            i += 1
            continue

        if stripped and pending_item and not stripped.startswith("#"):
            note = pending_item.get("note") or ""
            pending_item["note"] = (note + " " + stripped).strip() if note else stripped
            i += 1
            continue

        i += 1

    flush_pending()

    date = first_date(str(fm.get("date") or ""), title, filename) or ""
    if re.search(r"^## 今日要点", body, re.M) or re.search(r"^## 重点话题", body, re.M):
        digest_summary, digest_items = parse_digest_style(body, date)
        if digest_items:
            items = digest_items
        if digest_summary and not summary:
            summary = digest_summary
    for item in items:
        item["date"] = item.get("date") or date

    out = {
        "date": date,
        "keywords": keywords,
        "summary": summary,
        "items": items,
    }
    if image.get("source_url") or image.get("local_path") or image.get("credit"):
        out["image"] = image
    return out


class OgParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.og_image = None
        self.title = None

    def handle_starttag(self, tag, attrs):
        ad = {k.lower(): v for k, v in attrs}
        if tag == "meta":
            prop = (ad.get("property") or ad.get("name") or "").lower()
            if prop in {"og:image", "og:image:url", "twitter:image", "twitter:image:src"} and ad.get("content"):
                if not self.og_image:
                    self.og_image = ad["content"].strip()
        if tag == "meta" and (ad.get("property") or "").lower() == "og:site_name" and ad.get("content"):
            self.title = self.title or ad["content"].strip()


def http_get(url: str, timeout: int = 25) -> tuple[bytes, str]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        ctype = resp.headers.get("Content-Type", "")
        data = resp.read(MAX_IMAGE_BYTES + 1)
        if len(data) > MAX_IMAGE_BYTES:
            raise ValueError(f"response too large: {url}")
        return data, ctype


def resolve_image_url(source: str) -> tuple[str, str]:
    """Return (image_url, credit_guess). If source is already an image, use it."""
    data, ctype = http_get(source)
    if ctype.lower().startswith("image/"):
        return source, ""
    html = data.decode("utf-8", errors="replace")
    parser = OgParser()
    parser.feed(html)
    if not parser.og_image:
        raise ValueError(f"no og:image at {source}")
    img = parser.og_image
    if img.startswith("//"):
        img = "https:" + img
    return img, (parser.title or "")


def save_image(image_url: str, dest: Path) -> None:
    data, ctype = http_get(image_url)
    if not ctype.lower().startswith("image/"):
        # some CDNs omit type; accept if magic looks like an image
        if not data.startswith((b"\x89PNG", b"\xff\xd8\xff", b"RIFF", b"GIF8", b"<svg", b"<?xml")):
            raise ValueError(f"not an image content-type: {ctype}")
    dest.write_bytes(data)


def infer_ext(url: str, dest_hint: str = "") -> str:
    path = url.split("?")[0].lower()
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif", ".svg"):
        if path.endswith(ext):
            return ".jpg" if ext == ".jpeg" else ext
    return ".jpg"


MAX_IMAGE_WIDTH = 1200
JPEG_QUALITY = 78


def optimize_image(path: Path) -> Path:
    """Shrink a downloaded image to at most MAX_IMAGE_WIDTH px wide and re-encode as JPEG.

    Keeps the site small enough for hundreds of days. Requires Pillow; if it is
    missing, or the file is an SVG/GIF, the original is kept unchanged.
    """
    if path.suffix.lower() in {".svg", ".gif"}:
        return path
    try:
        from PIL import Image
    except ImportError:
        print("Pillow not installed; keeping original image", file=sys.stderr)
        return path
    with Image.open(path) as im:
        im.load()
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA")
            bg = Image.new("RGB", im.size, (255, 252, 246))
            bg.paste(im, mask=im.split()[-1])
            im = bg
        else:
            im = im.convert("RGB")
        if im.width > MAX_IMAGE_WIDTH:
            h = round(im.height * MAX_IMAGE_WIDTH / im.width)
            im = im.resize((MAX_IMAGE_WIDTH, h), Image.LANCZOS)
        out = path.with_suffix(".jpg")
        im.save(out, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
    if out != path and path.exists():
        path.unlink()
    return out


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    here = Path(__file__).resolve().parent
    repo = here.parent
    parser = argparse.ArgumentParser(description="Convert a daily Markdown report into site JSON.")
    parser.add_argument("--report", help="Path to reports/YYYY-MM-DD.md")
    parser.add_argument("--date", help="Date (YYYY-MM-DD). Defaults to the date in the file name or title.")
    parser.add_argument("--out", help="Output JSON path. Defaults to site/data/YYYY-MM-DD.json")
    parser.add_argument("--fetch-image", action="store_true", help="Download og:image or a direct image URL into site/assets/")
    parser.add_argument("--image-url", help="Optional explicit article or image URL, overriding the report field.")
    parser.add_argument("--image-credit", help="Optional credit text for the image, overriding the report field.")
    args = parser.parse_args()

    if not args.report and not args.date:
        parser.error("provide --report or --date")

    report_path = Path(args.report) if args.report else repo / "reports" / f"{args.date}.md"
    if not report_path.is_file():
        print(f"report not found: {report_path}", file=sys.stderr)
        return 1

    data = parse_markdown(report_path.read_text(encoding="utf-8"), report_path.name)
    if args.date:
        data["date"] = args.date
        for item in data.get("items") or []:
            item["date"] = item.get("date") or args.date
    if not data.get("date"):
        print("could not determine date; pass --date", file=sys.stderr)
        return 1

    if args.image_url:
        data.setdefault("image", {})["source_url"] = args.image_url
    if args.image_credit:
        data.setdefault("image", {})["credit"] = args.image_credit

    if args.fetch_image:
        source = ((data.get("image") or {}).get("source_url") or "").strip()
        if not source:
            # fall back to the first item url
            for item in data.get("items") or []:
                if item.get("url"):
                    source = item["url"]
                    data.setdefault("image", {})["source_url"] = source
                    break
        if source:
            try:
                img_url, credit_guess = resolve_image_url(source)
                ext = infer_ext(img_url)
                dest = here / "assets" / f"{data['date']}{ext}"
                dest.parent.mkdir(parents=True, exist_ok=True)
                save_image(img_url, dest)
                dest = optimize_image(dest)
                image = data.setdefault("image", {})
                image["local_path"] = f"assets/{dest.name}"
                image.setdefault("source_url", source)
                if credit_guess and not image.get("credit"):
                    image["credit"] = credit_guess
                print(f"saved image {dest} from {img_url}")
            except Exception as exc:
                print(f"image fetch skipped: {exc}", file=sys.stderr)
        else:
            print("no image source url; skipping image", file=sys.stderr)

    image = data.get("image") or {}
    if not image.get("local_path"):
        # keep a previously downloaded asset so re-ingesting without --fetch-image is safe
        for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"):
            existing = here / "assets" / f"{data['date']}{ext}"
            if existing.is_file():
                data.setdefault("image", {})["local_path"] = f"assets/{existing.name}"
                break

    out = Path(args.out) if args.out else here / "data" / f"{data['date']}.json"
    write_json(out, data)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
