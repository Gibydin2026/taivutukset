"""
Inspect raw kaikki.org data to understand how possessive suffix forms
and numerals are tagged. Run: python scripts/inspect_possessives.py
"""
from __future__ import annotations
import json
from pathlib import Path

RAW = Path(__file__).parent / "raw" / "kaikki_finnish.jsonl"
TARGETS = {("talo", "noun"), ("kaksi", "num"), ("kaksi", "numeral")}
found: set = set()

with RAW.open("r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        key = (e.get("word"), e.get("pos"))
        if key not in TARGETS or key in found:
            continue
        if not e.get("inflection_templates"):
            continue
        found.add(key)
        forms = e.get("forms") or []
        print(f"\n=== {key[0]} (pos={key[1]}) — {len(forms)} forms ===")
        for frm in forms[:50]:
            print(f"  {str(frm.get('form')):<28} {frm.get('tags')}")
        if len(found) >= 3:
            break

# Also count what pos values exist for numerals
print("\n=== POS values for 'kaksi', 'kolme', 'neljä', 'viisi' ===")
targets2 = {"kaksi", "kolme", "neljä", "viisi"}
with RAW.open("r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if e.get("word") in targets2:
            has_infl = bool(e.get("inflection_templates"))
            print(f"  {e['word']:<10} pos={e.get('pos'):<12} has_inflection_templates={has_infl}")
