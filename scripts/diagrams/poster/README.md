# Solution-architecture poster (canonical)

`generated-diagrams/solution-architecture.png` (shown at the top of the project
README) is rendered from **`solution-architecture.html`** here — a hand-composed,
self-contained layout (AWS icons live in `icons/`, no external paths).

## Regenerate

```bash
node scripts/diagrams/poster/render.js   # writes generated-diagrams/solution-architecture.png
```

Requires Playwright Chromium (`npx playwright install chromium`).

> This replaces the old graphviz auto-layout generator. Do **not** reintroduce a
> script that writes `generated-diagrams/solution-architecture.png` from graphviz —
> it would clobber this poster.
