#!/usr/bin/env python3
"""Turn the fetched anthologies in .cache into the site corpus.

Input : .cache/guwendao/yuefu.json            (from scripts/fetch-yuefu.py)
        .cache/chinese-poetry/records.json    (from scripts/fetch-chinese-poetry.py)
Output: public/corpus.json

Two kinds of label live in a record, and they are kept apart on purpose:

  coll / cat   the anthology the poem was printed in and its own division
               (乐府诗集 · 相和歌辞, 诗经 · 周南). Editorial, from the source's
               table of contents — never re-derived from the text.
  era / form / mood / view / len
               read off the poem itself. mood and view are lexicon hits, so
               every tag is checkable against the words on the screen.

era prefers the dynasty printed beside the author. When the source prints a
bare name, the dynasty is taken from the same author's labelled appearances
elsewhere in the anthology; only if that fails does it become 不详.

The same poem is often printed in more than one anthology — 短歌行 is in both
曹操诗集 and 乐府诗集. It is carried once, under the first anthology that has
it, because a reader asking for 曹操 wants the poet, not two copies.
"""
from __future__ import annotations

import argparse
import array
import gzip
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import anthology

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".cache" / "guwendao"
CHINESE_POETRY = ROOT / ".cache" / "chinese-poetry" / "records.json"
WORLD = ROOT / ".cache" / "world" / "records.json"
MODERN = ROOT / ".cache" / "modern" / "records.json"
OUT = ROOT / "public" / "corpus"

# The corpus is one file per book, not one file for everything. At 376,000 poems
# a single corpus.json is 160 MB and every reader downloads all of it to see one
# poem. Split by 诗集 the site can fetch the index, then only the books the
# reader actually draws from — and a reader who only ever opens 诗经 never pays
# for 全宋诗.
#
# The split is by `coll`, with the giant books cut into several parts by id so no
# single response is unmanageable: a chunk is fetched on demand and cached by the
# browser, and the pager asks for the next one as it runs out of poems.
CHUNK = 60_000

# ------------------------------------------------------------ editorial axes

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

# 词牌 are a closed class, which makes them a reliable signal: a title of the
# form 词牌·题目 is a 词, and 无题·… is not, because 无题 is not a 词牌.
CIPAI = {
    "水仙子", "临江仙", "一丛花", "点绛唇", "浣溪沙", "蝶恋花", "鹧鸪天",
    "菩萨蛮", "如梦令", "虞美人", "水调歌头", "念奴娇", "满江红", "声声慢",
    "雨霖铃", "青玉案", "破阵子", "渔家傲", "江城子", "卜算子", "清平乐",
    "忆秦娥", "西江月", "南乡子", "踏莎行", "苏幕遮", "少年游", "醉花阴",
    "浪淘沙", "望江南", "长相思", "生查子", "木兰花", "玉楼春", "采桑子",
    "诉衷情", "定风波", "行香子", "风流子", "喜迁莺", "桂枝香", "齐天乐",
    "高阳台", "解语花", "六丑", "兰陵王", "瑞龙吟", "莺啼序", "疏影",
    "暗香", "扬州慢", "一萼红", "八声甘州", "石州慢", "寿楼春", "三姝媚",
    "贺新郎", "永遇乐", "洞仙歌", "琐窗寒", "法曲献仙音", "天仙子",
}

# 乐府诗集 prints southern-dynasty 宋 齐 梁 陈, never 赵宋.
DYNASTY_ERA = {
    "先秦": "先秦", "秦": "秦", "前汉": "汉", "后汉": "汉", "两汉": "汉",
    "汉": "汉", "魏": "魏晋", "晋": "魏晋", "宋": "南北朝", "齐": "南北朝",
    "梁": "南北朝", "陈": "南北朝", "北魏": "南北朝", "北齐": "南北朝",
    "北周": "南北朝", "隋": "隋", "唐": "唐", "五代": "五代",
    # 蒙学 prints the dynasty as 唐代 / 兩漢 and 全唐诗's 繁體 files spell it
    # 劉長卿-style; both are the same label as the plain form, and a facet that
    # lists 唐 and 唐代 separately is a facet that lies about the corpus.
    "唐代": "唐", "兩漢": "汉", "汉代": "汉", "宋代": "宋", "明代": "明",
    # 繁體 spellings that arrive from 御定全唐詩 and 蒙学
    "魏晉": "魏晋", "南北朝": "南北朝", "隋代": "隋", "唐代": "唐",
    "清代": "清", "元代": "元", "魏晋南北朝": "魏晋", "南北朝时期": "南北朝",
    "五代十国": "五代", "隋代": "隋", "秦代": "秦", "先秦时期": "先秦",
}

