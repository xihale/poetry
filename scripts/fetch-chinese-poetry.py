#!/usr/bin/env python3
"""Read the chinese-poetry checkout in .cache and write one JSON per book.

This is the ingestion half of the corpus: it knows the shape of every file in
the mirror and nothing about the site. Its output is a flat list of records in
the shape scripts/build-corpus.py already reads, so the editorial work — era,
form, mood, dedupe — stays in one place.

The mirror is checked out (not fetched file by file) because 全唐诗 alone is
255 + 58 files totalling 139 MB, and a sparse checkout of the thirteen
directories we want is one round trip:

    git clone --depth 1 --filter=blob:none --no-checkout \\
        https://github.com/chinese-poetry/chinese-poetry .cache/chinese-poetry/repo
    cd .cache/chinese-poetry/repo && git sparse-checkout set --no-cone \\
        '/全唐诗/poet.tang.*.json' ... && git checkout

Everything here is public-domain classical text (the compilers died centuries
ago), so the only editorial question per book is whether it is *poetry*.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = ROOT / ".cache" / "chinese-poetry" / "repo"
OUT = ROOT / ".cache" / "chinese-poetry" / "records.json"

_cc = None


def simp(s: str) -> str:
    """繁体 → 简体, so the corpus is one script end to end.

    The mirror stores 全唐诗 and 御定全唐詩 in 繁體 and the rest in 简体; a reader
    who draws 李白 twice should not get 靜夜思 once and 静夜思 the next time.
    """
    global _cc
    if _cc is None:
        try:
            from opencc import OpenCC
        except ImportError:
            sys.exit("opencc is required: pip install opencc  (or apt install python3-opencc)")
        _cc = OpenCC("t2s")
    return _cc.convert(s)


def rec(*, title: str, text: str, coll: str, author: str = "佚名",
        cat: str = "", juan: str = "", chapter: str = "", era: str = "",
        dynasty: str = "", note: str = "", form: str | None = None) -> dict:
    """One poem, in the shape scripts/build-corpus.py reads."""
    out = {
        "title": title.strip(),
        "author": author.strip() or "佚名",
        "text": text.strip(),
        "coll": coll,
        "cat": cat,
        "juan": juan,
        "chapter": chapter,
        "note": note,
    }
    if era:
        out["era"] = era
    if dynasty:
        out["dynasty"] = dynasty
    if form:
        out["form"] = form
    return out


def paras(rs) -> str:
    """The verse, one 句 to a line. The builder re-breaks it anyway."""
    if isinstance(rs, str):
        rs = [rs]
    return "\n".join(p.strip() for p in rs if p and p.strip())


def load(rel: str):
    path = REPO / rel
    if not path.exists():
        sys.exit(f"{rel} missing from the checkout — re-run the sparse checkout")
    return json.loads(path.read_text(encoding="utf-8"))


# ── the big ones ────────────────────────────────────────────────────────────

def quan_tang():
    """全唐诗 + 全宋诗, 311,855 poems in 313 files of 1000.

    The mirror prints both dynasties under 全唐诗/ (poet.tang.* / poet.song.*);
    全宋诗 is 254,248 of those poems and has to be its own 诗集 or it would bury
    the 57,607 Tang poems eight to one. 全唐诗's own卷次 is not in this file at
    all — the 御定全唐詩 book below is the one that carries it.
    """
    for pat, coll, era in (
        ("全唐诗/poet.tang.*.json", "全唐诗", "唐"),
        ("全唐诗/poet.song.*.json", "全宋诗", "宋"),
    ):
        for f in sorted(REPO.glob(pat)):
            for r in load(f.relative_to(REPO).as_posix()):
                text = paras(r.get("paragraphs"))
                if not text:
                    continue
                yield rec(title=simp(r.get("title", "")), text=simp(text), coll=coll,
                          author=simp(r.get("author", "")), era=era)


def yuding_quan_tang():
    """御定全唐詩: the same 43,103 poems, but filed by the 卷 they are printed in.

    全唐诗 above is a flat dump with no volume; this one is [1-900].json and the
    file *is* the 卷. It is also 繁體 and carries 作者小傳 in `biography`, which
    the site shows as the 解题 when the book gives one.
    """
    for f in sorted(REPO.glob("御定全唐詩/json/*.json")):
        n = int(f.stem)
        juan = f"卷{n}"
        for r in load(f.relative_to(REPO).as_posix()):
            text = paras(r.get("paragraphs"))
            if not text:
                continue
            notes = [x for x in (r.get("notes") or []) if x and x.strip()]
            yield rec(title=simp(r.get("title", "")), text=simp(text),
                      coll="御定全唐詩", author=simp(r.get("author", "")),
                      juan=juan, chapter=juan, era="唐",
                      note=simp("　".join(notes)))


def quan_song_ci():
    """全宋词, 21,053 词. 词 have no title — they are cited 词牌·首句."""
    for f in sorted(REPO.glob("宋词/ci.song.*.json")):
        if f.name in ("ci.song.2019y.json",):
            continue
        for r in load(f.relative_to(REPO).as_posix()):
            text = paras(r.get("paragraphs"))
            if not text:
                continue
            rhythmic = (r.get("rhythmic") or "").strip()
            title = f"{rhythmic}·{first_clause(text)}" if rhythmic else first_clause(text)
            yield rec(title=title, text=text, coll="全宋词",
                      author=r.get("author", ""), era="宋", cat=rhythmic)


# 元曲 is stored with the actors' business inside the verse: (正末唱) (下) (带云).
STAGE = re.compile(r"[（(][^）)]{0,40}[）)]")
# a line that is nothing but a stage direction, or an empty bracket
ONLY_STAGE = re.compile(r"^[（(][^）)]*[）)]?[。，、！？]?$")


def is_direction(line: str) -> bool:
    return bool(ONLY_STAGE.match(line)) and len(line) <= 40


def first_clause(text: str) -> str:
    head = re.split(r"[，。；！？、]", text.strip(), maxsplit=1)[0]
    return head[:14]


# ── the small books ─────────────────────────────────────────────────────────

# 蒙学 is a shelf of primers, not one book: each file is its own 诗集 so a
# reader can ask for 三字经 without also getting 声律启蒙.
MENGXUE = {
    "baijiaxing": "百家姓",
    "dizigui": "弟子规",
    "guwenguanzhi": "古文观止",
    "qianjiashi": "千家诗",
    "qianziwen": "千字文",
    "sanzijing-new": "三字经",
    "shenglvqimeng": "声律启蒙",
    "tangshisanbaishou": "唐诗三百首",
    "wenzimengqiu": "文字蒙求",
    "youxueqionglin": "幼学琼林",
    "zengguangxianwen": "增广贤文",
    "zhuzijiaxun": "朱子家训",
}


def split_author(raw: str) -> tuple[str, str]:
    """蒙学 prints the dynasty inside the name: （唐）孟浩然, 先秦：左丘明."""
    raw = (raw or "").strip()
    dynasty = ""
    m = re.match(r"[（(]\s*([^）)]{1,6})\s*[）)]\s*(.+)", raw)
    if m:
        dynasty, raw = m.group(1).strip(), m.group(2).strip()
    elif "：" in raw:
        head, _, tail = raw.partition("：")
        if len(head) <= 6 and tail.strip():
            dynasty, raw = head.strip(), tail.strip()
    return dynasty, raw


def walk(node, *, book: str, cat: str = "", juan: str = "", depth: int = 0):
    """Yield poems from any of 蒙学's nested shapes.

    The primers nest differently from one another — 千字文 is one run of
    paragraphs, 千家诗 is 體裁 › 篇, 声律启蒙 is 卷 › 韻目 › 對句, 古文观止 is
    卷 › 篇 — but they all bottom out in the same place: a dict carrying
    `paragraphs`. Walking the tree for that leaf beats writing twelve parsers.
    """
    if isinstance(node, list):
        for child in node:
            yield from walk(child, book=book, cat=cat, juan=juan, depth=depth)
        return
    if not isinstance(node, dict):
        return

    here_cat = node.get("type") or cat
    here_juan = juan
    if depth and node.get("title") and not node.get("paragraphs") and not node.get("content"):
        here_juan = juan or node["title"]

    body = node.get("paragraphs")
    if isinstance(body, list) and any(isinstance(p, str) and p.strip() for p in body):
        title = node.get("chapter") or node.get("title") or book
        dynasty, author = split_author(node.get("author", ""))
        text = paras(body)
        if text:
            yield rec(title=title, text=text, coll=book, author=author,
                      dynasty=dynasty, cat=here_cat, juan=here_juan,
                      chapter=here_juan or here_cat)

    child = node.get("content")
    if isinstance(child, list):
        yield from walk(child, book=book, cat=here_cat, juan=here_juan, depth=depth + 1)


def mengxue():
    """蒙学: twelve primers. Each file is its own 诗集 — 三字经 is not 千家诗.

    The shelf is 繁體, so every field is converted on the way out; 三字经 ships
    twice (new/traditional) and only the newer one is read.
    """
    for stem, name in MENGXUE.items():
        f = f"蒙学/{stem}.json"
        if not (REPO / f).exists():
            continue
        for r in walk(load(f), book=name):
            for k in ("title", "text", "cat", "juan", "chapter"):
                r[k] = simp(r[k])
            yield r


def yuanqu():
    """元曲: 11,057 曲 from 233 剧作家 — but not as they are stored.

    The mirror's file is a transcription of whole 杂剧. A record is one 曲牌 of
    one 折, titled 剧名・宫调/曲牌, and 39% of the records have the actors' stage
    directions and spoken lines still welded into the verse — `(正末唱)` `(下)`.
    A reader who draws a 曲 and gets `(下)。` on the screen has been handed a
    script, not a poem.

    So: the 宫调 and 曲牌 are split out of the title (they are the book's own
    divisions, exactly like 乐府诗集's 部类), a record whose body is mostly
    stage business is dropped, and the marks inside the verse are removed —
    the same treatment 乐府诗集's 解题 gets, because it is the same kind of
    apparatus.
    """
    for r in load("元曲/yuanqu.json"):
        body = [p.strip() for p in r.get("paragraphs", []) if p and p.strip()]
        body = [p for p in body if not is_direction(p)]
        if not body:
            continue
        text = "\n".join(body)
        # mostly stage business left over: a script page, not a 曲
        marks = sum(len(m) for m in STAGE.findall(text))
        if marks > len(text) * 0.4:
            continue

        title = r.get("title", "")
        play, _, tail = title.partition("・")
        mode = tail.split("/")[0].strip() if "/" in tail else ""
        qupai = tail.split("/")[-1].strip() if tail else ""
        if not qupai:
            qupai = title
            play = ""
        yield rec(title=qupai, text=STAGE.sub("", text), coll="元曲",
                  author=r.get("author", ""), era="元",
                  cat=mode, juan="", chapter=play)


def shijing():
    """诗经: the file is already one poem per record with its section."""
    for r in load("诗经/shijing.json"):
        yield rec(title=r.get("title", ""), text=paras(r.get("content")),
                  coll="诗经", author="佚名", era="先秦",
                  cat=r.get("section", ""), chapter=r.get("chapter", ""))


def chuci():
    """楚辞: 离骚, 九歌 … are the book's own divisions."""
    for r in load("楚辞/chuci.json"):
        yield rec(title=r.get("title", ""), text=paras(r.get("content")),
                  coll="楚辞", author=r.get("author", "佚名"), era="先秦",
                  cat=r.get("section", ""), chapter=r.get("section", ""))


def nalan():
    for r in load("纳兰性德/纳兰性德诗集.json"):
        yield rec(title=r.get("title", ""), text=paras(r.get("para") or r.get("paragraphs")),
                  coll="纳兰性德诗集", author="纳兰性德", era="清",
                  cat=r.get("type", ""), chapter=r.get("type", ""))


def caocao():
    for r in load("曹操诗集/caocao.json"):
        yield rec(title=r.get("title", ""), text=paras(r.get("paragraphs")),
                  coll="曹操诗集", author="曹操", era="魏晋",
                  cat=r.get("type", ""), chapter=r.get("type", ""))


def huajianji():
    """花间集: ten 卷; the file names carry the number."""
    for f in sorted(REPO.glob("五代诗词/huajianji/huajianji-*-juan.json")):
        num = f.stem.split("-")[1]
        juan = f"卷{'一二三四五六七八九十'[int(num) - 1]}" if num.isdigit() else ""
        for r in load(f.relative_to(REPO).as_posix()):
            yield rec(title=r.get("title", ""), text=paras(r.get("paragraphs")),
                      coll="花间集", author=r.get("author", ""), era="五代",
                      juan=juan, chapter=juan)


def nantang():
    for r in load("五代诗词/nantang/poetrys.json"):
        yield rec(title=r.get("title", ""), text=paras(r.get("paragraphs")),
                  coll="南唐词", author=r.get("author", ""), era="五代")


def lunyu():
    """论语 is not poetry, and it is here anyway: it is the book 白卷 quotes most."""
    for r in load("论语/lunyu.json"):
        yield rec(title=r.get("chapter", "论语"), text=paras(r.get("paragraphs")),
                  coll="论语", author="孔子及弟子", era="先秦", chapter=r.get("chapter", ""))


SISHU = {"daxue": "大学", "zhongyong": "中庸", "mengzi": "孟子"}


def sishu():
    for stem, name in SISHU.items():
        f = f"四书五经/{stem}.json"
        if not (REPO / f).exists():
            continue
        data = load(f)
        items = data if isinstance(data, list) else [data]
        for r in items:
            for i, para in enumerate(r.get("paragraphs", []) or []):
                if not para.strip():
                    continue
                yield rec(title=f"{name}·{i + 1}", text=para, coll=name,
                          author="", era="先秦", cat=r.get("chapter", ""))


def youmengying():
    """幽梦影: 219 则, each a sentence with the friends' marginalia under it."""
    for i, r in enumerate(load("幽梦影/youmengying.json")):
        body = r.get("content", "").strip()
        if not body:
            continue
        comments = [c.strip() for c in (r.get("comment") or []) if c.strip()]
        yield rec(title=f"幽梦影·{i + 1}", text=body, coll="幽梦影",
                  author="张潮", era="清", note="　".join(comments))


def shuimo_tangshi():
    """水墨唐诗: 176 唐诗, each with a prose 赏析 — that is the 解题 here."""
    for r in load("水墨唐诗/shuimotangshi.json"):
        text = paras(r.get("paragraphs"))
        if not text:
            continue
        yield rec(title=r.get("title", ""), text=text, coll="水墨唐诗",
                  author=r.get("author", ""), era="唐",
                  note=(r.get("prologue") or "").strip())


# 御定全唐詩 comes first on purpose: it and the flat 全唐诗 hold the same poems,
# and only 御定 carries the 卷 each one is printed in. The dedupe in
# build-corpus.py keeps the first copy, so the copy that knows its volume wins
# and the 14,000 poems 御定 does not reach still arrive from 全唐诗.
BOOKS = (
    ("御定全唐詩", yuding_quan_tang),
    ("全唐诗 / 全宋诗", quan_tang),
    ("全宋词", quan_song_ci),
    ("元曲", yuanqu),
    ("蒙学", mengxue),
    ("诗经", shijing),
    ("楚辞", chuci),
    ("花间集", huajianji),
    ("南唐词", nantang),
    ("纳兰性德诗集", nalan),
    ("曹操诗集", caocao),
    ("论语", lunyu),
    ("四书五经", sishu),
    ("幽梦影", youmengying),
    ("水墨唐诗", shuimo_tangshi),
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="run one book by name")
    args = ap.parse_args()

    if not REPO.exists():
        sys.exit(f"{REPO.relative_to(ROOT)} missing — run the sparse checkout first")

    records: list[dict] = []
    for name, fn in BOOKS:
        if args.only and args.only != name:
            continue
        before = len(records)
        for r in fn():
            records.append(r)
        print(f"  {name:22} {len(records) - before:7}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(records, ensure_ascii=False, separators=(",", ":")),
                   encoding="utf-8")
    print(f"records: {len(records)}  -> {OUT.relative_to(ROOT)} "
          f"({OUT.stat().st_size / 1024 / 1024:.1f} MiB)")


if __name__ == "__main__":
    main()
