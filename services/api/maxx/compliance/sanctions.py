"""Screen seller names against the US Treasury OFAC sanctions lists.

The data is OFAC's public SDN list and its aliases (sdn.csv and alt.csv, from the Sanctions List
Service). It is refreshed into the `sanctions_entries` table by the worker every day, or by hand:

    uv run python -m maxx.compliance.sanctions refresh

Matching is deliberately generous: names are normalised (accents, punctuation, word order and
common company suffixes removed) and compared by shared words and by Jaro-Winkler similarity, so
"Acme Trading LLC" also finds "TRADING ACME". A match never rejects anyone by itself: it sends the
seller to a person, who clears or blocks them. If the list has never been loaded, nobody is
cleared; screening waits until it is.
"""

from __future__ import annotations

import csv
import io
import logging
import re
import sys
import time
import unicodedata
from dataclasses import dataclass
from threading import Lock

import httpx2 as httpx
from sqlalchemy import delete, func, select

from maxx import audit, schema, storage
from maxx.config import settings

log = logging.getLogger(__name__)
VERSION_FLAG = "sanctions_loaded_at"
SUFFIXES = {
    "LTD",
    "LIMITED",
    "LLC",
    "LLP",
    "INC",
    "INCORPORATED",
    "CORP",
    "CORPORATION",
    "CO",
    "COMPANY",
    "GMBH",
    "AG",
    "SA",
    "SAS",
    "SARL",
    "SRL",
    "SPA",
    "BV",
    "NV",
    "PLC",
    "PTY",
    "OOO",
    "OAO",
    "ZAO",
    "PJSC",
    "JSC",
    "AO",
    "THE",
    "AND",
    "OF",
    "DE",
    "LA",
    "EL",
    "AL",
}


@dataclass(frozen=True)
class Hit:
    entry_id: str
    name: str
    program: str
    score: float

    def as_dict(self) -> dict:
        return {
            "entry_id": self.entry_id,
            "name": self.name,
            "program": self.program,
            "score": round(self.score, 3),
        }


def normalise(name: str) -> str:
    text = unicodedata.normalize("NFKD", name or "")
    text = "".join(c for c in text if not unicodedata.combining(c)).upper()
    text = re.sub(r"[^A-Z0-9 ]+", " ", text)
    words = [w for w in text.split() if w not in SUFFIXES]
    return " ".join(sorted(words))


def _jaro_winkler(a: str, b: str) -> float:
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0
    window = max(len(a), len(b)) // 2 - 1
    flags_a, flags_b = [False] * len(a), [False] * len(b)
    matches = 0
    for i, char in enumerate(a):
        for j in range(max(0, i - window), min(len(b), i + window + 1)):
            if not flags_b[j] and b[j] == char:
                flags_a[i] = flags_b[j] = True
                matches += 1
                break
    if not matches:
        return 0.0
    transpositions, k = 0, 0
    for i, char in enumerate(a):
        if flags_a[i]:
            while not flags_b[k]:
                k += 1
            if char != b[k]:
                transpositions += 1
            k += 1
    m = float(matches)
    jaro = (m / len(a) + m / len(b) + (m - transpositions / 2) / m) / 3
    prefix = 0
    for x, y in zip(a[:4], b[:4], strict=False):
        if x != y:
            break
        prefix += 1
    return jaro + prefix * 0.1 * (1 - jaro)


def _covered(words: list[str], other: list[str]) -> float:
    """How well every word of `words` is matched by some word of `other` (mean best match)."""
    return sum(max(_jaro_winkler(w, o) for o in other) for w in words) / len(words)


def similarity(query: str, entry: str) -> float:
    """How alike a screened name and a list entry are, from 0 to 1 (both normalised).

    Each word must match a word of the other name (spelling variants allowed), so one shared word
    ("TRADING") is not a match. A name of two or more words whose words all appear exactly in a
    listed name also counts, because leaving out a middle name is the easiest way to slip past
    screening. That over-flags common names, which is why a match goes to a person.
    """
    q, e = query.split(), entry.split()
    if not q or not e:
        return 0.0
    if len(q) == 1 or len(e) == 1:
        return _jaro_winkler(query, entry)
    contained = 1.0 if len(q) >= 2 and set(q) <= set(e) else 0.0
    return max(contained, min(_covered(q, e), _covered(e, q)))


