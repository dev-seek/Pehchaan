// Live Playground: the claim, a sample call on any speech model, base beside Pehchaan, and confirm, replay, undo.
import {esc, plural} from './util.js';
import {info} from './info.js';
import {getJSON, presets as loadPresets, compare as postCompare, liveProblem,
  confirmCorrection, replayCall, learningLedger, rollbackCorrection} from './api.js';
import {labData} from './data.js';
import {showEvidence, openNote} from './evidence.js';
import {systemTitle, systemInfo} from './charts.js';
import {levels, sampleChip, sampleNote, emptySamples, contextFacts, storyBanner, resultPanel, scorecardBlock, ledger} from './pg-views.js';
import {leadBlock, modelPicker, defaultModel} from './lead.js';
import {mountLive} from './live.js';

const BASE_ID = 'B0_asr_plain';

const layout = `
  <section class="lead" id="pg-lead" aria-labelledby="hero-title"><h1 id="hero-title">Fewer wrong facts slip through. When unsure, it asks.</h1></section>

  <section aria-labelledby="pg-samples-title">
    <h2 class="pick-title" id="pg-samples-title">Pick a call</h2>
    <ul id="pg-samples" class="sample-strip"><li class="note">Loading sample calls…</li></ul>
    <p id="pg-sample-note" class="note"></p>
    <div class="model-box" id="pg-models"></div>
  </section>

  <section class="results" aria-label="Comparison">
    <p id="pg-status" class="status-line" role="status" aria-live="polite"></p>
    <div id="pg-playback" class="playback" hidden>
      <p id="pg-audio-label" class="note"></p>
      <audio id="pg-audio" controls preload="metadata" aria-labelledby="pg-audio-label"></audio>
      <p id="pg-playback-error" class="note" role="status" hidden>Playback is unavailable for this audio.</p>
    </div>
    <div id="pg-story"><div class="state-box"><strong>Loading a sample call…</strong>The result shows which facts the base model got wrong and what Pehchaan did about them.</div></div>
    <div id="pg-scorecard"></div>
    <div class="pair">
      <article class="panel" id="pg-base" aria-label="Base model"></article>
      <article class="panel panel-main" id="pg-main" aria-label="With Pehchaan"></article>
    </div>
  </section>

  <section class="more" aria-label="More">
    <details id="pg-live-box"><summary>Try your own call: live mic, audio file, or any transcript</summary><div class="live" id="pg-live"></div></details>
    <details id="pg-context-details"><summary>What the phone knows${info('context')}</summary>
      <fieldset class="levels">
        <legend class="sr-only">Pehchaan context level</legend>
        ${Object.entries(levels).map(([key, l]) => `<div class="level-opt"><label><input type="radio" name="pg-level" value="${key}" ${key === 'C3' ? 'checked' : ''}><span>${esc(l.label)} <b>${key}</b></span></label>${info(key)}</div>`).join('')}
      </fieldset>
      <p id="pg-context-description" class="note"></p>
      <div id="pg-preset-hints"></div>
    </details>
    <details id="pg-approaches"><summary>All approaches that ran <span id="pg-approach-count" class="note"></span></summary>
      <div id="pg-approach-items"><p class="note">Approaches appear as they finish.</p></div>
    </details>
    <details id="pg-ledger-box"><summary>What Pehchaan has learned${info('ledger')}</summary>
      <p class="note">Every confirmation is tested before it can change anything. You can undo any adopted correction${info('verified_learning')}.</p>
      <div id="pg-ledger"></div>
    </details>
  </section>`;

