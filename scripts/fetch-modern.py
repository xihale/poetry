#!/usr/bin/env python3
"""现代诗与当代诗, from the sheepzh/poetry corpus.

Source: https://github.com/sheepzh/poetry (code MIT) via its JSON mirror
https://github.com/sheepzh/poetry-page — one directory per poet, one page of
poems per file:

    json/<诗人>/<n>.json  ->  [{"title": …, "date": "198404", "content": …}]
    json/<诗人>/meta.json ->  {"p": pages, "t": poems}

The mirror is cloned into .cache/modern/repo (111 MB, gitignored) rather than
fetched file by file: 3,489 poets is 3,489 round trips.

── on the rights ───────────────────────────────────────────────────────────

Most of this corpus is IN COPYRIGHT. 海子 died 1989, 顾城 1993, 北岛 is alive;
China's term is life + 50 years, so their poems are protected, and this site
publishes them anyway — a deliberate decision by the site's owner, taken with
that stated. The mirror is a scrape of public websites and carries an MIT tag
that covers its own code, not the poems.

What this script does about that: it records the fact rather than hiding it.
Every poem from a poet who died less than 50 years ago (or whose death year is
unknown) is emitted with `note` carrying the attribution line, and the emitted
`rights` field says 在版. Nothing here is disguised as public domain. If a
takedown arrives, `scripts/build-corpus.py --drop-encumbered` drops exactly
those poems and nothing else.

Poets who died before 1976 are public domain in China and are emitted without
that note: 徐志摩 (1931), 朱湘 (1933), 鲁迅 (1936), 闻一多 (1946), 戴望舒 (1950),
林徽因 (1955), 刘半农 (1934), 胡适 (1962), 郭沫若 (1978 — not yet) …
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = ROOT / ".cache" / "modern" / "repo" / "json"
OUT = ROOT / ".cache" / "modern" / "records.json"

REPO_URL = "https://github.com/sheepzh/poetry"

# Death years, for the poets a reader is most likely to meet. Everything not
# listed is treated as still in copyright — the pessimistic default, which is
# the right way round: an unlisted living poet must not be published by
# accident.
DEATH = {
    "徐志摩": 1931, "朱湘": 1933, "刘半农": 1934, "鲁迅": 1936, "闻一多": 1946,
    "戴望舒": 1950, "林徽因": 1955, "胡适": 1962, "穆旦": 1977, "冯至": 1993,
    "海子": 1989, "骆一禾": 1989, "顾城": 1993, "昌耀": 2000, "木心": 2011,
    "汪国真": 2015, "余光中": 2017, "北岛": None, "舒婷": None, "席慕蓉": None,
    "郑愁予": None, "多多": None, "翟永明": None, "于坚": None, "韩东": None,
    "王小妮": None, "食指": None, "杨炼": None, "洛夫": 2018, "痖弦": None,
    "周梦蝶": 2014, "商禽": 2010, "纪弦": 2013, "覃子豪": 1963, "蓉子": None,
    "郑敏": 2022, "牛汉": 2013, "绿原": 2009, "曾卓": 2002, "彭燕郊": 2008,
    "蔡其矫": 2007, "邵燕祥": 2020, "公刘": 2003, "白桦": 2019, "流沙河": 2019,
    "田间": 1985, "艾青": 1996, "臧克家": 2004, "何其芳": 1977, "卞之琳": 2000,
    "废名": 1967, "朱英诞": 1983, "吴兴华": 1966, "陈梦家": 1966,
    "殷夫": 1931, "柔石": 1931, "冯雪峰": 1976, "蒋光慈": 1931, "汪静之": 1996,
    "康白情": 1957, "俞平伯": 1990, "朱自清": 1948, "冰心": 1999,
    "宗白华": 1986, "梁宗岱": 1983, "王独清": 1940, "穆木天": 1971,
    "李金发": 1976, "姚蓬子": 1969, "邵洵美": 1968, "于赓虞": 1963,
    "汪铭竹": 1989, "路易士": 2013, "南星": 1996, "辛笛": 2004,
    "陈敬容": 1989, "唐祈": 1990, "唐湜": 2005, "袁可嘉": 2008, "杜运燮": 2002,
    "郑燮": 1765,
}
# 1976 is the line: 1976 - 50 = 1926, so a poet who died in 1975 or earlier is
# out of term. 李金发 died 1976, so he is NOT in the clear.
PD_BEFORE = 1976

# ── attribution and dedupe ──────────────────────────────────────────────────

# The corpus is a scrape, so a handful of records are not poems at all: a
# biography pasted under the poet's own name, a table of contents, a note to the
# reader. They are recognisable by being titled after the poet and by carrying
# prose-length bodies.
MAX_LINES = 400
MIN_CHARS = 2

# A poem printed twice in one poet's file (two pages overlapping) is one poem.
# Titles alone are not enough — 「无题」 is a real title and appears many times —
# so the key is the title together with the first line.
def key_of(title: str, text: str) -> tuple[str, str]:
    head = re.split(r"[，。；！？、,.!?;]", text.strip(), maxsplit=1)[0]
    return (title.strip(), head[:20])


def clean(text: str) -> str:
    """One line per verse line, with the scrape's own noise removed."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln.rstrip() for ln in text.split("\n")]
    # collapse the runs of blank lines the scrape leaves between stanzas to one
    out: list[str] = []
    for ln in lines:
        if not ln.strip():
            if out and out[-1] != "":
                out.append("")
            continue
        out.append(ln.strip())
    while out and out[-1] == "":
        out.pop()
    return "\n".join(out)


