#!/usr/bin/env python3
"""Build the site corpus from an exported 古文岛 collection.

Input is the export produced by scripts/fetch-poemlist.py; run that first. This
script only shapes and classifies — it never touches the network.

Every axis is derived from the poem itself, never from a container it happened
to sit in:

  era   the dynasty of the author, taken from the poem page's 〔唐代〕 marker.
        This is why 洛神赋 is 魏晋 and 圆圆曲 is 明 rather than "the book I
        found it in".
  form  read off the line and clause lengths, plus the 词牌 in the title.
  mood  / view   lexicons — a poem joins 「愁」 because it contains 愁/泪/断肠,
        not because a model judged it sad, so every tag is checkable against
        the text on screen.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IN = ROOT / ".cache" / "guwendao" / "poemlist.json"
OUT = ROOT / "public" / "corpus.json"

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

# 〔唐代〕 -> 唐
ERA = {
    "先秦": "先秦", "秦代": "秦", "两汉": "汉", "汉代": "汉", "魏晋": "魏晋",
    "南北朝": "南北朝", "隋代": "隋", "唐代": "唐", "五代": "五代",
    "宋代": "宋", "辽代": "辽", "金朝": "金", "金代": "金", "元代": "元",
    "明代": "明", "清代": "清", "近现代": "近现代",
}

CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


def clause_lengths(text: str) -> list[int]:
    """Lengths of the metrical clauses, split on punctuation, ignoring non-CJK."""
    out = []
    for seg in re.split(r"[，。；！？、：\n]", text):
        n = len(CJK.findall(seg))
        if n:
            out.append(n)
    return out


def guess_form(title: str, era: str | None, text: str) -> str:
    """Verse form from the title and the actual clause lengths."""
    head = title.split("·")[0].strip()
    if "·" in title and head in CIPAI:
        return "词"

    lens = clause_lengths(text)
    if not lens:
        return "古体"

    # a run of unbroken prose: 洛神赋, 破窑赋, 滕王阁序, 焚鼠毁庐, 施氏食狮史
    longest_line = max((len(CJK.findall(ln)) for ln in text.split("\n")), default=0)
    if longest_line > 60:
        return "赋" if title.endswith("赋") else "文"

    for n, name in ((7, "七言"), (5, "五言"), (4, "四言")):
        if lens.count(n) / len(lens) >= 0.75:
            return name

    # irregular, and written after the classical forms fell out of use
    if era == "近现代":
        return "现代"
    return "杂言"


def length_band(chars: int) -> str:
    if chars <= 40:
        return "短"
    if chars <= 120:
        return "中"
    return "长"


def hits(text: str, lexicon: dict[str, tuple[str, ...]], cap: int) -> list[str]:
    found = [k for k, words in lexicon.items() if any(w in text for w in words)]
    return found[:cap]


def build() -> list[dict]:
    if not IN.exists():
        raise SystemExit(f"{IN.relative_to(ROOT)} missing — run scripts/fetch-poemlist.py first")
    raw = json.loads(IN.read_text(encoding="utf-8"))

    poems: list[dict] = []
    for rec in raw:
        text = rec["text"].strip()
        if not text:
            continue
        body = text.replace("\n", "")
        chars = len(CJK.findall(body))
        # guwendao appends its own doubts to the name, e.g. 吕蒙正(存疑)
        author = re.sub(r"[（(][^）)]*[）)]", "", rec["author"]).strip() or "佚名"
        era = ERA.get(rec.get("era") or "", rec.get("era"))
        poems.append({
            "title": rec["title"].strip(),
            "author": author,
            "era": era,
            "form": guess_form(rec["title"], era, text),
            "mood": hits(body, MOOD_LEXICON, 3),
            "view": hits(body, VIEW_LEXICON, 2),
            "len": length_band(chars),
            "text": text,
            "chars": chars,
        })

    for i, p in enumerate(poems):
        p["id"] = i
    return poems


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="report only, do not write")
    args = ap.parse_args()

    poems = build()
    for p in poems:
        print(f"  {p['era'] or '?':<4} {p['form']:<4} {p['len']:<2} "
              f"{','.join(p['mood']) or '-':<8} {p['title']} — {p['author']}")

    print(f"\n{len(poems)} poems")
    for axis in ("era", "form", "len"):
        counts = Counter(p[axis] for p in poems)
        print(f"  {axis}: " + ", ".join(f"{k} {v}" for k, v in counts.most_common()))
    print(f"  mood tagged {sum(1 for p in poems if p['mood'])}/{len(poems)}, "
          f"view tagged {sum(1 for p in poems if p['view'])}/{len(poems)}")
    print(f"  authors: {len({p['author'] for p in poems})}")

    if not args.check:
        OUT.write_text(json.dumps(poems, ensure_ascii=False, separators=(",", ":")),
                       encoding="utf-8")
        print(f"  -> {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 1024:.0f} KiB)")


if __name__ == "__main__":
    main()
