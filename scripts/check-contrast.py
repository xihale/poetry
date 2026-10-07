#!/usr/bin/env python3
"""Gate the palette on measured contrast, not on taste.

Every ink on this site is a token in app/assets/css/main.css, and every token is
text on --paper. The verse is the one thing that must be effortless to read; the
labels, counts and controls sit at the edge of legibility by design, but "at the
edge" has a floor: WCAG AA. This script parses the two token blocks out of the
stylesheet, resolves each text token against its own --paper, and fails if any
of them drops below its floor.

The floors are set by what the token actually is, not by size:

  --ink     body and verse                    7.0  (AAA body text)
  --faint   labels, counts, apparatus         4.5  (AA body text)
  --ghost   hairline text — the emptiest      3.0  (AA large / UI floor)
            chips and the paging marker,
            never a way to read anything
  --line    rules; a rule is a non-text UI     1.6  (visible against paper)

Run after touching the palette:  python3 scripts/check-contrast.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSS = ROOT / "app" / "assets" / "css" / "main.css"

# token -> the floor it has to clear against --paper
FLOORS = {"ink": 7.0, "faint": 4.5, "ghost": 3.0, "line": 1.6}

# --select is a fill, not a text colour: it is the one token judged against the
# ink that sits on it rather than against the paper.
SELECT_FLOOR = 7.0

BLOCK = re.compile(r"\{([^}]*)\}", re.S)


def _channel(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance(hex_colour: str) -> float:
    h = hex_colour.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def contrast(a: str, b: str) -> float:
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def tokens(text: str) -> dict[str, str]:
    """The custom properties declared in one :root block."""
    out: dict[str, str] = {}
    for name, value in re.findall(r"(--[a-z-]+)\s*:\s*([^;]+);", text):
        out[name[2:]] = value.strip()
    return out


def schemes() -> list[tuple[str, dict[str, str]]]:
    """The light :root, then the dark one inside the media query."""
    found: list[tuple[str, dict[str, str]]] = []
    for match in re.finditer(r"(:root)\s*" + BLOCK.pattern, CSS.read_text(encoding="utf-8"), re.S):
        found.append((match.group(1), tokens(match.group(2))))
    # the first :root is the light scheme, the second is the dark override
    return [("light", found[0][1]), ("dark", found[1][1])]


def main() -> int:
    bad = 0
    for name, tok in schemes():
        paper = tok.get("paper")
        if not paper:
            print(f"{name}: no --paper")
            return 1
        print(f"\n{name}  paper {paper}")
        for key, floor in FLOORS.items():
            value = tok.get(key)
            if not value:
                print(f"  {key:6} MISSING")
                bad += 1
                continue
            ratio = contrast(value, paper)
            ok = ratio >= floor
            bad += not ok
            print(f"  {key:6} {value:9} {ratio:6.2f}  floor {floor:4.1f}  {'ok' if ok else 'FAIL'}")

    # the selection fill carries ink, so it is measured that way
    for name, tok in schemes():
        sel, ink = tok.get("select"), tok.get("ink")
        if sel and ink:
            ratio = contrast(ink, sel)
            ok = ratio >= SELECT_FLOOR
            bad += not ok
            print(f"  {name:5} select {sel}  ink on it {ratio:5.2f}  "
                  f"floor {SELECT_FLOOR:4.1f}  {'ok' if ok else 'FAIL'}")

    # A control drawn in --ghost is a control the reader cannot find. Every
    # live control must resolve to --faint or stronger. `--empty` is the
    # exception written into the design: an option that is inert on purpose has
    # to look inert, and it sits at the 3:1 floor instead.
    css = CSS.read_text(encoding="utf-8")
    offenders = []
    for match in re.finditer(r"([^{}]+)\{([^}]*)\}", css):
        selector, body = match.group(1).strip(), match.group(2)
        if not re.search(r"color\s*:\s*var\(--ghost\)", body):
            continue
        if "--empty" in selector:
            continue
        interactive = (".tok", ".chip", ".menu__row", ".menu__more", "button",
                       ".leaf__cont", ".leaf__by", ".leaf__src", ".leaf__note",
                       ".find", ".hit", ".find__count")
        if any(s in selector for s in interactive):
            offenders.append(selector.split("\n")[-1].strip())
    if offenders:
        bad += len(offenders)
        print("\ncontrols painted in --ghost (unfindable):")
        for s in offenders:
            print(f"  {s}")

    print(f"\n{'FAIL' if bad else 'ok'} — {bad} problem(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
