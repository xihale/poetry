#!/usr/bin/env python3
"""Fetch the foreign poetry shelves into .cache/world/records.json.

Five collections, four of them English/French/German originals, one of them a
Chinese translation paired line for line with its original:

  飞鸟集            泰戈尔 Stray Birds, 郑振铎's Chinese against Tagore's English
  莎士比亚十四行诗    Shakespeare's Sonnets (Gutenberg #1041)
  恶之花             Baudelaire, Les Fleurs du Mal (Gutenberg #6099)
  海涅诗歌           Heine, Buch der Lieder (Gutenberg #3498)
  天真与经验之歌      Blake, Songs of Innocence and of Experience (#1934)

Sources, all public domain and all fetched at build time:

  https://zh.wikisource.org/w/index.php?title=飛鳥集&action=raw
      Wikisource's 飛鳥集, 鄭振鐸 譯 (d. 1958, PD in China since 2009; the 1922
      printing is PD in the US). Interleaves Chinese and English inside
      <poem> tags, but transcribes only 54 of the 326 stanzas and omits the
      English for 46 of those.
  https://www.gutenberg.org/cache/epub/6524/pg6524.txt
      Stray Birds, complete: 326 numbered stanzas of Tagore's own English.
      Used only to supply the English the Wikisource page lacks.
  https://www.gutenberg.org/cache/epub/1041/pg1041.txt
  https://www.gutenberg.org/cache/epub/6099/pg6099.txt
  https://www.gutenberg.org/cache/epub/3498/pg3498.txt
  https://www.gutenberg.org/cache/epub/1934/pg1934.txt

Every download lands in .cache/world/ so a re-run with --no-fetch is offline.

Nothing here is translated by us. 飞鸟集's Chinese is 郑振铎's, transcribed by
Wikisource; the other four shelves carry the original text alone, once as
`text` and once as `orig`, and are labelled 原文 · 英文/法文/德文 so a reader is
never shown a line they cannot check against a printed source.
"""
from __future__ import annotations

import argparse
import json
import re
import socket
import sys
import urllib.request
from pathlib import Path

socket.setdefaulttimeout(40)

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".cache" / "world"
OUT = CACHE / "records.json"

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "Chrome/120 Safari/537.36"}

WIKI_STRAY = ("https://zh.wikisource.org/w/index.php?title="
              "%E9%A3%9B%E9%B3%A5%E9%9B%86&action=raw")
PG = {n: f"https://www.gutenberg.org/cache/epub/{n}/pg{n}.txt"
      for n in (6524, 1041, 6099, 3498, 1934)}

FILES = {
    "stray.wiki": WIKI_STRAY,
    "pg6524.txt": PG[6524],
    "pg1041.txt": PG[1041],
    "pg6099.txt": PG[6099],
    "pg3498.txt": PG[3498],
    "pg1934.txt": PG[1934],
}


def get(url: str) -> str:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA)) as r:
        return r.read().decode("utf-8", "ignore")


def fetch(refresh: bool = False) -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    for name, url in FILES.items():
        p = CACHE / name
        if p.exists() and not refresh:
            continue
        print(f"  fetch {name}")
        p.write_text(get(url), encoding="utf-8")


def cached(name: str) -> str:
    p = CACHE / name
    if not p.exists():
        sys.exit(f"{p.relative_to(ROOT)} missing — run without --no-fetch first")
    return p.read_text(encoding="utf-8").replace("\r\n", "\n")


def rec(*, title, text, orig, lang, coll, author, cat="", juan="",
        chapter="", note="", era="", dynasty="") -> dict:
    """One poem, in the shape scripts/build-corpus.py reads.

    era/dynasty stay empty for a foreign poem: the builder fills 时代 from
    FOREIGN_ERA keyed on the 诗集, and never invents a Chinese 朝代 for a
    foreign poet.
    """
    return {
        "title": title.strip(),
        "author": author,
        "text": text.strip(),
        "orig": orig.strip(),
        "lang": lang,
        "coll": coll,
        "cat": cat,
        "juan": juan,
        "chapter": chapter,
        "note": note,
        "era": era,
        "dynasty": dynasty,
    }


