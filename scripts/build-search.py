#!/usr/bin/env python3
"""Build the search index: a sharded bigram index over the whole corpus.

Why an index at all
───────────────────
The corpus is 125,314 poems / 21 MB of text, and the reader's browser cannot
hold it, let alone scan it. But a poetry site's whole reason to have search is
the half-remembered line — 「明月几时有」 — and that is a *substring* query over
the verse, which no amount of cleverness on the labels can answer.

Why bigrams
───────────
CJK has no word boundaries, so a word index needs a segmenter and a dictionary
and still cannot find a phrase that crosses a word boundary. A 2-gram index
answers any substring query exactly: split the query into overlapping pairs,
intersect their posting lists, then confirm the exact phrase against the real
text. It also costs nothing to build — there is no tokeniser to get wrong.

Why shards
───────────
The index is ~8 M postings; as one file it would be tens of megabytes that a
reader pays for on every visit. Sharded by a hash of the bigram, a query only
fetches the shards for the bigrams it actually contains — six characters is
five shards, tens of kilobytes — and the browser caches each shard forever.

Format
──────
Shards are written gzipped, `search/NNNN.bin.gz`; the layout below is what the
inflated bytes hold. gzip is handed mtime=0, so a rebuild that changes nothing
rewrites byte-identical files and the deploy stays quiet. The text is read back
from `t/*.json.gz`.

One shard is a sequence of entries:

    varint  byte length of the bigram (UTF-8)
    bytes   the bigram
    varint  posting count
    varint… the poem indices, delta-encoded and ascending

Sorted ids plus delta encoding is what makes this small: a posting costs about
1.5-3 bytes instead of 4. Title bigrams go in the same index as body bigrams,
so a query finds 「静夜思」 whether it is the title or a line.
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "public" / "corpus"
OUT = CORPUS / "search"
META_TS = ROOT / "app" / "corpus-meta.ts"


def corpus_meta() -> tuple[int, str]:
    """The poem count and the stamp the artifacts carry, as build-corpus.py wrote them.

    The index is built from the chunks, and the chunk set it reads has to be the
    one the app draws from: an index over a different corpus answers about poems
    the app cannot show, and it answers without saying so. Stopping here is
    cheap; a reader finding 「没有这一句」 for a line that exists is not.
    """
    if not META_TS.exists():
        sys.exit("app/corpus-meta.ts is missing — run scripts/build-corpus.py first")
    text = META_TS.read_text(encoding="utf-8")
    poems = re.search(r"CORPUS_N = (\d+)", text)
    build = re.search(r"CORPUS_BUILD = '([^']+)'", text)
    if not poems or not build:
        sys.exit("app/corpus-meta.ts has no CORPUS_N/CORPUS_BUILD — rebuild the corpus")
    return int(poems.group(1)), build.group(1)


# A bigram's shard. FNV-1a over the UTF-8 bytes: cheap, stable across runs, and
# spreads CJK evenly enough that the shards come out the same size.
# What the index holds. CJK plus Latin letters and digits, lowercased, with
# everything else — punctuation, spaces, verse breaks — dropped. Two reasons:
# a query is matched against the same normalisation, so 「shall i compare」 and
# 「Shall I compare」 are the same query; and dropping the separators means a
# phrase that spans a line break or a comma still matches, which is exactly how
# a reader half-remembers a line.
INDEXED = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff0-9a-z]")


# set from --shards in main(); a module global so shard_of stays a pure function
SHARDS = 8192


def shard_of(bigram: str) -> int:
    h = 0x811C9DC5
    for b in bigram.encode("utf-8"):
        h ^= b
        h = (h * 0x01000193) & 0xFFFFFFFF
    return h % SHARDS


def varint(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def normalise(s: str) -> str:
    return "".join(INDEXED.findall(s.lower()))


def bigrams(s: str) -> set[str]:
    return {s[i:i + 2] for i in range(len(s) - 1)}


def main() -> None:
    global SHARDS
    ap = argparse.ArgumentParser()
    ap.add_argument("--shards", type=int, default=SHARDS)
    SHARDS = ap.parse_args().shards

    if not CORPUS.exists():
        sys.exit("run scripts/build-corpus.py first")

    # bigram -> set of poem ids. A set, because a poem that says 明月 twice is
    # still one result, and deduping here is cheaper than in the query.
    postings: dict[str, set[int]] = defaultdict(set)
    n = 0
    # the names are zero-padded to a fixed width, so sorting them as strings is
    # sorting them as numbers, and n — the global poem id — counts in that order
    for f in sorted((CORPUS / "t").glob("*.json.gz")):
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            poems = json.load(fh)
        for p in poems:
            for text in (p.get("t", ""), p.get("x", "")):
                body = normalise(text)
                for b in bigrams(body):
                    postings[b].add(n)
            n += 1

    corpus_n, build = corpus_meta()
    if n != corpus_n:
        sys.exit(f"the chunks hold {n} poems; app/corpus-meta.ts says {corpus_n} — "
                 "this index would be built from a corpus the app does not read")

    # A reader who types an odd number of characters still means the phrase: the
    # last character alone would be a poor term, so a 3-character query indexes
    # as two bigrams and the exact phrase is confirmed against the text.
    shards: dict[int, dict[str, list[int]]] = defaultdict(dict)
    for b, ids in postings.items():
        shards[shard_of(b)][b] = sorted(ids)

    OUT.mkdir(parents=True, exist_ok=True)
    for old in (*OUT.glob("*.bin"), *OUT.glob("*.bin.gz")):
        old.unlink()

    total_raw = total_gz = 0
    biggest = (0, "")
    for i in range(SHARDS):
        chunk = bytearray()
        for b in sorted(shards.get(i, {})):
            ids = shards[i][b]
            raw = b.encode("utf-8")
            chunk += varint(len(raw)) + raw + varint(len(ids))
            prev = 0
            for pid in ids:
                chunk += varint(pid - prev)
                prev = pid
        blob = bytes(chunk)
        # mtime=0: gzip stamps the header with the current time by default, so a
        # rebuild that changes nothing would otherwise rewrite all 8192 files
        packed = gzip.compress(blob, 9, mtime=0)
        (OUT / f"{i:04d}.bin.gz").write_bytes(packed)
        total_raw += len(blob)
        total_gz += len(packed)
        if len(packed) > biggest[0]:
            biggest = (len(packed), f"{i:04d}.bin.gz")

    meta = {
        "shards": SHARDS,
        "bigrams": len(postings),
        "postings": sum(len(v) for v in postings.values()),
        "poems": n,
        # the corpus this index was built from; the app refuses to search when
        # it does not match the corpus compiled into the page
        "corpus": build,
    }
    (OUT / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

    print(f"  corpus    {build:>12}  ({meta['poems']:,} poems)")
    print(f"  bigrams   {meta['bigrams']:>12,}")
    print(f"  postings  {meta['postings']:>12,}")
    print(f"  shards    {SHARDS:>12}  ({total_gz / 1024 / 1024:.1f} MiB gz on "
          f"disk, {total_raw / 1024 / 1024:.0f} MiB inflated, largest "
          f"{biggest[1]} {biggest[0] / 1024:.0f} KiB gz)")


if __name__ == "__main__":
    main()
