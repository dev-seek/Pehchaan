<!-- Project design context for 21st -->
# Pehchaan design context

Pehchaan is a local voice AI demo and benchmark lab. It runs on FastAPI with plain HTML, CSS, and JavaScript.

- `app/static/site.css` defines the white and slate palette, system typography, spacing, and visible focus.
- `app/static/playground.js` opens on the microphone action. It uses aligned comparison columns, native controls,
  and disclosures for methods and evidence. Each semantic color has a text label.
- `app/static/benchmark.js` pairs the chart with a semantic table and includes explicit report coverage and missing states.
- Keep design tooling out of runtime dependencies. The 21st comparison references and UI/UX Pro Max guidance were used
  for compact data layout, keyboard and touch interaction, and accessible feedback.
