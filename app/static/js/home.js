// Home: the whole idea in ten seconds, then the evidence. Every number is read from the API when the page opens.
import {esc, pct, int, badge, glyph, icon, languageNames, factWord} from './util.js';
import {info} from './info.js';
import {presets, runPreset, siteConfig} from './api.js';
import {benchReport, learningProof, intervalsOverlap, interval, sys} from './data.js';
import {passage, scorecard, storySentence} from './transcript.js';
import {dotPanel, dotLegend, barRow, evidenceBanner} from './charts.js';
import {showEvidence} from './evidence.js';

const mark = (kind, text, key) => `<span class="mark mark-${kind}">${text}${glyph(key)}</span>`;

const shell = `
  <section class="hero" aria-labelledby="hero-title">
    <h1 id="hero-title">Every fact in an Indian call: ${mark('verified', 'right', 'check')}, or ${mark('ask', 'it asks', 'ask')}.</h1>
    <p class="lede">Speech models get most words right and still get the facts wrong: phone numbers, PIN codes, rupee amounts, names and places. Pehchaan sits after speech-to-text. It makes each fact right, or asks one short question.</p>
    <p class="layer-strip" aria-label="Pehchaan sits between any speech model and your product"><span>Any speech model</span><i aria-hidden="true">→</i><strong>Pehchaan checks the facts</strong><i aria-hidden="true">→</i><span>Your voice product</span></p>
    <p class="note hero-who">For teams building voice agents, call summaries and support bots. It is a layer you add, not an app you install.</p>
    <div class="hero-actions">
      <a class="button button-primary" href="#playground">Try a sample call ${icon('arrow')}</a>
      <a class="button" href="#benchmark">See the proof</a>
      <a class="button" href="#integration">Add it to your product</a>
    </div>
    <div id="hero-call" class="hero-call" aria-live="polite"><div class="state-box">Loading a sample call…</div></div>
    <ul class="legend" aria-label="What the marks mean" id="hero-legend"></ul>
  </section>
  <section id="home-evidence" class="home-evidence" aria-label="Where these numbers come from"></section>
  <section aria-labelledby="pain-title" id="home-pain"></section>
  <section aria-labelledby="impact-title" id="home-impact"></section>
  <section aria-labelledby="llm-title" id="home-llm"></section>
  <section aria-labelledby="glance-title" id="home-glance"></section>
  <section aria-labelledby="learn-title" id="home-learning"></section>
  <section class="closing" aria-labelledby="close-title">
    <h2 id="close-title">Hear it for yourself</h2>
    <p class="lede">The sample calls are packaged with their answers, so they run instantly and offline. Pick one and watch what the base model got wrong.</p>
    <a class="button button-primary" href="#playground">Open the sample calls ${icon('arrow')}</a>
  </section>`;

// ---- hero: one real packaged call, plain speech-to-text beside Pehchaan ----
function voiceBadge(preset) {
  const real = preset.kind === 'real';
  return `<span class="chip ${real ? 'chip-real' : ''}">${real ? 'Real voice' : 'Synthetic voice'}${info(real ? 'real_voice' : 'synthetic_voice')}</span>`;
}

// The opener is chosen in data (`featured` in presets.json), so opening Home runs exactly one sample call.
async function pickHeroCall(list) {
  const preset = list.find(item => item.featured) || list[0];
  const run = await runPreset(preset.id);
  const base = run.results.get('B0_asr_plain');
  const main = run.results.get(run.started?.main_system);
  return base && main ? {preset, run, base, main} : null;
}

function heroCard({preset, run, base, main}) {
  const lang = preset.language || languageNames[main.language?.dominant] || '';
  const sentence = storySentence(base, main);
  return `<article class="call-card" data-system="">
    <header class="call-head">
      <div><h2 class="call-title">${esc(preset.label)}</h2><p class="note">${esc(preset.description)}</p></div>
      <div class="chips">${lang ? `<span class="chip">${esc(lang)}</span>` : ''}${voiceBadge(preset)}</div>
    </header>
    <audio class="call-audio" controls preload="none" src="${esc(preset.audio_url)}" aria-label="Play the call: ${esc(preset.label)}"></audio>
    <div class="call-pair">
      <section class="call-side" data-side="base" data-system="B0_asr_plain">
        <h3>Plain speech-to-text${info('sys_plain')}</h3>
        <p class="transcript" lang="">${passage(base, true)}</p>
      </section>
      <section class="call-side is-main" data-side="main" data-system="${esc(run.started.main_system)}">
        <h3>With Pehchaan${info('sys_pehchaan')}</h3>
        <p class="transcript">${passage(main, false)}</p>
      </section>
    </div>
    ${scorecard(base, main, 'Pehchaan')}
    <footer class="call-foot">
      <p>${esc(sentence)} <span class="note">One sample call. The measured results below cover all the calls.</span></p>
      <a class="button" href="#playground?sample=${encodeURIComponent(preset.id)}">Open this call ${icon('arrow')}</a>
    </footer>
  </article>`;
}