# ── shared text helpers ─────────────────────────────────────────────────────

CJK = re.compile(r"[\u4e00-\u9fff]")
LATIN = re.compile(r"[A-Za-z]")
ROMAN = re.compile(r"^[IVXLCDM]+$")
ROMAN_VAL = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
PICTURE = re.compile(r"^\s*\[(?:Picture|Illustration)[^\]]*\]\s*$")
TEMPLATE = re.compile(r"\{\{[^{}]*\}\}")
# a line that is still markup — an unclosed brace, a tag, a table cell — is
# apparatus, never verse; the etext is hand-transcribed and uneven
WIKITEXT = re.compile(r"[{}]|<[^>]*>|^\||^!|^\[\[")


def strip_templates(text: str) -> str:
    """Remove MediaWiki `{{…}}` templates, innermost first.

    The 飛鳥集 page ends with `{{translation license|original={{Pd|1941|1916}}|
    translation={{Pd|1958|1922}}}}`, so one non-recursive pass leaves the
    outer braces and their Latin parameter names behind — and those would then
    be read as the English half of the last stanza.
    """
    for _ in range(10):
        stripped = TEMPLATE.sub("", text)
        if stripped == text:
            return stripped
        text = stripped
    return text


def roman_to_int(s: str) -> int:
    total = prev = 0
    for ch in reversed(s.upper()):
        v = ROMAN_VAL[ch]
        total += -v if v < prev else v
        prev = max(prev, v)
    return total


def gutenberg(name: str) -> list[str]:
    """The body of a Gutenberg text: header, footer, credits and pictures gone."""
    text = cached(name)
    start = text.find("*** START OF")
    end = text.find("*** END OF")
    if start == -1 or end == -1:
        sys.exit(f"{name}: no *** START/END *** markers")
    body = text[text.index("\n", start) + 1:end]
    out = []
    for line in body.split("\n"):
        if PICTURE.match(line):
            continue
        if line.startswith("Ende dieses Projekt Gutenberg"):
            break
        if line.startswith("Produced by") or line.startswith("This etext was produced"):
            continue
        out.append(line.rstrip())
    # collapse the tail of blank lines
    while out and not out[-1].strip():
        out.pop()
    return out


def blank(a: str) -> bool:
    return not a.strip()


def paragraphs(lines: list[str], after: str | None = None) -> list[list[str]]:
    """The text split into paragraphs on blank lines, verse lines kept whole.

    Both #6099 and #3498 set a heading off from the verse by blank lines, so a
    heading is a paragraph of its own and the verse is the paragraphs after it.
    """
    if after is not None:
        lines = lines[next(i for i, l in enumerate(lines) if l.strip() == after):]
    out: list[list[str]] = []
    cur: list[str] = []
    for line in lines:
        if blank(line):
            if cur:
                out.append(cur)
                cur = []
            continue
        cur.append(line)
    if cur:
        out.append(cur)
    return out


def heading_run(paras: list[list[str]], is_head, start: int) -> tuple[list[str], int]:
    """Consume the heading paragraphs at `start`, returning their lines."""
    group: list[str] = []
    while start < len(paras) and all(is_head(l) for l in paras[start]):
        group.extend(l.strip() for l in paras[start])
        start += 1
    return group, start


def verse_run(paras: list[list[str]], is_head, start: int,
              drop=()) -> tuple[list[str], int]:
    """Consume the verse paragraphs at `start`; return its lines and the rest."""
    verse: list[str] = []
    while start < len(paras) and not all(is_head(l) for l in paras[start]):
        if not all(l.strip() in drop for l in paras[start]):
            verse.extend(l.strip() for l in paras[start])
        start += 1
    return verse, start


# ── 飞鸟集 ──────────────────────────────────────────────────────────────────

# a sentence break, with any closing quote carried onto the first sentence
SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[“\"'‘A-Z])"
                      r"|(?<=[.!?][”\"'’])\s+(?=[“\"'‘A-Z])")