# Bare names the anthology never labels: filled from the standard histories.
ERA_BY_AUTHOR = {
    "伯夷": "先秦", "宋玉": "先秦", "荆轲": "先秦", "项羽": "秦",
    "苏武": "汉", "李陵": "汉", "卓文君": "汉", "班婕妤": "汉",
    "赵飞燕": "汉", "蔡琰": "汉", "辛延年": "汉", "崔骃": "汉",
    "杨恽": "汉", "张衡": "汉", "曹操": "魏晋", "曹丕": "魏晋",
    "曹植": "魏晋", "王粲": "魏晋", "陈琳": "魏晋", "阮籍": "魏晋",
    "嵇康": "魏晋", "左思": "魏晋", "陆机": "魏晋", "张华": "魏晋",
    "傅玄": "魏晋", "石崇": "魏晋", "刘琨": "魏晋", "陶渊明": "魏晋",
    "谢灵运": "南北朝", "鲍照": "南北朝", "谢朓": "南北朝", "江淹": "南北朝",
    "沈约": "南北朝", "何逊": "南北朝", "吴均": "南北朝", "萧衍": "南北朝",
    "萧纲": "南北朝", "萧统": "南北朝", "徐陵": "南北朝", "庾信": "南北朝",
    "王褒": "南北朝", "卢思道": "隋", "杨广": "隋", "薛道衡": "隋",
    "李白": "唐", "杜甫": "唐", "王维": "唐", "白居易": "唐", "元稹": "唐",
    "刘禹锡": "唐", "李贺": "唐", "温庭筠": "唐", "李商隐": "唐",
    "王建": "唐", "张籍": "唐", "孟郊": "唐", "韩愈": "唐", "柳宗元": "唐",
    "刘希夷": "唐", "张若虚": "唐", "陈子昂": "唐", "沈佺期": "唐",
    "宋之问": "唐", "卢照邻": "唐", "骆宾王": "唐", "王勃": "唐",
    "杨炯": "唐", "张九龄": "唐", "崔颢": "唐", "高适": "唐", "岑参": "唐",
    "王昌龄": "唐", "李颀": "唐", "韦应物": "唐", "刘长卿": "唐",
    "钱起": "唐", "郎士元": "唐", "李益": "唐", "令狐楚": "唐",
    "张祜": "唐", "杜牧": "唐", "许浑": "唐", "赵嘏": "唐", "马戴": "唐",
    "聂夷中": "唐", "于濆": "唐", "于鹄": "唐", "储光羲": "唐",
    "丁仙芝": "唐", "乔知之": "唐", "刘方平": "唐", "刘商": "唐",
    "长孙无忌": "唐", "谢偃": "唐", "杜易简": "唐", "陈羽": "唐",
    "皎然": "唐", "贯休": "唐", "齐己": "唐", "子兰": "唐",
    "欧阳修": "宋", "苏轼": "宋", "黄庭坚": "宋", "陆游": "宋",
    "杨万里": "宋", "范成大": "宋", "姜夔": "宋", "辛弃疾": "宋",
}

CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
# guwendao prefixes a doubt marker: ※谢超宗
JUNK = re.compile(r"[※*†\s]|（[^）]*）|\([^)]*\)")


def clause_lengths(text: str) -> list[int]:
    """Lengths of the metrical clauses, split on punctuation, ignoring non-CJK."""
    out = []
    for seg in re.split(r"[，。；！？、：\n]", text):
        n = len(CJK.findall(seg))
        if n:
            out.append(n)
    return out


