const mainSystems = [
  ["B0_asr_plain", "Plain speech-to-text", "No context"],
  ["B1_asr_keywords_C3", "Keyword-assisted speech-to-text", "Normal context (C3)"],
  ["B1_asr_keywords_C4", "Keyword-assisted speech-to-text", "Misleading context (C4)"],
  ["B2_naive_llm_C3", "Generative rewrite", "Normal context (C3)"],
  ["B2_naive_llm_C4", "Generative rewrite", "Misleading context (C4)"],
  ["P_on_B1_C3", "Pehchaan", "Normal context (C3)"],
  ["P_on_B1_C4", "Pehchaan", "Misleading context (C4)"],
];
const variants = [
  ["P_C0", "Pehchaan on unprompted input", "Rules only (C0)"],
  ["P_C2", "Pehchaan on unprompted input", "Known brands and places (C2)"],
  ["P_C3", "Pehchaan on unprompted input", "Normal context (C3)"],
  ["P_C4", "Pehchaan on unprompted input", "Misleading context (C4)"],
];
const systemNames = new Map([...mainSystems, ...variants].map(([id, ...labels]) => [id, labels]));
const languages = {en: "Indian English", hi: "Hindi", hl: "Hinglish", te: "Telugu"};
const factTypes = {AMOUNT: "Amount", ORG: "Organisation", PERSON: "Person", PHONE: "Phone", PIN: "Postal PIN", PLACE: "Place"};

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({"&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"})[char]);
}

const validRate = (value) => Number.isFinite(value) && value >= 0 && value <= 1;
const percent = (value) => validRate(value) ? `${(100 * value).toFixed(1)}%` : "—";
const count = (value) => Number.isInteger(value) && value >= 0 ? String(value) : "—";
const decimal = (value) => Number.isFinite(value) && value >= 0 ? value.toFixed(2) : "—";
const ms = (value) => Number.isFinite(value) && value >= 0 ? `${value} ms` : "—";

function textName(id) {
  return (systemNames.get(id) || [id]).filter(Boolean).join(" · ");
}

function systemName(id) {
  const [name, context] = systemNames.get(id) || [id, ""];
  return `${escapeHtml(name)}${context ? `<small>${escapeHtml(context)}</small>` : ""}`;
}

function scoredMetric(row, key) {
  const value = row?.[key];
  const interval = row?.ci95?.[key];
  if (!validRate(value) || !Array.isArray(interval) || interval.length !== 2 || !interval.every(validRate)) {
    return percent(value);
  }
  return `${percent(value)}<small>${percent(interval[0])}–${percent(interval[1])}</small>`;
}

function table(caption, headers, ids, rows, main) {
  return `<div class="bench-table-scroll" tabindex="0" role="region" aria-label="${caption}">
    <table class="bench-table"><caption>${caption}</caption>
      <thead><tr><th scope="col">System</th>${headers.map((header) => `<th scope="col">${header}</th>`).join("")}</tr></thead>
      <tbody>${ids.map((id) => `<tr${id === main ? ' class="bench-main-system"' : ""}>
        <th scope="row">${systemName(id)}</th>${rows(id).map((value) => `<td>${value}</td>`).join("")}</tr>`).join("")}</tbody>
    </table></div>`;
}

function headline(run, systems) {
  return [["Silent errors", "silent_error_rate", "B1_asr_keywords_C3", percent],
    ["Fact accuracy", "entity_accuracy", "B1_asr_keywords_C3", percent],
    ["Damaged edits", "damaged_edits", "B2_naive_llm_C3", count]].map(([label, key, comparison, format]) => {
    const baseline = systems.get(comparison)?.[key];
    return `<div class="bench-kpi"><h2>${label}</h2><strong>${format(systems.get(run.main_system)?.[key])}</strong>
      <p>${escapeHtml(textName(run.main_system))}</p>
      <p class="bench-comparison"><b>${format(baseline)}</b> ${escapeHtml(textName(comparison))}</p></div>`;
  }).join("");
}

