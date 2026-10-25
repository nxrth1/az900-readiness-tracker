// End-to-end smoke test: the real index.html + app.js (in jsdom) talking to a live server.
// Usage: BASE_URL=http://127.0.0.1:8000 node smoke.mjs
import { createRequire } from 'node:module';
import { JSDOM, VirtualConsole } from 'jsdom';

const require = createRequire(import.meta.url);
const axeSource = require('axe-core').source;
const BASE = process.env.BASE_URL || 'http://127.0.0.1:8000';

const problems = [];
const warnings = [];
const fail = (msg) => { problems.push(msg); console.log(`FAIL  ${msg}`); };
const ok = (msg) => console.log(`ok    ${msg}`);
const check = (cond, msg) => (cond ? ok(msg) : fail(msg));

const virtualConsole = new VirtualConsole();
virtualConsole.on('jsdomError', (e) => { if (!/Not implemented/.test(e.message)) fail(`page error: ${e.message}`); });
virtualConsole.on('error', (...a) => fail(`console.error: ${a.join(' ')}`));

const dom = await JSDOM.fromURL(`${BASE}/`, {
  runScripts: 'dangerously', resources: 'usable', pretendToBeVisual: true, virtualConsole,
  beforeParse(window) {
    window.fetch = (u, o) => fetch(new URL(u, BASE), o);            // route page requests to the live server
    window.confirm = () => true;
    window.scrollTo = () => {};
    window.HTMLElement.prototype.scrollIntoView = () => {};
    if (!window.crypto.randomUUID) window.crypto.randomUUID = () => globalThis.crypto.randomUUID();
  },
});
const { window } = dom;
const { document } = window;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function until(fn, what, timeout = 6000) {
  const end = Date.now() + timeout;
  while (Date.now() < end) { try { const v = fn(); if (v) return v; } catch (_) { /* keep waiting */ } await sleep(40); }
  fail(`timed out waiting for ${what}`);
  throw new Error(`timeout: ${what}`);
}
const text = () => document.getElementById('app').textContent.replace(/\s+/g, ' ');
const click = (sel) => { const el = document.querySelector(sel); if (!el) throw new Error(`missing ${sel}`); el.click(); };

async function axeCheck(label) {
  window.eval(axeSource);
  const result = await window.axe.run(document, {
    // jsdom has no layout engine, so colour contrast and visibility-dependent rules cannot be judged here.
    rules: { 'color-contrast': { enabled: false }, 'scrollable-region-focusable': { enabled: false } },
  });
  const bad = result.violations.filter((v) => ['serious', 'critical'].includes(v.impact));
  const minor = result.violations.filter((v) => !['serious', 'critical'].includes(v.impact));
  minor.forEach((v) => warnings.push(`[${label}] ${v.impact}: ${v.id} - ${v.help} (${v.nodes.length})`));
  if (bad.length) bad.forEach((v) => fail(`[${label}] a11y ${v.impact}: ${v.id} - ${v.help} (${v.nodes.map((n) => n.target).join(' | ')})`));
  else ok(`axe: no serious/critical issues on ${label}`);
}

try {
  // ---- first run
  await until(() => text().includes('Get ready for your next step'), 'welcome screen');
  check(text().includes('not yet been independently reviewed'), 'welcome screen is honest about review status');
  check(!!document.querySelector('.content-note a[href*="study-guides/az-900"]'), 'links to the official study guide');
  check(!!document.querySelector('a[href="/privacy"]'), 'footer links to the privacy page');
  await axeCheck('welcome screen');

  // ---- demo data -> dashboard
  click('[data-act="demo"]');
  await until(() => text().includes('Your AZ-900 readiness'), 'dashboard after demo seed');
  ok('demo data loads and the dashboard renders');
  check(text().includes('How did the real thing go?'), 'outcome card is on the dashboard');

  // ---- report a practice assessment
  click('[data-act="outcome-kind"][data-v="practice_assessment"]');
  await until(() => document.querySelector('#oc-score'), 'practice-assessment form');
  check(!document.querySelector('#oc-passed'), 'practice form hides the pass/fail field');
  document.querySelector('#oc-score').value = '78';
  click('[data-act="outcome-submit"]');
  await until(() => text().includes('Practice assessment: 78%'), 'reported result listed');
  ok('practice-assessment result is saved and shown with our estimate');
  await axeCheck('dashboard');

  // ---- report an exam with a bad score -> friendly error, nothing saved
  click('[data-act="outcome-kind"][data-v="exam"]');
  await until(() => document.querySelector('#oc-passed'), 'exam form');
  document.querySelector('#oc-score').value = '50';
  click('[data-act="outcome-submit"]');
  const toastWith = (re) => [...document.querySelectorAll('.toast')].find((t) => re.test(t.textContent));
  await until(() => toastWith(/between 100 and 1000/), 'validation message');
  ok('invalid exam score gives a readable message (not raw JSON)');
  check(!toastWith(/\[|\{|"type"/), 'error text contains no raw JSON');

  // ---- practise: answer a question, see study + report links
  click('[data-act="start-adaptive"]');
  await until(() => document.querySelector('[data-act="pick"]'), 'first question');
  click('[data-act="pick"][data-k="0"]');
  click('[data-act="submit"]');
  await until(() => document.querySelector('.feedback'), 'feedback');
  const study = document.querySelector('.feedback .resource a[href^="https://learn.microsoft.com/en-us/training/modules/"]');
  check(!!study, 'feedback links to the matching Microsoft Learn module');
  check(study && study.rel.includes('noopener'), 'external links open safely');
  await axeCheck('question feedback');

  // ---- privacy page is real
  const privacy = await fetch(`${BASE}/privacy`);
  check(privacy.status === 200 && (await privacy.text()).includes('What is stored on the server'), 'privacy page is served');

  // ---- manifest + service worker reachable
  check((await fetch(`${BASE}/static/manifest.webmanifest`)).ok && (await fetch(`${BASE}/sw.js`)).ok, 'manifest and service worker are served');
} catch (e) {
  if (!/^timeout:/.test(e.message)) fail(`unexpected error: ${e.stack || e.message}`);
}

window.close();
if (warnings.length) { console.log('\nAccessibility notes (not failing):'); warnings.forEach((w) => console.log(`  - ${w}`)); }
console.log(problems.length ? `\n${problems.length} problem(s)` : '\nAll end-to-end checks passed');
process.exit(problems.length ? 1 : 0);
