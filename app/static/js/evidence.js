// The evidence dialog: why a fact came out the way it did. Used by the Live Playground.
import {esc, ms, badge, factWord} from './util.js';
import {info} from './info.js';
import {factStatus} from './transcript.js';

const stageNames = {prepare: 'Transcript preparation', numbers: 'Number rules', memory: 'Confirmed memory', names: 'Name and place matching'};
const sourceNames = {rule: 'Number or language rules', context: 'Call hints', lexicon: 'Built-in brands and places', memory: 'Confirmed memory', llm: 'LLM judge', asr: 'Speech-to-text', transcript: 'Transcript', contacts: 'Contacts', caller_id: 'Caller ID', sms: 'Messages', saved_places: 'Saved places'};
const gateRules = {critical_read_only: 'gate_critical_read_only', acronym_spelled: 'gate_acronym_spelled', common_word: 'gate_common_word', person_not_place: 'gate_person_not_place', second_opinion: 'gate_second_opinion'};

export const ruleName = rule => String(rule).replaceAll('_', ' ');

export function timingDetails(result) {
  const times = Object.entries(result.timings_ms || {}).filter(([k, v]) => k !== 'total' && Number.isFinite(v));
  const asr = (result.asr || []).filter(s => s.model !== 'typed');
  const rows = [
    ...asr.map(s => `<div><dt>${s.role === 'second_opinion' ? 'Second transcript' : 'Speech-to-text'} · ${esc(s.model)}</dt><dd>${ms(s.latency_ms)}${s.cached ? ' (cached model time)' : ''}</dd></div>`),
    ...times.map(([k, v]) => `<div><dt>${esc(stageNames[k] || k.replaceAll('_', ' '))}</dt><dd>${ms(v)}</dd></div>`),
    Number.isFinite(result.verifier_cache_hits) ? `<div><dt>LLM judge cache hits</dt><dd>${result.verifier_cache_hits}</dd></div>` : '',
    Number.isFinite(result.rewrite_calls) ? `<div><dt>Rewrite calls</dt><dd>${result.rewrite_calls}</dd></div>` : '',
  ].join('');
  return `<details class="timings"><summary>Models and timings${info('latency')}</summary><dl>${rows || '<div><dt>Speech-to-text</dt><dd>No model timing for this input</dd></div>'}</dl></details>`;
}

/** Fill and open the shared dialog for one fact. */
export function showEvidence(dialog, {result, entityId, baseline}) {
  const entity = result?.entities?.find(e => String(e.id) === String(entityId));
  if (!entity) return;
  const key = factStatus(entity, result, baseline);
  const stage = ['PHONE', 'PIN', 'AMOUNT'].includes(entity.etype) ? 'numbers' : entity.source === 'memory' ? 'memory' : 'names';
  const expected = key === 'wrong' ? result.scored?.entities?.filter(f => f.type === entity.etype && !f.correct && !f.flagged) : [];
  const model = result.asr?.[0];
  const refused = (result.refused || []).filter(r => r.surface === entity.surface);
  dialog.querySelector('#dialog-title').textContent = factWord(entity.etype);
  dialog.querySelector('#dialog-body').innerHTML = `
    <p>${badge(key, {withInfo: true})}</p>
    <dl class="evidence-list">
      <div><dt>Heard text</dt><dd>${esc(entity.surface)}</dd></div>
      <div><dt>Output</dt><dd>${esc(entity.display || entity.value || entity.surface)}</dd></div>
      <div><dt>Evidence</dt><dd>${esc(entity.reason || 'This fact came from the transcript.')}</dd></div>
      ${expected?.length === 1 ? `<div><dt>Known answer</dt><dd>${esc(expected[0].value)}</dd></div>` : ''}
      <div><dt>Source</dt><dd>${esc(sourceNames[entity.source?.split(':')[0]] || entity.source || 'Transcript')}</dd></div>
      ${baseline && model?.model === 'typed' ? '' : `<div><dt>${baseline ? 'Speech-to-text model time' : `${stageNames[stage]} stage`}</dt><dd>${ms(baseline ? model?.latency_ms : result.timings_ms?.[stage])}</dd></div>`}
      ${!baseline && entity.admission && entity.admission !== 'admitted' ? `<div><dt>Gate rule applied</dt><dd>${esc(ruleName(entity.admission))}${gateRules[entity.admission] ? info(gateRules[entity.admission]) : ''}</dd></div>` : ''}
    </dl>
    ${!baseline && refused.length ? `<p class="note">The gate refused a change here: ${refused.map(r => `${esc(ruleName(r.rule))}${gateRules[r.rule] ? info(gateRules[r.rule]) : ''}`).join(', ')}.</p>` : ''}
    ${timingDetails(result)}`;
  dialog.showModal();
}

export function openNote(dialog, title, html) {
  dialog.querySelector('#dialog-title').textContent = title;
  dialog.querySelector('#dialog-body').innerHTML = html;
  dialog.showModal();
}

export {gateRules};
