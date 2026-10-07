#!/usr/bin/env python3
"""Build the self-hosted CJK font subsets for the poetry site.

One face carries the site: Noto Serif CJK SC Light. Everything is set in Song
at a single weight — hierarchy comes from scale, space and colour, so a second
weight would cost another megabyte to say nothing. Nothing on the page asks for
bold, which matters: a synthetic bold on a Light Song face looks wrong.

Subset to the union of every character in public/corpus.json and the site's own
interface strings. Re-runnable:

    python3 scripts/build-fonts.py

A few dozen Extension-B forms (𪩷, 𫘞 …) appear in 诗经 and 楚辞 but are absent
from the Song face. They are served from a second, tiny face instead of being
left as blank gaps in the middle of a couplet.
"""
from __future__ import annotations

import gzip
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "public" / "corpus"
OUT = ROOT / "public" / "fonts"

FACE_TTC = "/usr/share/fonts/noto-cjk/NotoSerifCJK-Light.ttc"
FACE_FAMILY = "Noto Serif CJK SC"

# The Song face has no Extension-B coverage, and neither does anything else
# installed here. Jigmo2 does — it is CC0 and a Mincho face, so the rare forms
# sit beside Song without a change of voice. Fetched on demand into .cache/
# rather than installed system-wide; 霞鹜文楷 is used only if that fails.
JIGMO_URL = "https://kamichikoichi.github.io/jigmo/Jigmo-20250912.zip"
JIGMO_MEMBER = "Jigmo2.ttf"
FALLBACK_RARE = Path("/usr/share/fonts/TTF/LXGWWenKai-Regular.ttf")

UI_STRINGS = [
    "白卷拈一卷",
    "部类分类全部作者时代体裁语言情绪视角篇幅换一首",
    "合卷清除其余",
    "先秦秦汉魏晋南北朝隋唐五代宋元明清不详",
    "英法德俄印度美",
    "中文英文法文德文俄文日文",
    "三言四言五言六言七言杂言词曲楚辞赋文短中长",
    "十四行诗散文诗",
    "愁思独欢闲壮惊我你他谁天地",
    "佚名无名氏",
    "、。，；：？！“”‘’（）《》〈〉【】—…·　「」『』",
    "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",
    ".,;:!?'\"()[]{}<>/-–—+*=&%@#~|\\^$`_ \n\t",
]


def corpus_chars() -> set[str]:
    """Every character the page can draw, read off the emitted corpus.

    A chunk carries twenty poems — the verse, the title, the 解题 and the labels
    — so the chunks alone are the glyph inventory. Nothing is cross-checked
    against a second file, which is also why a label can never be missing from
    the font: it is drawn from the same file it is read from.
    """
    if not CORPUS.exists():
        raise SystemExit("run scripts/build-corpus.py first")
    chars: set[str] = set()
    for f in CORPUS.glob("t/*.json.gz"):
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            for poem in json.load(fh):
                # every field the page can draw needs a glyph: the 解题 and the
                # provenance line are rendered too, not just the verse
                for field in ("t", "x", "n", "o"):
                    chars |= set(poem.get(field) or "")
                for label in poem.get("l", ()):
                    chars |= set("".join(label) if isinstance(label, list) else label)
    return chars


def wanted() -> str:
    chars = corpus_chars()
    for s in UI_STRINGS:
        chars |= set(s)
    # str.isprintable() excludes every Unicode separator, including U+3000 —
    # but 赋 indent with 　, so dropping it would push those glyphs onto a
    # fallback face and break the indent width
    chars = {c for c in chars if (c.isprintable() or c == "\u3000") and c != "\n"}
    return "".join(sorted(chars))


def fetch_jigmo(tmp: Path) -> Path | None:
    """Jigmo2, for the Extension-B forms no installed face covers. CC0."""
    dest = tmp / JIGMO_MEMBER
    if dest.exists():
        return dest
    try:
        import io
        import urllib.request
        import zipfile

        with urllib.request.urlopen(JIGMO_URL, timeout=180) as r:
            data = r.read()
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            dest.write_bytes(z.read(JIGMO_MEMBER))
        print(f"  fetched {JIGMO_MEMBER} ({dest.stat().st_size / 1024 / 1024:.1f} MiB)")
        return dest
    except Exception as exc:  # the network is optional; the site still builds
        print(f"  · could not fetch Jigmo ({exc}); trying the local fallback")
        return None

