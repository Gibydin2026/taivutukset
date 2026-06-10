"""
Generate compound numerals (11-19 and the tens 20-90) into data/numerals.json
by composing the singular paradigms already extracted for the base numerals.
No network or raw dump needed — runs purely off data/numerals.json.

Composition rules (standard Finnish, see e.g. VISK § 780-781):

  Teens (yksitoista .. yhdeksäntoista):
    every case = <unit in that case> + invariant "toista"
    e.g. kaksitoista -> kahdentoista (gen), kahtatoista (part),
         kahdessatoista (iness)

  Tens (kaksikymmentä .. yhdeksänkymmentä):
    nominative   = <unit nominative> + "kymmentä"   (kymmenen in partitive)
    other cases  = <unit in that case> + <kymmenen in the same case>
    e.g. kaksikymmentä -> kahdenkymmenen (gen), kahtakymmentä (part),
         kahdessakymmenessä (iness)

Only singular forms are generated — plural forms of compound numerals
(kahdettoista etc.) are vanishingly rare and not worth drilling. The drill
pool builder simply skips absent keys, same as the plurale tantum nouns.

Idempotent: words already present in numerals.json are left untouched, so a
future re-run of extract_numerals.py (which may bring richer Wiktionary
paradigms for these same words) wins over the generated entries.

Run: python scripts/gen_compound_numerals.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NUMERALS_FILE = ROOT / "data" / "numerals.json"

# The 12 cases compound numerals are drilled in. Comitative and instructive
# are plural-only in the app's case config; accusative isn't drilled.
CASES = [
    "nominative", "genitive", "partitive", "inessive", "elative", "illative",
    "adessive", "ablative", "allative", "essive", "translative", "abessive",
]

UNITS = [
    ("yksi",      "one",   "eleven",    None),
    ("kaksi",     "two",   "twelve",    "twenty"),
    ("kolme",     "three", "thirteen",  "thirty"),
    ("neljä",     "four",  "fourteen",  "forty"),
    ("viisi",     "five",  "fifteen",   "fifty"),
    ("kuusi",     "six",   "sixteen",   "sixty"),
    ("seitsemän", "seven", "seventeen", "seventy"),
    ("kahdeksan", "eight", "eighteen",  "eighty"),
    ("yhdeksän",  "nine",  "nineteen",  "ninety"),
]


def main() -> int:
    data = json.loads(NUMERALS_FILE.read_text(encoding="utf-8"))
    words = data["words"]
    by_word = {w["word"]: w for w in words}

    def sg(word: str, case: str) -> str | None:
        entry = by_word.get(word)
        if not entry:
            return None
        return entry["inflections"].get(f"{case}_singular")

    added = []

    for unit, _, teen_gloss, ten_gloss in UNITS:
        # ---- teens: unit form + invariant "toista"
        teen_word = unit + "toista"
        if teen_word not in by_word:
            infl = {}
            for case in CASES:
                u = sg(unit, case)
                if u:
                    infl[f"{case}_singular"] = u + "toista"
            if len(infl) == len(CASES):
                entry = {"word": teen_word, "translations": [teen_gloss], "inflections": infl}
                words.append(entry)
                by_word[teen_word] = entry
                added.append(teen_word)

        # ---- tens: unit form + kymmenen in the same case (nom is special)
        if ten_gloss is None:
            continue
        ten_word = unit + "kymmentä"
        if ten_word not in by_word:
            infl = {}
            for case in CASES:
                u = sg(unit, case)
                k = sg("kymmenen", "partitive" if case == "nominative" else case)
                if u and k:
                    infl[f"{case}_singular"] = u + k
            if len(infl) == len(CASES):
                entry = {"word": ten_word, "translations": [ten_gloss], "inflections": infl}
                words.append(entry)
                by_word[ten_word] = entry
                added.append(ten_word)

    if not added:
        print("Nothing to add — all compound numerals already present.")
        return 0

    NUMERALS_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"Added {len(added)} compound numerals: {', '.join(added)}")
    for w in added:
        i = by_word[w]["inflections"]
        print(f"  {w:22s} gen={i['genitive_singular']:24s} part={i['partitive_singular']:22s} ill={i['illative_singular']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