function silentChart(ids, systems, main) {
  const rates = ids.map((id) => systems.get(id)?.silent_error_rate);
  const maxPercent = Math.max(25, Math.ceil(Math.max(0, ...rates.filter(validRate)) * 4) * 25);
  return `<figure class="bench-chart" aria-hidden="true">
    <figcaption><h2>Silent errors by approach</h2><p>Share of facts that were wrong without a warning. Lower is better.</p></figcaption>
    <div class="bench-chart-axis"><span></span><div>${[0, 1, 2, 3, 4, 5].map((i) => `<span>${maxPercent * i / 5}%</span>`).join("")}</div><span></span></div>
    <div class="bench-chart-rows">${ids.map((id, index) => {
      const rate = rates[index];
      const width = validRate(rate) ? rate * 10000 / maxPercent : 0;
      return `<div class="bench-chart-row${id === main ? " bench-main-system" : ""}">
        <span>${systemName(id)}</span><div class="bench-chart-track"><span style="width:${width}%"></span></div>
        <b>${percent(rate)}</b></div>`;
    }).join("")}</div></figure>`;
}

function scoreTable(caption, ids, systems, main) {
  return table(caption, ["Silent errors ↓<small>95% interval</small>", "Fact accuracy ↑<small>95% interval</small>", "Damaged edits ↓"], ids, (id) => {
    const s = systems.get(id);
    return [scoredMetric(s, "silent_error_rate"), scoredMetric(s, "entity_accuracy"), count(s?.damaged_edits)];
  }, main);
}

function breakdown(kind, ids, systems, main) {
  const keys = [...new Set(ids.flatMap((id) => Object.keys(systems.get(id)?.[kind] || {})))].sort();
  if (!keys.length) return '<p>Breakdown unavailable for this report.</p>';
  const isLanguage = kind === "by_lang";
  const labels = isLanguage ? languages : factTypes;
  const caption = `Fact accuracy / silent errors by ${isLanguage ? "language" : "fact type"}`;
  return table(caption, keys.map((key) => escapeHtml(Object.hasOwn(labels, key) ? labels[key] : key)), ids, (id) => {
    return keys.map((key) => {
      const value = systems.get(id)?.[kind]?.[key];
      if (!value) return "—";
      return `${percent(value.accuracy)} / ${percent(value.silent_error_rate)}<small>${count(value.n)} facts</small>`;
    });
  }, main);
}

function processingTable(ids, systems, main) {
  return table("Processing times per clip", ["Speech-to-text<small>p50 / p95</small>", "Post-transcription<small>p50 / p95</small>"], ids, (id) => {
    const s = systems.get(id);
    const asrTimings = [s?.asr_ms_p50, s?.asr_ms_p95];
    const timings = [s?.harness_ms_p50, s?.harness_ms_p95];
    return [asrTimings.some(Number.isFinite) ? asrTimings.map(ms).join(" / ") : "Unavailable",
      timings.some(Number.isFinite) ? timings.map(ms).join(" / ") : "—"];
  }, main);
}

function scoringDetails(ids, systems, main) {
  return table("Additional scoring metrics", ["Critical accuracy ↑", "Over-correction ↓", "Flag precision ↑", "Flags / clip ↓", "Reachable accuracy ↑", "Unreachable accuracy ↑", "Word error rate ↓", "LLM uses / clip", "Clips with damage ↓", "Damage by reason"], ids, (id) => {
    const s = systems.get(id);
    const reasons = Object.entries(s?.damage_by_reason || {});
    return [percent(s?.critical_accuracy), percent(s?.over_correction_rate), percent(s?.flag_precision),
      decimal(s?.flags_per_clip), percent(s?.accuracy_reachable), percent(s?.accuracy_unreachable),
      Number.isFinite(s?.wer) && s.wer >= 0 ? `${(100 * s.wer).toFixed(1)}%` : "—", decimal(s?.llm_calls_per_clip),
      Number.isInteger(s?.clips_with_damage) ? `${count(s.clips_with_damage)} of ${count(s.clips)}` : "—",
      reasons.length ? reasons.map(([reason, n]) => `${escapeHtml(reason.replaceAll("_", " "))} ${count(n)}`).join(", ") : "—"];
  }, main);
}