def guess_form(title: str, era: str | None, text: str) -> str:
    """Verse form from the title and the actual clause lengths.

    乐府 verse is printed as one unbroken line, so the tell for prose is a long
    *clause*, never a long line: 赋 and 文 run far past the next ，or 。.
    """
    head = title.split("·")[0].strip()
    if "·" in title and head in CIPAI:
        return "词"

    lens = clause_lengths(text)
    if not lens:
        return "古体"

    if max(lens) > 20:
        return "赋" if title.endswith("赋") else "文"

    for n, name in ((7, "七言"), (6, "六言"), (5, "五言"), (4, "四言"),
                    (3, "三言")):
        if lens.count(n) / len(lens) >= 0.75:
            return name

    return "杂言"


def lineate(text: str) -> str:
    """One 句 to a line, for every poem.

    The source is not consistent about this: some pieces arrive as one long
    run, others already broken into 句, and the same collection would then read
    two different ways. A break the source already made is kept — it can carry
    a stanza the punctuation does not — and any remaining run is broken at the
    marks the text already carries.
    """
    if max(clause_lengths(text), default=0) > 20:
        return text  # prose keeps its own measure
    lines: list[str] = []
    for para in text.split("\n"):
        para = para.strip()
        if para:
            lines.extend(
                ln for ln in re.sub(r"(?<=[，。；！？])", "\n", para).split("\n") if ln
            )
    # a closing mark after the break belongs to the 句 it closes, not the next
    out: list[str] = []
    for ln in lines:
        while ln and ln[0] in "”』」）】”" and out:
            out[-1] += ln[0]
            ln = ln[1:]
        if ln:
            out.append(ln)
    return "\n".join(out)


def length_band(chars: int) -> str:
    if chars <= 40:
        return "短"
    if chars <= 120:
        return "中"
    return "长"


def hits(text: str, lexicon: dict[str, tuple[str, ...]], cap: int) -> list[str]:
    found = [k for k, words in lexicon.items() if any(w in text for w in words)]
    return found[:cap]


DIGITS_ONLY = re.compile(r"^[0-9\s.]+$")


def clean_author(raw: str) -> str:
    a = JUNK.sub("", raw).strip()
    # a mis-parsed line, not a name: 几令吾几令诸韩乱发正令吾
    if not a or len(a) > 6 or CJK.findall(a) != list(a):
        return "佚名"
    # a numeric handle is a scrape artefact (the corpus has 00913, 13, 666 as
    # poet directories); it is not a name a reader can use
    if DIGITS_ONLY.match(a):
        return "佚名"
    # 全宋诗 signs its unsigned poems 无名氏 where the anthologies sign 佚名;
    # one absence of a name must be one facet value, not two
    if a in ("无名氏", "失名", "阙名", "未详"):
        return "佚名"
    return a


