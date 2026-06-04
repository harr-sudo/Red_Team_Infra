// Render the hand-composed solution-architecture poster to a PNG.
// Usage (from repo root):  node scripts/diagrams/poster/render.js
const path = require('path');
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  const html = 'file://' + path.join(__dirname, 'solution-architecture.html');
  const out  = path.join(__dirname, '..', '..', '..', 'generated-diagrams', 'solution-architecture.png');
  await page.goto(html, { waitUntil: 'networkidle' });
  await page.waitForTimeout(600);
  const el = await page.$('#poster');
  await el.screenshot({ path: out });
  await browser.close();
  console.log('rendered ->', out);
})().catch(e => { console.error(e); process.exit(1); });