class _Index:
    def __init__(self):
        self.lock = Lock()
        self.loaded_at: str | None = None
        self.entries: list[tuple[str, str, str, str]] = []  # entry_id, name, normalised, program
        self.by_word: dict[str, list[int]] = {}

    def ensure(self) -> None:
        version = audit.flag(VERSION_FLAG)
        if version == self.loaded_at:
            return
        with self.lock:
            if version == self.loaded_at:
                return
            with storage.get_store().engine.connect() as db:
                rows = db.execute(
                    select(
                        schema.sanctions_entries.c.entry_id,
                        schema.sanctions_entries.c.name,
                        schema.sanctions_entries.c.normalized,
                        schema.sanctions_entries.c.program,
                    )
                ).all()
            entries = [tuple(r) for r in rows]
            by_word: dict[str, list[int]] = {}
            for index, (_, _, norm, _) in enumerate(entries):
                for word in set(norm.split()):
                    by_word.setdefault(word[:4], []).append(index)
            self.entries, self.by_word, self.loaded_at = entries, by_word, version


_index = _Index()


def loaded() -> bool:
    return audit.flag(VERSION_FLAG) is not None


def screen(names: list[str]) -> list[Hit]:
    """Possible matches for any of these names, best first. Raises if the list is not loaded."""
    if not loaded():
        raise RuntimeError("The sanctions list has not been loaded yet.")
    _index.ensure()
    hits: dict[str, Hit] = {}
    for raw in names:
        query = normalise(raw)
        if len(query) < 3:
            continue
        candidates: set[int] = set()
        for word in query.split():
            candidates.update(_index.by_word.get(word[:4], []))
        for index in candidates:
            entry_id, name, norm, program = _index.entries[index]
            score = similarity(query, norm)
            if score >= settings.sanctions_threshold:
                best = hits.get(entry_id)
                if best is None or score > best.score:
                    hits[entry_id] = Hit(entry_id, name, program, score)
    return sorted(hits.values(), key=lambda h: -h.score)[:10]


# ---- loading -----------------------------------------------------------------------------------


def _clean(value: str) -> str:
    value = (value or "").strip()
    return "" if value == "-0-" else value


def parse(sdn_csv: str, alt_csv: str) -> list[dict]:
    """Rows for the table from OFAC's sdn.csv (primary names) and alt.csv (aliases)."""
    rows: list[dict] = []
    programs: dict[str, str] = {}
    for record in csv.reader(io.StringIO(sdn_csv)):
        if len(record) < 4 or not record[0].strip().isdigit():
            continue
        entry_id, name = record[0].strip(), _clean(record[1])
        programs[entry_id] = _clean(record[3])
        if name:
            rows.append(
                {
                    "id": f"{entry_id}:0",
                    "entry_id": entry_id,
                    "name": name[:400],
                    "normalized": normalise(name)[:400],
                    "kind": _clean(record[2])[:20] or "entity",
                    "program": programs[entry_id][:200],
                }
            )
    for record in csv.reader(io.StringIO(alt_csv)):
        if len(record) < 4 or not record[0].strip().isdigit():
            continue
        entry_id, alias_id, name = record[0].strip(), record[1].strip(), _clean(record[3])
        if name:
            rows.append(
                {
                    "id": f"{entry_id}:{alias_id}",
                    "entry_id": entry_id,
                    "name": name[:400],
                    "normalized": normalise(name)[:400],
                    "kind": "alias",
                    "program": programs.get(entry_id, "")[:200],
                }
            )
    return [r for r in rows if r["normalized"]]


def load(sdn_csv: str, alt_csv: str, source: str = "file") -> int:
    rows = parse(sdn_csv, alt_csv)
    if len(rows) < 10 and source == "ofac":
        raise RuntimeError("The downloaded sanctions list looks empty; keeping the old one.")
    unique = {row["id"]: row for row in rows}
    with storage.get_store().engine.begin() as db:
        db.execute(delete(schema.sanctions_entries))
        batch = list(unique.values())
        for start in range(0, len(batch), 1000):
            db.execute(schema.sanctions_entries.insert(), batch[start : start + 1000])
    audit.set_flag(VERSION_FLAG, f"{int(time.time())}:{len(unique)}:{source}"[:200])
    audit.record("system", "sanctions.loaded", source, f"{len(unique)} names")
    return len(unique)


async def refresh() -> int:
    """Download the current lists from OFAC and replace the table."""
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as http:
        sdn = await http.get(settings.sanctions_sdn_url)
        alt = await http.get(settings.sanctions_alt_url)
    if sdn.status_code != 200 or alt.status_code != 200:
        raise RuntimeError(f"OFAC download failed ({sdn.status_code}, {alt.status_code}).")
    return load(sdn.text, alt.text, "ofac")


def age_seconds() -> float | None:
    value = audit.flag(VERSION_FLAG)
    if not value:
        return None
    return time.time() - int(value.split(":")[0])


def count() -> int:
    with storage.get_store().engine.connect() as db:
        return int(db.execute(select(func.count()).select_from(schema.sanctions_entries)).scalar())


if __name__ == "__main__":
    import asyncio

    if sys.argv[1:] != ["refresh"]:
        print("usage: python -m maxx.compliance.sanctions refresh")
        sys.exit(2)
    print(f"Loaded {asyncio.run(refresh())} OFAC names.")
