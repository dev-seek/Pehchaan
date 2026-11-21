// How it works: the pipeline, the gate, the context levels, verified learning and why this is a harness.
import {esc, icon, badge, glyph} from './util.js';
import {info} from './info.js';

const stages = [
  ['Hear it twice', 'The audio goes to the speech model two ways: once with the call’s keywords, and once with none. The plain one is a second opinion.', ['asr', 'keywords', 'second_opinion']],
  ['Find the facts', 'Phone numbers, PIN codes, amounts, names, places and brands are located in the text, even when Hindi, Telugu and English are mixed in one sentence.', ['fact']],
  ['Propose', 'Specialists suggest what each fact should be: number grammar (“dedh lakh”), confirmed memory, sound matching across scripts, and an LLM judge only for the ambiguous ones.', ['resolver', 'sound_match', 'llm_judge']],
  ['Admit', 'The Admission Gate decides what may actually change the text. It applies six fixed rules and records any proposal it refuses.', ['gate']],
  ['Answer or ask', 'The output is a corrected transcript with every fact marked, and at most one short question for anything still uncertain.', ['status_ask']],
];

const rules = [
  ['critical_read_only', 'Phone numbers, PIN codes and money are never changed automatically.',
    'A callback number that was not read clearly is not \u201Cfixed\u201D. Pehchaan asks, in Telugu-English, \u201CNumber okasari confirm cheyandi?\u201D and offers the possible readings as choices.', 'From the Telugu Callback sample.'],
  ['acronym_spelled', 'A short all-caps brand needs its letters to be heard.',
    'The Hindi word “लिख” (write) sounds like “LIC”. Nobody spelled L, I, C, so it stays a word.', 'An earlier version made this mistake.'],
  ['common_word', 'An everyday word never becomes a brand or name.',
    '“डिलीवरी” (delivery) stays “delivery”. It does not become “Delhivery” just because the sound is close.', 'The Delivery sample shows this rule refusing the change.'],
  ['person_not_place', 'A word marked as a place cannot become a person from your contacts.',
    '“नारायणगुड़ा वाले” points to a place, so it is never replaced by a similar-sounding contact such as “Neha Agarwal”.', 'An earlier version made this mistake.'],
  ['second_opinion', 'A hint cannot replace a different name that both transcripts heard.',
    'Both transcripts heard “Rohit”, and a contact is called “Mohit”. Pehchaan does not swap them. It asks “Rohit or Mohit?”. It also asks when a hinted name appears only in the keyword transcript.', 'From the real-voice Wrong-context trap.'],
  ['known_name_heard', 'A learned correction cannot erase a real name the caller said.',
    'You teach it that “Basavanagudi” was wrong on one call. If a later caller really says Basavanagudi and both transcripts hear it, it stays.', 'From the Wrong-Context sample.'],
];

const levelRows = [
  ['C0', 'Nothing. Only number grammar and sound rules.', 'The floor: a stranger on an unknown phone.'],
  ['C1', 'One line about the call type, such as “bank EMI reminder”.', 'Not run in the live demo.'],
  ['C2', 'Pehchaan’s own lists of well-known brands and local areas for the caller’s city.', 'Works for any caller. Nothing about this caller.'],
  ['C3', 'C2, plus this call’s contacts, caller ID, SMS and saved places.', 'The product setting, and the one the headline numbers use.'],
  ['C4', 'C3’s machinery, fed context that is deliberately wrong: true names removed, sound-alike decoys added.', 'A stress test. Can the system be talked out of the truth?'],
];

const checks = [
  ['learnable_type', 'Only names, companies and places. Never numbers.'],
  ['not_everyday_word', 'The heard word must not be an ordinary word.'],
  ['sounds_alike', 'The correction must sound like what was heard.'],
  ['no_conflict', 'It must not contradict something already learned.'],
  ['repairs_this_call', 'It must fix the call it came from, without touching a number.'],
  ['no_regression', 'Replayed on labelled calls, it must harm nothing.'],
];

const harness = [
  ['A prompt asks the model to be careful.', 'A gate in code decides what may change, and records every refusal.', 'gate'],
  ['A prompt is graded by reading a few outputs.', 'An independent scorer marks every fact and audits every edit, sharing no code with the engine.', 'oracle'],
  ['A prompt change is judged by feel.', 'A regression gate rejects any change that makes a measured promise worse.', 'regression_gate'],
  ['A prompt trusts the user’s tap.', 'Verified learning tests a confirmation on labelled calls before it can change anything.', 'verified_learning'],
  ['A prompt is tuned until it looks good.', 'A locked real-voice exam is run once, and shown as pending until it is.', 'exam'],
];

const ruleTitles = {
  critical_read_only: 'Numbers and money are read-only', acronym_spelled: 'Brand initials must be heard',
  common_word: 'Everyday words stay words', person_not_place: 'Places stay places',
  second_opinion: 'Hints cannot replace a clear name', known_name_heard: 'Learning cannot erase a real name',
};

