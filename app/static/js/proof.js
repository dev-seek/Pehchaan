// Proof: the benchmark as a story first, then the detail tables. Every number is read from /api/bench/latest and /api/learning/proof.
import {esc, pct, int, dec, ms, isRate, plural, languageNames, factTypes} from './util.js';
import {info} from './info.js';
import {benchReport, reloadReport, learningProof, factCounts, intervalsOverlap, interval, sys} from './data.js';
import {dotPanel, dotLegend, barRow, evidenceBanner, systemNames, systemInfo} from './charts.js';
import {learningName} from './home.js';

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
  <dt>Context levels</dt><dd>Normal context (C3${info('C3')}) supplies relevant caller information. Misleading context (C4${info('C4')}) uses the same audio and swaps in decoys. The main system runs on the keyword transcript and checks it against a plain second transcript${info('second_opinion')}. The generative rewrite starts from an unprompted transcript.</dd>
  <dt>Timing</dt><dd>Post-transcription time covers Pehchaan’s own work, or the rewrite model’s request time. Speech-to-text time is the longest model request per call. Neither includes queueing, browser transfer or scoring.</dd>
  <dt>Coverage</dt><dd>The development set uses synthetic voices that were used for tuning. The locked real-voice test${info('exam')} covers one speaker and a simulated phone line${info('phone_line')}, so coverage of other speakers and accents is limited.</dd>
</dl>`;

// ---- the story ----
function storyBlock(report, final) {
  const main = report.main_system;
  const mainRow = sys(report, main);
  const plain = sys(report, 'B0_asr_plain');
  const keyword = sys(report, 'B1_asr_keywords_C3');
  const rewrite = sys(report, 'B2_naive_llm_C3');
  const rewrite4 = sys(report, 'B2_naive_llm_C4');
  const silentVsKeyword = intervalsOverlap(mainRow, keyword, 'silent_error_rate');
  const accVsKeyword = intervalsOverlap(mainRow, keyword, 'entity_accuracy');
  const line = (ok, win, tie) => ok === null ? '' : `<li class="${ok ? 'tie' : 'win'}">${ok ? tie : win}</li>`;
  return `<section class="story-proof" aria-labelledby="story-title">
    <div class="section-head"><h2 id="story-title">The same recordings, base model against Pehchaan</h2>
      <p>${int(report.n_clips)} calls, ${int(mainRow?.entities)} facts we know the answer to. Each dot is one fact. Same audio into every row, marked by the same independent scorer.</p></div>
    <div class="dots-row">
      ${dotPanel({id: 'B0_asr_plain', title: 'Plain speech-to-text', context: 'the base model', row: plain})}
      ${dotPanel({id: 'B1_asr_keywords_C3', title: 'With call keywords', context: 'a stronger base', row: keyword})}
      ${dotPanel({id: 'B2_naive_llm_C3', title: 'Rewritten by an LLM', context: 'the obvious fix', row: rewrite})}
      ${dotPanel({id: main, title: 'Pehchaan', context: 'the main system', row: mainRow, emphasis: true})}
    </div>
    ${dotLegend()}
    <h3 class="claims-title">What this does and does not show</h3>
    <ul class="claims">
      ${line(silentVsKeyword, `<strong>Silent errors: a clear difference.</strong> Pehchaan ${pct(mainRow?.silent_error_rate)} against ${pct(keyword?.silent_error_rate)} for keyword-assisted speech-to-text, and the 95% intervals do not overlap.`, `<strong>Silent errors: not a proven difference.</strong> The 95% intervals overlap.`)}
      ${line(accVsKeyword, `<strong>Accuracy: a clear difference.</strong> The intervals do not overlap.`, `<strong>Accuracy: not a proven win.</strong> Pehchaan ${pct(mainRow?.entity_accuracy)} against ${pct(keyword?.entity_accuracy)} for keyword-assisted speech-to-text, but the 95% intervals overlap, so we make no accuracy claim.`)}
      <li class="win"><strong>Damage: Pehchaan changed no right fact into a wrong one</strong> (${int(mainRow?.damaged_edits)} damaged edits). The LLM rewrite damaged ${int(rewrite?.damaged_edits)} with normal context and ${int(rewrite4?.damaged_edits)} with misleading context.</li>
      <li class="limit"><strong>What is still wrong:</strong> ${pct(mainRow?.silent_error_rate)} of facts came out wrong with no warning. ${final ? '' : 'These are development calls, so the real-voice number will likely be worse.'}</li>
    </ul>
  </section>`;
}

function typeBars(report) {
  const main = report.main_system;
  const types = Object.keys(sys(report, main)?.by_type || {}).sort();
  if (!types.length) return '';
  return `<section aria-labelledby="types-title"><div class="section-head"><h2 id="types-title">Where the help lands: by kind of fact</h2>
    <p>Share of facts wrong with no warning, by kind of fact${info('silent_error')}. Names, places and companies are where the base model slips most. Numbers are already strong in the base model, so Pehchaan’s job there is to leave them untouched and ask when something looks wrong.</p></div>
    <div class="type-bars">${types.map(type => {
      const p = sys(report, 'B0_asr_plain')?.by_type?.[type];
      const m = sys(report, main)?.by_type?.[type];
      const r = sys(report, 'B2_naive_llm_C3')?.by_type?.[type];
      const max = 1;
      return `<div class="type-row"><h3>${esc(factTypes[type] || type)} <small class="muted num">${int(m?.n)} facts</small></h3>
        ${barRow({label: 'Plain speech-to-text', value: p?.silent_error_rate, max, text: pct(p?.silent_error_rate), tone: 'bad'})}
        ${barRow({label: 'Rewritten by an LLM', value: r?.silent_error_rate, max, text: pct(r?.silent_error_rate), tone: 'bad'})}
        ${barRow({label: 'Pehchaan', value: m?.silent_error_rate, max, text: pct(m?.silent_error_rate), tone: 'good'})}</div>`;
    }).join('')}</div></section>`;
}

function proofBlock(proof) {
  const head = `<div class="section-head"><h2 id="learn-proof-title">Held-out learning proof</h2>
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

