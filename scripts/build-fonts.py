#!/usr/bin/env python3
"""Build self-hosted CJK font subsets for the poetry site.

Subsets two system fonts to the union of:
  - GB2312 level-1 hanzi (3755 common characters)
  - every character used by content/poems/*.txt
  - the site's UI strings, Latin, digits and CJK punctuation

Outputs woff2 files into public/fonts/. Re-runnable: run after adding poems.

    python3 scripts/build-fonts.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content" / "poems"
OUT = ROOT / "public" / "fonts"

UI_STRINGS = [
    "诗存个人诗稿全部篇目最新时间倒序按点标题通读全文首行日期编号",
    "返回目录上一篇下一篇这一篇共行第页正在载入无题草稿未收录",
    "首篇末篇已是最新的一篇之前读过的位置已恢复翻页浏览全部",
    "诗稿xihale二零二六年月日编号题名",
    "、。，；：？！“”‘’（）《》〈〉【】—…·　「」『』",
    "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",
    ".,;:!?'\"()[]{}<>/-–—+*=&%@#~|\\^$`_ \n\t",
]


def gb2312_level1() -> set[str]:
    chars: set[str] = set()
    for hi in range(0xB0, 0xD8):
        for lo in range(0xA1, 0xFF):
            try:
                chars.add(bytes([hi, lo]).decode("gb2312"))
            except UnicodeDecodeError:
                pass
    return chars


def content_chars() -> set[str]:
    chars: set[str] = set()
    for path in sorted(CONTENT.glob("*.txt")):
        chars |= set(path.read_text(encoding="utf-8"))
    return chars


def wanted() -> str:
    chars = gb2312_level1() | content_chars()
    for s in UI_STRINGS:
        chars |= set(s)
    chars = {c for c in chars if c.isprintable() and c != "\n"}
    return "".join(sorted(chars))


def extract_ttc(ttc: Path, family_fragment: str, dest: Path) -> None:
    """Pull one face out of a .ttc collection into a standalone .otf/.ttf."""
    from fontTools.ttLib import TTFont, TTCollection

    coll = TTCollection(str(ttc))
    for i, font in enumerate(coll.fonts):
        names = {n.toUnicode() for n in font["name"].names if n.nameID in (1, 4, 16)}
        if any(family_fragment in n for n in names):
            font.save(str(dest))
            return
    raise SystemExit(f"{family_fragment!r} not found in {ttc}")


def subset(src: Path, dest: Path, text_file: Path) -> int:
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable, "-m", "fontTools.subset", str(src),
        f"--text-file={text_file}",
        "--flavor=woff2",
        "--layout-features=kern,liga,vert,vrt2",
        "--no-hinting",
        "--drop-tables+=DSIG",
        f"--output-file={dest}",
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return dest.stat().st_size


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = ROOT / ".design" / ".fonts-tmp"
    tmp.mkdir(parents=True, exist_ok=True)

    text_file = tmp / "charset.txt"
    text_file.write_text(wanted(), encoding="utf-8")
    print(f"charset: {len(text_file.read_text(encoding='utf-8'))} chars")

    # 1. LXGW WenKai Regular — titles / headings (kai brush character)
    wenkai = Path("/usr/share/fonts/TTF/LXGWWenKai-Regular.ttf")
    if not wenkai.exists():
        raise SystemExit("LXGW WenKai not found")
    size = subset(wenkai, OUT / "wenkai.woff2", text_file)
    print(f"wenkai.woff2            {size/1024:8.1f} KiB")

    # 2. Noto Serif CJK SC Regular — body text
    ttc = Path("/usr/share/fonts/noto-cjk/NotoSerifCJK-Regular.ttc")
    sc = tmp / "NotoSerifSC-Regular.otf"
    if not sc.exists():
        extract_ttc(ttc, "Noto Serif CJK SC", sc)
    size = subset(sc, OUT / "serifsc.woff2", text_file)
    print(f"serifsc.woff2           {size/1024:8.1f} KiB")

    total = sum(p.stat().st_size for p in OUT.glob("*.woff2"))
    print(f"total                   {total/1024:8.1f} KiB")


if __name__ == "__main__":
    main()
