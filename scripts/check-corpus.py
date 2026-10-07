#!/usr/bin/env python3
"""Check that the built corpus agrees with itself.

The corpus is four artifacts written from one list of poems, and the site reads
them in three different places: the chips get their choices from facets.json.gz,
a filter reads the columns, and a leaf prints the labels that ride in a text
chunk. Nothing in the running site compares those three, so a build that got one
of them wrong would not fail — it would just print one label where another
belongs, or count a label it cannot show.

That is not hypothetical. The format this replaced wrote the two multi-valued
axes as one byte per poem and read them as two; every poem's 情绪 and 视角 were
the wrong poem's, and half the corpus had none at all. Nothing caught it because
nothing looked. This looks.

    python3 scripts/check-corpus.py

Exits non-zero with the offending poems named. Checks the chunks in a spread
rather than all of them: a systematic mistake — an axis out of order, a
column written one poem short — shows up in any sample, and reading all 21 MB
of chunks on every check is not worth the minutes it costs. The stamp is
read from every chunk, because a stamp is only worth having if it covers what
it claims to.
"""
from __future__ import annotations

import array
import gzip
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "public" / "corpus"
META = ROOT / "app" / "corpus-meta.ts"

# How many chunks to read in full. Every 20th covers 5% of the corpus spread
# evenly across it, which is far more than enough to catch a mapping mistake.
STEP = 20

problems: list[str] = []


def fail(message: str) -> None:
    problems.append(message)


def column(axis: str, n: int) -> array.array:
    path = CORPUS / "col" / f"{axis}.bin.gz"
    raw = gzip.decompress(path.read_bytes())
    if len(raw) == n:
        codes = array.array("B")
    elif len(raw) == n * 2:
        codes = array.array("H")
    else:
        fail(f"col/{axis}.bin.gz holds {len(raw)} bytes; {n} or {n * 2} expected")
        return array.array("B")
    codes.frombytes(raw)
    if sys.byteorder == "big":
        codes.byteswap()
    return codes


def meta() -> dict[str, object]:
    """The generated constants, read as written rather than imported."""
    text = META.read_text(encoding="utf-8")
    out: dict[str, object] = {}
    for name in ("CORPUS_N", "CORPUS_PER_CHUNK", "CORPUS_CHUNKS"):
        m = re.search(rf"{name} = (\d+)", text)
        out[name] = int(m.group(1)) if m else None
    m = re.search(r"CORPUS_BUILD = '([^']+)'", text)
    out["CORPUS_BUILD"] = m.group(1) if m else None
    m = re.search(r"CORPUS_ORDER = \[(.*?)\]", text)
    out["CORPUS_ORDER"] = re.findall(r"'([^']+)'", m.group(1)) if m else []
    return out


def stamp(facets: dict, cols: dict, chunks: list[Path]) -> str:
    """The stamp the artifacts carry, recomputed from the artifacts themselves.

    This is the number that says the four artifacts are one corpus, and it is
    recomputed rather than read back: a check that asks the thing it is checking
    what the answer is has checked nothing. The recipe has to match
    scripts/build-corpus.py — each axis's name, its column's codes and its
    dictionary, then the text of every chunk, in the order they were written.
    """
    digest = hashlib.sha1()
    for axis, packed in facets["byAxis"].items():
        digest.update(axis.encode())
        digest.update(cols[axis].tobytes())
        digest.update("\x00".join(packed["dict"]).encode())
    for path in chunks:
        digest.update(gzip.decompress(path.read_bytes()))
    return digest.hexdigest()[:8]


