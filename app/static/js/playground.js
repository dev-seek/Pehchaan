// The Live Playground: six working demos that share one packaged call.
import {esc} from './util.js';
import {info} from './info.js';
import {getJSON, presets as loadPresets, compare as postCompare, highlights, liveProblem,
  confirmCorrection, replayCall, learningLedger, rollbackCorrection} from './api.js';
import {labData} from './data.js';
import {showEvidence, openNote} from './evidence.js';
import {systemInfo} from './charts.js';
import {tally} from './transcript.js';
import {levels, sampleChips, sampleNote, contextFacts, storyTitle, transcriptCard, nextAction, columnPicker, factMatrix, retryBox} from './pg-views.js';
import {learningView, learnTarget} from './pg-learning.js';
import {leadBlock, modelPicker, defaultModel} from './lead.js';
import {mountLive} from './live.js';
import {mountKnowledge} from './pg-knowledge.js';

const BASE_ID = 'B0_asr_plain';
const TABS = [
  ['compare', 'Compare', 'The same call, with and without Pehchaan.'],
  ['voice', 'Your voice', 'Connect, choose a speech model, and speak.'],
  ['context', 'Context', 'Give it more to go on and watch each fact change.'],
  ['knowledge', 'Company data', 'Connect what a company knows. Watch each fact change.'],
  ['llm', 'vs LLM', 'Why not just ask an LLM to fix the transcript?'],
  ['learning', 'Learning', 'Answer once. It stops asking.'],
];
const LINES = [['clean', 'Clear'], ['phone', 'Phone'], ['noisy', 'Noisy'], ['very_noisy', 'Very noisy'], ['dropouts', 'Dropouts']];
const CONTEXT_COLUMNS = main => [['C0', 'P_C0'], ['C2', 'P_C2'], ['C3', main], ['C4', 'P_on_B1_C4']];

const layout = `
  <section class="lead" id="pg-lead" aria-labelledby="hero-title"><h1 id="hero-title">Every fact in an Indian call</h1></section>
  <section class="bench" aria-label="Live demos">
    <div class="bench-tabs" role="tablist" aria-label="Demos">${TABS.map(([id, label], i) => `<button role="tab" type="button" id="tab-${id}" data-tab="${id}" aria-controls="pg-pane-${id}" aria-selected="${i === 0}" tabindex="${i === 0 ? 0 : -1}">${label}</button>`).join('')}</div>
    <div class="bench-stage">
      <p class="bench-line" id="pg-tabline"></p>
      <div id="pg-callbar" class="callbar">
        <div id="pg-samples"><p class="note">Loading sample calls…</p></div>
        <p id="pg-sample-note" class="note"></p>
        <audio id="pg-audio" controls preload="metadata" aria-label="Listen to this call" hidden></audio>
      </div>
      <div role="tabpanel" id="pg-pane-compare" aria-labelledby="tab-compare">
        <div class="line-box" id="pg-lines"></div>
        <div class="model-box" id="pg-models"></div>
        <h2 id="pg-story" class="story-title" tabindex="-1">Loading a sample call…</h2>
        <div class="call-pair" id="pg-pair"></div>
        <div id="pg-matrix"></div>
        <div id="pg-next"></div>
      </div>
      <div role="tabpanel" id="pg-pane-voice" aria-labelledby="tab-voice" hidden><div class="live" id="pg-live"></div></div>
      <div role="tabpanel" id="pg-pane-context" aria-labelledby="tab-context" hidden></div>
      <div role="tabpanel" id="pg-pane-knowledge" aria-labelledby="tab-knowledge" hidden></div>
      <div role="tabpanel" id="pg-pane-llm" aria-labelledby="tab-llm" hidden></div>
      <div role="tabpanel" id="pg-pane-learning" aria-labelledby="tab-learning" hidden></div>
      <p id="pg-status" class="sr-only" role="status" aria-live="polite"></p>
    </div>
  </section>`;

/** Scroll the tab strip only when the chosen tab is cut off. */
function keepInView(tab) {
  const strip = tab.parentElement;
  const right = tab.offsetLeft + tab.offsetWidth;
  if (tab.offsetLeft < strip.scrollLeft) strip.scrollLeft = tab.offsetLeft - 4;
  else if (right > strip.scrollLeft + strip.clientWidth) strip.scrollLeft = right - strip.clientWidth + 4;
}

