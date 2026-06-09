"""
Build data/rection.json from the kaikki.org Finnish Wiktionary extract.

Reads scripts/raw/kaikki_finnish.jsonl directly so that all senses are
processed — data/verbs.json caps glosses at 5 per verb and would miss
rection annotations in later senses.

Two annotation sources are checked per sense:
  1. Bracketed text in the English gloss: "to hold [with partitive]"
  2. The sense's raw_tags field when it contains a "+ <case>" pattern
     emitted by Wiktionary rection templates.

Annotation grammar (unchanged from previous version):
  - `;`-separated clauses are alternative patterns for the same sense
  - `and` / `along with` joins complements with DIFFERENT roles
  - `or` joins interchangeable cases within one role
  - a quoted gloss after a case is the English meaning of that complement
  - `<case> of third infinitive` is the MA-infinitive in that case
  - parentheticals are usage conditions — stripped before parsing

Run: python scripts/extract_rection.py
     (requires scripts/raw/kaikki_finnish.jsonl from download.py)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = ROOT / "scripts" / "raw" / "kaikki_finnish.jsonl"
FREQ_FILE = ROOT / "scripts" / "raw" / "frequency_fi.txt"

FREQUENCY_CUTOFF = 20000

CASES = (
    "nominative|genitive|partitive|inessive|elative|illative|adessive|"
    "ablative|allative|essive|translative|abessive|instructive|comitative|"
    "accusative"
)
ORDINAL = {"first": "1", "second": "2", "third": "3"}

TOKEN = re.compile(
    rf"\b({CASES}|first infinitive|second infinitive|third infinitive)\b"
    r"(?:\s+of\s+(first|second|third)\s+infinitive)?"
    r"(?:\s+'([^']*)')?"
)

BRACKET = re.compile(r"\s*\[([^\]]*)\]")
PAREN = re.compile(r"\([^()]*\)")
PLUS_TAG = re.compile(rf"^\+\s*({CASES})\s*$")


def load_frequency() -> dict[str, int]:
    if not FREQ_FILE.exists():
        print(f"[warn] frequency list not found at {FREQ_FILE}; skipping freq filter")
        return {}
    ranks: dict[str, int] = {}
    with FREQ_FILE.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            parts = line.strip().split()
            if parts and parts[0] not in ranks:
                ranks[parts[0]] = i
    return ranks


def parse_segment(seg: str) -> dict | None:
    if "participle" in seg or "verbal noun" in seg:
        return None
    comps: list[str] = []
    hint: str | None = None
    for m in TOKEN.finditer(seg):
        base, ordinal, h = m.group(1), m.group(2), m.group(3)
        if base.endswith("infinitive"):
            comp = f"inf{ORDINAL[base.split()[0]]}"
        elif ordinal:
            comp = f"inf{ORDINAL[ordinal]}_{base}"
        else:
            comp = base
        if comp not in comps:
            comps.append(comp)
        if h:
            hint = h.strip()
    if not comps:
        return None
    return {"complements": comps, "hint": hint}


def parse_annotation(text: str) -> list[dict]:
    cleaned = PAREN.sub(" ", text)
    candidates = []
    for clause in re.split(r";\s*(?:or\s+)?", cleaned):
        for seg in re.split(r",?\s+(?:and|along with)\s+", clause):
            parsed = parse_segment(seg)
            if parsed:
                candidates.append(parsed)
    return candidates


def merge_candidates(candidates: list[dict]) -> list[dict]:
    by_hint: dict[str | None, list[str]] = {}
    for c in candidates:
        acc = by_hint.setdefault(c["hint"], [])
        for comp in c["complements"]:
            if comp not in acc:
                acc.append(comp)
    return [{"accept": comps, "hint": hint} for hint, comps in by_hint.items()]


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def display_gloss(gloss: str) -> str:
    g = BRACKET.sub("", gloss)
    g = re.sub(r"\s{2,}", " ", g).strip().strip(";").strip()
    if len(g) > 120:
        cut = g.find(" (")
        if 20 < cut < 120:
            g = g[:cut].rstrip(",;: ")
    return g


def items_from_sense(sense: dict) -> list[tuple[str, str | None, list[str], str]]:
    """Return (key, hint, accept, display_gloss) tuples from one sense."""
    results = []
    glosses = sense.get("glosses") or []
    first_gloss = glosses[0] if glosses and isinstance(glosses[0], str) else ""

    # Source 1: [with X] brackets in any gloss line
    for gloss in glosses:
        if not isinstance(gloss, str):
            continue
        for m in BRACKET.finditer(gloss):
            merged = merge_candidates(parse_annotation(m.group(1)))
            for item in merged:
                shown = display_gloss(gloss)
                if not shown:
                    continue
                key = "rection:" + "+".join(sorted(item["accept"]))
                if item["hint"]:
                    key += ":" + slug(item["hint"])
                results.append((key, item["hint"], item["accept"], shown))

    # Source 2: raw_tags matching "+ <case>" (Wiktionary rection templates)
    shown_fallback = display_gloss(first_gloss) if first_gloss else ""
    for tag in sense.get("raw_tags") or []:
        if not isinstance(tag, str):
            continue
        m = PLUS_TAG.match(tag.strip())
        if m and shown_fallback:
            comp = m.group(1)
            key = f"rection:{comp}"
            results.append((key, None, [comp], shown_fallback))

    return results


def main() -> int:
    if not RAW.exists():
        raise SystemExit(f"Missing {RAW}. Run scripts/download.py first.")

    print("Loading frequency list...")
    freq = load_frequency()

    out_words = []
    vocab: set[str] = set()
    n_items = 0

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

            if entry.get("pos") != "verb":
                continue
            if not entry.get("inflection_templates"):
                continue
            word = entry.get("word")
            if not word:
                continue

            # Frequency filter (same logic as extract.py)
            rank = freq.get(word.lower())
            for f in entry.get("forms") or []:
                s = f.get("form")
                if not s:
                    continue
                r = freq.get(s.lower())
                if r is not None and (rank is None or r < rank):
                    rank = r
            if freq and (rank is None or rank > FREQUENCY_CUTOFF):
                continue

            # Collect items from all senses and sub-senses
            items: dict[str, dict] = {}
            for sense in entry.get("senses") or []:
                for sense_like in [sense] + list(sense.get("subsenses") or []):
                    for key, hint, accept, shown in items_from_sense(sense_like):
                        existing = items.get(key)
                        if existing:
                            if shown not in existing["glosses"] and len(existing["glosses"]) < 3:
                                existing["glosses"].append(shown)
                        else:
                            items[key] = {
                                "key":    key,
                                "glosses": [shown],
                                "hint":   hint,
                                "accept": accept,
                            }

            if not items:
                continue

            for it in items.values():
                vocab.update(it["accept"])
            n_items += len(items)
            out_words.append({
                "word":           word,
                "frequency_rank": rank,
                "items":          list(items.values()),
            })

    out_words.sort(key=lambda w: w.get("frequency_rank") or 10**9)

    payload = {
        "_source": (
            "Rection annotations from English Wiktionary Finnish verb senses "
            "(en.wiktionary.org, via the kaikki.org extract), CC BY-SA 4.0. "
            "Parsed by scripts/extract_rection.py."
        ),
        "complements": sorted(vocab),
        "words":       out_words,
    }
    (DATA / "rection.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    print(f"Wrote {len(out_words)} verbs, {n_items} rection items")
    print(f"Complement vocabulary ({len(vocab)}): {', '.join(sorted(vocab))}")
    for w in out_words[:10]:
        for it in w["items"]:
            hint = f" '{it['hint']}'" if it["hint"] else ""
            print(f"  {w['word']:14s} + {' or '.join(it['accept'])}{hint}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