function disclosure(label, content) {
  return `<details class="bench-disclosure"><summary>${label}</summary><div>${content}</div></details>`;
}

const measurementMethods = `<dl class="bench-methods">
  <dt>Same clips, same scorer</dt><dd>Each system hears the same audio. An independent scorer compares the resulting transcripts with the script’s labelled facts. It uses its own number reader and name-matching rules, including equivalent spellings, and shares neither code nor word tables with Pehchaan.</dd>
  <dt>Silent errors ↓ and fact accuracy ↑</dt><dd>Silent errors are wrong or missing facts without a matching question, divided by all labelled facts. Accuracy is correctly stated facts divided by all labelled facts. A wrong fact flagged with a matching question avoids a silent error and still counts as incorrect.</dd>
  <dt>Damaged edits ↓</dt><dd>The total number of harmful changes from each approach’s input to its output across the scored clips. The audit counts changes such as an invented name, a changed number or a rewrite that changes meaning. Formatting and repairs carry no penalty. Clips with damage counts each affected clip once out of all clips, and damage by reason counts the edits in each category.</dd>
  <dt>95% intervals</dt><dd>The harness resamples whole clips with replacement to estimate how much fact accuracy and silent errors vary. Small or overlapping differences are uncertain. The language and fact-type tables calculate rates within each group and show how many labelled facts contribute.</dd>
  <dt>Context levels</dt><dd>Normal context (C3) supplies relevant caller information. Misleading context (C4) uses the same audio and substitutes decoy names and numbers. The main Pehchaan system runs on the keyword-assisted transcript and checks it against a plain second transcript. The generative rewrite starts with an unprompted transcript and asks a model to rewrite it.</dd>
  <dt>Post-transcription time ↓</dt><dd>For Pehchaan, processing time covers transcript preparation, fact checks, any verifier work, and building the output. The rewrite baseline uses the model’s recorded request time, which may be read from cache. Both exclude speech-to-text and scoring. After sorting the clips with a timing, p50 marks the middle of the list and p95 the point about 95% through the list. The speech-to-text approaches have no post-transcription step.</dd>
  <dt>Speech-to-text time ↓</dt><dd>Speech-to-text requests run in parallel. For each clip the harness takes the longest participating model request, using recorded request times from the cache when available. This excludes queueing, browser transfer, processing, and scoring. Historical reports without this timing show “Unavailable”.</dd>
  <dt>Other accuracy measures ↑</dt><dd>Critical accuracy is correct phone numbers, postal PINs and amounts divided by all labelled facts of those types. Reachable and unreachable split the labels by whether the correct answer occurs in the normal call context. Each divides the number correct by the facts in its group.</dd>
  <dt>Over-correction ↓ and flags</dt><dd>Over-correction is the share of facts that were right in the input and wrong in the output, out of all facts that were right in the input. Flag precision is warranted questions divided by all questions asked (higher is better). Flags per clip is the total questions divided by clips (lower means fewer interruptions).</dd>
  <dt>Word error rate ↓</dt><dd>For each clip, the scorer divides substitutions, deletions and insertions by reference words, after normalising script and number forms. The report averages those rates across clips.</dd>
  <dt>LLM uses per clip</dt><dd>The harness averages uses of a language model across scored clips. For Pehchaan the historical counter counts final entities attributed to the verifier, which can use cached answers. Fewer uses generally reduce model overhead.</dd>
  <dt>Coverage</dt><dd>The development set contains synthetic voices used for tuning. The locked human-voice test covers one speaker and a simulated phone line. Its results have limited coverage of other speakers, accents and phone conditions.</dd>
</dl>`;