export function mountPlayground(root) {
  root.classList.add('page', 'playground');
  root.innerHTML = layout;
  const find = name => root.querySelector(`#pg-${name}`);
  const dialog = document.getElementById('evidence-dialog');
  const emptyLearn = () => ({target: null, verdict: null, rejected: null, replay: null, busy: false, replaying: false});
  const ui = {
    tab: 'compare', level: 'C3', contextLevel: 'C3', hints: 'C3', llmColumn: 'pehchaan', working: false, presets: [], input: null, run: null,
    results: new Map(), errors: new Map(), shown: new Map(), done: false, failure: '', lab: null, model: 'gpt-transcribe',
    defaultModel: 'gpt-transcribe', modelView: null, modelAnswers: new Map(), next: null, wanted: null, picked: new Set(),
    learn: emptyLearn(), events: [], userChose: false, returnTo: null, learnNote: '', line: 'clean', lineAnswers: new Map(),
  };
  let live = null;
  const knowledge = mountKnowledge(find('pane-knowledge'), {dialog});
  const report = message => { find('status').textContent = message; };
  const setHtml = (el, html) => { if (el.cache !== html) { el.cache = html; el.innerHTML = html; } };
  const preset = () => ui.input?.preset;
  const mainId = () => ui.run?.main_system || 'P_on_B1_C3';
  const systemAt = level => (level === 'C4' ? 'P_on_B1_C4' : mainId());
  const isReal = () => preset()?.kind === 'real';
  const lineName = () => LINES.find(([id]) => id === ui.line)?.[1] || 'Clear';
  const remember = (key, result, baseline, ours) => { ui.shown.set(key, result); return [key, result, baseline, ours]; };

  // ---- one view per tab ----
  function renderCompare() {
    const base = ui.modelView ? ui.modelView.base : ui.results.get(BASE_ID);
    const main = ui.modelView ? ui.modelView.main : ui.results.get(systemAt(ui.level));
    const keyword = ui.modelView ? ui.modelView.keywords || null : ui.results.get(`B1_asr_keywords_${ui.level}`);
    if (ui.failure) find('story').textContent = ui.failure;
    else find('story').textContent = main ? storyTitle(base, keyword, main) : 'Checking this call…';
    const hints = ui.level === 'C4' ? 'misleading hints' : ui.line !== 'clean' && isReal() ? `${lineName().toLowerCase()} line` : '';
    setHtml(find('pair'), transcriptCard('Speech model alone', ui.model, ...remember('compare-base', base, true)) +
      transcriptCard('With Pehchaan', hints, ...remember('compare-main', main, false, true)));
    const columns = [{id: 'base', title: 'Alone', info: 'sys_plain', result: base}];
    if (keyword) columns.push({id: 'keyword', title: 'Keywords', info: 'sys_keywords', result: keyword});
    columns.push({id: 'main', title: 'Pehchaan', info: 'sys_pehchaan', result: main, ours: true});
    setHtml(find('matrix'), base && main ? factMatrix(columns, 'Each known fact in this call') : '');
    setHtml(find('next'), ui.failure ? retryBox(ui.failure) : nextAction(main));
  }

  function renderContext() {
    if (ui.failure) { setHtml(find('pane-context'), retryBox(ui.failure)); return; }
    const columns = CONTEXT_COLUMNS(mainId()).map(([level, id]) => ({id: level, title: levels[level].label, info: level, result: ui.results.get(id), ours: level === ui.contextLevel}));
    const current = columns.find(c => c.id === ui.contextLevel);
    const told = ['C3', 'C4'].includes(ui.contextLevel) ? preset()?.[ui.contextLevel === 'C4' ? 'context_adv' : 'context'] : null;
    setHtml(find('pane-context'), `${columnPicker('context', columns, ui.contextLevel)}
      <div class="told"><p class="note">${esc(levels[ui.contextLevel].blurb)}</p>${told ? `<details><summary>See what Pehchaan was told</summary>${contextFacts(told)}</details>` : ''}</div>
      ${factMatrix(columns, 'Each fact at each level of context')}
      <div class="call-pair is-single">${transcriptCard(`Transcript: ${levels[ui.contextLevel].label}`, '', ...remember('context', current?.result, false, true))}</div>`);
  }

  function renderLlm() {
    if (ui.failure) { setHtml(find('pane-llm'), retryBox(ui.failure)); return; }
    const at = ui.hints;
    const columns = [
      {id: 'plain', title: 'Alone', info: systemInfo(BASE_ID), result: ui.results.get(BASE_ID), baseline: true},
      {id: 'keywords', title: 'Keywords', info: 'sys_keywords', result: ui.results.get(`B1_asr_keywords_${at}`), baseline: true},
      {id: 'llm', title: 'LLM rewrite', info: 'sys_rewrite', result: ui.results.get(`B2_naive_llm_${at}`), baseline: true},
      {id: 'pehchaan', title: 'Pehchaan', info: 'sys_pehchaan', result: ui.results.get(systemAt(at)), ours: true},
    ];
    const current = columns.find(c => c.id === ui.llmColumn);
    const silent = id => tally(columns.find(c => c.id === id).result)?.silent;
    const [llm, ours] = [silent('llm'), silent('pehchaan')];
    const verdict = llm === undefined || ours === undefined ? '' : llm > ours ? `The LLM rewrite left ${llm} silent ${llm === 1 ? 'error' : 'errors'}. Pehchaan left ${ours}.`
      : llm === ours ? `Both left ${ours} silent ${ours === 1 ? 'error' : 'errors'} on this call.` : `Here the LLM rewrite did better: ${llm} silent errors against ${ours}.`;
    setHtml(find('pane-llm'), `<div class="seg" role="group" aria-label="Hints given to every system">
        ${['C3', 'C4'].map(l => `<span class="seg-item"><button type="button" data-hints="${l}" aria-pressed="${l === at}">${l === 'C3' ? 'Normal hints' : 'Misleading hints'}</button>${info(l)}</span>`).join('')}</div>
      <h2 class="story-title">${esc(verdict)}</h2>
      ${factMatrix(columns, 'Each fact across four approaches')}
      ${columnPicker('llm', columns, ui.llmColumn)}
      <div class="call-pair is-single">${transcriptCard(current.title, at === 'C4' ? 'misleading hints' : 'normal hints', ...remember('llm', current.result, Boolean(current.baseline), Boolean(current.ours)))}</div>`);
  }

  function renderLearning() {
    if (ui.failure) { setHtml(find('pane-learning'), retryBox(ui.failure)); return; }
    const target = ui.learn.target;
    setHtml(find('pane-learning'), (ui.learnNote ? `<p class="note">${esc(ui.learnNote)}</p>` : '') + learningView({target, result: target ? ui.results.get(target.systemId) : null, learn: ui.learn, events: ui.events}));
  }

  const views = {compare: renderCompare, context: renderContext, llm: renderLlm, learning: renderLearning, voice: () => {}, knowledge: () => {}};
  const render = () => views[ui.tab]();

  function renderSamples() {
    find('samples').innerHTML = sampleChips(ui.presets, preset()?.id, ui.working);
    const onLine = ui.tab === 'compare' && isReal() && ui.line !== 'clean';
    find('sample-note').innerHTML = onLine ? `<strong>Real voice, simulated ${esc(lineName().toLowerCase())} line.</strong> Saved answers, so this costs nothing.` : sampleNote(preset());
  }

  function renderTabs() {
    for (const [id,, line] of TABS) {
      const on = id === ui.tab;
      const tab = root.querySelector(`#tab-${id}`);
      tab.setAttribute('aria-selected', String(on));
      tab.tabIndex = on ? 0 : -1;
      if (on) keepInView(tab);
      find(`pane-${id}`).hidden = !on;
      if (on) find('tabline').textContent = line;
    }
    find('callbar').hidden = ui.tab === 'voice' || ui.tab === 'knowledge';
    find('samples').hidden = ui.tab === 'learning';
    find('sample-note').hidden = ui.tab === 'learning';
  }

  // ---- speech model: packaged answers, so this works with no key ----
  function linePicker() {
    if (!isReal()) return '';
    return `<div class="seg" role="group" aria-label="Phone line quality"><span class="seg-label">Phone line${info('line_quality')}</span>
      ${LINES.map(([id, label]) => `<span class="seg-item"><button type="button" data-line="${id}" aria-pressed="${id === ui.line}">${label}</button></span>`).join('')}</div>`;
  }

  function syncAudio() {
    const current = preset();
    if (!current?.audio_url) return;
    const line = ui.tab === 'compare' && isReal() && ui.line !== 'clean' ? `?line=${ui.line}` : '';
    const src = current.audio_url + line;
    if (find('audio').getAttribute('src') !== src) find('audio').src = src;
  }

  async function applyModel() {
    const current = preset();
    ui.modelView = null;
    const onLine = current?.kind === 'real' && ui.line !== 'clean';
    if (onLine) {
      try {
        if (!ui.lineAnswers.has(current.id)) ui.lineAnswers.set(current.id, await getJSON(`/api/demo/presets/${encodeURIComponent(current.id)}/lines`));
        ui.modelView = ui.lineAnswers.get(current.id)[ui.line] || null;
      } catch (error) {
        report(error.message);
      }
    } else if (current && ui.model !== ui.defaultModel) {
      try {
        if (!ui.modelAnswers.has(current.id)) ui.modelAnswers.set(current.id, await getJSON(`/api/demo/presets/${encodeURIComponent(current.id)}/models`));
        ui.modelView = ui.modelAnswers.get(current.id)[ui.model] || null;
      } catch (error) {
        report(error.message);
      }
    }
    find('models').innerHTML = modelPicker(ui.lab, ui.model);
    find('models').hidden = onLine;   // the line versions were measured on the default model
    find('lines').innerHTML = linePicker();
    syncAudio();
    renderSamples();
    render();
  }

  // ---- running a packaged call ----
  function accept(event) {
    if (event.event === 'started') ui.run = event;
    else if (event.event === 'result') ui.results.set(event.system_id, event.result);
    else if (event.event === 'system_error') ui.errors.set(event.system_id, event.message);
    else if (event.event === 'done') ui.done = true;
    render();
  }

  async function startCompare(input) {
    if (ui.working) { ui.next = input; return; }
    ui.input = input;
    const src = input.preset.audio_url || '';
    find('audio').hidden = !src;
    if (src && find('audio').getAttribute('src') !== src) find('audio').src = src;
    Object.assign(ui, {working: true, run: null, done: false, failure: '', modelView: null, learn: emptyLearn()});
    ui.level = input.preset.initial_level === 'C4' ? 'C4' : 'C3';
    for (const map of [ui.results, ui.errors]) map.clear();
    renderSamples();
    render();
    const fields = new FormData();
    fields.append('preset', input.preset.id);
    try {
      await postCompare(fields, accept);
      if (!ui.done) throw new Error('The sample stopped early. Choose it again.');
      report('Call ready.');
    } catch (error) {
      ui.failure = liveProblem(error).text;
      report(ui.failure);
    } finally {
      ui.working = false;
      renderSamples();
      if (ui.next) {
        const queued = ui.next;
        ui.next = null;
        await startCompare(queued);
      } else {
        if (ui.tab === 'learning') ui.learn.target = learnTarget(ui.results, mainId());
        await applyModel();
      }
    }
  }

  // ---- each demo opens on the call that shows it best ----
  async function prepare(tab) {
    await samplesReady;
    const wanted = (await highlights())[tab];
    const chosen = ui.presets.find(p => p.id === wanted);
    if (tab === 'learning') {
      ui.learn.target ||= learnTarget(ui.results, mainId());
      if (!ui.learn.target?.known && chosen && chosen.id !== preset()?.id) {
        const from = ui.userChose ? preset() : null;
        await startCompare({preset: chosen});
        if (from) { ui.returnTo = from; ui.learnNote = `${from.label} has nothing to teach, so this demo uses ${chosen.label}.`; }
      }
      ui.learn.target ||= learnTarget(ui.results, mainId());
      ui.learn.none = !ui.learn.target && !ui.working;
      await refreshLedger();
    } else if (!ui.picked.has(tab) && (tab === 'context' || tab === 'llm')) {
      ui.picked.add(tab);
      if (tab === 'llm' && chosen) ui.hints = 'C4';
      if (!ui.userChose && chosen && chosen.id !== preset()?.id) await startCompare({preset: chosen});
    }
    if (ui.tab === tab) render();
  }

  function openTab(name) {
    if (!TABS.some(([id]) => id === name)) return;
    ui.tab = name;
    if (name !== 'learning' && ui.returnTo) {   // Learning borrowed a call; give the visitor's choice back
      const back = ui.returnTo;
      Object.assign(ui, {returnTo: null, learnNote: ''});
      void startCompare({preset: back});
    }
    renderTabs();
    syncAudio();
    renderSamples();
    render();
    if (name === 'voice') live?.activate();
    else if (name === 'knowledge') knowledge.activate();
    else void prepare(name);
  }

  const samplesReady = (async () => {
    const [lab] = await Promise.all([labData(), (async () => {
      try { ui.presets = await loadPresets(); } catch { ui.presets = []; }
    })()]);
    ui.lab = lab;
    ui.defaultModel = defaultModel(lab);
    ui.model = ui.defaultModel;
    find('lead').innerHTML = leadBlock(lab);
    find('models').innerHTML = modelPicker(lab, ui.model);
    live = mountLive(find('live'), {lab});
    if (ui.tab === 'voice') live.activate();
    renderSamples();
    if (!ui.presets.length) { find('story').textContent = 'Sample calls could not be loaded. Reload the page.'; return; }
    const first = ui.presets.find(p => p.id === ui.wanted) || ui.presets.find(p => p.featured) || ui.presets[0];
    await startCompare({preset: first});
  })();

  // ---- learning: answer, test, replay, undo ----
  async function refreshLedger() {
    try { ui.events = await learningLedger(); } catch { ui.events = []; }
  }

  async function teach(canonical) {
    const {learn, run} = {learn: ui.learn, run: ui.run};
    if (!canonical || learn.busy || !learn.target || !run) return;
    learn.busy = true;
    learn.rejected = null;
    render();
    report('Testing this answer on labelled calls…');
    try {
      const verdict = await confirmCorrection(run.run_id, {system_id: learn.target.systemId, entity_id: learn.target.entityId, canonical});
      if (ui.learn !== learn) return;
      if (verdict.adopted) learn.verdict = verdict;
      else learn.rejected = {...verdict, canonical};
      await refreshLedger();
      report(verdict.adopted ? 'Learned.' : 'Refused. Nothing was saved.');
    } catch (error) {
      report(error.message);
    } finally {
      learn.busy = false;
      if (ui.learn === learn) render();
    }
  }

  async function replay() {
    const {learn, run} = {learn: ui.learn, run: ui.run};
    if (learn.replaying || !learn.target) return;
    learn.replaying = true;
    render();
    try {
      const result = await replayCall(run.run_id, learn.target.systemId);
      if (ui.learn === learn) learn.replay = result;
      report('Replay finished.');
    } catch (error) {
      report(error.message);
    } finally {
      learn.replaying = false;
      if (ui.learn === learn) render();
    }
  }

  async function undo(eventId) {
    try {
      await rollbackCorrection(eventId);
      Object.assign(ui.learn, {verdict: null, replay: null, rejected: null});
      await refreshLedger();
      render();
      report('Undone. Pehchaan no longer applies that answer.');
    } catch (error) {
      report(error.message);
    }
  }

  // ---- events ----
  root.addEventListener('change', event => {
    if (event.target.name === 'pg-model') { ui.model = event.target.value; void applyModel(); }
  });
  root.addEventListener('submit', event => {
    if (!event.target.matches('[data-learn-form]')) return;
    event.preventDefault();
    void teach(event.target.elements.canonical.value.trim());
  });
  root.addEventListener('keydown', event => {
    const tab = event.target.closest?.('[role="tab"][data-tab]');
    if (!tab || !['ArrowRight', 'ArrowLeft', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const ids = TABS.map(([id]) => id);
    const at = ids.indexOf(tab.dataset.tab);
    const next = {ArrowRight: (at + 1) % ids.length, ArrowLeft: (at - 1 + ids.length) % ids.length, Home: 0, End: ids.length - 1}[event.key];
    openTab(ids[next]);
    root.querySelector(`#tab-${ids[next]}`).focus();
  });
  root.addEventListener('click', event => {
    const button = event.target.closest('button');
    if (!button || button.closest('#pg-live, #pg-pane-knowledge') || button.classList.contains('info')) return;
    const data = button.dataset;
    if (data.tab) openTab(data.tab);
    else if (data.preset) {
      const chosen = ui.presets.find(p => p.id === data.preset);
      if (chosen) { Object.assign(ui, {userChose: true, returnTo: null, learnNote: ''}); void startCompare({preset: chosen}); }
    } else if (data.col) {
      const [name, id] = data.col.split(':');
      if (name === 'context') ui.contextLevel = id; else ui.llmColumn = id;
      render();
    } else if (data.line) { ui.line = data.line; void applyModel(); }
    else if (data.hints) { ui.hints = data.hints; render(); }
    else if (data.evidence) {
      const holder = button.closest('[data-system]');
      if (holder) showEvidence(dialog, {result: ui.shown.get(holder.dataset.system), entityId: data.evidence, baseline: holder.dataset.baseline === '1'});
    } else if (data.callback) openNote(dialog, 'Callback preview', `<p class="preview-number">${esc(data.callback)}</p><p class="note">No call has been placed.</p>`);
    else if ('retry' in data) { if (ui.input) void startCompare(ui.input); }
    else if (data.learn) void teach(data.learn);
    else if ('replay' in data) void replay();
    else if (data.undo) void undo(data.undo);
  });

  renderTabs();

  return {
    openTab,
    async openSample(id) {
      ui.wanted = id;
      ui.userChose = true;
      await samplesReady;
      const chosen = ui.presets.find(p => p.id === id);
      if (chosen && preset()?.id !== id) await startCompare({preset: chosen});
    },
  };
}
