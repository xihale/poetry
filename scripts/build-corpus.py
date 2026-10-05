#!/usr/bin/env python3
"""Build the site corpus from canonical Chinese poetry anthologies.

Sources (all from the MIT-licensed chinese-poetry dataset):
    诗经          305 首   先秦 · 佚名
    楚辞           65 篇   先秦 · 屈原等
    曹操诗集       26 首   汉   · 曹操
    唐诗三百首    366 首   唐   · 86 位诗人
    宋词三百首    280 首   宋   · 83 位词人
    纳兰词        258 首   清   · 纳兰性德

Writes public/corpus.json. Facets are derived at runtime from the corpus, so
this file stays the single source of truth.

    python3 scripts/build-corpus.py            # uses .cache/, fetches if cold
    python3 scripts/build-corpus.py --refresh  # force re-download

Axes marked "editorial" below (mood, perspective) are curated by this script,
not by the source data: mood prefers the source's own tags when a collection
has them, otherwise a conservative keyword lexicon; a poem with no confident
match is simply absent from that facet rather than being guessed into one.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".cache" / "corpus"
OUT = ROOT / "public" / "corpus.json"

RAW = "https://raw.githubusercontent.com/chinese-poetry/chinese-poetry/master"

# ------------------------------------------------------------ editorial axes
#
# Both axes below are read off the text itself rather than inferred from it:
# a poem joins 「愁」 because it contains 愁/泪/断肠, not because a model decided
# it felt sad. That keeps every facet checkable against the poem on screen, and
# it applies uniformly to all six collections (only 唐诗三百首 ships tags).

MOOD_LEXICON: dict[str, tuple[str, ...]] = {
    "愁": ("愁", "恨", "怨", "悲", "伤", "哀", "苦", "叹", "泪", "泣", "啼",
           "凄", "痛", "怆", "惆", "怅", "断肠", "销魂", "伤心"),
    "思": ("思", "忆", "念", "梦", "怀", "恋", "盼", "望乡", "归心"),
    "独": ("独", "孤", "单", "无眠", "无人"),
    "欢": ("喜", "乐", "欢", "笑", "悦", "畅", "娱", "嬉", "赏心"),
    "闲": ("闲", "逸", "幽", "静", "澹", "悠然", "恬"),
    "壮": ("豪", "壮", "雄", "烈", "慷慨", "愤", "怒", "剑", "戈", "万里",
           "千秋", "丈夫", "功名"),
    "惊": ("惊", "惧", "恐", "怕", "骇", "愕"),
}

# perspective <- grammar, not reading. 第一人称 and 第二人称 are unambiguous
# pronouns; 君 is only second-person in the set phrases below, never in 君子.
VIEW_LEXICON: dict[str, tuple[str, ...]] = {
    "我": ("我", "吾", "余", "予", "妾", "侬", "吾辈", "我辈"),
    "你": ("尔", "汝", "卿", "君不见", "劝君", "与君", "问君", "逢君",
           "送君", "知君", "感君", "为君", "忆君", "思君", "赠君", "寄君"),
    "他": ("其人", "斯人", "彼", "之子", "伊人"),
    "谁": ("谁", "何", "安得", "岂", "焉", "胡为", "何以", "几时", "何时"),
    "天地": ("天地", "千古", "万古", "人间", "古今", "四海", "八荒", "宇宙",
             "苍生", "九州", "六合"),
}

FORM_BY_TAG = {
    "五言律诗": "五言", "七言律诗": "七言",
    "五言绝句": "五言", "七言绝句": "七言",
    "五言古诗": "五言", "七言古诗": "七言",
}


def _hits(text: str, lexicon: dict[str, tuple[str, ...]], cap: int) -> list[str]:
    found = [k for k, words in lexicon.items() if any(w in text for w in words)]
    return found[:cap]


def guess_form(lines: list[str], book: str) -> str:
    """Verse form from the actual line lengths, or 词 for the 词 collections."""
    if book in ("宋词三百首", "纳兰词"):
        return "词"
    if book == "楚辞":
        return "骚体"
    lens: list[int] = []
    for ln in lines:
        for seg in re.split(r"[，。；！？、]", ln):
            seg = seg.strip()
            if seg:
                lens.append(len(seg))
    if not lens:
        return "古体"
    common = max(set(lens), key=lens.count)
    # mixed line lengths are 杂言; the counts here are overwhelmingly regular
    if lens.count(common) / len(lens) < 0.6:
        return "杂言"
    return {4: "四言", 5: "五言", 7: "七言"}.get(common, "杂言")


def length_band(chars: int) -> str:
    if chars <= 40:
        return "短"
    if chars <= 120:
        return "中"
    return "长"

# ---------------------------------------------------------------- conversion

def t2s(text: str) -> str:
    """Traditional -> simplified, for the collections that ship traditional."""
    try:
        from opencc import OpenCC
    except ImportError:  # pragma: no cover
        raise SystemExit("need opencc: pacman -S opencc  /  pip install opencc")
    global _cc
    try:
        _cc
    except NameError:
        _cc = OpenCC("t2s")
    return _cc.convert(text)


# ------------------------------------------------------------------ assembly

def load(name: str, refresh: bool) -> list:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{name}.json"
    if refresh or not path.exists():
        url = SOURCES[name]
        with urllib.request.urlopen(url, timeout=60) as r:
            path.write_bytes(r.read())
        print(f"  fetched {name} ({path.stat().st_size / 1024:.0f} KiB)")
    return json.loads(path.read_text(encoding="utf-8"))


def clean_lines(raw: list[str]) -> list[str]:
    out = []
    for ln in raw:
        ln = t2s(ln).strip()
        if ln:
            out.append(ln)
    return out


def build(refresh: bool) -> list[dict]:
    poems: list[dict] = []

    def add(title, author, era, book, lines):
        lines = clean_lines(lines)
        if not lines:
            return
        text = "\n".join(lines)
        body = text.replace("\n", "")
        chars = len(re.sub(r"[^\u4e00-\u9fff]", "", body))
        poems.append({
            "title": t2s(title).strip(),
            "author": t2s(author).strip(),
            "era": era,
            "book": book,
            "form": guess_form(lines, book),
            "mood": _hits(body, MOOD_LEXICON, 3),
            "view": _hits(body, VIEW_LEXICON, 2),
            "len": length_band(chars),
            "text": text,
            "chars": chars,
        })

    for p in load("shijing", refresh):
        add(p["title"], "佚名", "先秦", "诗经", p["content"])

    for p in load("chuci", refresh):
        add(p["title"], p.get("author") or "佚名", "先秦", "楚辞", p["content"])

    for p in load("caocao", refresh):
        add(p["title"], "曹操", "汉", "曹操诗集", p["paragraphs"])

    for p in load("tang300", refresh):
        add(p["title"], p.get("author") or "佚名", "唐", "唐诗三百首",
            p["paragraphs"])

    for p in load("song300", refresh):
        add(p["rhythmic"], p.get("author") or "佚名", "宋", "宋词三百首",
            p["paragraphs"])

    for p in load("nalan", refresh):
        add(p["title"], p.get("author") or "纳兰性德", "清", "纳兰词", p["para"])

    return poems


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    poems = build(args.refresh)

    # drop exact repeats (the collections overlap a little)
    seen: set[tuple[str, str]] = set()
    unique = []
    for p in poems:
        key = (p["title"], p["text"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(p)

    # stable ids
    for i, p in enumerate(unique):
        p["id"] = i
    # a collection with one author (曹操诗集, 纳兰词) already implies the poet,
    # so a leaf can name the book alone instead of repeating both
    authors_by_book: dict[str, set[str]] = {}
    for p in unique:
        authors_by_book.setdefault(p["book"], set()).add(p["author"])
    for p in unique:
        p["solo"] = len(authors_by_book[p["book"]]) == 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(unique, ensure_ascii=False, separators=(",", ":")),
                   encoding="utf-8")

    books: dict[str, int] = {}
    eras: dict[str, int] = {}
    for p in unique:
        books[p["book"]] = books.get(p["book"], 0) + 1
        eras[p["era"]] = eras.get(p["era"], 0) + 1
    tagged = sum(1 for p in unique if p["mood"])
    viewed = sum(1 for p in unique if p["view"])

    print(f"\n{len(unique)} poems  ({OUT.stat().st_size / 1024:.0f} KiB)")
    print("  books:", ", ".join(f"{k} {v}" for k, v in books.items()))
    print("  eras: ", ", ".join(f"{k} {v}" for k, v in sorted(eras.items())))
    print(f"  mood tagged {tagged}/{len(unique)}, perspective tagged {viewed}/{len(unique)}")
    print(f"  poets: {len({p['author'] for p in unique})}")


if __name__ == "__main__":
    main()