def stray_wiki() -> dict[int, tuple[list[str], list[str]]]:
    """The Wikisource page as {number: (chinese lines, english lines)}.

    The page transcribes 54 stanzas, and only 8 of those with the English;
    the rest arrive with Chinese alone and get their English from Gutenberg.
    """
    raw = strip_templates(cached("stray.wiki"))
    chunks = re.split(r"^==\s*([0-9０-９]+)\s*==\s*$", raw, flags=re.M)
    out: dict[int, tuple[list[str], list[str]]] = {}
    for num, body in zip(chunks[1::2], chunks[2::2]):
        n = int(num.translate(str.maketrans("０１２３４５６７８９",
                                            "0123456789")))
        lines = [l.strip() for l in re.sub(r"<[^>]+>", "", body).split("\n")]
        lines = [l for l in lines if l and not WIKITEXT.search(l)]
        zh = [l for l in lines if CJK.search(l)]
        en = [l for l in lines if LATIN.search(l) and not CJK.search(l)]
        out[n] = (zh, en)
    return out


def stray_gutenberg() -> dict[int, str]:
    """The 326 stanzas of Stray Birds, each unwrapped to one run of text."""
    out: dict[int, str] = {}
    cur: int | None = None
    buf: list[str] = []
    for line in gutenberg("pg6524.txt"):
        if re.fullmatch(r"\d+", line.strip()):
            if cur is not None:
                out[cur] = " ".join(buf)
            cur, buf = int(line.strip()), []
        elif cur is not None:
            if line.strip():
                buf.append(line.strip())
    if cur is not None:
        out[cur] = " ".join(buf)
    return out


def stray_birds() -> tuple[list[dict], int, int]:
    """Pair 郑振铎's Chinese with Tagore's English by stanza number 1..326.

    A stanza is emitted only when both halves exist. The Chinese half exists
    for 54 stanzas; the English comes from Wikisource where the page carries
    it (8 stanzas, its own line breaks) and from Gutenberg otherwise, where
    the run is re-broken at sentence ends so the two halves read alike.
    """
    wiki = stray_wiki()
    english = stray_gutenberg()
    recs: list[dict] = []
    dropped = 0
    for n in range(1, 327):
        zh, en = wiki.get(n, ([], []))
        if not zh:
            dropped += 1
            continue
        if en:
            en_lines = en
        else:
            text = english.get(n, "")
            en_lines = [p for p in SENTENCE.split(text) if p.strip()]
        if not en_lines:
            dropped += 1
            continue
        recs.append(rec(title=f"飞鸟集·{n}", text="\n".join(zh),
                        orig="\n".join(en_lines), lang="en", coll="飞鸟集",
                        author="泰戈尔", cat="", note="郑振铎 译"))
    return recs, len(recs), dropped


# ── 莎士比亚十四行诗 ────────────────────────────────────────────────────────

def sonnets() -> list[dict]:
    """Gutenberg #1041: CLIV sonnets, each a Roman numeral then 14 lines."""
    lines = gutenberg("pg1041.txt")
    heads = [i for i, l in enumerate(lines)
             if not l.startswith((" ", "\t")) and ROMAN.match(l.strip())]
    recs: list[dict] = []
    for k, i in enumerate(heads):
        end = heads[k + 1] if k + 1 < len(heads) else len(lines)
        verse = [l.strip() for l in lines[i + 1:end] if l.strip()]
        if not verse:
            continue
        n = roman_to_int(lines[i].strip())
        recs.append(rec(title=f"十四行诗·{n}", text="\n".join(verse),
                        orig="\n".join(verse), lang="en",
                        coll="莎士比亚十四行诗", author="莎士比亚",
                        note="原文 · 英文"))
    return recs


# ── 恶之花 ──────────────────────────────────────────────────────────────────

# the book's own divisions, printed in caps like the poem titles
FLEURS_SECTIONS = {
    "SPLEEN ET IDÉAL", "TABLEAUX PARISIENS", "LE VIN", "RÉVOLTE",
    "LA MORT", "PIÈCES CONDAMNÉES",
}
FR_SMALL = {"de", "du", "des", "le", "la", "les", "un", "une", "et", "a", "à",
            "au", "aux", "en", "d", "l", "sur", "dans", "pour", "par", "sans"}
