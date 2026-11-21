<!-- Project design context for 21st -->
# Pehchaan design context

Pehchaan is a local voice AI demo and benchmark lab. It runs on FastAPI with plain HTML, CSS, and JavaScript.

- `app/static/css/core.css` defines the palette, typography, spacing and visible focus. Each page has its own stylesheet.
- `app/static/js/site.js` routes Home, Try it, How it works, Proof and API. `js/info.js` and `js/glossary.js` provide the
  info button on every term. Each status has a word and a shape as well as a colour.
- Every measured number is read from the API when a page opens. `js/charts.js` pairs charts with a table.
- Keep design tooling out of runtime dependencies. The 21st comparison references and UI/UX Pro Max guidance were used
  for compact data layout, keyboard and touch interaction, and accessible feedback.