function reportBody(data) {
  const {report, final} = data;
  const main = report.main_system;
  const systems = new Map(Object.entries(report.systems));
  const extra = [...systems.keys()].filter(id => !PRIORITY.includes(id));
  const all = [...PRIORITY.filter(id => systems.has(id)), ...extra];
  const fp = report.manifest ? Object.entries(report.manifest).filter(([, v]) => typeof v === 'string') : [];
  return `${storyBlock(report, final)}
    ${typeBars(report)}
    <section aria-labelledby="tables-title"><div class="section-head"><h2 id="tables-title">The scored comparison</h2>
      <p>The seven main approaches, normal and misleading context. The Pehchaan row is highlighted.</p></div>
      ${scoreTable('Scored benchmark comparisons', PRIORITY.filter(id => systems.has(id)), report, main)}
      <p class="note">Lower is better for silent errors and damaged edits. Higher is better for accuracy. A dash means no reported value.</p></section>
    <div id="proof-learning"></div>
    <section aria-labelledby="detail-title"><div class="section-head"><h2 id="detail-title">All the detail</h2></div>
      <div class="disclosures">
        ${disclosure('By language', breakdown('by_lang', all, report, main))}
        ${disclosure('By fact type', breakdown('by_type', all, report, main))}
        ${extra.length ? disclosure('Pehchaan on a plain transcript, by context level', scoreTable('Other systems scored in this run', extra, report, main)) : ''}
        ${disclosure('Processing times', processing(all, report, main))}
        ${disclosure('Other scoring measures and the damage audit', details(all, report, main))}
        ${disclosure('How we measured', methods)}
        ${fp.length ? disclosure('Run fingerprint', `<p class="note">Digests of the engine, scorer, language packs, lexicons, settings and models used for this run, so two results can be compared honestly.</p><dl class="fingerprint">${fp.map(([k, v]) => `<div><dt>${esc(k.replaceAll('_', ' '))}</dt><dd><code>${esc(v)}</code></dd></div>`).join('')}</dl>`) : ''}
      </div></section>`;
}

export async function mountProof(root) {
  root.classList.add('page', 'proof');
  root.innerHTML = `<header class="page-head"><h1>Proof</h1>
    <p class="lede">The track asked for the same recordings on a base model and on your system, and a measurable improvement on a frustration everyone knows. This page is both, with the weak spots left in.</p></header>
    <div id="proof-evidence"></div>
    <div id="proof-body" aria-busy="true"><p role="status" class="note">Loading measured results…</p></div>`;
  const body = root.querySelector('#proof-body');
  const [data, proof] = await Promise.all([benchReport(), learningProof()]);
  root.querySelector('#proof-evidence').innerHTML = evidenceBanner(data);
  body.setAttribute('aria-busy', 'false');
  if (!data.report) {
    body.innerHTML = `<div class="state-box"><strong>No measured results yet</strong>Nothing has been benchmarked on this deployment. The method is described below, and the numbers will appear after a scored run.
      <p><button type="button" class="button" id="proof-retry">Reload results</button></p></div>
      ${disclosure('How we measured', methods, true)}${proof ? '' : ''}`;
    body.querySelector('#proof-retry').addEventListener('click', async () => { await reloadReport(); await mountProof(root); });
    return;
  }
  body.innerHTML = reportBody(data);
  root.querySelector('#proof-learning').innerHTML = proofBlock(proof);
}
