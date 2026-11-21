// Benchmark Lab: the locked exam first, then the stress curve, the model table and the detail. Every number is read from /api/bench/latest and /api/learning/proof.
import {esc, pct, int, dec, ms, isRate, languageNames, factTypes} from './util.js';
import {info} from './info.js';
import {labData, learningProof, interval, sys} from './data.js';
import {systemNames, systemInfo} from './charts.js';
import {lineChart, wireChart} from './curve.js';

const learningName = id => ({P_C0: 'Rules only (C0)', P_C2: 'Built-in lists (C2)', P_on_B1_C3: 'Main system (C3)'})[id] || id;

const PRIORITY = ['B0_asr_plain', 'B1_asr_keywords_C3', 'B1_asr_keywords_C4', 'B2_naive_llm_C3', 'B2_naive_llm_C4', 'P_on_B1_C3', 'P_on_B1_C4'];

const sysCell = id => {
  const [name, ctx] = systemNames.get(id) || [id, ''];
  return `${esc(name)}${systemInfo(id) ? info(systemInfo(id)) : ''}${ctx ? `<small>${esc(ctx)}</small>` : ''}`;
};

function withRange(row, key) {
  const v = row?.[key];
  const r = interval(row, key);
  if (!isRate(v)) return '—';
  return r ? `${pct(v)}<small>${pct(r[0])} to ${pct(r[1])}</small>` : pct(v);
}

function table(caption, headers, ids, rows, main) {
  return `<div class="table-scroll" tabindex="0" role="region" aria-label="${esc(caption)}">
    <table><caption>${esc(caption)}</caption>
      <thead><tr><th scope="col">System</th>${headers.map(h => `<th scope="col">${h}</th>`).join('')}</tr></thead>
      <tbody>${ids.map(id => `<tr${id === main ? ' class="is-main"' : ''}><th scope="row">${sysCell(id)}</th>${rows(id).map(c => `<td>${c}</td>`).join('')}</tr>`).join('')}</tbody>
    </table></div>`;
}

const scoreTable = (caption, ids, report, main) => table(caption, [
  `Silent errors, lower is better${info('silent_error')}<small>95% interval${info('ci95')}</small>`,
  `Fact accuracy, higher is better${info('accuracy')}<small>95% interval</small>`,
  `Damaged edits, lower is better${info('damaged_edits')}`,
], ids, id => {
  const s = sys(report, id);
  return [withRange(s, 'silent_error_rate'), withRange(s, 'entity_accuracy'), int(s?.damaged_edits)];
}, main);

function breakdown(kind, ids, report, main) {
  const keys = [...new Set(ids.flatMap(id => Object.keys(sys(report, id)?.[kind] || {})))].sort();
  if (!keys.length) return '<p class="note">Breakdown unavailable for this report.</p>';
  const labels = kind === 'by_lang' ? languageNames : factTypes;
  return table(`Accuracy and silent errors by ${kind === 'by_lang' ? 'language' : 'fact type'}`,
    keys.map(k => esc(labels[k] || k)), ids, id => keys.map(k => {
      const v = sys(report, id)?.[kind]?.[k];
      return v ? `${pct(v.accuracy)} / ${pct(v.silent_error_rate)}<small>${int(v.n)} facts</small>` : '—';
    }), main);
}

const processing = (ids, report, main) => table('Processing time per call', [
  `Speech-to-text${info('asr')}<small>p50 / p95${info('latency')}</small>`, `Post-transcription<small>p50 / p95</small>`], ids, id => {
  const s = sys(report, id);
  const a = [s?.asr_ms_p50, s?.asr_ms_p95];
  const h = [s?.harness_ms_p50, s?.harness_ms_p95];
  return [a.some(Number.isFinite) ? a.map(ms).join(' / ') : 'Unavailable', h.some(Number.isFinite) ? h.map(ms).join(' / ') : '—'];
}, main);