CAPS = re.compile(r"^ {2}([A-ZÀ-ÖØ-Þ][A-ZÀ-ÖØ-Þ0-9' \-.,]{1,})$")
FLEURS_NUM = re.compile(r"^ {2}[IVXLCDM]+$")


def fr_head(line: str) -> bool:
    """A heading line in #6099: a caps title, a Roman numeral, or a section."""
    return bool(CAPS.match(line) or FLEURS_NUM.match(line)
                or line.strip() in FLEURS_SECTIONS)


def fr_title(s: str) -> str:
    """ALL-CAPS French typesetting back into ordinary title case."""
    parts = []
    for i, w in enumerate(s.lower().replace("_", "").split()):
        if i and w in FR_SMALL:
            parts.append(w)
            continue
        segs = w.split("'")
        word = segs[0][:1].upper() + segs[0][1:]
        for sg in segs[1:]:
            word += "'" + (sg if len(sg) <= 2 and sg in FR_SMALL
                           else sg[:1].upper() + sg[1:])
        parts.append(word)
    return " ".join(parts)


def fleurs() -> list[dict]:
    """Gutenberg #6099: Les Fleurs du Mal, sectioned and titled in caps.

    Each heading is set off by blank lines, so a heading is the run of caps
    and Roman-numeral paragraphs before the verse; the first cap is the title
    and any later ones are the dedication or part name printed under it. A
    Roman numeral is a numbered part, and since the parts of Un Fantôme and
    Le Voyage are separate poems, each becomes its own record under the poem's
    title. The section heading (Spleen et Idéal …) is the `cat`.
    """
    paras = paragraphs(gutenberg("pg6099.txt"), after="AU LECTEUR")
    recs: list[dict] = []
    section = ""
    base = ""      # the poem a numbered part belongs to
    i = 0
    while i < len(paras):
        group, i = heading_run(paras, fr_head, i)
        if not group:
            i += 1
            continue
        if group[0] in FLEURS_SECTIONS:
            section = fr_title(group[0])
            base = ""
            group = group[1:]
        verse, i = verse_run(paras, fr_head, i)
        if not group:
            continue
        caps = [g for g in group if not ROMAN.match(g)]
        nums = [g for g in group if ROMAN.match(g)]
        note = ["原文 · 法文"]
        if caps:
            title = fr_title(caps[0])
            note += [fr_title(c) for c in caps[1:]]
            if nums:
                base = title
                title = f"{title}·{nums[-1]}"
        elif nums:
            title = f"{base}·{nums[-1]}" if base else nums[-1]
        else:
            continue
        if not verse:
            base = title.split("·")[0]
            continue
        recs.append(rec(title=title, text="\n".join(verse),
                        orig="\n".join(verse), lang="fr", coll="恶之花",
                        author="波德莱尔", cat=section,
                        note=" · ".join(note)))
    return recs


# ── 海涅诗歌 ────────────────────────────────────────────────────────────────

# Buch der Lieder's own cycles, as the etext prints them on a line of their
# own. Everything else in a heading slot is a poem title, a dedication, or a
# number — Götterdämmerung and Bergidylle are poems, not shelves.
HEINE_GROUPS = {
    "Junge Leiden", "Traumbilder", "Lieder", "Romanzen", "Sonette",
    "Lyrisches Intermezzo", "Die Heimkehr", "Aus der Harzreise",
    "Die Nordsee", "Erster Zyklus", "Zweiter Zyklus",
}
# "An meine Mutter, B. Heine, / geborene von Geldern" is the one heading the
# etext breaks over two lines; every other heading is a line of its own.
HEINE_SPLIT = "An meine Mutter, B. Heine,"
NUMERAL = re.compile(r"^(?:[IVXLCDM]{1,10}|\d{1,2}|l)$")
HEINE_YEAR = re.compile(r"^\d{4}(?:[-–]\d{4})?$")


