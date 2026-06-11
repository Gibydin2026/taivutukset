// Word marks: per-lemma labels that override the normal scheduler weights.
//
// Three states per word:
//   "normal"  — default, no override
//   "pin"     — always surfaces frequently, regardless of SRS/stats
//   "forget"  — surfaces very rarely (buried)
//
// Marks are stored per lemma (the dictionary headword), not per inflection
// key — if you pin "juosta" you want ALL its forms to come up more, not
// just one tense.

import * as storage from "./storage.js";

const KEY = "wordmarks_v1";

export const MARK = {
  NORMAL: "normal",
  PIN:    "pin",
  FORGET: "forget",
};

// Picker weight multipliers applied on top of the normal weight.
// PIN multiplier is high enough to dominate SRS weight even for a well-known
// word. FORGET is low enough to bury it without removing it entirely.
export const MARK_WEIGHT = {
  [MARK.NORMAL]: 1.0,
  [MARK.PIN]:    8.0,
  [MARK.FORGET]: 0.05,
};

export function loadMarks() {
  return storage.load(KEY, {});
}

export function saveMarks(marks) {
  storage.save(KEY, marks);
}

/** Get the mark for a lemma. Returns MARK.NORMAL if unset. */
export function getMark(marks, lemma) {
  return marks[lemma] || MARK.NORMAL;
}

/**
 * Cycle through NORMAL → PIN → FORGET → NORMAL and save.
 * Returns the new mark.
 */
export function cycleMark(marks, lemma) {
  const current = getMark(marks, lemma);
  const next =
    current === MARK.NORMAL ? MARK.PIN    :
    current === MARK.PIN    ? MARK.FORGET :
    MARK.NORMAL;
  if (next === MARK.NORMAL) {
    delete marks[lemma]; // keep storage compact
  } else {
    marks[lemma] = next;
  }
  saveMarks(marks);
  return next;
}

/** Apply the mark multiplier to an existing weight value. */
export function applyMark(weight, mark) {
  return weight * (MARK_WEIGHT[mark] || 1.0);
}