export function mountPlayground(root) {
  root.classList.add('page', 'playground');
  root.innerHTML = layout;
  const find = name => root.querySelector(`#pg-${name}`);
  const dialog = document.getElementById('evidence-dialog');
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const ui = {
    level: 'C3', working: false, presets: [], input: null, run: null, results: new Map(), errors: new Map(), replays: new Map(),
    verdicts: new Map(), confirming: null, ledger: null, canReplay: false, replaying: null, done: false,
    lab: null, model: 'gpt-transcribe', defaultModel: 'gpt-transcribe', modelView: null, modelAnswers: new Map(), next: null, wanted: null,
  };
  const report = message => { find('status').textContent = message; };
  const getMain = () => ({C0: 'P_C0', C2: 'P_C2', C3: ui.run?.main_system || 'P_on_B1_C3', C4: 'P_on_B1_C4'})[ui.level];
  const getResult = id => {
    if (ui.modelView) return id === BASE_ID ? ui.modelView.base : ui.modelView.main;
    return ui.replays.get(id) || ui.results.get(id);
  };
  const currentPreset = () => ui.input?.preset;
  const setHtml = (el, html) => { if (el.cache !== html) { el.cache = html; el.innerHTML = html; } };

  function setLevel(level) {
    ui.level = level;
    root.querySelector(`[name="pg-level"][value="${level}"]`).checked = true;
    renderContext();
    renderPanels();
  }

  function renderContext() {
    const preset = currentPreset();
    const city = preset?.context?.user?.city;
    find('context-description').textContent = ui.modelView ? `Other speech models are packaged at the product setting (C3). Switch back to ${ui.defaultModel} to compare levels.`
      : ui.level === 'C2' && city ? `Uses the built-in brands and places around ${city}.` : levels[ui.level].blurb;
    for (const input of root.querySelectorAll('[name="pg-level"]')) input.disabled = !!ui.modelView;
    find('preset-hints').hidden = !preset || ['C0', 'C2'].includes(ui.level);
    if (preset) find('preset-hints').innerHTML = contextFacts(preset[ui.level === 'C4' ? 'context_adv' : 'context']);
  }

  function renderSamples() {
    find('samples').innerHTML = ui.presets.length
      ? ui.presets.map(p => sampleChip(p, {selected: p.id === currentPreset()?.id, disabled: ui.working})).join('')
      : emptySamples();
    find('sample-note').innerHTML = sampleNote(currentPreset());
  }

  function renderModels() {
    find('models').innerHTML = modelPicker(ui.lab, ui.model);
    find('models').hidden = !ui.lab?.model_profiles;
  }

  // ---- speech model: packaged answers, so this works with no key ----
  async function applyModel() {
    const preset = currentPreset();
    ui.modelView = null;
    if (preset && ui.model !== ui.defaultModel) {
      try {
        if (!ui.modelAnswers.has(preset.id)) ui.modelAnswers.set(preset.id, await getJSON(`/api/demo/presets/${encodeURIComponent(preset.id)}/models`));
        ui.modelView = ui.modelAnswers.get(preset.id)[ui.model] || null;
        if (ui.modelView && ui.level !== 'C3') setLevel('C3');
        report(ui.modelView ? `Showing ${ui.model} on this call. Same frozen harness.` : `No packaged answer for ${ui.model} on this call.`);
      } catch (error) {
        report(error.message);
      }
    } else if (preset && !ui.working) {
      report(`Showing ${ui.model} on this call.`);
    }
    find('approaches').hidden = !!ui.modelView;
    renderModels();
    renderContext();
    renderPanels();
  }

  // ---- playback ----
  function updatePlayback(input) {
    const src = input.preset?.audio_url || '';
    find('playback-error').hidden = true;
    if (src) {
      find('audio-label').textContent = `Listen: ${input.preset.label}`;
      find('audio').src = src;
    }
    find('playback').hidden = !src;
  }

  // ---- rendering results ----
  function renderPanels() {
    const baseResult = getResult(BASE_ID);
    const mainId = getMain();
    const mainResult = getResult(mainId);
    const common = {level: ui.level, done: ui.done, ui};
    setHtml(find('base'), resultPanel({id: BASE_ID, result: baseResult, error: ui.errors.get(BASE_ID), baseline: true, ...common}));
    setHtml(find('main'), resultPanel({id: mainId, result: mainResult, error: ui.errors.get(mainId), baseline: false, ...common}));
    const story = mainResult && ui.input ? storyBanner({base: baseResult, main: mainResult, input: ui.input, level: ui.level,
      keywords: ui.modelView ? ui.modelView.keywords_used : ['C3', 'C4'].includes(ui.level),
      keywordResult: ui.modelView ? null : ui.results.get(`B1_asr_keywords_${ui.level}`)}) : '';
    if (story) setHtml(find('story'), story);
    setHtml(find('scorecard'), mainResult && baseResult ? scorecardBlock(baseResult, mainResult, ui.level) : '');
    renderApproaches();
  }

  function renderApproaches() {
    if (!ui.run) {
      find('approach-count').textContent = '';
      return;
    }
    const systems = ui.run.systems;
    find('approach-count').textContent = `${ui.results.size + ui.errors.size} of ${systems.length} finished`;
    const html = systems.map(system => {
      const {id} = system;
      const result = ui.results.get(id);
      const error = ui.errors.get(id);
      const status = result ? 'Ready' : error ? 'Failed' : ui.done ? 'No result' : 'Waiting';
      const extra = system.kind === 'pehchaan' ? `Pehchaan processing ${result?.timings_ms?.total ?? '—'} ms, LLM calls ${result?.llm_calls ?? '—'}`
        : system.kind === 'naive_llm' ? `Rewrite time ${result?.timings_ms?.total ?? '—'} ms` : '';
      return `<details data-system="${esc(id)}"><summary><span>${esc(systemTitle(id))}${systemInfo(id) ? info(systemInfo(id)) : ''}</span><span class="note">${status}</span></summary>
        ${result ? `<div class="approach-content"><p class="approach-text">${esc(result.text) || 'No speech was transcribed.'}</p><p class="note">${esc(extra)}</p></div>`
        : `<p class="approach-content note">${esc(error || (ui.done ? 'No result returned.' : 'Waiting for this approach…'))}</p>`}</details>`;
    }).join('');
    const holder = find('approach-items');
    const open = new Set([...holder.querySelectorAll('details[open]')].map(d => d.dataset.system));
    if (holder.cache !== html) {
      holder.cache = html;
      holder.innerHTML = html;
      for (const d of holder.querySelectorAll('details')) d.open = open.has(d.dataset.system);
    }
  }

  function accept(event) {
    if (event.event === 'started') { ui.run = event; find('approach-items').cache = null; }
    else if (event.event === 'result') ui.results.set(event.system_id, event.result);
    else if (event.event === 'system_error') ui.errors.set(event.system_id, event.message);
    else if (event.event === 'done') ui.done = true;
    if (!ui.modelView) renderPanels();
  }

  async function startCompare(input, {playSelection = false, scroll = true} = {}) {
    if (ui.working) { ui.next = {input, options: {playSelection, scroll}}; return; }
    const leavingTrap = currentPreset()?.initial_level === 'C4' && ui.level === 'C4';
    if (ui.input !== input) updatePlayback(input);
    ui.input = input;
    Object.assign(ui, {working: true, run: null, done: false, canReplay: ui.canReplay, replaying: null, confirming: null, modelView: null});
    for (const map of [ui.results, ui.errors, ui.replays, ui.verdicts]) map.clear();
    find('story').innerHTML = `<div class="state-box"><strong>Comparing this call…</strong>Results appear as each approach finishes.</div>`;
    find('story').cache = null;
    renderSamples();
    renderPanels();
    if (Object.hasOwn(levels, input.preset.initial_level)) setLevel(input.preset.initial_level);
    else if (leavingTrap) setLevel('C3');
    report('Comparing this call. Results appear as each approach finishes.');
    if (playSelection) find('audio').play().catch(() => {});
    if (scroll) root.querySelector('.results').scrollIntoView({behavior: reduced ? 'auto' : 'smooth', block: 'start'});

    const fields = new FormData();
    fields.append('preset', input.preset.id);
    try {
      await postCompare(fields, accept);
      if (!ui.done) throw new Error('The comparison stream closed early.');
      report(ui.errors.size ? `Comparison finished. ${plural(ui.errors.size, 'approach', 'approaches')} failed.` : 'Comparison complete.');
    } catch (error) {
      ui.done = true;
      const problem = liveProblem(error);
      report(problem.text);
      if (!ui.results.size) find('story').innerHTML = `<div class="state-box is-error"><strong>The comparison could not run</strong>${esc(problem.text)}</div>`;
    } finally {
      ui.working = false;
      renderSamples();
      renderContext();
      renderPanels();
      if (ui.next) {
        const {input: queued, options} = ui.next;
        ui.next = null;
        void startCompare(queued, options);
      } else {
        await applyModel();
      }
    }
  }

  const samplesReady = (async () => {
    const [lab] = await Promise.all([labData(), (async () => {
      try {
        ui.presets = await loadPresets();
      } catch (error) {
        find('samples').innerHTML = `<li class="state-box is-error"><strong>Sample calls unavailable</strong>${esc(error.message)}</li>`;
      }
    })()]);
    ui.lab = lab;
    ui.defaultModel = defaultModel(lab);
    ui.model = ui.defaultModel;
    find('lead').innerHTML = leadBlock(lab);
    renderModels();
    if (!ui.presets.length) return;
    renderSamples();
    const first = ui.presets.find(p => p.id === ui.wanted) || ui.presets.find(p => p.featured) || ui.presets[0];
    void startCompare({preset: first}, {scroll: Boolean(ui.wanted)});
  })();

  // ---- learning: confirm, test, replay, undo ----
  async function refreshLedger() {
    try {
      ui.ledger = await learningLedger();
    } catch {
      ui.ledger = [];
    }
    ui.canReplay = ui.ledger.some(e => e.active) || [...ui.verdicts.values()].some(v => v.adopted);
    setHtml(find('ledger'), ledger(ui.ledger));
  }

  async function confirm(form, canonical) {
    const id = getMain();
    const run = ui.run;
    const entityId = form.dataset.confirm;
    const key = `${id}:${entityId}`;
    if (!canonical || ui.confirming || !run) return;
    ui.confirming = key;
    renderPanels();
    report('Testing this correction on labelled calls…');
    try {
      const verdict = await confirmCorrection(run.run_id, {system_id: id, entity_id: entityId, canonical});
      if (ui.run !== run) return;
      ui.verdicts.set(key, verdict);
      ui.confirming = null;
      await refreshLedger();
      renderPanels();
      report(verdict.adopted
        ? `Adopted. Tested on ${verdict.clips_replayed} labelled calls with ${verdict.facts_harmed} facts harmed.`
        : 'Not adopted. Nothing was saved. The checks below say why.');
      (find('main').querySelector(verdict.adopted ? '[data-replay]' : '.verdict') || find('main')).focus?.();
    } catch (error) {
      ui.confirming = null;
      renderPanels();
      const status = find('main').querySelector(`[data-confirm="${CSS.escape(entityId)}"] .confirm-status`);
      if (status) status.textContent = error.message;
      report(error.message);
    }
  }

  async function replay() {
    if (ui.replaying || ui.working) { report('Wait for the current comparison to finish before replaying.'); return; }
    const id = getMain();
    const run = ui.run;
    ui.replaying = id;
    renderPanels();
    try {
      const result = await replayCall(run.run_id, id);
      if (ui.run !== run) return;
      ui.replays.set(id, result);
      const hits = Array.isArray(result.memory_hits) ? result.memory_hits.length : (result.memory_hits || 0);
      report(`Replay complete. ${hits} memory ${hits === 1 ? 'hit' : 'hits'} and ${result.llm_calls ?? 'unmeasured'} LLM calls.`);
    } catch (error) {
      report(error.message);
    } finally {
      if (ui.run === run) {
        ui.replaying = null;
        renderPanels();
        find('main').querySelector('[data-replay]')?.focus();
      }
    }
  }

  async function undo(eventId) {
    try {
      await rollbackCorrection(eventId);
      for (const [key, verdict] of [...ui.verdicts]) if (String(verdict.event_id) === String(eventId)) ui.verdicts.delete(key);
      ui.replays.clear();
      await refreshLedger();
      renderPanels();
      report('Undone. Pehchaan no longer applies that correction. Replay shows the original result again.');
    } catch (error) {
      report(error.message);
    }
  }

  // ---- events ----
  find('audio').addEventListener('error', () => { find('playback-error').hidden = find('playback').hidden; });
  root.addEventListener('change', event => {
    if (event.target.name === 'pg-level') setLevel(event.target.value);
    if (event.target.name === 'pg-model') { ui.model = event.target.value; void applyModel(); }
  });
  root.addEventListener('submit', event => {
    const form = event.target;
    if (form.matches('[data-confirm]')) {
      event.preventDefault();
      void confirm(form, form.elements.canonical?.value.trim());
    }
  });
  root.addEventListener('click', event => {
    const button = event.target.closest('button');
    if (!button || button.closest('#pg-live')) return;
    if (button.dataset.preset) {
      const preset = ui.presets.find(p => p.id === button.dataset.preset);
      if (preset) void startCompare({preset}, {playSelection: true});
    } else if (button.hasAttribute('data-evidence')) {
      const panel = button.closest('[id="pg-base"], [id="pg-main"]');
      const baseline = panel === find('base');
      showEvidence(dialog, {result: getResult(baseline ? BASE_ID : getMain()), entityId: button.dataset.evidence, baseline});
    } else if (button.hasAttribute('data-callback')) {
      openNote(dialog, 'Callback preview', `<p class="preview-number">${esc(button.dataset.callback)}</p><p class="note">No call has been placed.</p>`);
    } else if (button.hasAttribute('data-choice')) void confirm(button.closest('form'), button.dataset.choice);
    else if (button.hasAttribute('data-replay')) void replay();
    else if (button.hasAttribute('data-undo')) void undo(button.dataset.undo);
  });

  mountLive(find('live'), {model: () => ui.model});
  renderContext();
  renderPanels();
  void refreshLedger();

  return {
    async openSample(id) {
      ui.wanted = id;
      await samplesReady;
      const preset = ui.presets.find(p => p.id === id);
      if (preset && currentPreset()?.id !== id) void startCompare({preset}, {playSelection: false});
    },
  };
}