const details = (ids, report, main) => table('Other scoring measures', [
  `Critical accuracy${info('critical_accuracy')}`, `Over-correction${info('over_correction')}`, `Flag precision${info('flag_precision')}`,
  `Flags per call${info('flags_per_clip')}`, `Reachable${info('reachable')}`, 'Unreachable', `Word error rate${info('wer')}`,
  `LLM calls per call${info('llm_calls')}`, `Calls with damage${info('clips_with_damage')}`, 'Damage by reason',
], ids, id => {
  const s = sys(report, id);
  const reasons = Object.entries(s?.damage_by_reason || {});
  return [pct(s?.critical_accuracy), pct(s?.over_correction_rate), pct(s?.flag_precision), dec(s?.flags_per_clip),
    pct(s?.accuracy_reachable), pct(s?.accuracy_unreachable), pct(s?.wer), dec(s?.llm_calls_per_clip),
    Number.isInteger(s?.clips_with_damage) ? `${int(s.clips_with_damage)} of ${int(s.clips)}` : '—',
    reasons.length ? reasons.map(([r, n]) => `${esc(r.replaceAll('_', ' '))} ${int(n)}`).join(', ') : '—'];
}, main);

const disclosure = (label, content, open = false) => `<details class="disclosure"${open ? ' open' : ''}><summary>${label}</summary><div>${content}</div></details>`;

const methods = `<dl class="methods">
  <dt>Same clips, same scorer</dt><dd>Each system hears the same audio. An independent scorer${info('oracle')} compares each transcript with the labelled facts of the script. It has its own number reader and name rules and shares no code or word tables with Pehchaan.</dd>
  <dt>Silent errors and accuracy</dt><dd>Silent errors${info('silent_error')} are wrong or missing facts without a matching question, divided by all labelled facts. Accuracy${info('accuracy')} is correct facts divided by all labelled facts. A wrong fact that was flagged with a question avoids a silent error and still counts as not correct.</dd>
  <dt>Damaged edits</dt><dd>${info('damaged_edits')}The count of changes that turned a right fact into a wrong one between a system’s input and output, across the scored calls. Formatting and real repairs carry no penalty.</dd>
  <dt>95% intervals</dt><dd>${info('ci95')}The harness resamples whole calls with replacement to estimate how much a rate could vary. Small or overlapping differences are uncertain. This site claims a win only where intervals do not overlap.</dd>
  <dt>Context levels</dt><dd>Normal context (C3${info('C3')}) supplies relevant caller information. Misleading hints (C4${info('C4')}) uses the same audio and swaps in decoys. The main system runs on the keyword transcript and checks it against a plain second transcript${info('second_opinion')}. The generative rewrite starts from an unprompted transcript.</dd>
  <dt>Timing</dt><dd>Post-transcription time covers Pehchaan’s own work, or the rewrite model’s request time. Speech-to-text time is the longest model request per call. Neither includes queueing, browser transfer or scoring.</dd>
  <dt>Coverage</dt><dd>The development set uses synthetic voices that were used for tuning. The locked real-voice test${info('exam')} covers one speaker and a simulated phone line${info('phone_line')}, so coverage of other speakers and accents is limited.</dd>
</dl>`;

const LINES = [['clean', 'Clean recording'], ['phone', 'Phone line'], ['noisy', 'Noisy line'], ['very_noisy', 'Very noisy line'], ['dropouts', 'Line with dropouts']];
const LINE_SYSTEMS = [['B0_asr_plain', 'Plain speech-to-text', 'normal hints'], ['B1_asr_keywords_C3', 'With keywords', 'normal hints'],
  ['B2_naive_llm_C3', 'LLM rewrite', 'normal hints'], ['P_on_B1_C3', 'Pehchaan', 'normal hints'],
  ['B2_naive_llm_C4', 'LLM rewrite', 'misleading hints'], ['P_on_B1_C4', 'Pehchaan', 'misleading hints']];

function lineCell(row) {
  if (!row) return '—';
  return `<b class="num">${int(row.silent)}</b><small>${int(row.right)} of ${int(row.facts)} right, asked ${int(row.asked)}</small>`;
}

function lineTable(real) {
  const lines = LINES.filter(([key]) => real[key]?.totals);
  const rows = lines.map(([key, label]) => `<tr><th scope="row">${esc(label)}</th>${LINE_SYSTEMS.map(([id]) =>
    `<td${id.startsWith('P_') ? ' class="is-ours"' : ''}>${lineCell(real[key].totals[id])}</td>`).join('')}</tr>`).join('');
  return `<div class="table-scroll" tabindex="0" role="region" aria-label="Real-voice results by line quality">
    <table><caption>Facts wrong with no warning${info('silent_error')}, lower is better</caption>
    <thead><tr><th scope="col">Line</th>${LINE_SYSTEMS.map(([, name, hints]) => `<th scope="col">${esc(name)}<small>${esc(hints)}</small></th>`).join('')}</tr></thead>
    <tbody>${rows}</tbody></table></div>`;
}