def rights_of(poet: str) -> tuple[str, str]:
    """The rights line for a poet, and whether the poem is encumbered."""
    death = DEATH.get(poet, "unknown")
    if isinstance(death, int) and death < PD_BEFORE:
        return ("", "公版")
    if death is None:
        return (f"著作权归作者所有 · 在世诗人 · 取自 sheepzh/poetry", "在版")
    if death == "unknown":
        return (f"著作权归作者所有 · 取自 sheepzh/poetry", "在版")
    return (f"著作权归作者所有 · {poet}（卒于 {death}） · 取自 sheepzh/poetry", "在版")


def poets() -> list[str]:
    if not REPO.exists():
        sys.exit(f"{REPO} missing — clone https://github.com/sheepzh/poetry-page "
                 f"into .cache/modern/repo first")
    return sorted(d.name for d in REPO.iterdir()
                  if d.is_dir() and not d.name.startswith("__"))


def records():
    total = 0
    encumbered = 0
    for poet in poets():
        note, rights = rights_of(poet)
        seen: set[tuple[str, str]] = set()
        for page in sorted((REPO / poet).glob("*.json")):
            if page.name == "meta.json":
                continue
            try:
                rows = json.loads(page.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                title = (row.get("title") or "").strip()
                body = clean(row.get("content") or "")
                if not title or len(body) < MIN_CHARS:
                    continue
                # a poem titled after its own poet is the scrape's biography page
                if title == poet and body.count("\n") > 6:
                    continue
                if body.count("\n") + 1 > MAX_LINES:
                    continue
                k = key_of(title, body)
                if k in seen:
                    continue
                seen.add(k)
                total += 1
                if rights != "公版":
                    encumbered += 1
                yield {
                    "title": title,
                    "author": poet,
                    "text": body,
                    "coll": "现代诗",
                    "cat": "",
                    "juan": "",
                    "chapter": "",
                    "note": note,
                    "era": "",
                    "rights": rights,
                    "date": (row.get("date") or "").strip(),
                }
    print(f"  poets {len(poets()):6}")
    print(f"  poems {total:6}  在版 {encumbered}  公版 {total - encumbered}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="one poet")
    args = ap.parse_args()

    if args.only:
        global poets
        base = poets
        poets = lambda: [p for p in base() if p == args.only]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    rows = list(records())
    OUT.write_text(json.dumps(rows, ensure_ascii=False, separators=(",", ":")),
                   encoding="utf-8")
    print(f"records {len(rows)} -> {OUT.relative_to(ROOT)} "
          f"({OUT.stat().st_size / 1024 / 1024:.1f} MiB)")


if __name__ == "__main__":
    main()
