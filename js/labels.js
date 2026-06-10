// Human-readable labels for inflection keys.
//
// Inflection keys in the data look like:
//   nouns: "genitive_singular"
//   verbs: "present_active_positive_1sg"        (finite with person)
//          "present_passive_positive"           (impersonal / passive)
//          "inf3_active", "inf5_active"         (infinitives)
//          "participle_past_active"             (participles)
//
// These helpers turn those keys into pretty labels using the config files.

function byId(list, id) {
  return list.find((x) => x.id === id);
}

// Rection complement labels. The drill answer is a case (or infinitive form)
// name, so each option carries a quick reminder of what that complement looks
// like — the question word for locative cases, the suffix or a model form
// elsewhere. Infinitive complements use the school-grammar names with a
// "tehdä" model so they're recognizable without knowing the numbering.
// Each entry has a primary name (the grammar term) and a hint (the question
// word or suffix that reminds learners what the case looks/sounds like).
// The hint is shown as secondary text in choice buttons and folded into the
// combined label string used by stats tables.
const COMPLEMENT_LABELS = {
  nominative:    { name: "nominative",          hint: "mikä" },
  genitive:      { name: "genitive",            hint: "kenen / minkä" },
  partitive:     { name: "partitive",           hint: "mitä" },
  accusative:    { name: "accusative",          hint: "kenet / minkä" },
  inessive:      { name: "inessive",            hint: "missä" },
  elative:       { name: "elative",             hint: "mistä" },
  illative:      { name: "illative",            hint: "mihin" },
  adessive:      { name: "adessive",            hint: "millä" },
  ablative:      { name: "ablative",            hint: "miltä" },
  allative:      { name: "allative",            hint: "mille" },
  essive:        { name: "essive",              hint: "-na / -nä" },
  translative:   { name: "translative",         hint: "-ksi" },
  abessive:      { name: "abessive",            hint: "-tta / -ttä" },
  instructive:   { name: "instructive",         hint: "-in" },
  comitative:    { name: "comitative",          hint: "-ine-" },
  inf1:          { name: "1st infinitive",      hint: "tehdä" },
  inf2_inessive: { name: "2nd inf. inessive",   hint: "tehdessä" },
  inf3_illative: { name: "MA-inf. illative",    hint: "tekemään" },
  inf3_elative:  { name: "MA-inf. elative",     hint: "tekemästä" },
  inf3_inessive: { name: "MA-inf. inessive",    hint: "tekemässä" },
};

// Full "name (hint)" string — used in stats tables where space is limited.
export function complementLabel(id) {
  const e = COMPLEMENT_LABELS[id];
  if (!e) return id;
  return e.hint ? `${e.name} (${e.hint})` : e.name;
}

// Just the grammar term, for use as the primary button label.
export function complementName(id) {
  return (COMPLEMENT_LABELS[id] || {}).name || id;
}

// Just the question-word / suffix reminder, for secondary button text.
export function complementHint(id) {
  return (COMPLEMENT_LABELS[id] || {}).hint || "";
}

// Label for a rection item key: "rection:<comp>[+<comp>…][:<hint-slug>]".
// Used by the stats tables, where the full per-option labels would be noisy —
// strip the parenthetical reminders and re-space the hint slug.
export function rectionLabel(key) {
  const parts = key.split(":");
  const comps = (parts[1] || "")
    .split("+")
    .map((c) => complementLabel(c).replace(/\s*\(.*\)$/, ""))
    .join(" or ");
  const hint = parts[2] ? ` ‘${parts[2].replace(/-/g, " ")}’` : "";
  return `+ ${comps}${hint}`;
}

export function nounLabel(key, cfg) {
  const [caseId, numberId] = key.split("_");
  const c = byId(cfg.nounCases.cases, caseId);
  const n = byId(cfg.nounCases.numbers, numberId);
  const caseLabel = c ? c.label : caseId;
  const numberLabel = n ? n.label.toLowerCase() : numberId;
  // Tack the ending hint onto the prompt (e.g. "ablative plural (-ltA)") so
  // the user has a reminder of what the target suffix looks like without
  // needing to cross-reference the filter grid. The nominative has no
  // ending, so we skip the parenthetical there. Empty-string hints are also
  // skipped for forward-compat with future cases whose shape doesn't map
  // cleanly to a single suffix.
  const hint = c && c.ending_hint ? ` (${c.ending_hint})` : "";
  return `${caseLabel} ${numberLabel}${hint}`;
}

export function verbLabel(key, cfg) {
  const parts = key.split("_");

  // Participles: "participle_<tense>_<voice>"
  if (parts[0] === "participle") {
    const [, tense, voice] = parts;
    return `${tense} ${voice} participle`;
  }

  // Infinitives: "inf1_long_<voice>", "inf2_<voice>", ... "inf5_<voice>"
  if (parts[0].startsWith("inf")) {
    const voice = parts[parts.length - 1];
    const tenseId = parts.slice(0, -1).join("_");
    const tense = byId(cfg.verbForms.tenses, tenseId);
    return `${tense ? tense.label : tenseId} (${voice})`;
  }

  // Finite: "<tense>_<voice>_<polarity>[_<person>]"
  // Tense can be a compound mood+aspect like "conditional_perfect" — take
  // two tokens when they form a known compound, otherwise one.
  const compound = new Set([
    "conditional_perfect", "imperative_perfect", "potential_perfect",
  ]);
  const twoTok = parts[0] + "_" + parts[1];
  let tenseId, rest;
  if (compound.has(twoTok)) {
    tenseId = twoTok;
    rest = parts.slice(2);
  } else {
    tenseId = parts[0];
    rest = parts.slice(1);
  }
  const [voiceId, polarityId, personId] = rest;
  const tense = byId(cfg.verbForms.tenses, tenseId);
  const voice = byId(cfg.verbForms.voices, voiceId);
  const polarity = byId(cfg.verbForms.polarities, polarityId);
  const person = personId ? byId(cfg.verbForms.persons, personId) : null;

  // "present, active, positive \u2014 min\u00e4"
  // The em-dash separates the grammatical description from the person/subject
  // so the person stays visually distinct (it's the part you actually say).
  const grammar = [
    tense ? tense.label : tenseId,
    voice ? voice.label : voiceId,
    polarity ? polarity.label : polarityId,
  ].join(", ");
  return person ? `${grammar} \u2014 ${person.label}` : grammar;
}
