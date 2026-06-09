"""
Build data/rection.json from the rection annotations already present in
data/verbs.json.

English Wiktionary marks verb rection (which case or infinitive form a verb's
complement takes) inside the sense gloss as a bracketed editorial note, e.g.

    "to believe, have faith [with illative 'in'] (someone's abilities ...)"
    "to hold [with partitive; or with elative 'onto' (often with kiinni)] (...)"
    "to speak, talk [with elative 'about, of' and allative 'to'] (...)"

Those brackets travel verbatim into the `translations` field that
scripts/extract.py copies out of the kaikki.org dump, so this script needs no
network access and no re-download — it parses what's already shipped. The
annotations are human-written Wiktionary content (CC BY-SA), not generated.

Annotation grammar, as observed across the dataset:
  - `;`-separated clauses are alternative patterns for the same sense
  - `and` / `along with` joins complements with DIFFERENT roles
    ("elative 'about' and allative 'to'" — two separate things to learn)
  - `or` joins interchangeable cases within one role
    ("with illative or allative")
  - a quoted gloss after a case is the English meaning of that complement
  - `<case> of third infinitive` is the MA-infinitive in that case
    ("illative of third infinitive 'to do'" → tekemään)
  - parentheticals are usage conditions, not rection — stripped before parsing

Each (verb, role) pair becomes one drill item: the prompt shows the verb, its
gloss, and the role's English hint (if any); the acceptable answers are the
role's interchangeable complements. Roles whose hints are missing get merged
per-verb-sense, since without a hint the drill question can't distinguish them.

Run:  python scripts/extract_rection.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

CASES = (
    "nominative|genitive|partitive|inessive|elative|illative|adessive|"
    "ablative|allative|essive|translative|abessive|instructive|comitative|"
    "accusative"
)
ORDINAL = {"first": "1", "second": "2", "third": "3"}

# One complement mention: a case or infinitive, optionally "of Nth infinitive",
# optionally followed by a curly-quoted English hint.
TOKEN = re.compile(
    rf"\b({CASES}|first infinitive|second infinitive|third infinitive)\b"
    r"(?:\s+of\s+(first|second|third)\s+infinitive)?"
    r"(?:\s+‘([^’]*)’)?"
)

BRACKET = re.compile(r"\s*\[([^\]]*)\]")
PAREN = re.compile(r"\([^()]*\)")


def parse_segment(seg: str) -> dict | None:
    """One role segment → {complements: [...], hint: str|None} or None."""
    # Complements expressed through participles or verbal nouns aren't case
    # rection in the drillable sense — skip those segments entirely.
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
    """Bracket text → list of role candidates [{complements, hint}]."""
    # Strip usage-condition parentheticals ("(of direction)", "(uncommon)")
    # so e.g. "(with adjectives or participles) with ablative" isn't dropped
    # by the participle filter. Hints use curly quotes, so nothing is lost.
    cleaned = PAREN.sub(" ", text)
    candidates = []
    for clause in re.split(r";\s*(?:or\s+)?", cleaned):
        for seg in re.split(r",?\s+(?:and|along with)\s+", clause):
            parsed = parse_segment(seg)
            if parsed:
                candidates.append(parsed)
    return candidates


def merge_candidates(candidates: list[dict]) -> list[dict]:
    """Group role candidates by hint.

    Hintless candidates from alternative clauses collapse into one item whose
    acceptable set is the union — without a hint the prompt can't tell the
    alternatives apart, so all of them must count as correct. Hinted
    candidates stay separate items (the hint disambiguates the prompt).
    """
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
    """Strip the rection bracket; trim an over-long trailing parenthetical."""
    g = BRACKET.sub("", gloss)
    g = re.sub(r"\s{2,}", " ", g).strip().strip(";").strip()
    if len(g) > 120:
        cut = g.find(" (")
        if 20 < cut < 120:
            g = g[:cut].rstrip(",;: ")
    return g


def main() -> int:
    verbs = json.loads((DATA / "verbs.json").read_text(encoding="utf-8"))

    out_words = []
    vocab: set[str] = set()
    n_items = 0

    for w in verbs["words"]:
        # key → item, keyed on (accept-set, hint) so identical patterns from
        # different glosses of the same verb merge instead of duplicating.
        items: dict[str, dict] = {}
        for gloss in w.get("translations") or []:
            for m in BRACKET.finditer(gloss):
                merged = merge_candidates(parse_annotation(m.group(1)))
                if not merged:
                    continue
                shown = display_gloss(gloss)
                for item in merged:
                    key = "rection:" + "+".join(sorted(item["accept"]))
                    if item["hint"]:
                        key += ":" + slug(item["hint"])
                    existing = items.get(key)
                    if existing:
                        if shown not in existing["glosses"] and len(existing["glosses"]) < 2:
                            existing["glosses"].append(shown)
                        continue
                    items[key] = {
                        "key": key,
                        "glosses": [shown],
                        "hint": item["hint"],
                        "accept": item["accept"],
                    }
        if not items:
            continue
        for it in items.values():
            vocab.update(it["accept"])
        n_items += len(items)
        out_words.append({
            "word": w["word"],
            "frequency_rank": w.get("frequency_rank"),
            "items": list(items.values()),
        })

    payload = {
        "_source": (
            "Rection annotations from English Wiktionary Finnish verb glosses "
            "(en.wiktionary.org, via the kaikki.org extract), CC BY-SA 4.0. "
            "Parsed by scripts/extract_rection.py from data/verbs.json."
        ),
        "complements": sorted(vocab),
        "words": out_words,
    }
    (DATA / "rection.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    print(f"Wrote {len(out_words)} verbs, {n_items} rection items")
    print(f"Complement vocabulary ({len(vocab)}): {', '.join(sorted(vocab))}")
    for w in out_words[:8]:
        for it in w["items"]:
            hint = f" ‘{it['hint']}’" if it["hint"] else ""
            print(f"  {w['word']:14s} + {' or '.join(it['accept'])}{hint}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
