// The router: hash routes, one mounted page per route, shared dialog and tooltip.
import {initInfo} from './info.js';
import {mountHome} from './home.js';
import {mountPlayground} from './playground.js';
import {mountHow} from './how.js';
import {mountProof} from './proof.js';
import {mountIntegration} from './integration.js';
import {siteConfig} from './api.js';

const routes = new Map([
  ['home', {mount: mountHome, title: 'Every fact in an Indian call: right, or it asks'}],
  ['playground', {mount: mountPlayground, title: 'Try a call'}],
  ['how', {mount: mountHow, title: 'How it works'}],
  ['benchmark', {mount: mountProof, title: 'Proof'}],
  ['integration', {mount: mountIntegration, title: 'API'}],
]);
const instances = new Map();
const mounted = new Set();
const main = document.getElementById('main');
let active = 'home';

function parse() {
  const [name, query = ''] = location.hash.slice(1).split('?');
  return {name: routes.has(name) ? name : 'home', params: new URLSearchParams(query)};
}

async function show() {
  const {name, params} = parse();
  active = name;
  for (const id of routes.keys()) {
    const page = document.getElementById(id);
    const link = document.querySelector(`.site-nav a[href="#${id}"]`);
    page.hidden = id !== active;
    if (id === active) link.setAttribute('aria-current', 'page'); else link.removeAttribute('aria-current');
  }
  document.title = `${routes.get(active).title} | Pehchaan`;
  if (!mounted.has(active)) {
    mounted.add(active);
    const result = routes.get(active).mount(document.getElementById(active));
    instances.set(active, await result);
  }
  const sample = params.get('sample');
  if (active === 'playground' && sample) {
    history.replaceState(null, '', '#playground');
    instances.get('playground')?.openSample(sample);
  }
}

initInfo();
document.querySelector('.skip-link').addEventListener('click', event => {
  event.preventDefault();
  main.focus();
});
document.addEventListener('click', event => {
  const link = event.target.closest('a[href^="#"]');
  if (!link || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) return;
  const target = link.getAttribute('href');
  if (!routes.has(target.slice(1).split('?')[0])) return;
  event.preventDefault();
  if (location.hash !== target) history.pushState(null, '', target);
  void show().then(() => { main.focus({preventScroll: true}); window.scrollTo(0, 0); });
});
window.addEventListener('popstate', () => void show());
window.addEventListener('hashchange', () => void show());

document.getElementById('evidence-dialog').addEventListener('click', event => {
  if (event.target === event.currentTarget) event.currentTarget.close();
});

void siteConfig().then(config => {
  if (!config.studio) return;          // the Studio only exists on the laptop
  const link = document.createElement('a');
  link.href = '/studio';
  link.textContent = 'Studio';
  document.querySelector('.site-nav').append(link);
});
void show();
