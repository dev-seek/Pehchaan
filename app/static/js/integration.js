// API: the one endpoint, two copy-paste examples, and the fields that come back.
import {icon} from './util.js';
import {siteConfig} from './api.js';

export async function mountIntegration(root) {
  const config = await siteConfig();
  const endpoint = new URL('/v1/pehchaan/transcribe', location.origin).href;
  const needsCode = config.live_needs_passcode;
  const python = ['import httpx', 'with open("call.wav", "rb") as audio:',
    `    print(httpx.post("${endpoint}", files={"audio": audio},${needsCode ? ' headers={"X-Demo-Passcode": "..."},' : ''} timeout=120).json())`].join('\n');
  const curl = [`curl --fail-with-body "${endpoint}" \\`, ...(needsCode ? ['  -H "X-Demo-Passcode: ..." \\'] : []), '  -F "audio=@call.wav" \\', '  -F "level=C3"'].join('\n');
  root.classList.add('page', 'api');
  root.innerHTML = `
    <header class="page-head"><h1>API</h1>
      <p class="lede">Send call audio or a transcript. Get back the facts, the questions, the evidence and the timings.</p></header>
    <div class="endpoint card"><span class="method">POST</span><code>/v1/pehchaan/transcribe</code>
      <a href="/docs">Open the interactive API docs</a></div>
    ${needsCode ? '<p class="note">This is a public deployment. Live requests need the demo passcode, sent in the <code>X-Demo-Passcode</code> header.</p>' : ''}
    <div class="examples">
      ${[['Python', 'python-example', python], ['curl', 'curl-example', curl]].map(([title, id, code]) => `<article class="card-soft example">
        <header><h2>${title}</h2><button class="button" type="button" data-copy="${id}">${icon('check')} Copy ${title}</button></header>
        <pre tabindex="0" aria-label="${title} request"><code id="${id}">${code.replace(/&/g, '&amp;').replace(/</g, '&lt;')}</code></pre></article>`).join('')}
    </div>
    <p id="api-copy-status" class="sr-only" role="status"></p>
    <p class="note">Replace <code>call.wav</code> with your audio file. The Python example uses <code>httpx</code>. For a transcript, send the multipart <code>text</code> field instead of <code>audio</code>.</p>
    <article class="card-soft fields"><h2>What comes back</h2>
      <dl>
        <div><dt><code>baseline</code> and <code>asr</code></dt><dd>The plain and the keyword-assisted transcripts, model names and speech-to-text time in milliseconds. With typed input, <code>baseline</code> is empty.</dd></div>
        <div><dt><code>pehchaan.text_out</code> and <code>.entities</code></dt><dd>The corrected transcript and each typed fact, with what was heard, the value, the status and the source.</dd></div>
        <div><dt><code>pehchaan.questions</code></dt><dd>The short follow-up question for each fact that needs clarifying.</dd></div>
        <div><dt><code>entities[].reason</code>, <code>.candidates</code>, <code>.admission</code></dt><dd>The evidence for a decision, the alternatives considered and the gate rule applied. <code>pehchaan.refused</code> lists proposals the gate blocked.</dd></div>
        <div><dt><code>pehchaan.timings_ms</code> and <code>.llm_calls</code></dt><dd>Processing time per stage and the number of LLM judge requests.</dd></div>
      </dl></article>`;
  root.addEventListener('click', async event => {
    const button = event.target.closest('[data-copy]');
    if (!button) return;
    const code = document.getElementById(button.dataset.copy);
    const status = root.querySelector('#api-copy-status');
    const label = button.innerHTML;
    try {
      await navigator.clipboard.writeText(code.textContent);
      button.textContent = 'Copied';
      status.textContent = 'Example copied.';
      setTimeout(() => { button.innerHTML = label; }, 1500);
    } catch {
      getSelection().selectAllChildren(code);
      code.closest('pre').focus();
      status.textContent = 'Example selected. Use your keyboard to copy.';
    }
  });
}