function lineBlock(real) {
  if (!real) return '';
  const lines = LINES.filter(([key]) => real[key]?.totals);
  const llmAhead = lines.filter(([key]) => real[key].totals.B2_naive_llm_C3?.right > real[key].totals.P_on_B1_C3?.right).map(([, label]) => label.toLowerCase());
  return `<section class="lab-section" aria-labelledby="real-title"><div class="section-head"><h2 id="real-title">How it holds up as the line gets worse</h2>
    <p>Six real recordings${info('real_voice')} through a worsening phone line${info('phone_line')}. A stress test, not the exam.</p></div>
    ${lineChart(real)}
    <ul class="claims">
      <li class="limit"><strong>On a clear line the base model needs little help.</strong> Pehchaan's job there is to change nothing.</li>
      ${llmAhead.length ? `<li class="limit"><strong>Where Pehchaan does not win:</strong> on the ${esc(llmAhead.join(' and '))}, an LLM rewrite got more facts right with normal hints. With misleading hints the rewrite does far worse.</li>` : ''}
    </ul>
    ${disclosure('See every line and system as a table', lineTable(real))}</section>`;
}

function proofBlock(proof) {
  const head = `<div class="section-head"><h2 id="learn-proof-title">Does learning help on a voice it has not heard?</h2>
    <p>Does verified learning${info('verified_learning')} help, and does it ever hurt? Label: scripted confirmations, dev data, names recurring in a different voice${info('held_out_voice')}. This is not a result on real users.</p></div>`;
  if (!proof) return `<section aria-labelledby="learn-proof-title">${head}<div class="state-box"><strong>No learning results yet</strong>This table fills in once the learning proof has been run.</div></section>`;
  const entries = Object.entries(proof.systems);
  const table = `<div class="table-scroll" tabindex="0" role="region" aria-label="Held-out learning proof">
    <table><caption>Facts right before and after learning, by system</caption>
    <thead><tr><th scope="col">System</th><th scope="col">Facts right</th><th scope="col">Silent errors${info('silent_error')}</th><th scope="col">Facts harmed</th><th scope="col">Corrections adopted</th><th scope="col">True fixes adopted</th><th scope="col">Wrong confirmations blocked</th></tr></thead>
    <tbody>${entries.map(([id, s]) => `<tr${id === 'P_on_B1_C3' ? ' class="is-main"' : ''}><th scope="row">${esc(learningName(id))}</th>
      <td>${int(s.right_before)} → ${int(s.right_after)} of ${int(s.facts)}<small>${s.right_after - s.right_before >= 0 ? '+' : ''}${int(s.right_after - s.right_before)}</small></td>
      <td>${int(s.silent_before)} → ${int(s.silent_after)}</td><td>${int(s.facts_harmed)}</td><td>${int(s.learned)}</td>
      <td>${int(s.true_fixes_tried - (s.true_fixes_not_adopted ?? 0))} of ${int(s.true_fixes_tried)}</td>
      <td>${int(s.wrong_blocked)} of ${int(s.wrong_tried)}</td></tr>`).join('')}</tbody></table></div>`;
  const gains = entries.map(([id, s]) => [id, s.right_after - s.right_before]);
  const small = gains.find(([id]) => id === 'P_on_B1_C3') || gains[gains.length - 1];
  const big = gains.slice().sort((a, b) => b[1] - a[1])[0];
  return `<section aria-labelledby="learn-proof-title">${head}${table}
    <p class="note">${proof.run ? `Run ${esc(proof.run)}, ${int(proof.clips)} calls. ` : ''}${esc(proof.note || '')}</p>
    <p class="callout">The gain on the main system is small (${small[1] >= 0 ? '+' : ''}${int(small[1])} ${small[1] === 1 ? 'fact' : 'facts'}), because keywords already help it. With less context the gain is larger: ${esc(learningName(big[0]))} gains ${int(big[1])}. ${entries.every(([, s]) => s.facts_harmed === 0) ? 'No fact was harmed in any row.' : 'Some rows harmed facts: see the table.'}</p></section>`;
}

const EXAM_ROWS = ['B0_asr_plain', 'B1_asr_keywords_C3', 'B2_naive_llm_C3', 'P_on_B1_C3', 'B1_asr_keywords_C4', 'B2_naive_llm_C4', 'P_on_B1_C4'];

