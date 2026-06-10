"""
Augment data/nouns.json and data/verbs.json with example sentences from
Tatoeba (tatoeba.org, CC BY 2.0 FR).

Downloads three files into scripts/raw/ — safe to re-run, already-cached
files are skipped:
  fin_sentences.tsv.bz2   (~2 MB)   Finnish sentences
  eng_sentences.tsv.bz2   (~45 MB)  English sentences
  links.tar.bz2            (~100 MB) All inter-language links (contains links.csv)

Only words with fewer than 3 examples are augmented. Words that already have
3 are left untouched, so you can re-run safely.

Run: python scripts/extract_tatoeba.py
     (needs network on first run; cached files are reused on subsequent runs)
"""

from __future__ import annotations

import bz2
import io
import json
import re
import sys
import tarfile
from collections import defaultdict
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
RAW  = ROOT / "scripts" / "raw"
DATA = ROOT / "data"

SOURCES = {
    "fin_sentences.tsv.bz2": "https://downloads.tatoeba.org/exports/per_language/fin/fin_sentences.tsv.bz2",
    "eng_sentences.tsv.bz2": "https://downloads.tatoeba.org/exports/per_language/eng/eng_sentences.tsv.bz2",
    "links.tar.bz2":         "https://downloads.tatoeba.org/exports/links.tar.bz2",
}

MIN_LEN = 8    # characters — skip very short sentences
MAX_LEN = 120  # characters — skip sentences too long to read comfortably
MAX_EX  = 3    # examples per word (same cap as extract.py)


# --------------------------------------------------------------------------

def download(url: str, dest: Path) -> None:
    if dest.exists():
        print(f"  [skip] {dest.name} ({dest.stat().st_size / 1e6:.1f} MB cached)")
        return
    print(f"  [get]  {url}")
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        written = 0
        with dest.open("wb") as f:
            for chunk in r.iter_content(chunk_size=256 * 1024):
                if not chunk:
                    continue
                f.write(chunk)
                written += len(chunk)
                if total:
                    pct = 100 * written / total
                    print(f"\r       {written/1e6:7.1f} / {total/1e6:.1f} MB  ({pct:.0f}%)", end="", flush=True)
                else:
                    print(f"\r       {written/1e6:7.1f} MB", end="", flush=True)
        print()


def load_tsv_bz2(path: Path) -> dict[int, str]:
    """Return {sentence_id: text} from a bz2-compressed tab-separated sentences file."""
    out: dict[int, str] = {}
    with bz2.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 3:
                try:
                    out[int(parts[0])] = parts[2]
                except ValueError:
                    continue
    return out


def load_links(path: Path, fi_ids: set[int]) -> dict[int, list[int]]:
    """Return {fi_sentence_id: [en_sentence_id, ...]} for Finnish sentences only.
    Handles both plain .tar.bz2 (contains links.csv) and plain .bz2 formats.
    The links file is large; we only keep rows where one side is a known Finnish ID.
    """
    fi_to_en: dict[int, list[int]] = defaultdict(list)
    raw_bytes: bytes

    # links.tar.bz2 is a tarball containing a single "links.csv"
    with tarfile.open(path, "r:bz2") as tf:
        member = next((m for m in tf.getmembers() if m.name.endswith(".csv")), None)
        if member is None:
            raise RuntimeError(f"No .csv found inside {path.name}")
        raw_bytes = tf.extractfile(member).read()

    for line in io.TextIOWrapper(io.BytesIO(raw_bytes), encoding="utf-8"):
        parts = line.rstrip("\n").split("\t")
        if len(parts) < 2:
            continue
        try:
            a, b = int(parts[0]), int(parts[1])
        except ValueError:
            continue
        if a in fi_ids:
            fi_to_en[a].append(b)
        elif b in fi_ids:
            fi_to_en[b].append(a)
    return fi_to_en


# --------------------------------------------------------------------------