async function mountHero(root, hero) {
  const target = root.querySelector('#hero-call');
  root.querySelector('#hero-legend').innerHTML = ['verified', 'fixed', 'ask', 'heard', 'wrong']
    .map(k => `<li>${badge(k, {withInfo: true})}</li>`).join('');
  try {
    const list = await presets();
    if (!list.length) throw new Error('No sample calls are packaged with this build.');
    const picked = await pickHeroCall(list);
    if (!picked) throw new Error('The sample call could not be run.');
    Object.assign(hero, picked);
    target.innerHTML = heroCard(picked);
  } catch (error) {
    target.innerHTML = `<div class="state-box is-error"><strong>No sample call to show</strong>${esc(error.message)} Open <a href="#playground">Try it</a> to check the samples.</div>`;
  }
}

// ---- the frustration everyone knows ----
function typeStat(report, id, type) {
  const row = sys(report, id)?.by_type?.[type];
  if (!row || !Number.isFinite(row.n)) return null;
  return {n: row.n, silent: Math.round(row.n * row.silent_error_rate)};
}

const callsLabel = ({report, final}) => (final
  ? `${int(report.n_clips)} real-voice exam calls, one speaker, simulated phone line, run once`
  : `${int(report.n_clips)} development calls, synthetic voices, used for tuning, so likely optimistic`);

function painSection(data) {
  const {report} = data;
  const cases = [
    {type: 'PHONE', title: 'A callback to the wrong number', story: 'The caller says a mobile number. One digit is off, and the call you return goes to a stranger.'},
    {type: 'PLACE', title: 'A parcel to the wrong area', story: 'The rider says the locality. The transcript has a different one, so the delivery goes the wrong way.'},
    {type: 'AMOUNT', title: 'The wrong EMI', story: 'The bank says the amount. A lakh turns into a thousand, and the reminder is wrong.'},
    {type: 'ORG', title: 'A bank that is not the bank', story: 'The caller names a company. The transcript spells it as something that sounds close, and nobody can tell who called.'},
  ];
  const main = report?.main_system;
  const cards = cases.map(c => {
    const plain = report && typeStat(report, 'B0_asr_plain', c.type);
    const ours = report && typeStat(report, main, c.type);
    const word = factWord(c.type).toLowerCase();
    const stat = plain && ours ? `<dl class="pain-stat">
        <div><dt>Plain speech-to-text</dt><dd><b class="num">${int(plain.silent)} of ${int(plain.n)}</b> ${word} facts wrong with no warning</dd></div>
        <div${ours.silent < plain.silent ? ' class="is-main"' : ''}><dt>Pehchaan</dt><dd><b class="num">${int(ours.silent)} of ${int(ours.n)}</b> ${word} facts wrong with no warning</dd></div></dl>`
      : '<p class="note">Measured counts appear here when a benchmark run is available.</p>';
    return `<article class="pain card-soft"><h3>${esc(c.title)}</h3><p>${esc(c.story)}</p>${stat}</article>`;
  }).join('');
  return `<div class="section-head"><h2 id="pain-title">The mistake nobody notices</h2>
    <p>A transcript can get most words right and still ruin a call, because the wrong part is the part that matters. The scenes below are imagined. The counts are measured.</p></div>
    <div class="pain-grid">${cards}</div>
    <p class="note pain-note">${report ? `Counts: ${callsLabel(data)}. Facts "wrong with no warning" are silent errors${info('silent_error')}.` : ''}</p>`;
}

// ---- measured impact: the same recordings, base model against Pehchaan ----
function claim(label, mine, theirs, key) {
  const overlap = intervalsOverlap(mine, theirs, key);
  const a = interval(mine, key);
  const b = interval(theirs, key);
  const range = row => (row ? `${pct(row[0])} to ${pct(row[1])}` : '');
  if (overlap === null) return '';
  return `<li><strong>${label}</strong> 95% intervals${info('ci95')}: ${range(a)} against ${range(b)}.
    ${overlap ? 'They overlap, so this is not a proven difference.' : 'They do not overlap.'}</li>`;
}

