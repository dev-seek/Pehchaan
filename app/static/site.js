import { mountPlayground } from "./playground.js";
import { mountBenchmark } from "./benchmark.js";

const mounts = new Map([
  ["playground", mountPlayground],
  ["benchmark", mountBenchmark],
  ["integration", mountIntegration],
]);
const titles = new Map([
  ["playground", "Live Call Playground"],
  ["benchmark", "Benchmark Lab"],
  ["integration", "API & Integration"],
]);
const mounted = new Set();
let active = "playground";

function showPage() {
  const hash = location.hash.slice(1);
  if (mounts.has(hash)) active = hash;
  else if (!hash) active = "playground";
  for (const id of mounts.keys()) {
    const page = document.getElementById(id);
    const link = document.querySelector(`.site-nav a[href="#${id}"]`);
    page.hidden = id !== active;
    if (page.hidden) {
      link.removeAttribute("aria-current");
      continue;
    }
    link.setAttribute("aria-current", "page");
    if (!mounted.has(id)) {
      mounts.get(id)(page);
      mounted.add(id);
    }
  }
  document.title = `Pehchaan | ${titles.get(active)}`;
}

function mountIntegration(page) {
  const endpoint = new URL("/v1/pehchaan/transcribe", location.origin).href;
  page.querySelector("#python-example").textContent = [
    "import httpx",
    'with open("call.wav", "rb") as audio:',
    `    print(httpx.post("${endpoint}", files={"audio": audio}, timeout=120).json())`,
  ].join("\n");
  page.querySelector("#curl-example").textContent = [
    `curl --fail-with-body "${endpoint}" \\`,
    '  -F "audio=@call.wav" \\',
    '  -F "level=C3"',
  ].join("\n");
  page.addEventListener("click", async event => {
    const button = event.target.closest("[data-copy]");
    if (!button) return;
    const code = document.getElementById(button.dataset.copy);
    const status = page.querySelector("#api-copy-status");
    const label = button.textContent;
    try {
      await navigator.clipboard.writeText(code.textContent);
      button.textContent = "Copied";
      button.disabled = true;
      status.textContent = `${label.slice(5)} example copied.`;
      setTimeout(() => {
        button.textContent = label;
        button.disabled = false;
      }, 1500);
    } catch {
      const selection = window.getSelection();
      selection.selectAllChildren(code);
      code.closest("pre").focus();
      status.textContent = "Example selected. Use your keyboard to copy.";
    }
  });
}

const main = document.getElementById("main");
document.querySelector(".skip-link").addEventListener("click", event => {
  event.preventDefault();
  main.focus();
});
document.querySelector(".site-header").addEventListener("click", event => {
  const link = event.target.closest("a[href^='#']");
  if (!link || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) return;
  event.preventDefault();
  if (location.hash !== link.hash) history.pushState(null, "", link.hash);
  showPage();
  main.focus({preventScroll: true});
  window.scrollTo(0, 0);
});
window.addEventListener("hashchange", showPage);
showPage();