function examBlock(lab) {
  const {standard, noisy} = lab.exam;
  if (!standard || !noisy) return '<div class="state-box"><strong>No exam results yet</strong></div>';
  const body = EXAM_ROWS.map(id => {
    const ours = id.startsWith('P_');
    return `<tr${ours ? ' class="is-main"' : ''}><th scope="row">${sysCell(id)}</th>
      ${[standard, noisy].flatMap(r => [withRange(sys(r, id), 'silent_error_rate'), withRange(sys(r, id), 'entity_accuracy')]).map(c => `<td>${c}</td>`).join('')}</tr>`;
  }).join('');
  const lines = lab.exam_paired?.lines;
  const pair = lines ? [['standard', lines.test_real_phone.C3], ['noisy', lines.test_real_noisy.C3]] : [];
  const ours = sys(standard, 'P_on_B1_C3');
  return `<section class="lab-section" aria-labelledby="exam-title"><div class="section-head"><h2 id="exam-title">The locked exam</h2>
    <p>${int(standard.n_clips)} real-voice clips${info('exam')}, ${int(ours.entities)} facts, one speaker, on a simulated phone line${info('phone_line')}. Each line ran once, on code frozen before the run.</p></div>
    <div class="table-scroll" tabindex="0" role="region" aria-label="Locked exam results">
      <table class="exam-table"><caption>Lower is better for silent errors, higher for right facts. Small print is the 95% interval${info('ci95')}.</caption>
      <thead><tr><th scope="col" rowspan="2">System</th><th scope="colgroup" colspan="2">Standard line</th><th scope="colgroup" colspan="2">Noisy line</th></tr>
      <tr><th scope="col">Silent errors${info('silent_error')}</th><th scope="col">Right${info('accuracy')}</th><th scope="col">Silent errors</th><th scope="col">Right</th></tr></thead>
      <tbody>${body}</tbody></table></div>
    <ul class="claims">
      ${pair.map(([name, x]) => `<li class="win"><strong>${name === 'standard' ? 'Standard' : 'Noisy'} line:</strong> silent errors ${int(x.silent_before)} → ${int(x.silent_after)} against keywords alone. Money, phone and PIN ${int(x.critical_silent_before)} → ${int(x.critical_silent_after)}.</li>`).join('')}
      ${lines ? `<li class="limit"><strong>It mostly asks rather than fixes.</strong> Right facts: ${int(pair[0][1].right_before)} → ${int(pair[0][1].right_after)} and ${int(pair[1][1].right_before)} → ${int(pair[1][1].right_after)} of ${int(pair[0][1].facts)}. It also made ${int(lines.test_real_phone.C3.damaged_edits)} and ${int(lines.test_real_noisy.C3.damaged_edits)} damaging edits${info('damaged_edits')}.</li>` : ''}
      <li class="limit"><strong>Limits.</strong> One speaker, simulated phone line. The 95% intervals overlap. The clip-by-clip check was chosen after seeing results.</li>
    </ul></section>`;
}

const FACT_MARK = {right: 'Yes', asked: 'Asks', missed: 'No', wrong: 'Wrong'};
const TIER_WORD = {measured: 'Real voice', built: 'Synthetic only', partial: 'Partial', unsupported: 'Not supported'};

function languagesBlock(lab) {
  const table = lab.languages;
  if (!table) return '';
  const rows = table.languages.map(r => `<tr><th scope="row">${esc(r.name)}<small>${esc(r.script)}</small></th>
    <td><span class="tier tier-${r.tier}">${TIER_WORD[r.tier]}</span></td>
    <td>${FACT_MARK[r.facts.name]}</td><td>${FACT_MARK[r.facts.place]}</td><td>${FACT_MARK[r.facts.phone_digits]}</td>
    <td>${r.facts.money_words === table.money_checks ? 'Yes' : r.facts.money_words ? 'Some' : 'Asks or kept'}</td></tr>`).join('');
  return `<section class="lab-section" aria-labelledby="lang-title"><div class="section-head"><h2 id="lang-title">Which languages work</h2>
    <p>A capability check on one invented call per language, not an accuracy score. Only the first three rows were tested on real voices.</p></div>
    <div class="table-scroll" tabindex="0" role="region" aria-label="Language support">
    <table class="lang-table"><thead><tr><th scope="col">Language</th><th scope="col">Evidence</th><th scope="col">Names</th><th scope="col">Places</th><th scope="col">Digit numbers</th><th scope="col">Spoken money</th></tr></thead>
    <tbody>${rows}</tbody></table></div></section>`;
}