def heine_head(line: str) -> bool:
    """A heading line in #3498: a title, a group name, a number, or a star row.

    Headings are unindented, short, and unpunctuated; verse is not. The two
    exceptions are the title the etext wraps onto a second line and the
    `(Stammbuchblatt)` sub-title in parentheses.
    """
    s = line.strip()
    if not s or line.startswith((" ", "\t")):
        return False
    if (s in HEINE_GROUPS or s == "* * *" or NUMERAL.match(s)
            or HEINE_YEAR.match(s)):
        return True
    if s == HEINE_SPLIT or s.startswith("("):
        return True
    if s.endswith(".") and len(s) <= 40 and s[-2:-1].isupper():
        # a title the etext abbreviates: "An H.S.", "Fresko-Sonette an
        # Christian S." — verse never ends on a capital before a full stop
        return True
    return len(s) <= 60 and s[-1] not in ',;:.!?"\'’—»'


def heine_names(group: list[str]) -> list[tuple[int, str]]:
    """Heading lines that are names, as (index, name), continuations folded.

    The etext wraps one title over two lines ("An meine Mutter, B. Heine," /
    "geborene von Geldern"); a lower-case continuation belongs to the name
    above it.
    """
    out: list[tuple[int, str]] = []
    for k, g in enumerate(group):
        if (g in HEINE_GROUPS or g == "* * *" or NUMERAL.match(g)
                or HEINE_YEAR.match(g)):
            continue
        if out and g[:1].islower():
            out[-1] = (out[-1][0], f"{out[-1][1]} {g}")
        else:
            out.append((k, g))
    return out


def first_verse(verse: list[str]) -> str:
    """The title German Wikisource gives a poem the etext leaves untitled.

    Its Editionsrichtlinien for this very etext: a poem without an explicit
    name is filed under its first verse, with a trailing comma, semicolon or
    colon dropped, and an exclamation or question mark kept.
    """
    head = verse[0].strip().strip("«»\"'")
    return head[:-1] if head.endswith((",", ";", ":")) else head


def heine() -> list[dict]:
    """Gutenberg #3498: Buch der Lieder, filed under its cycles.

    Every heading is a paragraph of its own, so a heading is any paragraph
    whose lines all look like headings — a cycle or group name, a poem title,
    a dedication, a number, or the `* * *` the etext prints for an untitled
    piece. A numeral before a title is the cycle's numbering; a numeral after
    one numbers a part of that poem, as Der arme Peter's three parts and Die
    Nordsee's twelve do. A numbered heading with no title of its own is an
    untitled poem, and takes its first verse as its title, the way Wikisource
    files this very text.
    """
    paras = paragraphs(gutenberg("pg3498.txt"), after="Junge Leiden")
    recs: list[dict] = []
    cat = ""
    part_of = ""   # the poem a bare number continues
    i = 0
    while i < len(paras):
        group, i = heading_run(paras, heine_head, i)
        if not group:
            i += 1
            continue
        if group[0].startswith("Ende dieses Projekt Gutenberg"):
            break
        for g in group:
            if g in ("Erster Zyklus", "Zweiter Zyklus"):
                cat = f"Die Nordsee·{g}"
            elif g in HEINE_GROUPS:
                cat = g
        names = heine_names(group)
        verse, i = verse_run(paras, heine_head, i, drop=("* * *",))
        if names:
            k, title = names[0]
            parts = [g for g in group[k + 1:] if NUMERAL.match(g)]
            if parts:
                num = "1" if parts[0] == "l" else parts[0]
                title = f"{title}·{num}"
                part_of = names[0][1]
            else:
                part_of = ""
        elif part_of:
            num = next((g for g in group if NUMERAL.match(g)), "")
            title = f"{part_of}·{'1' if num == 'l' else num}"
        else:
            # untitled: the etext gives only a number or a `* * *`
            title = first_verse(verse) if verse else cat
        if not verse:
            continue
        recs.append(rec(title=title, text="\n".join(verse),
                        orig="\n".join(verse), lang="de", coll="海涅诗歌",
                        author="海涅", cat=cat, note="原文 · 德文"))
    return recs


# ── 天真与经验之歌 ──────────────────────────────────────────────────────────