def build(records: list[dict]) -> list[dict]:
    # dynasty evidence for authors the anthology usually labels
    labelled: dict[str, Counter] = defaultdict(Counter)
    for r in records:
        a = clean_author(r["author"])
        if r.get("dynasty") and a != "佚名":
            labelled[a][DYNASTY_ERA.get(r["dynasty"], r["dynasty"])] += 1
        elif r.get("era") and a != "佚名":
            labelled[a][r["era"]] += 1

    unresolved: Counter = Counter()
    poems: list[dict] = []
    seen: dict[tuple[str, str], dict] = {}
    dupes: Counter = Counter()
    for rec in records:
        text = lineate(rec["text"].strip())
        if not text:
            continue
        author = clean_author(rec["author"])
        era = DYNASTY_ERA.get(rec.get("dynasty") or "") or rec.get("era")
        if not era and (rec.get("lang") or rec["coll"] in FOREIGN_ERA):
            era = FOREIGN_ERA.get(rec["coll"], "")
        elif not era and rec["coll"] == MODERN_COLL:
            era = MODERN_ERA
        # the anthology's own dynasty evidence is Chinese; a foreign poet never
        # borrows a 朝代, and never falls back to 不详 either — the leaf drops
        # an empty era and the 时代 axis simply does not offer one
        if not era and author != "佚名" and not rec.get("lang") and rec["coll"] not in FOREIGN_ERA:
            votes = labelled.get(author)
            era = votes.most_common(1)[0][0] if votes else ERA_BY_AUTHOR.get(author)
            if not era:
                unresolved[author] += 1
        # `lang` is the language of the text on the page; `olang` is the language
        # of the poem underneath it. 飞鸟集 is 郑振铎's Chinese with Tagore's
        # English under it, so its text is 中文 and its original is en — the two
        # must not be conflated, or the reader filtering for 英文 would get a
        # book they cannot read and the leaf would label the wrong line.
        text_lang = "中文" if CJK.search(text) else (rec.get("lang") or "en")
        orig_lang = rec["lang"] if (rec.get("lang") and text_lang == "中文") else None

        body = text.replace("\n", "")
        # a Latin or Cyrillic poem has no CJK characters at all; counting them
        # would file every foreign poem as 短 no matter how long it is
        chars = len(CJK.findall(body)) or len(body)
        # the same poem printed in two anthologies is one poem; the first
        # anthology to carry it keeps it, and the copy is counted
        key = (rec["title"].strip(), body)
        if key in seen:
            dupes[rec["coll"]] += 1
            continue
        poem = {
            "title": rec["title"].strip(),
            "author": author,
            "lang": text_lang,
            **({"olang": rec["lang"]} if orig_lang else {}),
            "era": era or ("" if (rec.get("lang") or rec["coll"] in FOREIGN_ERA
                                or rec["coll"] == MODERN_COLL) else "不详"),
            "coll": rec["coll"],
            "cat": rec["cat"],
            "chapter": rec["chapter"],
            # 乐府诗集 labels the juan inside the chapter (卷三十七·相和歌辞十二);
            # other sources carry it as its own field, or have no juan at all —
            # 诗经's 周南 is a section, not a volume
            "juan": rec.get("juan") or (
                rec["chapter"].split("·")[0] if rec["chapter"].startswith("卷") else ""
            ),
            "note": rec.get("note", ""),
            "form": (rec.get("form") or FOREIGN_FORM.get(rec["coll"])
                     or (MODERN_FORM if rec["coll"] == MODERN_COLL else None)
                     or guess_form(rec["title"], era, text)),
            "mood": hits(body, MOOD_LEXICON, 3),
            "view": hits(body, VIEW_LEXICON, 2),
            "len": length_band(chars),
            "text": text,
            "chars": chars,
        }
        # `orig` is the poem *underneath* the translation, so it is only carried
        # when it is a different text. A book of originals has no translation to
        # sit under, and its `orig` equals its `text` — emitting both would print
        # the poem twice, once large and once faint, which reads as a bug.
        if rec.get("orig") and rec["orig"].strip() != text.strip():
            poem["orig"] = rec["orig"]
        seen[key] = poem
        poems.append(poem)

    for i, p in enumerate(poems):
        p["id"] = i
    report(poems, unresolved, dupes)
    return poems


def report(poems: list[dict], unresolved: Counter, dupes: Counter | None = None) -> None:
    n = len(poems)
    print(f"poems: {n}")
    for axis in ("coll", "lang", "era", "form", "len"):
        c = Counter(p[axis] for p in poems)
        detail = dict(c.most_common(14)) if axis != "coll" else dict(c.most_common(20))
        print(f"  {axis:7} {len(c):3}  {detail}")
    for axis in ("mood", "view"):
        c = Counter(v for p in poems for v in p[axis])
        untagged = sum(1 for p in poems if not p[axis])
        print(f"  {axis:7} {len(c):3}  {dict(c.most_common(10))}  untagged={untagged}")
    juans = Counter(p["juan"] for p in poems)
    print(f"  juan    {len(juans):3}  {', '.join(list(juans)[:3])} .."
          f"  unlabelled={sum(n for j, n in juans.items() if not j)}")
    print(f"  authors {len(set(p['author'] for p in poems))}"
          f"  anon={sum(1 for p in poems if p['author'] == '佚名')}")
    print(f"  era 不详 {sum(1 for p in poems if p['era'] == '不详')}"
          f"  (unresolved names {len(unresolved)}: {unresolved.most_common(8)})")
    if dupes:
        print(f"  duplicates dropped: {sum(dupes.values())}  {dict(dupes)}")