export function mountHow(root) {
  root.classList.add('page', 'how');
  root.innerHTML = `
    <header class="page-head"><h1>How it works</h1>
      <p class="lede">Pehchaan is a layer after speech-to-text. The speech model is the ear. Pehchaan is the part that checks the facts before anyone acts on them.</p></header>

    <section aria-labelledby="pipe-title">
      <div class="section-head"><h2 id="pipe-title">The pipeline</h2><p>Five steps. Only the third one proposes. Only the fourth one decides.</p></div>
      <ol class="pipeline">${stages.map(([title, text, keys], i) => `<li class="${i === 3 ? 'is-gate' : ''}">
        <h3>${esc(title)}</h3><p>${esc(text)}</p><p class="terms">${keys.map(k => info(k)).join('')}</p></li>`).join('')}</ol>
    </section>

    <section aria-labelledby="out-title">
      <div class="section-head"><h2 id="out-title">What can happen to a fact</h2>
        <p>Every fact ends in exactly one of these. Colour is never the only signal: each has its own word and its own shape.</p></div>
      <dl class="outcomes">
        <div><dt>${badge('verified', {withInfo: true})}</dt><dd>Evidence says it is right. Example: a name that sounds like a contact and was also heard in the second transcript.</dd></div>
        <div><dt>${badge('fixed', {withInfo: true})}</dt><dd>A misheard name, place or brand was changed to the right one, with the reason stored.</dd></div>
        <div><dt>${badge('ask', {withInfo: true})}</dt><dd>Not sure, so one short question: “Kondapur or Kothapur?”</dd></div>
        <div><dt>${badge('heard', {withInfo: true})}</dt><dd>No evidence either way, so it stays exactly as the speech model wrote it.</dd></div>
        <div><dt>${badge('wrong', {withInfo: true})}</dt><dd>Only on scored samples: wrong, and nobody was warned. The one to push toward zero.</dd></div>
      </dl>
    </section>

    <section aria-labelledby="gate-title">
      <div class="section-head"><h2 id="gate-title">The Admission Gate${info('gate')}</h2>
        <p>Specialist checkers only suggest changes. The gate decides, so a bug in one checker cannot break a promise. Six rules:</p></div>
      <div class="rules">${rules.map(([key, rule, example, source]) => `<article class="rule-card card-soft">
        <h3>${esc(ruleTitles[key])}${info(`gate_${key}`)}</h3><p class="note"><code>${esc(key)}</code></p><p><strong>${esc(rule)}</strong></p><p>${example}</p><p class="note">${esc(source)}</p></article>`).join('')}</div>
    </section>

    <section aria-labelledby="ctx-title">
      <div class="section-head"><h2 id="ctx-title">Context levels, C0 to C4</h2>
        <p>Context is what the phone already knows${info('context')}. The levels turn it up one step at a time, so the benchmark can show what each step buys.</p></div>
      <div class="table-scroll" tabindex="0" role="region" aria-label="Context levels">
        <table><thead><tr><th scope="col">Level</th><th scope="col">What it adds</th><th scope="col">Why it exists</th></tr></thead>
        <tbody>${levelRows.map(([k, add, why]) => `<tr><th scope="row">${k}${info(k)}</th><td>${esc(add)}</td><td>${esc(why)}</td></tr>`).join('')}</tbody></table></div>
    </section>

    <section aria-labelledby="learn-title">
      <div class="section-head"><h2 id="learn-title">Verified learning${info('verified_learning')}</h2>
        <p>When you answer a question, the answer is a candidate, not a fact. A wrong tap should not rewrite every later call. So the candidate must pass six checks before it becomes automatic.</p></div>
      <ol class="checks-list">${checks.map(([k, text]) => `<li><b>${esc(k.replaceAll('_', ' '))}</b>${info(`learn_${k}`)}<span>${esc(text)}</span></li>`).join('')}</ol>
      <p>Every decision, adopted or rejected, goes in an append-only ledger${info('ledger')}. Any adopted correction can be undone. A rejection is a normal outcome, not an error: the site shows which check failed.</p>
      <a class="button" href="#playground">Try the confirm, test and undo flow ${icon('arrow')}</a>
    </section>

    <section aria-labelledby="harness-title">
      <div class="section-head"><h2 id="harness-title">A harness, not a prompt${info('harness')}</h2>
        <p>The track said there is much to invent in the harness. This is the harness: the machinery that makes the model safe to rely on, and measurable.</p></div>
      <ul class="harness-list">${harness.map(([a, b, key]) => `<li><span class="was">${esc(a)}</span><span class="is">${esc(b)}${info(key)}</span></li>`).join('')}</ul>
      <p>The evidence is on the <a href="#benchmark">Proof</a> page.</p>
    </section>`;
}
