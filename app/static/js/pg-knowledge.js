// The Company data demo: connect simulated company systems and watch each fact change. Costs nothing to run.
import {esc, badge, statusOfEntity, factWord, plural} from './util.js';
import {info} from './info.js';
import {getJSON, postJSON} from './api.js';
import {showEvidence} from './evidence.js';
import {passage, showValue} from './transcript.js';
import {retryBox} from './pg-views.js';

const stateWord = (source) => {
  if (!source) return 'Off';
  if (source.status === 'timeout') return 'Timed out, skipped';
  if (source.status === 'error') return 'Failed, skipped';
  if (source.status === 'no_record') return 'No record';
  if (source.status === 'skipped') return 'Skipped';
  const n = Object.values(source.used || {}).reduce((sum, value) => sum + value, 0);
  return n ? `Gave ${plural(n, 'fact')}` : 'Nothing usable';
};

const stateClass = source => (!source ? 'is-off' : ['timeout', 'error'].includes(source.status) ? 'is-bad' : source.status === 'ok' ? 'is-ok' : '');

function headline(result, chosen) {
  if (!chosen) return 'Nothing connected. Pehchaan only has the call.';
  const facts = result.entities.length;
  const backed = result.entities.filter(e => e.backed_by?.length).length;
  return `${backed} of ${plural(facts, 'fact')} now ${backed === 1 ? 'has' : 'have'} a company record behind ${backed === 1 ? 'it' : 'them'}`;
}

const factRow = e => `<tr>
  <th scope="row">${esc(factWord(e.etype))}<small>${esc(showValue(e.etype, e.value))}</small></th>
  <td data-label="Result">${badge(statusOfEntity(e))}</td>
  <td data-label="Backed by">${e.backed_by?.length ? esc(e.backed_by.join(', ')) : '<span class="note">Nothing</span>'}</td></tr>`;

function refusedList(report) {
  const rows = report.sources.flatMap(s => s.dropped.map(d => ({...d, source: s.name})));
  if (!rows.length) return '';
  return `<div class="kb-refused"><h3>Not used as evidence</h3><ul>${rows.map(d =>
    `<li><b>${esc(d.value)}</b> from ${esc(d.source)}: ${esc(d.reason)}</li>`).join('')}</ul></div>`;
}

export function mountKnowledge(root, {dialog}) {
  const ui = {data: null, call: null, on: new Set(), fault: 'none', result: null, failure: '', turn: 0, started: false};
  const current = () => ui.data?.calls.find(c => c.id === ui.call);

  function render() {
    if (!ui.data) { root.innerHTML = ui.failure ? retryBox(ui.failure) : '<p class="note">Loading company systems…</p>'; return; }
    const call = current();
    const report = ui.result?.knowledge;
    const faults = ui.data.faults.filter(f => call.faults.includes(f.id));
    const fault = faults.find(f => f.id === ui.fault) || faults[0];
    const question = ui.result?.questions?.[0]?.question;
    const rows = ui.data.sources.map(s => {
      const state = report?.sources.find(r => r.name === s.name);
      return `<li><label class="kb-source"><input type="checkbox" data-kb-source="${esc(s.id)}" ${ui.on.has(s.id) ? 'checked' : ''}>
        <span><b>${esc(s.name)}</b><small>${esc(s.holds)}</small></span></label>
        <span class="kb-state ${ui.on.has(s.id) ? stateClass(state) : 'is-off'}">${esc(ui.on.has(s.id) ? stateWord(state) : 'Off')}</span></li>`;
    }).join('');
    root.innerHTML = `<p class="kb-notice">${esc(ui.data.notice)}${info('company_data')}</p>
      <ul class="sample-strip" aria-label="Sample calls">${ui.data.calls.map(c => `<li><button class="sample-chip" type="button" data-kb-call="${esc(c.id)}" aria-pressed="${c.id === ui.call}">${esc(c.label)}</button></li>`).join('')}</ul>
      <div class="kb-grid">
        <section class="kb-panel" aria-label="Company systems">
          <h3>Connected systems</h3><ul class="kb-sources">${rows}</ul>
          <h3>Try a failure</h3>
          <div class="kb-faults" role="group" aria-label="Try a failure">${faults.map(f => `<button type="button" data-kb-fault="${esc(f.id)}" aria-pressed="${f.id === fault.id}">${esc(f.label)}</button>`).join('')}</div>
          <p class="note">${esc(fault.line)}</p>
        </section>
        <section class="kb-result" aria-live="polite">
          ${ui.failure ? retryBox(ui.failure) : ui.result ? `<h2 class="story-title">${esc(headline(ui.result, ui.on.size))}</h2>
          <article class="call-side is-main" data-system="knowledge"><h3>With Pehchaan</h3><p class="transcript">${passage(ui.result, false)}</p></article>
          ${question ? `<div class="next is-hold"><div><h3>Your agent should ask</h3><p>${esc(question)}</p></div></div>` : ''}
          <div class="matrix-wrap"><table class="matrix kb-facts"><caption class="sr-only">Each fact and the system behind it</caption>
            <thead><tr><th scope="col">Fact</th><th scope="col">Result</th><th scope="col">Backed by</th></tr></thead>
            <tbody>${ui.result.entities.map(factRow).join('')}</tbody></table></div>
          ${refusedList(report)}` : '<p class="note">Checking this call…</p>'}
        </section>
      </div>`;
  }

  async function run() {
    const turn = ++ui.turn;
    ui.failure = '';
    try {
      const result = await postJSON('/api/demo/knowledge', {call: ui.call, sources: [...ui.on], fault: ui.fault});
      if (turn !== ui.turn) return;
      ui.result = result;
    } catch (error) {
      if (turn !== ui.turn) return;
      ui.failure = error.status === 429 ? 'Too many tries in a minute. Wait a moment, then try again.' : 'This call could not be checked.';
    }
    render();
  }

  function chooseCall(id) {
    const call = ui.data.calls.find(c => c.id === id);
    if (!call) return;
    Object.assign(ui, {call: id, on: new Set(call.sources), fault: 'none', result: null});
    render();
    void run();
  }

  async function load() {
    try {
      ui.data = await getJSON('/api/demo/knowledge');
      ui.failure = '';
      if (ui.data.calls.length) chooseCall(ui.data.calls[0].id);
      else { ui.data = null; ui.failure = 'No sample calls are available.'; render(); }
    } catch {
      ui.started = false;
      ui.failure = 'Company systems could not be loaded.';
      render();
    }
  }

  root.addEventListener('change', event => {
    const id = event.target.dataset?.kbSource;
    if (!id) return;
    if (event.target.checked) ui.on.add(id); else ui.on.delete(id);
    render();
    root.querySelector(`[data-kb-source="${id}"]`)?.focus();
    void run();
  });

  root.addEventListener('click', event => {
    const button = event.target.closest('button');
    if (!button || button.classList.contains('info')) return;
    const data = button.dataset;
    if (data.kbCall) chooseCall(data.kbCall);
    else if (data.kbFault) {
      ui.fault = data.kbFault;
      render();
      root.querySelector(`[data-kb-fault="${data.kbFault}"]`)?.focus();
      void run();
    } else if ('retry' in data) {
      if (ui.data) void run(); else { ui.started = true; void load(); }
    } else if (data.evidence) showEvidence(dialog, {result: ui.result, entityId: data.evidence, baseline: false});
  });

  return {
    activate() {
      if (ui.started) return;
      ui.started = true;
      render();
      void load();
    },
  };
}