# ── the corpus the site actually loads ──────────────────────────────────────
#
# The whole corpus cannot be one file, and a reader should not pay for the ones
# they are not reading. Four kinds of artifact carry the site, and each is
# fetched only when something asks for it:
#
#   facets.json.gz      every axis's dictionary — the values a facet can offer —
#                       each with the count it has over the whole corpus.
#                       Opening 分类 with nothing filtered costs this and
#                       nothing else: a count over the whole corpus is a fact about
#                       the corpus, not something to recompute in the browser.
#   col/<axis>.bin.gz   one axis's codes, one per poem, in the dictionary's own
#                       order: a byte where the axis has ≤256 values (≤8 for a
#                       bitfield), two otherwise. Only a filter needs these, and
#                       then only for the axes it names.
#   t/NNNNN.json.gz     twenty poems: title, verse and labels together. Twenty
#                       because a draw is random, so a page turn almost never
#                       lands in the file already in hand, and 200 to a file
#                       meant paying for 200 poems to read one.
#   search/*.bin.gz     the bigram index, sharded by a hash (build-search.py).
#
# The labels are written twice — codes to filter on, words beside the text to
# print — and the duplication is the point. Both come from one pass over one
# list of poems, and a drawn poem can then be printed from the single file that
# carries it, its labels in the same request as its verse. Two things fetched
# separately can disagree about a poem; one file cannot.

# The axes, in a fixed order. A chunk's labels are positional, so this list is
# the only place their meaning is written down — it is generated into the app
# (CORPUS_ORDER in app/corpus-meta.ts) and read there by name, never by number.
ORDER = ("coll", "cat", "juan", "chapter", "era", "author",
         "form", "len", "lang", "olang", "mood", "view")

# The axes a reader can filter by — the ones the app's own AXES names. 卷次's
# caption and the language of a translation are printed on a leaf but are not
# choices, so those two are written beside the text and never as a column: a
# column is what a filter scans, and nothing can filter on them.
FACETED = tuple(axis for axis in ORDER if axis not in ("chapter", "olang"))

# The axes a poem can carry more than one value of. These are stored as a
# bitfield rather than as an index.
MULTI = ("mood", "view")

TEXT_PER_CHUNK = 20

META_TS = ROOT / "app" / "corpus-meta.ts"

# A foreign poem is not a 律诗 and has no dynasty. Its 体裁 comes from the book
# it is printed in, and its 时代 stays empty rather than borrowing a Chinese one
# — the leaf drops an empty era and the 时代 axis never offers it.
FOREIGN_FORM = {
    "莎士比亚十四行诗": "十四行诗",
    "飞鸟集": "散文诗",
    "恶之花": "诗",
    "海涅诗歌": "诗",
    "天真与经验之歌": "诗",
}
FOREIGN_ERA = {"莎士比亚十四行诗": "英", "飞鸟集": "印度", "恶之花": "法",
               "海涅诗歌": "德", "天真与经验之歌": "英"}

# 现代诗 is written in 白话, so 律诗 clause-counting would file a free-verse poem
# as 五言 whenever it happens to break that way. The form is a fact about the
# book, not something to infer.
MODERN_FORM = "新诗"
MODERN_ERA = "现代"
# The name the selection carries (scripts/anthology.py). The three checks below
# must follow the collection's name, or 现代诗 gets its form guessed by counting
# clauses like a 律诗 and its 时代 falls through to 不详.
MODERN_COLL = anthology.MODERN_NAME


