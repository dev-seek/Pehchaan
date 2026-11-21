// How it works: the short version. The Playground tabs show each idea running.
import {esc, icon, badge} from './util.js';
import {info} from './info.js';

const stages = [
  ['Hear it twice', 'Once with call keywords, once plain.', 'second_opinion'],
  ['Find the facts', 'Numbers, money, names, places, brands.', 'fact'],
  ['Propose', 'Specialists suggest each value.', 'resolver'],
  ['Admit', 'A code gate decides what may change.', 'gate'],
  ['Answer or ask', 'A checked transcript, or one question.', 'status_ask'],
];
const rules = [
  ['critical_read_only', 'Numbers and money are read-only'],
  ['acronym_spelled', 'Brand initials must be heard'],
  ['common_word', 'Everyday words stay words'],
  ['person_not_place', 'Places stay places'],
  ['second_opinion', 'Hints cannot replace a clear name'],
  ['known_name_heard', 'Learning cannot erase a real name'],
];
const harness = [
  ['A prompt asks the model to be careful.', 'A gate in code decides what may change.', 'gate'],
  ['A prompt is graded by reading a few outputs.', 'An independent scorer marks every fact.', 'oracle'],
  ['A prompt trusts the user’s tap.', 'Each answer is tested on labelled calls first.', 'verified_learning'],
  ['A prompt is tuned until it looks good.', 'A locked exam ran once, on frozen code.', 'exam'],
];

export function mountHow(root) {
  root.classList.add('page', 'how');
  root.innerHTML = `
    <header class="page-head"><h1>How it works</h1>
      <p class="lede">The speech model is the ear. Pehchaan checks the facts before anyone acts on them.</p></header>
    <section aria-labelledby="pipe-title">
      <div class="section-head"><h2 id="pipe-title">Five steps</h2></div>
      <ol class="how-steps">${stages.map(([title, text, key], i) => `<li class="${i === 3 ? 'is-gate' : ''}"><h3>${esc(title)}${info(key)}</h3><span>${esc(text)}</span></li>`).join('')}</ol>
    </section>
    <section aria-labelledby="out-title">
      <div class="section-head"><h2 id="out-title">Every fact ends in one status</h2></div>
      <p class="chips">${['verified', 'fixed', 'ask', 'heard', 'wrong'].map(k => badge(k)).join(' ')}</p>
    </section>
    <section aria-labelledby="gate-title">
      <div class="section-head"><h2 id="gate-title">Six rules the gate enforces${info('gate')}</h2></div>
      <ul class="rule-list">${rules.map(([key, title]) => `<li>${esc(title)}${info(`gate_${key}`)}</li>`).join('')}</ul>
    </section>
    <section aria-labelledby="harness-title">
      <div class="section-head"><h2 id="harness-title">A harness, not a prompt${info('harness')}</h2></div>
      <ul class="harness-list">${harness.map(([a, b, key]) => `<li><span class="was">${esc(a)}</span><span class="is">${esc(b)}${info(key)}</span></li>`).join('')}</ul>
      <p class="head-links"><a class="button" href="#playground?tab=learning">See it learn ${icon('arrow')}</a> <a class="button" href="#benchmark">See the results</a></p>
    </section>`;
}