function impactSection(data) {
  const {report} = data;
  if (!report) return `<div class="section-head"><h2 id="impact-title">Same recordings, base model against Pehchaan</h2></div>
    <div class="state-box"><strong>No measured results yet</strong>Run a benchmark to fill this section.</div>`;
  const main = report.main_system;
  const mainRow = sys(report, main);
  const plain = sys(report, 'B0_asr_plain');
  const keyword = sys(report, 'B1_asr_keywords_C3');
  const rewrite = sys(report, 'B2_naive_llm_C3');
  const lines = [
    keyword && claim('Silent errors against keyword-assisted speech-to-text.', mainRow, keyword, 'silent_error_rate'),
    keyword && claim('Fact accuracy against keyword-assisted speech-to-text.', mainRow, keyword, 'entity_accuracy'),
  ].filter(Boolean).join('');
  return `<div class="section-head"><h2 id="impact-title">Same recordings, base model against Pehchaan</h2>
    <p>Every dot is one fact whose answer we know, in ${callsLabel(data)}. The same audio went through each system. An independent scorer${info('oracle')} marked the result.</p></div>
    <div class="dots-row">
      ${dotPanel({id: 'B0_asr_plain', title: 'Plain speech-to-text', context: 'the base model', row: plain})}
      ${dotPanel({id: 'B1_asr_keywords_C3', title: 'With call keywords', context: 'a stronger base', row: keyword})}
      ${dotPanel({id: 'B2_naive_llm_C3', title: 'Rewritten by an LLM', context: 'an LLM cleans the text', row: rewrite})}
      ${dotPanel({id: main, title: 'Pehchaan', context: 'the main system', row: mainRow, emphasis: true})}
    </div>
    ${dotLegend()}
    <ul class="claims">
      <li><strong>Damaged edits${info('damaged_edits')}:</strong> ${mainRow ? `Pehchaan damaged ${int(mainRow.damaged_edits)} correct facts. The LLM rewrite damaged ${int(rewrite?.damaged_edits)}.` : ''}</li>
      ${lines}
      <li><strong>Where it does not win:</strong> Pehchaan is not perfect. ${mainRow ? `${pct(mainRow.silent_error_rate)} of facts were still wrong with no warning on these calls.` : ''}</li>
    </ul>`;
}

// ---- why "just use an LLM" makes it worse ----
function llmSection({report}) {
  const main = report?.main_system;
  const rows = ['B2_naive_llm_C3', 'B2_naive_llm_C4', main, report && main === 'P_on_B1_C3' ? 'P_on_B1_C4' : null].filter(Boolean);
  const body = report && rows.every(id => sys(report, id)) ? (() => {
    const maxSilent = Math.max(...rows.map(id => sys(report, id).silent_error_rate), 0.05);
    const maxDamage = Math.max(...rows.map(id => sys(report, id).damaged_edits), 1);
    const label = id => {
      const [name, ctx] = id.startsWith('B2') ? ['Rewritten by an LLM', id.endsWith('C4') ? 'misleading context' : 'normal context'] : ['Pehchaan', id.endsWith('C4') ? 'misleading context' : 'normal context'];
      return esc(name) + `<small>${esc(ctx)}</small>`;
    };
    const tone = id => id.startsWith('B2') ? 'bad' : 'good';
    return `<div class="llm-grid">
      <div><h3>Wrong with no warning${info('silent_error')}</h3>${rows.map(id => barRow({label: label(id), value: sys(report, id).silent_error_rate, max: maxSilent, text: pct(sys(report, id).silent_error_rate), tone: tone(id)})).join('')}</div>
      <div><h3>Correct facts damaged${info('damaged_edits')}</h3>${rows.map(id => barRow({label: label(id), value: sys(report, id).damaged_edits, max: maxDamage, text: int(sys(report, id).damaged_edits), tone: tone(id)})).join('')}</div>
    </div>`;
  })() : '<div class="state-box"><strong>No measured results yet</strong>This comparison appears when a benchmark run is available.</div>';
  const c4 = sys(report, 'B2_naive_llm_C4');
  const guarded = sys(report, 'P_on_B1_C4');
  return `<div class="section-head"><h2 id="llm-title">“Just use an LLM” makes it worse</h2>
    <p>The obvious fix is to give a language model the transcript and the phone’s context and say: fix the mistakes. We tested exactly that${info('sys_rewrite')}. It rewrites freely, so when the context is wrong it copies the wrong names and numbers into the transcript.</p></div>
    ${body}
    ${c4 ? `<p class="callout">With misleading context, the rewrite damaged ${int(c4.damaged_edits)} correct facts across ${int(c4.clips_with_damage)} of ${int(c4.clips)} calls${info('clips_with_damage')}. Pehchaan has a gate${info('gate')} that decides what may change${guarded ? `, and it damaged ${int(guarded.damaged_edits)} in the same test` : ''}.</p>` : ''}`;
}