def normalize(s: str) -> str:
    """Lowercase, collapse whitespace, normalize apostrophes (matches drill.js)."""
    s = s.strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[‘’‚‛ʼ´`]", "'", s)
    return s


def tokenize(s: str) -> list[str]:
    """Split a normalized Finnish sentence into word tokens."""
    return re.findall(r"[a-zåäöšž']+", s)


def build_token_index(fi_sentences: dict[int, str]) -> dict[str, list[int]]:
    """token → [sentence_id, ...] inverted index."""
    idx: dict[str, list[int]] = defaultdict(list)
    for sid, text in fi_sentences.items():
        if not (MIN_LEN <= len(text) <= MAX_LEN):
            continue
        for tok in set(tokenize(normalize(text))):  # set: one entry per sentence
            idx[tok].append(sid)
    return idx


def find_examples(
    inflections: dict[str, str],
    token_index: dict[str, list[int]],
    fi_sentences: dict[int, str],
    fi_to_en: dict[int, list[int]],
    en_sentences: dict[int, str],
    existing: list[dict],
    max_ex: int = MAX_EX,
) -> list[dict]:
    """Return up to max_ex new {fi, en} examples not duplicating existing ones."""
    existing_fi = {normalize(e["fi"] if isinstance(e, dict) else e) for e in existing}
    needed = max_ex - len(existing)
    if needed <= 0:
        return []

    # Collect candidate sentence IDs — one per unique form to spread variety
    candidates: list[tuple[int, str]] = []  # (sid, fi_text)
    seen_sids: set[int] = set()
    forms_used: set[str] = set()

    # Sort forms by length desc so longer (more specific) forms match first
    sorted_forms = sorted(
        ((k, v) for k, v in inflections.items() if v and v not in ("-", "—")),
        key=lambda kv: len(kv[1]), reverse=True
    )

    for _, form in sorted_forms:
        norm_form = normalize(form)
        if norm_form in forms_used:
            continue
        for sid in token_index.get(norm_form, []):
            if sid in seen_sids:
                continue
            fi_text = fi_sentences.get(sid, "")
            if not (MIN_LEN <= len(fi_text) <= MAX_LEN):
                continue
            if normalize(fi_text) in existing_fi:
                continue
            # Whole-word check: token must appear as an exact token
            if norm_form not in set(tokenize(normalize(fi_text))):
                continue
            candidates.append((sid, fi_text))
            seen_sids.add(sid)
            forms_used.add(norm_form)
        if len(candidates) >= needed * 3:
            break  # enough raw candidates

    # Prefer sentences that have English translations
    def has_en(sid: int) -> bool:
        return any(en_sentences.get(eid) for eid in fi_to_en.get(sid, []))

    candidates.sort(key=lambda x: (not has_en(x[0]), len(x[1])))

    new_examples: list[dict] = []
    for sid, fi_text in candidates:
        if len(new_examples) >= needed:
            break
        en_text = ""
        for eid in fi_to_en.get(sid, []):
            t = en_sentences.get(eid, "")
            if t:
                en_text = t
                break
        new_examples.append({"fi": fi_text, "en": en_text})

    return new_examples


# --------------------------------------------------------------------------

def main() -> int:
    RAW.mkdir(parents=True, exist_ok=True)

    print("[1/5] downloading Tatoeba files (skipped if already cached)...")
    for fname, url in SOURCES.items():
        download(url, RAW / fname)

    print("[2/5] loading Finnish sentences...")
    fi_sentences = load_tsv_bz2(RAW / "fin_sentences.tsv.bz2")
    print(f"      {len(fi_sentences):,} Finnish sentences")

    print("[3/5] loading English sentences...")
    en_sentences = load_tsv_bz2(RAW / "eng_sentences.tsv.bz2")
    print(f"      {len(en_sentences):,} English sentences")

    print("[4/5] loading cross-language links (this takes a minute)...")
    fi_ids = set(fi_sentences)
    fi_to_en = load_links(RAW / "links.tar.bz2", fi_ids)
    fi_with_en = sum(1 for v in fi_to_en.values() if v)
    print(f"      {len(fi_to_en):,} Finnish sentences linked, {fi_with_en:,} have English translation")

    print("[5/5] building inverted index...")
    token_index = build_token_index(fi_sentences)
    print(f"      {len(token_index):,} unique tokens indexed")

    for fname in ("nouns.json", "verbs.json"):
        path = DATA / fname
        data = json.loads(path.read_text(encoding="utf-8"))
        words = data["words"]

        already = sum(1 for w in words if len(w.get("examples") or []) >= MAX_EX)
        n_added = 0
        for w in words:
            existing = list(w.get("examples") or [])
            if len(existing) >= MAX_EX:
                continue
            new_ex = find_examples(
                w.get("inflections") or {},
                token_index,
                fi_sentences,
                fi_to_en,
                en_sentences,
                existing,
            )
            if new_ex:
                w["examples"] = existing + new_ex
                n_added += 1

        after = sum(1 for w in words if len(w.get("examples") or []) >= MAX_EX)
        print(f"\n{fname}: {already} → {after} words with full examples (+{n_added} words augmented)")
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    print("\nDone. Re-run anytime to top up examples for newly added words.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