function modelsBlock(lab) {
  const sets = lab.models?.datasets;
  if (!sets) return '';
  const names = Object.keys(sets.dev.models);
  const cell = row => `${pct(row.plain.silent)} → <b>${pct(row.C3.silent)}</b><small>misleading hints ${pct(row.C4.silent)}</small>`;
  return `<section class="lab-section" aria-labelledby="models-title"><div class="section-head"><h2 id="models-title">The same harness on four OpenAI speech models</h2>
    <p>Same engine, no keywords for any model. Not the exam. Other providers are unmeasured.</p></div>
    <div class="table-scroll" tabindex="0" role="region" aria-label="Speech model comparison">
    <table><caption>Silent errors: model alone → with Pehchaan</caption>
    <thead><tr><th scope="col">Model</th><th scope="col">${int(sets.dev.clips)} development calls<small>synthetic, tuned on</small></th><th scope="col">Bad real lines<small>${int(sets.real_bad_lines.clips)} runs of 6 calls</small></th><th scope="col">Median speech time</th><th scope="col">Takes keywords</th></tr></thead>
    <tbody>${names.map(name => `<tr><th scope="row"><code>${esc(name)}</code></th><td>${cell(sets.dev.models[name])}</td><td>${cell(sets.real_bad_lines.models[name])}</td><td>${ms(sets.dev.models[name].asr_ms_p50)}</td><td>${lab.model_profiles?.[name]?.keywords ? 'Yes' : 'No'}</td></tr>`).join('')}</tbody></table></div></section>`;
}

function detailBlock(lab) {
  const report = lab.exam.standard || lab.dev;
  const main = report.main_system;
  const ids = Object.keys(report.systems);
  const all = [...PRIORITY.filter(id => ids.includes(id)), ...ids.filter(id => !PRIORITY.includes(id))];
  const fp = report.manifest ? Object.entries(report.manifest).filter(([, v]) => typeof v === 'string') : [];
  const dev = lab.dev;
  return `<section class="lab-section" aria-labelledby="detail-title"><div class="section-head"><h2 id="detail-title">All the detail</h2></div>
    <div class="disclosures">
      ${dev ? disclosure('Development set (synthetic voices, used for tuning, so optimistic)', scoreTable('Development results', PRIORITY.filter(id => dev.systems[id]), dev, dev.main_system)) : ''}
      ${disclosure('Exam by language', breakdown('by_lang', all, report, main))}
      ${disclosure('Exam by kind of fact', breakdown('by_type', all, report, main))}
      ${disclosure('Processing times', processing(all, report, main))}
      ${disclosure('Other scoring measures and the damage audit', details(all, report, main))}
      ${disclosure('Does learning help?', '<div id="proof-learning"></div>')}
      ${disclosure('How we measured', methods)}
      ${fp.length ? disclosure('Run fingerprint', `<p class="note">Digests of the code and data behind the exam, so anyone can check what ran.</p><dl class="fingerprint">${fp.map(([k, v]) => `<div><dt>${esc(k.replaceAll('_', ' '))}</dt><dd><code>${esc(v)}</code></dd></div>`).join('')}</dl>`) : ''}
    </div></section>`;
}

export async function mountProof(root) {
  root.classList.add('page', 'proof');
  root.innerHTML = `<header class="page-head"><h1>Benchmark Lab</h1>
    <p class="lede">Same recordings, every system, one independent scorer. The weak spots stay in.</p></header>
    <div id="proof-body" aria-busy="true"><p role="status" class="note">Loading measured results…</p></div>`;
  const body = root.querySelector('#proof-body');
  const [lab, proof] = await Promise.all([labData(), learningProof()]);
  body.setAttribute('aria-busy', 'false');
  if (!lab?.exam) {
    body.innerHTML = `<div class="state-box is-error"><strong>Results could not be loaded</strong>Reload the page to try again.</div>`;
    return;
  }
  body.innerHTML = `${examBlock(lab)}${lineBlock(lab.line_quality)}${modelsBlock(lab)}${languagesBlock(lab)}${detailBlock(lab)}`;
  const learning = root.querySelector('#proof-learning');
  if (learning) learning.innerHTML = proofBlock(proof);
  wireChart(root);
}