// ---- how it works, in one glance ----
function glanceSection() {
  const steps = [
    ['Listen twice', 'The audio is transcribed once with the call’s keywords and once without, as a second opinion' , 'second_opinion'],
    ['Propose', 'Rules for numbers, confirmed memory, sound matching across scripts and, rarely, an LLM judge suggest what each fact should be', 'resolver'],
    ['Admit', 'The Admission Gate decides what is allowed to change the text. Phone, PIN and money are never changed automatically', 'gate'],
    ['Answer or ask', 'A corrected transcript, and at most one short question such as “Kondapur or Kothapur?”', 'status_ask'],
  ];
  return `<div class="section-head"><h2 id="glance-title">How it works, in one glance</h2>
    <p>A harness${info('harness')} is the set of checks around a model. Pehchaan does not change the speech model. It checks what comes out.</p></div>
    <ol class="glance">${steps.map(([title, text, key]) => `<li><h3>${esc(title)}${info(key)}</h3><p>${esc(text)}.</p></li>`).join('')}</ol>
    <a class="button" href="#how">See each step in detail ${icon('arrow')}</a>`;
}

// ---- verified learning ----
function learningSection(proof, {report}) {
  const head = `<div class="section-head"><h2 id="learn-title">It only learns what it can prove is safe</h2>
    <p>When you confirm a correction, it is a candidate${info('verified_learning')}. It becomes automatic only if it passes six checks, including a replay on labelled calls to see that no fact is harmed. Every decision goes in a ledger${info('ledger')} and can be undone.</p></div>`;
  if (!proof) return `${head}<div class="state-box"><strong>No learning results yet</strong>The held-out learning proof appears here when it has been run.</div>`;
  const entries = Object.entries(proof.systems);
  const main = report?.main_system;
  const gain = ([, s]) => s.right_after - s.right_before;
  const mainEntry = entries.find(([id]) => id === main) || entries[entries.length - 1];
  const widest = entries.slice().sort((a, b) => gain(b) - gain(a))[0];
  const row = ([id, s], strong) => `<li class="${strong ? 'is-main' : ''}"><span>${esc(learningName(id))}</span>
    <b class="num">${int(s.right_before)} → ${int(s.right_after)}</b> of ${int(s.facts)} facts right, ${int(s.facts_harmed)} harmed</li>`;
  const tried = entries.reduce((a, [, s]) => a + s.wrong_tried, 0);
  const blocked = entries.reduce((a, [, s]) => a + s.wrong_blocked, 0);
  return `${head}
    <div class="learn-grid">
      <div class="card-soft"><h3>What it gained</h3>
        <ul class="learn-list">${row(mainEntry, true)}${widest && widest[0] !== mainEntry[0] ? row(widest, false) : ''}</ul>
        <p class="note">The gain on the main system is small, because the speech model with keywords already gets most names right. It is larger when the system has less context.</p></div>
      <div class="card-soft"><h3>What it refused</h3>
        <p><b class="num">${int(blocked)} of ${int(tried)}</b> deliberately wrong confirmations were blocked by the checks.</p>
        <p class="note">Scripted confirmations, dev data, names recurring in a different voice${info('held_out_voice')}. Not a result on real users.</p></div>
    </div>
    <a class="button" href="#how">How the six checks work ${icon('arrow')}</a>`;
}

export const learningName = id => ({P_C0: 'Rules only (C0)', P_C2: 'Built-in lists (C2)', P_on_B1_C3: 'Main system (C3)'})[id] || id;

export async function mountHome(root) {
  root.classList.add('page', 'home');
  root.innerHTML = shell;
  const hero = {};
  void mountHero(root, hero);
  root.addEventListener('click', event => {
    const button = event.target.closest('button[data-evidence]');
    if (!button || !hero.base) return;
    const baseline = button.closest('[data-side]')?.dataset.side === 'base';
    showEvidence(document.getElementById('evidence-dialog'), {result: baseline ? hero.base : hero.main, entityId: button.dataset.evidence, baseline});
  });
  const [data, proof] = await Promise.all([benchReport(), learningProof(), siteConfig()]);
  root.querySelector('#home-evidence').innerHTML = evidenceBanner(data);
  root.querySelector('#home-pain').innerHTML = painSection(data);
  root.querySelector('#home-impact').innerHTML = impactSection(data);
  root.querySelector('#home-llm').innerHTML = llmSection(data);
  root.querySelector('#home-glance').innerHTML = glanceSection();
  root.querySelector('#home-learning').innerHTML = learningSection(proof, data);
}
