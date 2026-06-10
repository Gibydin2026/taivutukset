"""
Build data/possessives.json from the kaikki.org Finnish Wiktionary extract.

Finnish nouns inflect with possessive suffixes for 5 possessor persons:
  1sg  taloni    2sg  talosi    3rd  talonsa
  1pl  talomme   2pl  talonne

The kaikki.org data emits possessive paradigms as separate inflection tables
after the base forms, each delimited by metadata-marker entries tagged
['table-tags'] or ['inflection-template']. This script splits on those
boundaries and detects which person each table belongs to by inspecting the
nominative singular form's suffix.

Requires:
  scripts/raw/kaikki_finnish.jsonl  — from download.py
  data/nouns.json                   — from extract.py  (provides word list
                                       and translations; no re-scraping needed)

Run: python scripts/extract_possessives.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = ROOT / "scripts" / "raw" / "kaikki_finnish.jsonl"

CASE_TAGS = frozenset({
    "nominative", "genitive", "partitive", "inessive", "elative", "illative",
    "adessive", "ablative", "allative", "essive", "translative", "abessive",
    "instructive", "comitative", "accusative",
})
NUMBER_TAGS = frozenset({"singular", "plural"})
META_TAGS   = frozenset({"table-tags", "inflection-template", "class"})


def split_into_tables(forms: list[dict]) -> list[dict[str, str]]:
    """Split a forms list into inflection tables at metadata-marker boundaries.

    Metadata entries (tagged with 'table-tags', 'inflection-template', or
    'class') act as separators. Each run of actual case+number forms between
    those markers becomes one table dict keyed by "case_number".

    Return value: list of non-empty table dicts.
      [0]  bare (base) forms
      [1+] possessive-suffix tables in kaikki's emission order
    """
    tables: list[dict[str, str]] = []
    current: dict[str, str] = {}

    for f in forms:
        tags = set(f.get("tags") or [])
        if tags & META_TAGS:
            if current:
                tables.append(current)
                current = {}
            continue
        form_str = f.get("form")
        if not form_str or form_str in ("-", "—"):
            continue
        cases = tags & CASE_TAGS
        nums  = tags & NUMBER_TAGS
        if len(cases) == 1 and len(nums) == 1:
            key = f"{next(iter(cases))}_{next(iter(nums))}"
            if key not in current:
                current[key] = form_str

    if current:
        tables.append(current)
    return tables


def detect_person(table: dict[str, str]) -> str:
    """Infer possessor person from the nominative form's suffix.

    Finnish possessive suffixes are unambiguous:
      -ni   → 1sg    -si   → 2sg
      -mme  → 1pl    -nne  → 2pl
      anything else → 3rd  (-nsa/-nsä/-Vn/-an/-ään etc.)

    Regular nouns: use nominative_singular.
    Plural-only nouns (plurale tantum like kasvot, housut): fall back to
    nominative_plural — the suffix pattern is identical.
    """
    nom = table.get("nominative_singular") or table.get("nominative_plural", "")
    if nom.endswith("mme"):
        return "1pl"
    if nom.endswith("nne"):
        return "2pl"
    if nom.endswith("ni"):
        return "1sg"
    if nom.endswith("si"):
        return "2sg"
    return "3rd"


def main() -> int:
    if not RAW.exists():
        raise SystemExit(f"Missing {RAW}. Run scripts/download.py first.")
    nouns_path = DATA / "nouns.json"
    if not nouns_path.exists():
        raise SystemExit("Missing data/nouns.json. Run scripts/extract.py first.")

    # Load the word list and metadata from data/nouns.json.
    # Those words are already frequency-filtered; we re-use that work.
    nouns_data = json.loads(nouns_path.read_text(encoding="utf-8"))
    noun_meta: dict[str, dict] = {}
    for w in nouns_data["words"]:
        noun_meta[w["word"]] = {
            "translations":   w.get("translations") or [],
            "group":          w.get("group") or "other",
            "frequency_rank": w.get("frequency_rank"),
        }
    wanted = set(noun_meta)
    print(f"Loaded {len(wanted):,} nouns from data/nouns.json")

    out_words: list[dict] = []
    skipped = 0

    print(f"Streaming {RAW.name}...")
    with RAW.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            if entry.get("pos") != "noun":
                continue
            if not entry.get("inflection_templates"):
                continue
            word = entry.get("word")
            if word not in wanted:
                continue

            tables = split_into_tables(entry.get("forms") or [])

            # tables[0] = bare forms (already in nouns.json); skip it.
            poss_tables = tables[1:]
            if not poss_tables:
                skipped += 1
                wanted.discard(word)
                continue

            inflections: dict[str, dict[str, str]] = {}
            for tbl in poss_tables:
                if not tbl:
                    continue
                person = detect_person(tbl)
                if person not in inflections:
                    inflections[person] = tbl

            if not inflections:
                skipped += 1
                wanted.discard(word)
                continue

            meta = noun_meta[word]
            out_words.append({
                "word":           word,
                "frequency_rank": meta["frequency_rank"],
                "translations":   meta["translations"],
                "group":          meta["group"],
                "inflections":    inflections,
            })
            wanted.discard(word)

    out_words.sort(key=lambda w: w.get("frequency_rank") or 10**9)

    payload = {
        "_source": (
            "Possessive suffix forms from English Wiktionary Finnish noun paradigms "
            "(en.wiktionary.org, via the kaikki.org extract), CC BY-SA 4.0. "
            "Parsed by scripts/extract_possessives.py."
        ),
        "possessors": ["1sg", "2sg", "3rd", "1pl", "2pl"],
        "cases":      nouns_data["cases"],
        "numbers":    nouns_data["numbers"],
        "words":      out_words,
    }
    (DATA / "possessives.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    print(f"Wrote {len(out_words):,} nouns with possessive forms "
          f"({skipped} skipped — no possessive table in kaikki data)")

    # Sanity check on a handful of well-known words
    sample = {"talo", "koira", "käsi", "nainen", "auto"}
    print("\nSanity check:")
    for w in out_words:
        if w["word"] not in sample:
            continue
        p1 = w["inflections"].get("1sg", {})
        p3 = w["inflections"].get("3rd", {})
        print(f"  {w['word']:10s}  "
              f"1sg nom={p1.get('nominative_singular','?')!r}  "
              f"ine={p1.get('inessive_singular','?')!r}  "
              f"3rd nom={p3.get('nominative_singular','?')!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