def blake() -> list[dict]:
    """Gutenberg #1934: the two song books, titled as the CONTENTS lists them.

    The verse prints its titles in caps, so the CONTENTS block is kept as the
    authority on their real casing, and the section heading decides whether a
    poem is filed under Innocence or Experience.
    """
    lines = gutenberg("pg1934.txt")
    first = next(i for i, l in enumerate(lines)
                 if l.startswith("SONGS OF INNOCENCE"))
    lines = lines[first:]

    full = gutenberg("pg1934.txt")
    # the CONTENTS block comes before the verse, in ordinary case
    contents: dict[str, list[str]] = {"Innocence": [], "Experience": []}
    where = "Innocence"
    ci = full.index("CONTENTS")
    cj = next(i for i in range(ci, len(full)) if full[i] == "SONGS OF INNOCENCE")
    for l in full[ci + 1:cj]:
        s = l.strip()
        if not s:
            continue
        if s.startswith("SONGS OF "):
            where = "Experience" if "EXPERIENCE" in s else "Innocence"
            continue
        contents[where].append(s)

    def real_title(caps: str) -> str:
        key = re.sub(r"[^a-z]", "", caps.lower())
        for sec in ("Innocence", "Experience"):
            for t in contents[sec]:
                if re.sub(r"[^a-z]", "", t.lower()) == key:
                    return t
        return caps.title()

    heads = [i for i, l in enumerate(lines)
             if l.startswith(("SONGS OF ", "CONTENTS")) or
             (l.strip() and not l.startswith((" ", "\t")) and
              l.strip().upper() == l.strip() and LATIN.search(l)
              and len(l.strip()) > 2 and not re.fullmatch(r"[^A-Za-z]+", l.strip()))]
    recs: list[dict] = []
    cat = ""
    for k, i in enumerate(heads):
        s = lines[i].strip()
        if s.startswith("SONGS OF ") or s == "CONTENTS":
            if "INNOCENCE" in s:
                cat = "Innocence"
            elif "EXPERIENCE" in s:
                cat = "Experience"
            continue
        end = heads[k + 1] if k + 1 < len(heads) else len(lines)
        verse = [l.strip() for l in lines[i + 1:end] if l.strip()]
        if not verse:
            continue
        recs.append(rec(title=real_title(s), text="\n".join(verse),
                        orig="\n".join(verse), lang="en",
                        coll="天真与经验之歌", author="布莱克", cat=cat,
                        note="原文 · 英文"))
    return recs


# ── driver ──────────────────────────────────────────────────────────────────

BOOKS = (
    ("飞鸟集", lambda: stray_birds()[0]),
    ("莎士比亚十四行诗", sonnets),
    ("恶之花", fleurs),
    ("海涅诗歌", heine),
    ("天真与经验之歌", blake),
)

SAMPLES = ("飞鸟集", "莎士比亚十四行诗", "恶之花")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-fetch", action="store_true",
                    help="parse the cache only, never touch the network")
    ap.add_argument("--refresh", action="store_true",
                    help="re-download even what is already cached")
    args = ap.parse_args()

    CACHE.mkdir(parents=True, exist_ok=True)
    if not args.no_fetch:
        fetch(refresh=args.refresh)

    records: list[dict] = []
    per: dict[str, list[dict]] = {}
    for name, fn in BOOKS:
        got = fn()
        per[name] = got
        records.extend(got)
        print(f"  {name:12} {len(got):5}")

    sb, paired, dropped = stray_birds()
    print(f"  飞鸟集: paired {paired}, dropped {dropped} (no Chinese on Wikisource)")

    OUT.write_text(json.dumps(records, ensure_ascii=False, separators=(",", ":")),
                   encoding="utf-8")
    print(f"records: {len(records)}  -> {OUT.relative_to(ROOT)} "
          f"({OUT.stat().st_size / 1024:.0f} KiB)")

    for name in SAMPLES:
        r = per[name][0]
        print(f"\n── {name} · {r['title']} [{r['lang']}] {r['note']}")
        print("   text: " + " / ".join(r["text"].split("\n")[:3]))
        print("   orig: " + " / ".join(r["orig"].split("\n")[:3]))


if __name__ == "__main__":
    main()