def main() -> int:
    if not CORPUS.exists():
        print("no corpus — run scripts/build-corpus.py first")
        return 1

    for stale in ("index.json", "corpus.json"):
        if (CORPUS / stale).exists():
            fail(f"{stale} is still there; the site does not read it")
    if any((CORPUS / "search").glob("*.bin")):
        fail("search/ still holds uncompressed .bin shards")
    if any((CORPUS / "t").glob("*.json")):
        fail("t/ still holds uncompressed chunks")

    facets = json.load(gzip.open(CORPUS / "facets.json.gz", "rt", encoding="utf-8"))
    n = facets["n"]
    order = facets["order"]
    multi = set(facets["multi"])

    if not set(facets["byAxis"]) <= set(order):
        fail("facets.json.gz names an axis the chunk order does not have")

    cols = {}
    for axis, packed in facets["byAxis"].items():
        codes = column(axis, n)
        cols[axis] = codes
        if len(codes) != n:
            continue
        widest = (1 << len(packed["dict"])) - 1 if axis in multi else len(packed["dict"]) - 1
        high = max(codes) if n else 0
        if high > widest:
            fail(f"{axis}: a code is {high}, past the end of its {len(packed['dict'])}-value table")
        # the build-time counts have to be what the column says, or the panel's
        # first number and its hundredth would disagree
        if axis in multi:
            seen = Counter()
            for code in codes:
                for bit in range(len(packed["dict"])):
                    if code & (1 << bit):
                        seen[packed["dict"][bit]] += 1
        else:
            seen = Counter(packed["dict"][code] for code in codes)
        want = [seen[v] for v in packed["dict"]]
        if want != packed["counts"]:
            off = [packed["dict"][i] for i in range(len(want)) if want[i] != packed["counts"][i]][:4]
            fail(f"{axis}: facets counts disagree with the column at {off}")

    generated = meta()
    if generated["CORPUS_N"] != n:
        fail(f"app/corpus-meta.ts says {generated['CORPUS_N']} poems, the corpus has {n}")
    if generated["CORPUS_ORDER"] != order:
        fail("app/corpus-meta.ts lists the axes in a different order than the corpus")
    per = generated["CORPUS_PER_CHUNK"]
    chunks = sorted((CORPUS / "t").glob("*.json.gz"))
    if generated["CORPUS_CHUNKS"] != len(chunks):
        fail(f"app/corpus-meta.ts says {generated['CORPUS_CHUNKS']} chunks, there are {len(chunks)}")

    # The stamp is what says these artifacts are one corpus. They are written by
    # two passes — the columns and the chunks by build-corpus.py, the shards and
    # their meta by build-search.py — so a run that rebuilt some of them leaves
    # a site whose pieces disagree, and disagree quietly: a label counted out of
    # one corpus beside the text of another, or an index of poems that are no
    # longer on the site. Not one of those shows up as an error in the reader's
    # browser, which is why it is checked here.
    mine = stamp(facets, cols, chunks)
    index_path = CORPUS / "search" / "meta.json"
    index: dict = {}
    if not index_path.exists():
        fail("search/meta.json is missing — run scripts/build-search.py")
    else:
        index = json.loads(index_path.read_text(encoding="utf-8"))
        if index.get("poems") != n:
            fail(f"search/meta.json was built from {index.get('poems')} poems, "
                 f"the corpus has {n}")
    for where, got in (("app/corpus-meta.ts", generated["CORPUS_BUILD"]),
                       ("facets.json.gz", facets.get("v")),
                       ("search/meta.json", index.get("corpus"))):
        if got != mine:
            fail(f"{where} is stamped {got!r}; the artifacts hash to {mine!r}")
    want_per = max(per, 1)
    for at, f in enumerate(chunks):
        if f.name != f"{at:05d}.json.gz":
            fail(f"chunk {f.name} is not chunk number {at}")
            break
    if want_per * (len(chunks) - 1) >= n:
        fail(f"{len(chunks)} chunks of {want_per} hold more than the {n} poems that exist")

    checked = 0
    for at, f in enumerate(chunks):
        if at % STEP:
            continue
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            records = json.load(fh)
        if len(records) > want_per:
            fail(f"{f.name} holds {len(records)} poems, not {want_per}")
        for within, rec in enumerate(records):
            i = at * want_per + within
            if i >= n:
                fail(f"{f.name} poem {within} is past the end of the corpus")
                break
            if len(rec["l"]) != len(order):
                fail(f"poem {i}: a chunk label list {len(rec['l'])} long, not {len(order)}")
                break
            for axis in facets["byAxis"]:
                got = rec["l"][order.index(axis)]
                code = cols[axis][i]
                if axis in multi:
                    want = [v for k, v in enumerate(facets["byAxis"][axis]["dict"]) if code & (1 << k)]
                    # the leaf keeps the order the build ranked the tags in, so
                    # only the set is comparable
                    if sorted(got) != sorted(want):
                        fail(f"poem {i} {axis}: the chunk says {got}, the column says {want}")
                else:
                    want = facets["byAxis"][axis]["dict"][code]
                    if got != want:
                        fail(f"poem {i} {axis}: the chunk says {got!r}, the column says {want!r}")
            checked += 1

    print(f"  poems      {n}")
    print(f"  stamp      {mine}  (columns, dictionaries and every chunk)")
    print(f"  axes       {len(facets['byAxis'])} columns, "
          f"{sum(len(p['dict']) for p in facets['byAxis'].values())} values")
    print(f"  chunks     {len(chunks)} of {per}")
    print(f"  labels     {checked} poems checked against the columns")
    print()
    if problems:
        print(f"FAIL — {len(problems)} problem(s)")
        for p in problems[:20]:
            print("  ·", p)
        return 1
    print("ok — the columns, the tables, the counts, the chunk labels and the stamp agree")
    return 0


if __name__ == "__main__":
    sys.exit(main())
