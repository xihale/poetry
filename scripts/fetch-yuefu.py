#!/usr/bin/env python3
"""Fetch 乐府诗集 (郭茂倩) from 古文岛 古籍 and parse it into records.

Book page lists 100 卷 (bookv_*); each chapter page holds its poems as
【题名】 blocks, optionally followed by a `朝代·作者` line and 解题 prose
(quoting 《...》) before the verse itself.

Network only fills .cache; parsing is re-runnable offline via --no-fetch.
Output: .cache/guwendao/yuefu.json — records this script could parse, plus
a stats report of everything it could not, so gaps stay visible.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import socket
import time
import urllib.request
from pathlib import Path

socket.setdefaulttimeout(25)

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".cache" / "guwendao" / "yuefu"
OUT = ROOT / ".cache" / "guwendao" / "yuefu.json"
BOOK = "https://www.guwendao.net/guwen/book_277586224cba.aspx"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}

# 宋/齐/梁/陈 inside 乐府诗集 are the southern dynasties, not 赵宋.
DYNASTY_ERA = {
    "先秦": "先秦", "秦": "秦", "前汉": "汉", "后汉": "汉", "两汉": "汉",
    "汉": "汉", "魏": "魏晋", "晋": "魏晋", "宋": "南北朝", "齐": "南北朝",
    "梁": "南北朝", "陈": "南北朝", "北魏": "南北朝", "北齐": "南北朝",
    "北周": "南北朝", "隋": "隋", "唐": "唐", "五代": "五代",
}
# lines in the author slot that are notes, not people
NOTE_LINES = ("晋宋齐辞", "吴声", "西曲", "古辞", "古词", "古歌", "古曲",
              "古调", "古意", "杂言", "瑟调", "楚调", "平调", "清调")


def get(url: str) -> str:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA)) as r:
        return r.read().decode("utf-8", "ignore")


def chapters() -> list[tuple[str, str]]:
    h = get(BOOK)
    out = []
    for i, n in re.findall(r'href="/guwen/(bookv_[0-9a-f]+)\.aspx"[^>]*>([^<]{1,40})', h):
        out.append((i, html.unescape(n).replace("&#183;", "·").strip()))
    return out


def page_text(h: str) -> str:
    """Plain text of a chapter, without the reader nav and site footer.

    The nav is stripped after tag removal rather than before: cutting the raw
    HTML at `>上一章<` would leave the anchor's opening tag dangling, and a
    dangling tag has no `>` for the tag stripper to match.
    """
    h = re.sub(r"<script.*?</script>", "", h, flags=re.S)
    t = re.sub(r"<[^>]+>", "\n", h)
    cut = t.find("上一章")
    # only trust the cut when it clearly sits below the text, never a top bar
    if cut != -1 and cut > len(t) * 0.5:
        t = t[:cut]
    t = re.sub(r"\s*\n\s*", "\n", t)
    return re.sub(r"\n{3,}", "\n\n", html.unescape(t))


# 乐府诗集 marks its own scaffolding inline: ○ introduces a section heading,
# ── closes a set of 解. Neither is verse.
MARKER = re.compile(r"^[○●◎◯]|^[─—―-]{2,}")

# The compiler's 解题 is prose that cites a source. Verse that merely names a
# book — 「自古咏《采薇》」 — must not be mistaken for it, so a bare 《 is not
# enough: the line has to open with the citation or carry a 曰：“ quotation.
QUOTED = re.compile(r"^[\u4e00-\u9fff]{2,4}(?:曰|云)[：:]")


def is_note(line: str) -> bool:
    if line.startswith("《"):
        return True
    if "：" in line and "”" in line and len(line) > 20:
        return "《" in line or bool(QUOTED.match(line))
    return False


def parse_chapter(name: str, text: str) -> tuple[list[dict], dict]:
    """Split on 【】; resolve 同前; separate 作者 / 解题 / 正文."""
    cat = name.split("·")[-1].rstrip("一二三四五六七八九十") or name
    parts = re.split(r"【([^】]{1,40})】", text)
    # parts[0] is the chapter head (nav, 卷名, 小序); poems follow in pairs
    recs: list[dict] = []
    stats: dict = {"marks": 0, "same": 0, "anon": 0, "with_note": 0, "empty": 0,
                   "dynasties": set(), "bare_authors": set(), "note_lines": set()}
    last_title = ""
    for mark, seg in zip(parts[1::2], parts[2::2]):
        mark = mark.strip()
        if not mark or len(mark) > 30:
            continue
        stats["marks"] += 1
        if mark.startswith("同"):
            title = last_title or mark
            stats["same"] += 1
        else:
            title = mark
            last_title = mark
        lines = [ln.strip("　 \t") for ln in seg.strip().split("\n")]
        author, dynasty, note = "佚名", "", ""
        if lines and len(lines[0]) <= 14 and not any(
                p in lines[0] for p in "，。；！？：、"):
            m = re.match(r"^(?:(先秦|秦|前汉|后汉|两汉|汉|魏|晋|宋|齐|梁|陈|"
                         r"北魏|北齐|北周|隋|唐|五代)[·•．.])?(.+)$", lines[0])
            if m:
                dynasty, author = m.group(1) or "", m.group(2).strip()
                lines = lines[1:]
        if author == "佚名" or dynasty == "":
            pass
        if dynasty:
            stats["dynasties"].add(dynasty)
        if author != "佚名" and not dynasty:
            if any(author.startswith(n) or n in author for n in NOTE_LINES) \
                    or author in NOTE_LINES:
                stats["note_lines"].add(author)
                author = "佚名"
            else:
                stats["bare_authors"].add(author)
        # 解题: leading lines quoting a source are the compiler's apparatus
        note_lines = []
        while lines and is_note(lines[0]):
            note_lines.append(lines.pop(0))
        if note_lines:
            note = "\n".join(note_lines)
            stats["with_note"] += 1
        lines = [ln for ln in lines if not MARKER.match(ln)]
        body = "\n".join(lines).strip()
        if not body:
            stats["empty"] += 1
            continue
        if author == "佚名":
            stats["anon"] += 1
        recs.append({
            "title": title, "author": author,
            "dynasty": dynasty or None, "cat": cat, "chapter": name,
            "coll": "乐府诗集",
            "note": note, "text": body,
        })
    stats["dynasties"] = sorted(stats["dynasties"])
    stats["bare_authors"] = sorted(stats["bare_authors"])[:40]
    stats["note_lines"] = sorted(stats["note_lines"])
    return recs, stats


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-fetch", action="store_true")
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)

    if not args.no_fetch:
        chs = chapters()
        print(f"chapters: {len(chs)}")
        (CACHE / "_chapters.json").write_text(
            json.dumps(chs, ensure_ascii=False), encoding="utf-8")
        for i, (cid, name) in enumerate(chs):
            p = CACHE / f"{cid}.html"
            if p.exists() and not args.refresh:
                continue
            try:
                p.write_text(get(f"https://www.guwendao.net/guwen/{cid}.aspx"),
                             encoding="utf-8")
            except Exception as e:  # noqa: BLE001 — keep going, report below
                print(f"  FAIL {name}: {str(e)[:60]}")
            if i % 10 == 9:
                print(f"  {i + 1}/100")
            time.sleep(0.4)
    else:
        chs = json.loads((CACHE / "_chapters.json").read_text(encoding="utf-8"))

    all_recs: list[dict] = []
    agg: dict = {"marks": 0, "same": 0, "anon": 0, "with_note": 0, "empty": 0,
                 "dynasties": set(), "bare": set(), "notes": set(),
                 "chapters_ok": 0, "chapters_missing": []}
    for cid, name in chs:
        p = CACHE / f"{cid}.html"
        if not p.exists():
            agg["chapters_missing"].append(name)
            continue
        recs, st = parse_chapter(name, page_text(p.read_text(encoding="utf-8")))
        all_recs.extend(recs)
        agg["chapters_ok"] += 1
        for k in ("marks", "same", "anon", "with_note", "empty"):
            agg[k] += st[k]
        agg["dynasties"] |= set(st["dynasties"])
        agg["bare"] |= set(st["bare_authors"])
        agg["notes"] |= set(st["note_lines"])

    (OUT.parent).mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(all_recs, ensure_ascii=False), encoding="utf-8")
    chrome = ("上一章", "下一章", "古诗文网", "古文岛", "纠错", "播放列表", "朗诵")
    leak = [(r["chapter"], r["title"]) for r in all_recs
            if any(c in r["text"] for c in chrome)]
    print(f"poems: {len(all_recs)} from {agg['chapters_ok']}/100 chapters")
    print(f"chrome leaks: {len(leak)} {leak[:5]}")
    print(f"marks={agg['marks']} 同前={agg['same']} anon={agg['anon']} "
          f"with_note={agg['with_note']}")
    print(f"missing: {agg['chapters_missing']}")
    print(f"dynasties: {sorted(agg['dynasties'])}")
    print(f"bare authors ({len(agg['bare'])}): {sorted(agg['bare'])[:50]}")
    print(f"note-lines: {sorted(agg['notes'])}")
    print(f"  -> {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 1024:.0f} KiB)")


if __name__ == "__main__":
    main()
