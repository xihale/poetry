#!/usr/bin/env python3
"""Export a 古文岛 (guwendao.net) 诗文 collection to JSON.

The collection list at /user/wode.aspx is the only page behind a login: it is
served from the `gsw2017user` cookie. Individual poem pages are public, so the
cookie is sent to the list endpoint and nowhere else.

Credentials stay out of the repo. Point --cookie-jar at a Netscape cookie file
(`curl -c jar.txt ... ` after logging in), or set GUWENDAO_COOKIE. The export
is cached under .cache/, which is gitignored.

    scripts/fetch-poemlist.py --cookie-jar /tmp/jar.txt
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".cache" / "guwendao"
OUT = CACHE / "poemlist.json"

BASE = "https://www.guwendao.net"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"

# 〔唐代〕 -> 唐. guwendao writes the dynasty of the author, which is the whole
# point: era comes from who wrote it, not from which book it was filed in.
ERA = {
    "先秦": "先秦", "秦代": "秦", "两汉": "汉", "汉代": "汉", "魏晋": "魏晋",
    "南北朝": "南北朝", "隋代": "隋", "唐代": "唐", "五代": "五代",
    "宋代": "宋", "元代": "元", "明代": "明", "清代": "清", "近现代": "近现代",
}


def cookie_header(jar: str | None) -> str:
    """Read `gsw2017user` from a Netscape cookie file or the environment."""
    if jar:
        for line in Path(jar).read_text(encoding="utf-8").splitlines():
            if line.startswith("#") or not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) >= 7 and parts[5] == "gsw2017user":
                return f"gsw2017user={parts[6]}"
        raise SystemExit(f"no gsw2017user cookie in {jar}")
    value = os.environ.get("GUWENDAO_COOKIE")
    if not value:
        raise SystemExit("pass --cookie-jar or set GUWENDAO_COOKIE")
    return f"gsw2017user={value}"


def get(url: str, cookie: str | None = None) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    if cookie:
        req.add_header("Cookie", cookie)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", "replace")


def strip(tag: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", tag)).strip()


# The site files a collection under four tabs. Only 诗文 is scraped for the
# site; the other three are counted and reported so a silent cap cannot hide
# behind a plausible-looking number.
TABS = {"s": "诗文", "m": "名句", "d": "古籍", "a": "作者"}


def _pager_next(doc: str) -> str | None:
    """The 下一页 href, if the site is offering one. guwendao server-renders
    the whole list today, but if it ever starts paging we follow it rather
    than quietly keeping page one."""
    m = re.search(r'<a[^>]+href="([^"]*page=\d+[^"]*)"[^>]*>\s*下一页', doc)
    return html.unescape(m.group(1)) if m else None


def list_poems(cookie: str, user_id: str) -> list[tuple[str, str]]:
    """Return [(key, title)] for every 诗文 in the collection, in site order.

    Follows the pager to exhaustion, so a collection larger than one page
    cannot be truncated silently.
    """
    url = f"{BASE}/user/wode.aspx?type=s&id={user_id}&sort=t"
    out, seen, pages = [], set(), 0
    while url:
        doc = get(url, cookie)
        pages += 1
        for block in re.findall(r'<div class="contentLine">(.*?)</div>\s*</div>', doc, re.S):
            m = re.search(r'href="/shiwenv_([0-9a-f]+)\.aspx"[^>]*>(.*?)</a>', block, re.S)
            if not m or m.group(1) in seen:
                continue
            seen.add(m.group(1))
            out.append((m.group(1), strip(m.group(2))))
        nxt = _pager_next(doc)
        if not nxt:
            break
        url = nxt if nxt.startswith("http") else BASE + nxt
        if pages > 200:  # a pager loop is a bug, not a collection
            raise SystemExit(f"pager did not terminate after {pages} pages")
    if not out:  # the block regex is the fragile part; fail loudly, not silently
        raise SystemExit("no poems found — is the cookie still valid?")
    if pages > 1:
        print(f"  (walked {pages} pages)")
    return out


def tab_counts(cookie: str, user_id: str) -> dict[str, int]:
    """How many items the site says each collection tab holds."""
    counts = {}
    for t, label in TABS.items():
        doc = get(f"{BASE}/user/collect.aspx?type={t}&sort=t", cookie)
        counts[label] = len(re.findall("收藏时间：", doc))
    return counts


def parse_poem(doc: str) -> dict:
    title = re.search(r'<div id="zhengwen[^"]*">\s*<h1[^>]*>(.*?)</h1>', doc, re.S)
    source = re.search(r'<p class="source">(.*?)</p>', doc, re.S)
    body = re.search(r'<div class="contson"[^>]*>(.*?)</div>', doc, re.S)

    author, era = "佚名", None
    if source:
        author_tag = re.search(r'<a href="/authorv[^"]*"[^>]*>(.*?)</a>', source.group(1), re.S)
        if author_tag:
            author = strip(re.sub(r"<img[^>]*>", "", author_tag.group(1)))
        era_tag = re.search(r"〔([^〕]+)〕", source.group(1))
        if era_tag:
            era = ERA.get(era_tag.group(1).strip(), era_tag.group(1).strip())

    text = ""
    if body:
        raw = re.sub(r"<br\s*/?>", "\n", body.group(1))
        text = "\n".join(ln.strip() for ln in strip(raw).split("\n") if ln.strip())

    return {
        "title": strip(title.group(1)) if title else None,
        "author": author,
        "era": era,
        "text": text,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cookie-jar", help="Netscape cookie file holding gsw2017user")
    ap.add_argument("--user-id", help="account id from the wode.aspx URL")
    ap.add_argument("--refresh", action="store_true", help="re-fetch poem pages")
    args = ap.parse_args()

    cookie = cookie_header(args.cookie_jar)
    # the cookie value is url-encoded: "4533625%7C<token>%7C..." — the leading
    # field is the account id the collection URL wants
    raw = urllib.parse.unquote(cookie.split("=", 1)[1])
    user_id = args.user_id or raw.split("|")[0]
    if not user_id:
        raise SystemExit("pass --user-id")

    CACHE.mkdir(parents=True, exist_ok=True)
    # report every tab the site keeps, so a collection larger than 诗文 is
    # visible rather than assumed absent
    counts = tab_counts(cookie, user_id)
    print("collection: " + "  ".join(f"{k} {v}" for k, v in counts.items()))
    listed = list_poems(cookie, user_id)
    print(f"  -> {len(listed)} 诗文 to fetch")
    cache = {}
    if OUT.exists() and not args.refresh:
        cache = {p["key"]: p for p in json.loads(OUT.read_text(encoding="utf-8"))}

    poems = []
    for i, (key, title) in enumerate(listed, 1):
        if key in cache and cache[key].get("text"):
            poems.append(cache[key])
            continue
        doc = get(f"{BASE}/shiwenv_{key}.aspx")
        rec = {"key": key, "url": f"{BASE}/shiwenv_{key}.aspx", **parse_poem(doc)}
        rec["title"] = rec["title"] or title
        if not rec["text"]:
            print(f"  !! {title}: no body parsed")
        poems.append(rec)
        print(f"  [{i}/{len(listed)}] {rec['title']} — {rec['author']}"
              f" {'〔' + rec['era'] + '〕' if rec['era'] else ''}")
        time.sleep(0.3)
    OUT.write_text(json.dumps(poems, ensure_ascii=False, indent=1), encoding="utf-8")
    missing = [p["title"] for p in poems if not p["text"]]
    print(f"\n{len(poems)} poems -> {OUT.relative_to(ROOT)}")
    if missing:
        print(f"  without text: {missing}")


if __name__ == "__main__":
    main()