def write_gz(path: Path, payload: bytes) -> None:
    """One artifact, gzipped, byte-identical across rebuilds.

    mtime is pinned to zero because a deploy is a git checkout: rebuilding the
    same corpus should show as no change at all, not as every file touched.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress(payload, 9, mtime=0))


def columns(poems: list[dict]) -> dict[str, dict]:
    """Every axis as a dictionary of its values plus one code per poem.

    A single-valued axis stores the index of the value; a multi-valued one
    (情绪, 视角) stores a bitfield, one bit per value the poem carries. The width
    follows the dictionary — a code must hold len(dict) - 1, or every bit the
    axis can set — so a byte covers everything except 作者 and the three other
    long axes.

    This is the form that makes filtering cheap: the whole corpus is 916 KB as
    2-byte codes and 458 KB as 1-byte ones, so a filter can look at every poem
    in memory rather than maintaining an inverted index for every axis pair.
    """
    out: dict[str, dict] = {}
    for axis in FACETED:
        if axis in MULTI:
            dictionary = sorted({v for p in poems for v in (p.get(axis) or [])})
            bit = {v: i for i, v in enumerate(dictionary)}
            values = (sum(1 << bit[v] for v in (p.get(axis) or [])) for p in poems)
            width = 1 if len(dictionary) <= 8 else 2
        else:
            dictionary = sorted({p.get(axis, "") for p in poems})
            index = {v: i for i, v in enumerate(dictionary)}
            values = (index[p.get(axis, "")] for p in poems)
            width = 1 if len(dictionary) <= 256 else 2
        codes = array.array("B" if width == 1 else "H", values)
        if width == 2 and sys.byteorder == "big":
            codes.byteswap()
        out[axis] = {"dict": dictionary, "w": width, "codes": codes}
    return out


def counts_of(poems: list[dict], axis: str, dictionary: list[str]) -> list[int]:
    """How many poems carry each value of one axis, over the whole corpus.

    A multi-valued axis counts a poem once per value it carries, so its counts
    add up to more than the corpus — 情绪 and 视角 are things a poem can have
    several of, and a reader asking for 愁 wants every poem that has it.
    """
    if axis in MULTI:
        seen = Counter(v for p in poems for v in (p.get(axis) or []))
    else:
        seen = Counter(p.get(axis, "") for p in poems)
    return [seen[v] for v in dictionary]


CORPUS_META = '''/**
 * Generated by scripts/build-corpus.py. Do not edit — rebuild the corpus.
 *
 * The app needs a few facts about the corpus before it can draw anything, and
 * fetching them would put a round trip in front of the first poem. They are
 * facts about a corpus that changes only when the corpus does, so they are
 * compiled in, and `CORPUS_BUILD` is the stamp the artifacts carry: a hash of
 * every column, every dictionary and the text of every chunk (also in
 * facets.json.gz, which is where a mismatch is worth noticing; the search index
 * records the same stamp in search/meta.json, because an index built from
 * another corpus answers without saying so).
 *
 * `CORPUS_ORDER` is the axis order of a chunk's positional labels. The app
 * reads its positions out of this list by name rather than by number, so
 * reordering the axes here cannot silently print one label where another
 * belongs.
 */
export const CORPUS_N = {n}
export const CORPUS_PER_CHUNK = {per_chunk}
export const CORPUS_CHUNKS = {chunks}
export const CORPUS_BUILD = '{build}'
export const CORPUS_ORDER = [{order}] as const

/** Every axis the corpus stores, in the order a chunk's labels are written. */
export type CorpusAxis = (typeof CORPUS_ORDER)[number]
'''


def write_corpus(poems: list[dict]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    # The old shape is removed rather than kept alongside: index.json was every
    # poem's labels in one 11 MB request, and the reader should never pay it.
    # search/meta.json goes too — build-search.py writes it from the new chunks.
    for old in OUT.rglob("*.json"):
        old.unlink()

    n = len(poems)
    cols = columns(poems)

    # The stamp is what the artifacts are versioned by, so it has to cover
    # everything they hold: every column, every dictionary, and the text of
    # every chunk. Columns alone would miss the case that matters most — a
    # selection changed for a poem that keeps all of its labels, which moves no
    # code, leaves the columns identical and makes the text a different poem's.
    stamp = hashlib.sha1()
    facets: dict = {"n": n, "order": list(ORDER), "multi": list(MULTI), "byAxis": {}}
    for axis in FACETED:
        col = cols[axis]
        stamp.update(axis.encode())
        stamp.update(col["codes"].tobytes())
        stamp.update("\x00".join(col["dict"]).encode())
        write_gz(OUT / "col" / f"{axis}.bin.gz", col["codes"].tobytes())
        facets["byAxis"][axis] = {
            "dict": col["dict"],
            "w": col["w"],
            "multi": axis in MULTI,
            "counts": counts_of(poems, axis, col["dict"]),
        }

    text_dir = OUT / "t"
    text_dir.mkdir(exist_ok=True)
    for old in text_dir.glob("*.json*"):
        old.unlink()
    chunks = 0
    for start in range(0, n, TEXT_PER_CHUNK):
        records = [
            {"t": p["title"], "x": p["text"], "c": p["chars"],
             **({"o": p["orig"]} if p.get("orig") else {}),
             **({"n": p["note"]} if p["note"] else {}),
             "l": [(p.get(axis) or []) if axis in MULTI else p.get(axis, "")
                   for axis in ORDER]}
            for p in poems[start:start + TEXT_PER_CHUNK]
        ]
        payload = json.dumps(records, ensure_ascii=False, separators=(",", ":")).encode()
        stamp.update(payload)
        write_gz(text_dir / f"{chunks:05d}.json.gz", payload)
        chunks += 1

    # The stamp is published, so it is taken after the last file it covers has
    # been written: facets.json.gz and app/corpus-meta.ts carry it, and
    # scripts/build-search.py copies it into the index's own meta.json.
    build = stamp.hexdigest()[:8]
    facets["v"] = build
    write_gz(OUT / "facets.json.gz",
             json.dumps(facets, ensure_ascii=False, separators=(",", ":")).encode())

    META_TS.write_text(CORPUS_META.format(
        n=n, per_chunk=TEXT_PER_CHUNK, chunks=chunks, build=build,
        order=", ".join(f"'{axis}'" for axis in ORDER)), encoding="utf-8")

    def size(pattern: str) -> int:
        return sum(f.stat().st_size for f in OUT.glob(pattern))

    print(f"  -> public/corpus/facets.json.gz  {size('facets.json.gz') / 1024:>7.0f} KiB"
          f"   {len(ORDER)} axes, {n} poems")
    print(f"  -> public/corpus/col/            {size('col/*.bin.gz') / 1024 / 1024:>7.2f} MiB"
          f"   {len(ORDER)} column files")
    print(f"  -> public/corpus/t/              {size('t/*.json.gz') / 1024 / 1024:>7.1f} MiB"
          f"   {chunks} chunks of {TEXT_PER_CHUNK}")
    print(f"  -> app/corpus-meta.ts            n={n}  build={build}")
    print("     · run scripts/build-search.py after this: the bigram index is "
          "built from the chunks")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="report only, do not write")
    ap.add_argument("--drop-encumbered", action="store_true",
                    help="leave out the poems that are still in copyright")
    args = ap.parse_args()

    src = CACHE / "yuefu.json"
    if not src.exists():
        raise SystemExit(f"{src.relative_to(ROOT)} missing — run scripts/fetch-yuefu.py first")
    # 乐府诗集 first: where the same poem is printed twice, the anthology the
    # site is built around is the one that keeps it
    records = json.loads(src.read_text(encoding="utf-8"))
    if MODERN.exists():
        modern = json.loads(MODERN.read_text(encoding="utf-8"))
        print(f"· {len(modern)} 现代诗 records from {MODERN.relative_to(ROOT)}")
        records += modern
    else:
        print(f"· {MODERN.relative_to(ROOT)} missing — run scripts/fetch-modern.py "
              f"for 现代诗")
    if CHINESE_POETRY.exists():
        records += json.loads(CHINESE_POETRY.read_text(encoding="utf-8"))
    else:
        print(f"· {CHINESE_POETRY.relative_to(ROOT)} missing — "
              f"run scripts/fetch-chinese-poetry.py for the other anthologies")

    if args.drop_encumbered:
        before = len(records)
        records = [r for r in records if r.get("rights") != "在版"]
        print(f"· dropped {before - len(records)} poems still in copyright "
              f"(--drop-encumbered)")

    if WORLD.exists():
        world = json.loads(WORLD.read_text(encoding="utf-8"))
        print(f"· {len(world)} foreign records from {WORLD.relative_to(ROOT)}")
        records += world
    else:
        print(f"· {WORLD.relative_to(ROOT)} missing — run scripts/fetch-world.py "
              f"for the bilingual books")

    # 全宋诗与现代诗换成选本：这两本合起来是 73% 的条目、77% 的正文，
    # 而它们的问题是「全」——见 scripts/anthology.py 里的选家与选目。
    records = anthology.select(records)

    poems = build(records)
    if args.check:
        return

    write_corpus(poems)


if __name__ == "__main__":
    main()