def extract_ttc(ttc: Path, family_fragment: str, dest: Path) -> None:
    """Pull one face out of a .ttc collection into a standalone .otf."""
    from fontTools.ttLib import TTCollection

    for font in TTCollection(str(ttc)).fonts:
        names = {n.toUnicode() for n in font["name"].names if n.nameID in (1, 4, 16)}
        if any(family_fragment in n for n in names):
            font.save(str(dest))
            return
    raise SystemExit(f"{family_fragment!r} not found in {ttc}")


def subset(src: Path, dest: Path, text_file: Path) -> int:
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        sys.executable, "-m", "fontTools.subset", str(src),
        f"--text-file={text_file}",
        "--flavor=woff2",
        "--layout-features=kern,liga,vert,vrt2",
        "--no-hinting",
        "--drop-tables+=DSIG",
        f"--output-file={dest}",
    ], check=True, capture_output=True)
    return dest.stat().st_size


def missing(src: Path, charset: str) -> list[str]:
    from fontTools.ttLib import TTFont

    cmap = TTFont(str(src)).getBestCmap()
    return [c for c in charset if ord(c) not in cmap]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = ROOT / ".cache" / "fonts"
    tmp.mkdir(parents=True, exist_ok=True)

    charset = wanted()
    text_file = tmp / "charset.txt"
    text_file.write_text(charset, encoding="utf-8")
    print(f"charset                 {len(charset):8} chars")

    ttc = Path(FACE_TTC)
    if not ttc.exists():
        raise SystemExit(f"{ttc} not found")
    face = tmp / "NotoSerifSC-Light.otf"
    if not face.exists():
        extract_ttc(ttc, FACE_FAMILY, face)

    gaps = missing(face, charset)
    size = subset(face, OUT / "song.woff2", text_file)
    print(f"song.woff2              {size/1024:8.1f} KiB")

    # 诗经 and 楚辞 use a few dozen Extension-B forms. Serve whichever of them
    # any local font actually draws — a partial companion still closes most of
    # the gaps — and report the rest, which no font here can supply.
    if not gaps:
        # Nothing in this corpus needs the companion face. Leaving the file
        # behind would ship a download the browser never has a use for.
        stale = OUT / "rare.woff2"
        if stale.exists():
            stale.unlink()
            print("rare.woff2              removed (no Ext-B forms in this corpus)")
        total = sum(p.stat().st_size for p in OUT.glob("*.woff2"))
        print(f"total                   {total/1024:8.1f} KiB")
        return

    # A collection that does reach into Extension-B needs a companion face:
    # serve whichever forms any local font actually draws — a partial companion
    # still closes most of the gaps — and report the rest.
    source = fetch_jigmo(tmp)
    if source is None and FALLBACK_RARE.exists():
        source = FALLBACK_RARE
    if source is None:
        print(f"  · {len(gaps)} Ext-B forms: no source available; they fall "
              f"back to the reader's system font")
    else:
        absent = set(missing(source, "".join(gaps)))
        coverable = [c for c in gaps if c not in absent]
        if coverable:
            rare_file = tmp / "rare.txt"
            rare_file.write_text("".join(coverable), encoding="utf-8")
            rare_size = subset(source, OUT / "rare.woff2", rare_file)
            print(f"rare.woff2              {rare_size/1024:8.1f} KiB  "
                  f"({len(coverable)}/{len(gaps)} Ext-B forms Song lacks, "
                  f"from {source.name})")
        if len(coverable) < len(gaps):
            print(f"  · {len(gaps) - len(coverable)} Ext-B forms have no "
                  f"source here; they fall back to the reader's system font")
    total = sum(p.stat().st_size for p in OUT.glob("*.woff2"))
    print(f"total                   {total/1024:8.1f} KiB")


if __name__ == "__main__":
    main()