function renderReport(run) {
  const isFinal = run.clips === "test_real_phone";
  const source = isFinal ? "single-speaker real-voice test (simulated phone line)" : "multi-voice dev set (synthetic voices, tuned on)";
  const systems = new Map(Object.entries(run.systems));
  const priority = mainSystems.map(([id]) => id);
  const additional = [...systems.keys()].filter((id) => !priority.includes(id));
  const allScored = [...priority.filter((id) => systems.has(id)), ...additional];
  const main = run.main_system;
  const facts = systems.get(main)?.entities;
  const factCount = Number.isInteger(facts) ? ` · ${count(facts)} labelled facts` : "";
  const ranAt = escapeHtml(run.ran_at);
  const machineDate = escapeHtml(run.ran_at.replace(" ", "T"));
  return `<div class="bench-status"><strong>${isFinal ? "Locked final test" : "Final test pending"}</strong>
    <div><b>${count(run.n_clips)}-clip ${source}</b>${factCount}
      ${isFinal ? '<p>One speaker. Coverage of other speakers and accents is limited.</p>' : '<p>Development measurements may be optimistic because these clips were used for tuning.</p>'}</div></div>
    <dl class="bench-meta"><div><dt>Run date</dt><dd><time datetime="${machineDate}">${ranAt}</time></dd></div>
      <div><dt>Main system</dt><dd>${escapeHtml(textName(main))} <code>${escapeHtml(main)}</code></dd></div></dl>
    <div class="bench-headlines" aria-label="Headline metrics">${headline(run, systems)}</div>
    ${silentChart(priority, systems, main)}
    ${scoreTable("Scored benchmark comparisons", priority, systems, main)}
    <p class="bench-table-note">↑ Higher is better. ↓ Lower is better. A dash marks a metric without a reported value.</p>
    <div class="bench-disclosures">
      ${disclosure("By language", breakdown("by_lang", allScored, systems, main))}
      ${disclosure("By fact type", breakdown("by_type", allScored, systems, main))}
      ${additional.length ? disclosure("Additional Pehchaan comparisons", scoreTable("Other systems scored in this run", additional, systems, main)) : ""}
      ${disclosure("Processing times", processingTable(allScored, systems, main))}
      ${disclosure("Scoring details and damage audit", scoringDetails(allScored, systems, main))}
      ${disclosure("How we measured", measurementMethods)}
    </div>`;
}

async function loadReport(dataset) {
  const response = await fetch(`/api/bench/latest?clips=${dataset}`, {cache: "no-store"});
  if (!response.ok) return null;
  const report = await response.json();
  const {clips, simulated, n_clips, ran_at, main_system, systems} = report || {};
  if (clips !== dataset || simulated !== false || !Number.isInteger(n_clips) || n_clips < 1 ||
      typeof ran_at !== "string" || !ran_at || typeof main_system !== "string" || !main_system ||
      !systems || typeof systems !== "object" || Array.isArray(systems) || !Object.keys(systems).length ||
      Object.values(systems).some((system) => !system || typeof system !== "object" || Array.isArray(system))) return null;
  return report;
}

export async function mountBenchmark(root) {
  root.classList.add("benchmark-lab");
  root.innerHTML = `<h1 tabindex="-1">Benchmark Lab</h1><p class="bench-intro">See how each approach handles known facts in Indian phone calls.</p>
    <div class="bench-body" aria-busy="true"><p role="status">Loading benchmark results…</p></div>`;
  const body = root.querySelector(".bench-body");
  const report = await loadReport("test_real_phone").catch(() => null) || await loadReport("dev").catch(() => null);
  body.setAttribute("aria-busy", "false");
  if (report) {
    body.innerHTML = renderReport(report);
    return;
  }
  body.innerHTML = `<div class="bench-status"><strong>Final test pending</strong><div><b>Measured development report unavailable</b>
    <p>Check again after a scored run is available.</p><button type="button" class="button bench-retry">Reload reports</button></div></div>
    <div class="bench-disclosures">${disclosure("How we measured", measurementMethods)}</div>`;
  body.querySelector("button").addEventListener("click", async () => {
    await mountBenchmark(root);
    (root.querySelector(".bench-retry") || root.querySelector("h1")).focus();
  });
}
