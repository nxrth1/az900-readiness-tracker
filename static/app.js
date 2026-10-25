/* AZ-900 Readiness Tracker (unofficial) - vanilla JS, no build step. */
(() => {
  'use strict';

  // ---------- helpers ----------
  const $ = (sel, el = document) => el.querySelector(sel);
  const app = $('#app');
  const icon = (name, className = '') => {
    const paths = {
      arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
      check: '<path d="m5 12 4 4L19 6"/>',
      chart: '<path d="M4 19V5M4 19h16M8 15v-3m5 3V8m5 7v-5"/>',
      target: '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/><path d="m16.5 7.5 4-4"/>',
      calendar: '<rect x="4" y="5" width="16" height="15" rx="2"/><path d="M8 3v4m8-4v4M4 10h16m-9 4h.01M15 14h.01M11 17h.01"/>',
      users: '<path d="M16 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="10" cy="7" r="4"/><path d="M20 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
      balance: '<path d="M12 3v17m-7 0h14M5 7h14M7 7l-4 7h8L7 7zm10 0-4 7h8l-4-7z"/>',
      server: '<rect x="3" y="4" width="18" height="7" rx="2"/><rect x="3" y="14" width="18" height="7" rx="2"/><path d="M7 7.5h.01M7 17.5h.01m4-10h6m-6 10h6"/>',
      cache: '<path d="M12 3 4 7l8 4 8-4-8-4zM4 12l8 4 8-4M4 17l8 4 8-4"/>',
      database: '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.66 3.58 3 8 3s8-1.34 8-3V5M4 12c0 1.66 3.58 3 8 3s8-1.34 8-3"/>',
    };
    return `<svg class="icon${className ? ` ${className}` : ''}" viewBox="0 0 24 24" aria-hidden="true" focusable="false">${paths[name]}</svg>`;
  };
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const pct = (v) => `${Math.round(v * 100)}%`;
  const shuffle = (a) => { a = a.slice(); for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; };

  const store = {
    get(k) { try { return localStorage.getItem(k); } catch (_) { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (_) { /* private mode */ } },
    remove(k) { try { localStorage.removeItem(k); } catch (_) { /* private mode */ } },
  };
  const savedIds = () => {
    try {
      const ids = JSON.parse(store.get('az900.saved') || '[]');
      return Array.isArray(ids) ? [...new Set(ids.filter((id) => typeof id === 'string'))] : [];
    } catch (_) { return []; }
  };
  const toggleSaved = (id) => {
    const ids = savedIds();
    const next = ids.includes(id) ? ids.filter((item) => item !== id) : [...ids, id];
    store.set('az900.saved', JSON.stringify(next));
    return next.includes(id);
  };
  const planChecks = () => {
    try {
      const checks = JSON.parse(store.get('az900.planChecks') || '{}');
      return checks && typeof checks === 'object' && !Array.isArray(checks) ? checks : {};
    } catch (_) { return {}; }
  };
  const learner = (() => {
    let id = store.get('az900.learner');
    if (!id) {
      const raw = (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : `${Date.now()}${Math.random().toString(36).slice(2)}`;
      id = raw.replace(/[^A-Za-z0-9_-]/g, '');
      store.set('az900.learner', id);
    }
    return id;
  })();
  const SESSION_KEY = `az900.session.${learner}`;
  const loadSession = () => {
    try {
      const session = JSON.parse(store.get(SESSION_KEY) || 'null');
      if (!session || session.version !== 1 || !Array.isArray(session.items)
        || !['adaptive', 'topic', 'domain', 'exam', 'saved', 'retry'].includes(session.mode)
        || !Number.isInteger(session.i) || session.i < 0 || session.i >= session.items.length
        || !session.items.every((item) => item && typeof item.id === 'string'
          && Array.isArray(item.options) && item.options.length === 4
          && Array.isArray(item.order) && item.order.length === 4
          && item.order.every((index) => Number.isInteger(index) && index >= 0 && index < 4))
        || (session.deadline !== null && session.deadline !== undefined && !Number.isFinite(session.deadline))) return null;
      session.answers = Array.from({ length: session.items.length }, (_, index) => {
        const answer = Array.isArray(session.answers) ? session.answers[index] : null;
        return answer && Number.isInteger(answer.picked) && answer.picked >= 0 && answer.picked < 4
          ? { picked: answer.picked, sure: answer.sure !== false, persisted: answer.persisted === true } : null;
      });
      session.flags = Array.from({ length: session.items.length }, (_, index) =>
        Array.isArray(session.flags) ? Boolean(session.flags[index]) : false);
      session.results = Array.isArray(session.results) ? session.results : [];
      return session;
    } catch (_) { return null; }
  };

  async function api(path, opts = {}) {
    let res;
    try { res = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...opts }); }
    catch (error) { throw new Error(`Could not connect to the server. Check your connection and retry. (${error.message})`); }
    if (!res.ok) {
      let msg = `Request failed (${res.status})`;
      try { const j = await res.json(); if (j.detail) msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail); } catch (_) { /* ignore */ }
      throw new Error(msg);
    }
    return res.json();
  }

  function toast(msg) {
    const t = document.createElement('div');
    t.className = 'toast'; t.setAttribute('role', 'status'); t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(() => t.remove(), 3200);
  }

  // ---------- state ----------
  const loadPlanSnapshot = () => {
    try {
      const plan = JSON.parse(store.get('az900.planSnapshot') || 'null');
      return plan && Array.isArray(plan.days) && typeof plan.exam === 'string' ? plan : null;
    } catch (_) { return null; }
  };
  const S = { view: 'dashboard', meta: null, report: null, quiz: null, interrupted: loadSession(), lang: 'en', loading: false, plan: null, previousPlan: loadPlanSnapshot(), planError: null, planNotice: null, planPrefs: null, timer: null, lastTimerAnnouncement: null };

  function saveSession() {
    if (!S.quiz) return;
    try {
      store.set(SESSION_KEY, JSON.stringify({ ...S.quiz, version: 1, savedAt: Date.now() }));
    } catch (_) { toast('Could not save this session on this device. Your submitted answers are still recorded.'); }
  }

  function clearSavedSession() {
    store.remove(SESSION_KEY);
    S.interrupted = null;
  }

  function resumeSession() {
    if (!S.interrupted) return;
    const session = S.interrupted;
    S.interrupted = null;
    S.quiz = {
      ...session,
      answers: Array.isArray(session.answers) ? session.answers : [],
      flags: Array.isArray(session.flags) ? session.flags : [],
      results: Array.isArray(session.results) ? session.results : [],
      busy: false,
      t0: Date.now(),
    };
    const answer = S.quiz.answers[S.quiz.i];
    S.quiz.picked = answer && Number.isInteger(answer.picked) ? answer.picked
      : S.quiz.mode !== 'exam' && Number.isInteger(session.picked) ? session.picked : null;
    S.quiz.sure = answer ? answer.sure !== false : session.sure !== false;
    S.quiz.answered = S.quiz.mode !== 'exam' ? (S.quiz.results[S.quiz.i] || null) : null;
    S.view = 'quiz';
    saveSession();
    render();
    startExamClock();
    focusQuizQuestion();
  }

  // ---------- colour scale for the topic map ----------
  const STOPS = [[0, [227, 154, 122]], [0.5, [239, 230, 208]], [1, [111, 191, 176]]];
  function tileColor(v) {
    v = Math.max(0, Math.min(1, v));
    for (let i = 1; i < STOPS.length; i++) {
      if (v <= STOPS[i][0]) {
        const [a, ca] = STOPS[i - 1]; const [b, cb] = STOPS[i];
        const t = (v - a) / (b - a);
        return `rgb(${ca.map((c, k) => Math.round(c + (cb[k] - c) * t)).join(',')})`;
      }
    }
    return `rgb(${STOPS[STOPS.length - 1][1].join(',')})`;
  }

  // ---------- SVG pieces ----------
  function arcPath(cx, cy, r, v0, v1) {
    const pt = (v) => [cx - r * Math.cos(Math.PI * v), cy - r * Math.sin(Math.PI * v)];
    const [x0, y0] = pt(v0); const [x1, y1] = pt(v1);
    // A gauge sweeps at most a half circle, so the large-arc flag is always 0.
    return `M ${x0.toFixed(2)} ${y0.toFixed(2)} A ${r} ${r} 0 0 1 ${x1.toFixed(2)} ${y1.toFixed(2)}`;
  }

  function gaugeSvg(o, passMark) {
    const cx = 150, cy = 150, r = 120;
    const tickA = [cx - (r - 16) * Math.cos(Math.PI * passMark), cy - (r - 16) * Math.sin(Math.PI * passMark)];
    const tickB = [cx - (r + 16) * Math.cos(Math.PI * passMark), cy - (r + 16) * Math.sin(Math.PI * passMark)];
    const label = [cx - (r + 28) * Math.cos(Math.PI * passMark), cy - (r + 28) * Math.sin(Math.PI * passMark)];
    const hasData = o.answered > 0;
    return `
      <svg class="gauge" viewBox="0 0 300 185" role="img" aria-label="Estimated exam score ${pct(o.score)}, likely range ${pct(o.low)} to ${pct(o.high)}, pass line ${pct(passMark)}">
        <title>Estimated score ${pct(o.score)}; likely range ${pct(o.low)} to ${pct(o.high)}; pass line ${pct(passMark)}</title>
        <path class="track" d="${arcPath(cx, cy, r, 0, 1)}" fill="none" stroke-width="18" stroke-linecap="round"/>
        ${hasData ? `<path class="band" d="${arcPath(cx, cy, r, o.low, Math.max(o.high, o.low + 0.004))}" fill="none" stroke-width="30"/>` : ''}
        ${hasData ? `<path class="val" d="${arcPath(cx, cy, r, 0.0001, Math.max(o.score, 0.003))}" fill="none" stroke-width="18" stroke-linecap="round"/>` : ''}
        <line class="pass" x1="${tickA[0].toFixed(1)}" y1="${tickA[1].toFixed(1)}" x2="${tickB[0].toFixed(1)}" y2="${tickB[1].toFixed(1)}" stroke-width="3"/>
        <text x="${label[0].toFixed(1)}" y="${(label[1] - 2).toFixed(1)}" font-size="11" text-anchor="middle" style="font-family:var(--sans);fill:var(--clay)">pass ${pct(passMark)}</text>
        <text x="150" y="138" font-size="40" font-weight="600" text-anchor="middle">${hasData ? pct(o.score) : '--'}</text>
        <text x="150" y="162" font-size="13" text-anchor="middle" style="font-family:var(--sans);fill:var(--muted)">estimated exam score</text>
      </svg>`;
  }

  function sparkSvg(hist, passMark) {
    if (hist.length < 2) return '<p class="muted">Your trend appears after you have practised on two different days.</p>';
    const W = 520, H = 150, pad = { l: 34, r: 12, t: 12, b: 24 };
    const vals = hist.map((h) => h.score);
    const lo = Math.max(0, Math.min(Math.min(...vals), passMark) - 0.08);
    const hi = Math.min(1, Math.max(Math.max(...vals), passMark) + 0.08);
    const x = (i) => pad.l + (i * (W - pad.l - pad.r)) / (hist.length - 1);
    const y = (v) => pad.t + (1 - (v - lo) / (hi - lo)) * (H - pad.t - pad.b);
    const pts = hist.map((h, i) => `${x(i).toFixed(1)},${y(h.score).toFixed(1)}`);
    const area = `${pts.join(' ')} ${x(hist.length - 1).toFixed(1)},${H - pad.b} ${x(0).toFixed(1)},${H - pad.b}`;
    const fmt = (d) => { const [, m, dd] = d.split('-'); return `${dd}/${m}`; };
    const last = hist[hist.length - 1];
    return `
      <svg class="spark" viewBox="0 0 ${W} ${H}" role="img" aria-label="Estimated score over time, now ${pct(last.score)}">
        <line class="pl" x1="${pad.l}" x2="${W - pad.r}" y1="${y(passMark).toFixed(1)}" y2="${y(passMark).toFixed(1)}"/>
        <text x="${pad.l - 6}" y="${(y(passMark) + 4).toFixed(1)}" text-anchor="end">${pct(passMark)}</text>
        <polygon class="area" points="${area}"/>
        <polyline class="line" points="${pts.join(' ')}"/>
        <circle cx="${x(hist.length - 1).toFixed(1)}" cy="${y(last.score).toFixed(1)}" r="4.5"/>
        <text x="${pad.l}" y="${H - 6}">${fmt(hist[0].date)}</text>
        <text x="${W - pad.r}" y="${H - 6}" text-anchor="end">${fmt(last.date)}</text>
      </svg>`;
  }

  // ---------- dashboard ----------
  function passLikelihood(p) {
    if (p < 0.01) return 'under 1%';
    if (p > 0.99) return 'over 99%';
    return `about ${Math.round(p * 100)}%`;
  }

  function interruptedSessionCard() {
    if (!S.interrupted) return '';
    const session = S.interrupted;
    const completed = session.results ? session.results.length : 0;
    const label = session.mode === 'exam' ? 'Mock exam' : 'Practice session';
    return `<section class="card interrupted-session" aria-label="Interrupted session">
      <div><span class="chip close">Session saved</span><h2>${label} in progress</h2>
        <p>${session.i + 1} of ${session.items.length} questions · ${completed} responses recorded. Resume where you left off.</p></div>
      <div class="row"><button class="btn primary" data-act="resume-session">Resume session</button><button class="btn quiet" data-act="discard-session">Discard</button></div>
    </section>`;
  }

  function domainBars(r) {
    return r.domains.map((d) => `
      <div class="dom">
        <div class="dom-head"><strong>${esc(d.name)}</strong><span>${pct(d.score)} &middot; about ${Math.round(d.weight * 100)}% of the exam</span></div>
        <div class="meter" role="img" aria-label="${esc(d.name)}: ${pct(d.score)}, likely between ${pct(d.low)} and ${pct(d.high)}">
          <div class="fill" style="width:${(d.score * 100).toFixed(1)}%"></div>
          <div class="whisk" style="left:${(d.low * 100).toFixed(1)}%;width:${Math.max((d.high - d.low) * 100, 0.8).toFixed(1)}%"></div>
          <div class="tick" style="left:${r.pass_mark * 100}%"></div>
        </div>
      </div>`).join('') + `
      <div class="legend"><span><i style="background:var(--teal)"></i>Estimated score</span><span><i style="background:color-mix(in srgb,var(--ink) 38%,transparent)"></i>Likely range</span><span><i style="background:var(--clay)"></i>Pass line</span></div>`;
  }

  function topicMap(r) {
    const cols = r.domains.map((d) => {
      const tiles = r.topics.filter((t) => t.domain === d.id).map((t) => {
        const dots = [0, 1, 2, 3].map((i) => `<i class="${t.coverage * 4 > i + 0.01 ? 'on' : ''}"></i>`).join('');
        const thin = t.coverage < 0.5;
        const evidence = thin ? 'Early evidence' : t.coverage < 1 ? 'Building evidence' : 'Solid evidence';
        return `
          <button class="tile ${thin ? 'thin' : ''}" data-act="start-topic" data-topic="${esc(t.id)}"
                  style="background:${tileColor(t.score)}"
                  aria-label="${esc(t.name)}: ${pct(t.score)}, ${evidence}; based on ${t.answered} answers. Practise this topic." title="${evidence}; ${t.answered} answers">
            <span class="tn">${esc(t.name)}</span>
            <span class="tp">${pct(t.score)}</span>
            <span class="evidence">${evidence} · ${t.answered} answers</span>
            <span class="dots" title="Evidence: ${t.answered} answers">${dots}</span>
          </button>`;
      }).join('');
      return `<div><h3>${esc(d.name)} <span class="muted">&middot; ${pct(d.score)}</span></h3><div class="tiles">${tiles}</div></div>`;
    }).join('');
    return `<div class="tmap-cols">${cols}</div><p class="muted" style="margin-top:14px;font-size:.84rem">Colour and score show estimated mastery; text and dots show how much evidence supports the estimate. Early estimates are uncertain. Solid evidence means four or more recent, weighted answers. Select a topic to practise it.</p>`;
  }

  function activityStrip(history) {
    if (!history.length) return '<p class="muted">Your recent practice activity will appear here.</p>';
    const start = Math.max(0, history.length - 7);
    const activity = history.slice(start).map((entry, offset) => ({
      ...entry,
      count: entry.activity ?? Math.max(0, entry.answered - (history[start + offset - 1]?.answered || 0)),
    }));
    const max = Math.max(...activity.map((day) => day.count), 1);
    return `<div class="activity" role="list" aria-label="Recent study days">${activity.map((day) => {
      const [, month, date] = day.date.split('-');
      const height = Math.max(8, Math.round(day.count / max * 40));
      return `<div class="activity-day" role="listitem" aria-label="${day.count} answers on ${day.date}" title="${day.count} answers · ${day.date}">
        <span class="activity-count">${day.count}</span><i style="height:${height}px"></i><small>${date}/${month}</small>
      </div>`;
    }).join('')}</div>`;
  }

  function learningInsights(insights) {
    const accuracy = (value) => value === null ? 'Not enough data' : pct(value);
    const newSet = insights.new_questions;
    const repeats = insights.repeat_questions;
    const sure = insights.confidence.sure;
    const guess = insights.confidence.guess;
    return `<section class="card learning-insights" aria-labelledby="h-insights">
      <h2 id="h-insights">What your answers show</h2>
      <div class="insight-grid">
        <div><strong>New questions</strong><b>${accuracy(newSet.accuracy)}</b><span>${newSet.correct}/${newSet.total} correct first attempts</span></div>
        <div><strong>Repeat attempts</strong><b>${accuracy(repeats.accuracy)}</b><span>${repeats.correct}/${repeats.total} correct repeats</span></div>
        <div><strong>When you're sure</strong><b>${accuracy(sure.accuracy)}</b><span>${sure.correct}/${sure.total} confident answers correct</span></div>
        <div><strong>When guessing</strong><b>${accuracy(guess.accuracy)}</b><span>${guess.correct}/${guess.total} guesses correct</span></div>
      </div>
      <p class="muted">New-question accuracy better reflects recall than repeats. Confidence is useful when compared with correctness; a small sample can swing these percentages.</p>
    </section>`;
  }

  function renderLearningPath() {
    const topicMeta = new Map(S.meta.domains.flatMap((domain) =>
      domain.topics.map((topic) => [topic.id, { ...topic, domainName: domain.name, weight: domain.weight / domain.topics.length }])));
    const initialOrder = new Map(S.meta.domains.flatMap((domain) =>
      domain.topics.map((topic, index) => [topic.id, S.meta.domains.indexOf(domain) * 100 + index])));
    const topics = S.report.topics.map((topic) => {
      const meta = topicMeta.get(topic.id);
      const priority = meta.weight * (1 - topic.score) * (1 + 0.65 * (1 - topic.coverage));
      const evidence = topic.answered === 0 ? 'Not practised'
        : topic.coverage < 0.5 ? 'Early evidence'
          : topic.coverage < 1 ? 'Building confidence' : 'Solid evidence';
      return { ...topic, ...meta, priority, evidence, initialOrder: initialOrder.get(topic.id) };
    }).sort((a, b) => S.report.overall.answered > 0
      ? b.priority - a.priority || a.initialOrder - b.initialOrder
      : a.initialOrder - b.initialOrder);
    const steps = topics.map((topic, index) => `
      <li class="path-step">
        <span class="path-number">${String(index + 1).padStart(2, '0')}</span>
        <div class="path-topic">
          <span class="path-domain">${esc(topic.domainName)}</span>
          <strong>${esc(topic.name)}</strong>
          <div class="path-evidence"><span>${topic.answered ? `${topic.answered} answer${topic.answered === 1 ? '' : 's'}` : 'Ready when you are'}</span><span>${topic.evidence}</span></div>
          <div class="path-meter" role="img" aria-label="${esc(topic.name)} estimated mastery ${pct(topic.score)}"><i style="width:${Math.round(topic.score * 100)}%"></i></div>
        </div>
        <span class="path-score">${pct(topic.score)}</span>
        <button class="btn path-action" data-act="start-topic" data-topic="${esc(topic.id)}">Practise</button>
      </li>`).join('');
    const practiced = topics.filter((topic) => topic.answered > 0).length;
    return `
      <header class="page-heading">
        <span class="eyebrow"><i></i> A route through the exam</span>
        <h1>Your learning path.</h1>
        <p>This path adapts to your practice. Topics with the biggest readiness gaps and least evidence rise to the top.</p>
      </header>
      <section class="card path-card" aria-labelledby="learning-path-title">
        <div class="path-heading">
          <div><span class="eyebrow">Recommended next steps</span><h2 id="learning-path-title">Study in priority order</h2></div>
          <span class="path-count">${practiced} of ${topics.length} topics practised</span>
        </div>
        <ol class="path-list">${steps}</ol>
        <p class="path-footnote">Order is estimated from exam weighting, topic performance and evidence coverage. It updates as you answer questions.</p>
      </section>
      <section class="architecture-section" aria-labelledby="architecture-title">
        <header class="page-heading">
          <span class="eyebrow"><i></i> Azure architecture concept</span>
          <h2 id="architecture-title">Where do load balancing and caching fit?</h2>
          <p>A simple web-app pattern: distribute incoming requests, serve them from healthy app instances, and avoid repeating expensive data reads.</p>
        </header>
        <div class="card architecture-card">
          <div class="architecture-flow" role="img" aria-label="Web users send requests through Azure Load Balancer to healthy application instances. The application checks an in-memory cache first and reads the database when data is not cached.">
            <div class="architecture-node">
              <span class="architecture-icon">${icon('users')}</span>
              <strong>Web users</strong>
              <span>Requests arrive</span>
            </div>
            <span class="architecture-link" aria-hidden="true"></span>
            <div class="architecture-node load-balancer">
              <span class="architecture-icon">${icon('balance')}</span>
              <strong>Azure Load Balancer</strong>
              <span>Spreads network traffic across healthy instances</span>
              <small>Layer 4 · TCP / UDP</small>
            </div>
            <span class="architecture-link" aria-hidden="true"></span>
            <div class="architecture-node">
              <span class="architecture-icon">${icon('server')}</span>
              <strong>Application instances</strong>
              <span>Run the web app; scale out as demand grows</span>
            </div>
          </div>
          <div class="architecture-dataflow">
            <div class="architecture-app-link"><span></span><small>checks for frequently used data</small></div>
            <div class="architecture-data-nodes">
              <article class="architecture-node cache-node">
                <span class="architecture-icon">${icon('cache')}</span>
                <strong>In-memory cache</strong>
                <span>Fast answers for data used often</span>
                <small>Cache hit → return data quickly</small>
              </article>
              <div class="cache-miss"><span>On cache miss</span><i aria-hidden="true"></i></div>
              <article class="architecture-node database-node">
                <span class="architecture-icon">${icon('database')}</span>
                <strong>Database</strong>
                <span>Durable source of truth</span>
                <small>Read data, then refresh the cache</small>
              </article>
            </div>
          </div>
          <p class="architecture-note"><strong>Key idea:</strong> the load balancer distributes traffic; the cache reduces repeated database reads. They solve different problems and are optional design choices, not required parts of every Azure app.</p>
          <p class="architecture-exam-note"><strong>Exam distinction:</strong> Azure Load Balancer handles TCP/UDP at Layer 4. Application Gateway handles web traffic at Layer 7 and can provide a web application firewall.</p>
          <details class="architecture-scenario">
            <summary>Scenario: a product page slows down during a traffic spike. What helps?</summary>
            <p>The load balancer spreads incoming requests across healthy app instances so one server is not doing all the work.</p>
            <p>The app can check its cache for frequently requested product details first. If the item is not cached, it reads the database and can refresh the cache for the next request.</p>
          </details>
        </div>
      </section>`;
  }

  function winsList(r) {
    if (!r.wins.length) return '<p class="muted">Nothing stands out. Keep your strong topics fresh with a mixed review.</p>';
    return r.wins.map((w, i) => `
      <div class="win">
        <div class="num">${i + 1}</div>
        <div>
          <strong>${esc(w.name)}</strong>
          <p>${esc(w.reason)}</p>
          <button class="btn" data-act="start-topic" data-topic="${esc(w.topic)}">Practise ${esc(w.name)}</button>
        </div>
      </div>`).join('');
  }

  function renderDashboard() {
    const r = S.report; const o = r.overall;
    if (o.answered === 0) {
      const blueprint = S.meta.domains.map((domain, index) => `
        <li class="blueprint-row">
          <span class="blueprint-index">${String(index + 1).padStart(2, '0')}</span>
          <div class="blueprint-detail">
            <strong>${esc(domain.name)}</strong>
            <span>${domain.topics.length} topics to explore</span>
          </div>
          <span class="blueprint-weight">${Math.round(domain.weight * 100)}%</span>
          <i class="blueprint-bar" style="--weight:${Math.round(domain.weight * 100)}%"></i>
        </li>`).join('');
      return `
        ${interruptedSessionCard()}
        <section class="welcome">
          <div class="welcome-copy">
            <span class="eyebrow"><i></i> AZ-900 exam preparation</span>
            <h1>Get ready for your next step.</h1>
            <p>Practice original questions, see which topics need more attention, and build a study plan that fits your exam date.</p>
            <div class="welcome-actions">
              <button class="btn primary" data-act="start-adaptive">Start practising ${icon('arrow')}</button>
              <button class="btn quiet" data-act="demo">Try the demo</button>
              <button class="btn quiet" data-act="import">Import a backup</button>
              <input id="import-file" type="file" accept="application/json,.json" hidden>
            </div>
            <div class="welcome-note">${icon('check')} Original questions · progress saved on this device</div>
          </div>
          <aside class="blueprint-card" aria-label="AZ-900 exam blueprint">
            <div class="blueprint-head">
              <div><span class="eyebrow">A quick overview</span><h2>Exam blueprint</h2></div>
              <span class="blueprint-count">3 domains</span>
            </div>
            <div class="blueprint-total"><strong>${S.meta.total_questions}</strong><span>original practice questions<br>across the exam domains</span></div>
            <ol class="blueprint-list">${blueprint}</ol>
            <div class="blueprint-foot"><span>Weighted like the AZ-900 skills outline</span>${icon('arrow')}</div>
          </aside>
        </section>
        <section class="welcome-features" aria-label="How the tracker helps">
          <article><span class="feature-icon">${icon('chart')}</span><div><h2>Track your readiness</h2><p>See your progress by exam domain and topic.</p></div></article>
          <article><span class="feature-icon">${icon('target')}</span><div><h2>Focus your practice</h2><p>Spend time on the subjects that need it.</p></div></article>
          <article><span class="feature-icon">${icon('calendar')}</span><div><h2>Plan your study</h2><p>Turn your exam date into a realistic schedule.</p></div></article>
        </section>`;
    }
    const reliable = r.topics.filter((t) => t.coverage >= 1).length;
    const lead = o.status === 'start'
      ? 'Early days: this estimate is rough. Keep answering and it will sharpen.'
      : `Likely range ${pct(o.low)} to ${pct(o.high)}. On today's evidence, your chance of reaching the ${pct(r.pass_mark)} pass line is ${passLikelihood(o.p_pass)}.`;
    const mis = r.misconceptions.length
      ? `<div class="callout"><strong>Confident but wrong.</strong> In the last 14 days you were sure, then wrong, in: ${r.misconceptions.map((m) => `${esc(m.name)} (${m.count})`).join(', ')}. These misconceptions are worth fixing first.</div>`
      : '';
    return `
      <div class="card hero">
        ${gaugeSvg(o, r.pass_mark)}
        <div>
          <span class="chip ${esc(o.status)}">${esc(o.status_label)}</span>
          <h1 style="margin-top:10px">Your AZ-900 readiness</h1>
          <p>${lead}</p>
          <div class="stats">
            <div><b>${o.answered}</b><span>answers logged</span></div>
            <div><b>${o.unique_seen}/${r.total_questions}</b><span>questions seen</span></div>
            <div><b>${reliable}/${r.topics.length}</b><span>topics with solid evidence</span></div>
          </div>
          <div class="row" style="margin-top:16px">
            <button class="btn primary" data-act="start-adaptive">Smart review (10)</button>
            <button class="btn" data-act="start-exam">Mock exam (40)</button>
          </div>
          <div class="next-step">
            <div><small>Recommended next step</small><strong>${r.wins.length ? esc(r.wins[0].name) : 'Keep your knowledge fresh'}</strong>
              <span>${r.wins.length ? esc(r.wins[0].reason) : 'Run a mixed smart review to reinforce your strongest topics.'}</span></div>
            <button class="btn" data-act="${r.wins.length ? 'start-topic' : 'start-adaptive'}" ${r.wins.length ? `data-topic="${esc(r.wins[0].topic)}"` : ''}>${r.wins.length ? 'Practise this topic' : 'Start review'}</button>
          </div>
        </div>
      </div>

      ${interruptedSessionCard()}
      <div class="grid two top-align" style="margin-top:16px">
        <div class="grid">
          <section class="card" aria-labelledby="h-dom"><h2 id="h-dom">By exam domain</h2>${domainBars(r)}</section>
          <section class="card" aria-labelledby="h-trend"><h2 id="h-trend">Trend</h2>${sparkSvg(r.history, r.pass_mark)}
            <p class="muted" style="font-size:.84rem;margin-top:10px">Older answers count for less (they fade with a 10-day half-life), lucky guesses count for half, and confident mistakes count extra.</p>
            <h3 class="activity-title">Recent study days</h3>${activityStrip(r.history)}
          </section>
        </div>
        <section class="card" aria-labelledby="h-win"><h2 id="h-win">Biggest wins next</h2>${winsList(r)}${mis ? `<div style="margin-top:10px">${mis}</div>` : ''}</section>
      </div>

      ${learningInsights(r.insights)}
      <section class="card tmap" style="margin-top:16px" aria-labelledby="h-map"><h2 id="h-map">Topic map</h2>${topicMap(r)}</section>

      <div class="row" style="margin-top:10px">
        <button class="btn quiet" data-act="demo">Load demo data</button>
        <button class="btn quiet" data-act="export">Export my data</button>
        <button class="btn quiet" data-act="import">Import backup</button>
        <input id="import-file" type="file" accept="application/json,.json" hidden>
        <button class="btn quiet" data-act="reset">Reset my data</button>
      </div>`;
  }

  // ---------- practice setup ----------
  function renderPractice() {
    const m = S.meta;
    const saved = savedIds();
    const domainOpts = m.domains.map((d) => `<option value="${esc(d.id)}">${esc(d.name)}</option>`).join('');
    const topicOpts = m.domains.map((d) => `<optgroup label="${esc(d.name)}">${d.topics.map((t) => `<option value="${esc(t.id)}">${esc(t.name)} (${t.questions})</option>`).join('')}</optgroup>`).join('');
    return `
      <header class="page-heading">
        <span class="eyebrow"><i></i> Build your confidence</span>
        <h1>Practice, your way.</h1>
        <p>${m.total_questions} original questions across the three exam domains. Choose a quick review, focus on one topic, or take a full mock exam.</p>
      </header>
      ${interruptedSessionCard()}
      <div class="practice-options card">
        <label for="practice-count">Questions per session</label>
        <select id="practice-count">
          ${[5, 10, 15, 20].map((n) => `<option value="${n}" ${n === 10 ? 'selected' : ''}>${n} questions</option>`).join('')}
        </select>
        <span class="muted">Choose a short session or go deeper. Mock exams always use ${m.exam_size} questions.</span>
      </div>
      <div class="modes">
        <button class="mode" data-act="start-adaptive"><span class="tag">Recommended</span><h3>Smart review</h3><p>Questions picked from your weakest, highest-value topics, plus anything you got wrong or have not seen lately.</p></button>
        <div class="mode"><h3>Mock exam</h3><p>${m.exam_size} questions weighted like the real exam. No feedback until the end, then review every miss.</p>
          <label class="timer-choice"><input id="timed-exam" type="checkbox" checked> Use a 45-minute timer</label>
          <button class="btn" data-act="start-exam">Start mock exam</button></div>
        <div class="mode"><h3>By domain</h3><p>Focus on one of the three exam domains.</p>
          <div class="row"><select id="dom-sel" aria-label="Domain">${domainOpts}</select><button class="btn" data-act="start-domain">Start</button></div></div>
        <div class="mode"><h3>By topic</h3><p>Drill one topic. Numbers show how many questions it has.</p>
          <div class="row"><select id="top-sel" aria-label="Topic">${topicOpts}</select><button class="btn" data-act="start-topic-select">Start</button></div></div>
      </div>
      ${saved.length ? `<section class="card saved-panel"><div><h2>Saved for later</h2><p class="muted">${saved.length} question${saved.length === 1 ? '' : 's'} saved from practice sessions.</p></div>
        <div class="row"><button class="btn primary" data-act="start-saved">Practise saved questions</button><button class="btn quiet" data-act="clear-saved">Clear saved list</button></div></section>` : ''}`;
  }

  // ---------- quiz ----------
  const LETTERS = ['A', 'B', 'C', 'D'];

  function renderQuiz() {
    const Q = S.quiz; const item = Q.items[Q.i]; const done = Q.answered;
    const exam = Q.mode === 'exam';
    const timeExpired = exam && Q.deadline && Date.now() >= Q.deadline;
    const flagged = Boolean(Q.flags && Q.flags[Q.i]);
    const answered = Q.answers && Q.answers[Q.i] && Number.isInteger(Q.answers[Q.i].picked);
    const opts = item.order.map((orig, k) => {
      let cls = 'opt'; let mark = '';
      if (done) {
        if (orig === done.correct_index) { cls += ' right'; mark = '<span class="mk">Correct</span>'; }
        else if (k === Q.picked) { cls += ' wrong'; mark = '<span class="mk">Your answer</span>'; }
      } else if (k === Q.picked) cls += ' sel';
      return `<button class="${cls}" data-act="pick" data-k="${k}" ${done || (timeExpired && exam) ? 'disabled' : ''} aria-pressed="${k === Q.picked}">
        <span class="let">${LETTERS[k]}</span><span>${esc(item.options[orig])}</span>${mark}</button>`;
    }).join('');

    const last = Q.i === Q.items.length - 1;
    let controls = '';
    if (timeExpired) {
      controls = `<div class="row"><p class="timer-expired" role="status">Time is up. Unanswered questions are left blank.</p><button class="btn primary" data-act="finish-exam">Finish exam</button></div>`;
    } else if (done && !exam) {
      controls = '';  // the Next button follows the feedback panel below
    } else if (exam) {
      controls = `
        <div class="exam-controls">
          <button class="btn" data-act="previous-question" ${Q.i === 0 ? 'disabled' : ''}>Previous</button>
          <button class="btn" data-act="toggle-flag" aria-pressed="${flagged}">${flagged ? 'Flagged for review' : 'Flag for review'}</button>
          <span class="muted">${answered ? 'Answer saved on this device' : 'Not answered yet'}</span>
          <button class="btn" data-act="next-question">${last ? 'Review answers' : answered ? 'Save & next' : 'Skip'}</button>
          <button class="btn primary" data-act="finish-exam">Finish exam</button>
        </div>`;
    } else {
      const label = exam ? (last ? 'Finish exam' : 'Next question') : 'Check answer';
      controls = `
        <div class="row">
          <span class="muted" style="font-size:.88rem">How sure are you?</span>
          <div class="seg" role="group" aria-label="Confidence">
            <button data-act="conf" data-v="sure" aria-pressed="${Q.sure}">I'm sure</button>
            <button data-act="conf" data-v="guess" aria-pressed="${!Q.sure}">Just guessing</button>
          </div>
          <button class="btn primary" data-act="${exam ? 'submit-next' : 'submit'}" ${Q.picked === null || Q.busy ? 'disabled' : ''}>${label}</button>
        </div>
        <p class="kbd" style="margin:8px 0 0">Keys: 1-4 to choose, Enter to continue</p>`;
    }

    let feedback = '';
    if (done && !exam) {
      feedback = `
        <div class="feedback ${done.correct ? 'ok' : 'no'}" role="region" aria-label="Feedback">
          <h3 id="feedback-title" tabindex="-1">${done.correct ? 'Correct' : 'Not quite'}</h3>
          ${done.correct ? '' : `<p>${esc(done.why_not)}</p>`}
          <p>${esc(done.explanation)}</p>
          ${S.meta.ai ? `
          <div class="row">
            <button class="btn" data-act="explain">Explain it simply</button>
            <div class="seg" role="group" aria-label="Explanation language">
              <button data-act="lang" data-v="en" aria-pressed="${S.lang === 'en'}">English</button>
              <button data-act="lang" data-v="sw" aria-pressed="${S.lang === 'sw'}">Kiswahili</button>
            </div>
          </div>
          <div id="ai-out" aria-live="polite"></div>` : '<p class="muted" style="font-size:.84rem;margin:6px 0 0">Tip: set ANTHROPIC_API_KEY on the server to unlock plain-language AI explanations with everyday examples, in English or Kiswahili.</p>'}
        </div>
        <div style="margin-top:14px"><button class="btn primary" data-act="next">${last ? 'See results' : 'Next question'}</button></div>`;
    }

    const isSaved = savedIds().includes(item.id);
    const timerLabel = exam && Q.deadline
      ? `<span class="exam-clock" id="exam-timer" role="timer" aria-label="Time remaining">${formatTime(Math.max(0, Math.ceil((Q.deadline - Date.now()) / 1000)))}</span>`
      : '';
    return `
      <div class="card">
        <div class="qhead">
          <span class="qtag">${exam ? 'Mock exam' : Q.mode === 'saved' ? 'Saved review' : Q.mode === 'retry' ? 'Retry missed' : 'Practice'} &middot; Question ${Q.i + 1} of ${Q.items.length} &middot; ${esc(item.topic_name)}</span>
          <div class="bar" aria-hidden="true"><i style="width:${(Q.i / Q.items.length) * 100}%"></i></div>
          ${timerLabel}
          ${exam ? `<span id="timer-announcement" class="sr-only" aria-live="polite"></span>` : ''}
          <button class="btn quiet save-question" data-act="toggle-save" data-question="${esc(item.id)}">${isSaved ? 'Saved' : 'Save for later'}</button>
          <button class="btn quiet" data-act="quit">Quit</button>
        </div>
        <h2 class="qtext" id="question-title" tabindex="-1">${esc(item.q)}</h2>
        ${exam ? `<section class="exam-navigation" aria-label="Exam question navigation">
          <div class="exam-nav-summary" tabindex="-1"><strong>Question review</strong><span>${Q.answers.filter((answer) => answer && Number.isInteger(answer.picked)).length} answered · ${Q.flags.filter(Boolean).length} flagged · ${Q.items.length - Q.answers.filter((answer) => answer && Number.isInteger(answer.picked)).length} unanswered</span></div>
          <div class="exam-nav-grid">${Q.items.map((question, index) => {
            const answer = Q.answers[index];
            const state = answer && Number.isInteger(answer.picked) ? 'answered' : 'unanswered';
            return `<button class="exam-nav-item ${state} ${Q.flags[index] ? 'flagged' : ''} ${index === Q.i ? 'current' : ''}"
              data-act="go-question" data-index="${index}" aria-current="${index === Q.i ? 'step' : 'false'}"
              aria-label="Question ${index + 1}, ${state}${Q.flags[index] ? ', flagged for review' : ''}">${index + 1}</button>`;
          }).join('')}</div>
        </section>` : ''}
        <div class="opts">${opts}</div>
        ${Q.error ? `<p id="quiz-error" class="form-error" role="alert" tabindex="-1">${esc(Q.error)}</p>` : ''}
        <div style="margin-top:16px">${controls}</div>
        ${feedback}
      </div>`;
  }

  function formatTime(seconds) {
    const mins = Math.floor(seconds / 60);
    return `${String(mins).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
  }

  function startExamClock() {
    clearInterval(S.timer);
    if (!S.quiz || !S.quiz.deadline) return;
    const tick = () => {
      const left = Math.max(0, Math.ceil((S.quiz.deadline - Date.now()) / 1000));
      const el = $('#exam-timer');
      if (el) {
        el.textContent = formatTime(left);
        el.classList.toggle('urgent', left <= 300);
        el.setAttribute('aria-label', `${Math.ceil(left / 60)} minutes remaining`);
      }
      const announce = $('#timer-announcement');
      const threshold = left <= 60 ? '1 minute remaining' : left <= 300 ? '5 minutes remaining' : null;
      if (threshold && threshold !== S.lastTimerAnnouncement && announce) {
        announce.textContent = threshold;
        S.lastTimerAnnouncement = threshold;
      }
      if (!left) {
        clearInterval(S.timer);
        S.timer = null;
        render();
      }
    };
    tick();
    S.timer = setInterval(tick, 1000);
  }

  async function submitAnswer() {
    const Q = S.quiz; const item = Q.items[Q.i];
    if (Q.picked === null || Q.busy) return null;
    if (Q.mode === 'exam') {
      Q.answers[Q.i] = { picked: Q.picked, sure: Q.sure };
      saveSession();
      return { saved: true };
    }
    Q.busy = true;
    const orig = item.order[Q.picked];
    try {
      const res = await api('/api/answer', {
        method: 'POST',
        body: JSON.stringify({
          learner, question_id: item.id, choice: orig, confidence: Q.sure ? 'sure' : 'guess',
          mode: Q.mode === 'retry' ? 'adaptive' : Q.mode, seconds: Math.round((Date.now() - Q.t0) / 100) / 10,
        }),
      });
      Q.results.push({ item, chosen: orig, sure: Q.sure, ...res });
      Q.answered = res;
      Q.error = null;
      Q.answers[Q.i] = { picked: Q.picked, sure: Q.sure };
      saveSession();
      return res;
    } finally { Q.busy = false; }
  }

  async function advance() {
    const Q = S.quiz;
    if (Q.i >= Q.items.length - 1) { await finishQuiz(); return; }
    Q.i += 1; Q.picked = null; Q.answered = null; Q.t0 = Date.now();
    Q.sure = true;
    saveSession();
    render();
    window.scrollTo({ top: 0 });
    focusQuizQuestion();
  }

  function focusQuizQuestion() {
    const title = $('#question-title');
    if (title) title.focus({ preventScroll: true });
  }

  function moveExamQuestion(index) {
    const Q = S.quiz;
    if (!Q || Q.mode !== 'exam' || index < 0 || index >= Q.items.length) return;
    Q.answers[Q.i] = Q.picked === null ? null : { picked: Q.picked, sure: Q.sure };
    Q.i = index;
    const answer = Q.answers[index];
    Q.picked = answer ? answer.picked : null;
    Q.sure = answer ? answer.sure !== false : true;
    Q.answered = null;
    Q.t0 = Date.now();
    saveSession();
    render();
    focusQuizQuestion();
  }

  async function submitExam() {
    const Q = S.quiz;
    Q.answers[Q.i] = Q.picked === null ? null : { picked: Q.picked, sure: Q.sure };
    const unanswered = Q.answers.filter((answer) => !answer || !Number.isInteger(answer.picked)).length;
    const confirmed = window.confirm(
      `Finish this mock exam? ${Q.items.length - unanswered} answered, ${unanswered} unanswered${unanswered ? '. Unanswered questions will be left blank' : ''}.`
    );
    if (!confirmed) return;
    saveSession();
    Q.busy = true;
    render();
    try {
      for (let i = 0; i < Q.items.length; i++) {
        const answer = Q.answers[i];
        if (!answer || !Number.isInteger(answer.picked) || answer.persisted) continue;
        const item = Q.items[i];
        const chosen = item.order[answer.picked];
        const result = await api('/api/answer', {
          method: 'POST',
          body: JSON.stringify({
            learner, question_id: item.id, choice: chosen, confidence: answer.sure ? 'sure' : 'guess',
            mode: 'exam', seconds: 0,
          }),
        });
        Q.results[i] = { item, chosen, sure: answer.sure, ...result };
        answer.persisted = true;
        Q.error = null;
        saveSession();
      }
      Q.results = Q.results.filter(Boolean);
      Q.busy = false;
      await finishQuiz();
    } catch (error) {
      Q.busy = false;
      Q.error = `Could not submit the exam: ${error.message}. Your answers remain saved here. Try finishing again.`;
      saveSession();
      render();
      const errorEl = $('#quiz-error');
      if (errorEl) errorEl.focus();
    }
  }

  async function finishQuiz() {
    const Q = S.quiz;
    clearInterval(S.timer); S.timer = null;
    try { S.report = await api(`/api/readiness?learner=${learner}`); } catch (e) { toast(`Could not refresh readiness: ${e.message}`); }
    Q.after = S.report ? S.report.overall.score : null;
    clearSavedSession();
    S.plan = null;
    S.view = 'results';
    render();
    window.scrollTo({ top: 0 });
  }

  function renderResults() {
    const Q = S.quiz; const R = Q.results;
    const right = R.filter((x) => x.correct).length;
    const byDom = {};
    R.forEach((x) => { const d = byDom[x.domain] || (byDom[x.domain] = { n: 0, ok: 0 }); d.n += 1; d.ok += x.correct ? 1 : 0; });
    const domName = (id) => (S.meta.domains.find((d) => d.id === id) || { name: id }).name;
    const delta = Q.after !== null && Q.before !== null ? Math.round((Q.after - Q.before) * 100) : null;
    const missed = R.filter((x) => !x.correct);
    const blankCount = Q.mode === 'exam' ? Q.items.length - R.length : 0;
    const flagged = Q.mode === 'exam' ? Q.flags.map((value, index) => value ? index : -1).filter((index) => index >= 0) : [];
    return `
      <h1>${Q.mode === 'exam' ? 'Mock exam complete' : 'Session complete'}</h1>
      <p class="muted">${Q.mode === 'exam' ? 'Your mock is complete. Review the domain breakdown and revisit missed questions before your next attempt.' : 'A little review now makes this practice session more useful.'}</p>
      ${blankCount ? `<p class="callout results-blank">${blankCount} question${blankCount === 1 ? ' was' : 's were'} left unanswered and were not counted as incorrect.</p>` : ''}
      <div class="res-grid">
        <div class="card"><b>${right}/${R.length}</b><span class="muted">correct (${pct(R.length ? right / R.length : 0)})</span></div>
        <div class="card"><b>${delta === null ? '--' : `${delta > 0 ? '+' : ''}${delta} pts`}</b><span class="muted">change in your estimated exam score</span></div>
        ${Object.entries(byDom).map(([d, v]) => `<div class="card"><b>${v.ok}/${v.n}</b><span class="muted">${esc(domName(d))}</span></div>`).join('')}
      </div>
      <div class="row" style="margin-bottom:18px">
        <button class="btn primary" data-act="go-dashboard">See my dashboard</button>
        <button class="btn" data-act="start-adaptive">Another smart review</button>
        ${missed.length ? `<button class="btn" data-act="retry-missed">Retry ${missed.length} missed</button>` : ''}
      </div>
      <section class="card">
        <h2>${missed.length ? `Review the ${missed.length} you missed` : 'Clean sheet'}</h2>
        ${missed.length ? missed.map((x) => `
          <div class="missed">
            <strong>${esc(x.item.q)}</strong>
            <div class="a">You chose: ${esc(x.item.options[x.chosen])}${x.sure ? ' (you were sure)' : ''}</div>
            <div class="a">Correct: <strong style="color:var(--ink)">${esc(x.item.options[x.correct_index])}</strong></div>
            <p style="margin:6px 0 0">${esc(x.why_not)} ${esc(x.explanation)}</p>
            <button class="btn quiet" data-act="toggle-save" data-question="${esc(x.item.id)}">${savedIds().includes(x.item.id) ? 'Saved for later' : 'Save question for later'}</button>
          </div>`).join('') : '<p class="muted">Every answer was right. Your dashboard has the next best topic to stretch.</p>'}
      </section>
      ${flagged.length ? `<section class="card">
        <h2>Flagged for review</h2>
        ${flagged.map((index) => {
          const item = Q.items[index];
          const answer = Q.answers[index];
          return `<div class="missed">
            <strong>Question ${index + 1}: ${esc(item.q)}</strong>
            <p class="muted">${answer && Number.isInteger(answer.picked) ? `Your answer: ${esc(item.options[item.order[answer.picked]])}` : 'Left unanswered'}</p>
          </div>`;
        }).join('')}
      </section>` : ''}`;
  }

  // ---------- study plan ----------
  const WD = [['Mon', 0], ['Tue', 1], ['Wed', 2], ['Thu', 3], ['Fri', 4], ['Sat', 5], ['Sun', 6]];
  const TYPE_LABEL = { learn: 'Learn', practice: 'Practise', review: 'Review', mock: 'Mock exam' };
  const isoToday = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; };
  const fmtDay = (iso) => new Date(`${iso}T12:00:00`).toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' });
  const hm = (m) => (m >= 60 ? `${Math.floor(m / 60)}h${m % 60 ? ` ${m % 60}m` : ''}` : `${m}m`);
  const planBlockKey = (exam, date, block, index) =>
    `${exam}-${date}-${index}-${encodeURIComponent(`${block.type}:${block.topic || block.name}`)}`;
  const shiftDate = (date, amount) => {
    const d = new Date(`${date}T12:00:00`);
    d.setDate(d.getDate() + amount);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  };
  const daysBetween = (start, end) => Math.round((Date.parse(`${end}T00:00:00Z`) - Date.parse(`${start}T00:00:00Z`)) / 86400000);

  function loadPrefs() {
    try { const p = JSON.parse(store.get('az900.plan') || 'null'); if (p && p.exam) return p; } catch (_) { /* ignore */ }
    return { exam: '', hours: 6, days: [0, 1, 2, 3, 4, 5] };
  }

  function renderPlan() {
    const P = S.planPrefs; const plan = S.plan;
    const dayBoxes = WD.map(([n, i]) => `<label class="chk"><input type="checkbox" data-wd="${i}" ${P.days.includes(i) ? 'checked' : ''}> ${n}</label>`).join('');
    const form = `
      <form class="card planform" id="plan-form">
        <label>Exam date <input type="date" id="p-exam" value="${esc(P.exam)}" min="${isoToday()}" required></label>
        <label>Hours per week <input type="number" id="p-hours" value="${P.hours}" min="0.5" max="40" step="0.5" required></label>
        <fieldset><legend>Study days</legend><div class="row">${dayBoxes}</div></fieldset>
        <button class="btn primary" type="submit">${plan ? 'Update plan' : 'Build my plan'}</button>
      </form>`;
    if (!plan) {
      return `<header class="page-heading">
          <span class="eyebrow"><i></i> Make time for what matters</span>
          <h1>A study plan that fits.</h1>
          <p>Set your exam date and weekly study time. Your plan will focus on high-impact topics, include a mock exam, and leave room to review.</p>
        </header>
        ${form}${S.planError ? `<div class="callout" style="margin-top:14px">${esc(S.planError)}</div>` : ''}`;
    }
    const checks = planChecks();
    const dayMap = new Map();
    plan.days.forEach((source) => source.blocks.forEach((block, index) => {
      const key = planBlockKey(plan.exam, source.date, block, index);
      const state = checks[key];
      const saved = state && typeof state === 'object' ? state : {};
      const effectiveDate = typeof saved.date === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(saved.date)
        && daysBetween(saved.date, plan.exam) > 0 ? saved.date : source.date;
      let day = dayMap.get(effectiveDate);
      if (!day) {
        day = { ...source, date: effectiveDate, days_to_exam: daysBetween(effectiveDate, plan.exam), minutes: 0, blocks: [] };
        dayMap.set(effectiveDate, day);
      }
      day.blocks.push({ block, key, sourceDate: source.date, effectiveDate, status: saved.status || (state === true ? 'done' : '') });
      day.minutes += block.minutes;
    }));
    const displayDays = [...dayMap.values()].sort((a, b) => a.date.localeCompare(b.date));
    const weeks = [];
    displayDays.forEach((d) => {
      const dt = new Date(`${d.date}T12:00:00`); const mon = new Date(dt); mon.setDate(dt.getDate() - ((dt.getDay() + 6) % 7));
      const key = mon.toISOString().slice(0, 10);
      let w = weeks.find((x) => x.key === key); if (!w) { w = { key, days: [] }; weeks.push(w); }
      w.days.push(d);
    });
    const maxFocus = Math.max(...plan.focus.map((f) => f.minutes), 1);
    const allBlocks = plan.days.flatMap((day) => day.blocks.map((block, index) => ({
      key: planBlockKey(plan.exam, day.date, block, index),
      state: checks[planBlockKey(plan.exam, day.date, block, index)],
    })));
    const blockCount = allBlocks.length;
    const doneCount = allBlocks.filter(({ state }) => state && (state.status === 'done' || state === true)).length;
    const skippedCount = allBlocks.filter(({ state }) => state && state.status === 'skipped').length;
    const days = weeks.map((w, wi) => {
      const weekBlocks = w.days.flatMap((day) => day.blocks);
      const weekDone = weekBlocks.filter((block) => block.status === 'done').length;
      return `
      <h3 class="wk">Week ${wi + 1} <span class="muted">&middot; ${weekDone}/${weekBlocks.length} blocks done &middot; ${hm(w.days.reduce((s, d) => s + d.minutes, 0))}</span></h3>
      ${w.days.map((d) => `
        <div class="pday ${d.date === plan.today ? 'today' : ''}">
          <div class="pd-head"><strong>${fmtDay(d.date)}</strong><span class="muted">${d.days_to_exam} day${d.days_to_exam === 1 ? '' : 's'} to exam &middot; ${hm(d.minutes)}</span></div>
          ${d.blocks.map((entry) => {
            const { block: b, key, sourceDate, effectiveDate, status } = entry;
            const done = status === 'done';
            const skipped = status === 'skipped';
            const canMove = daysBetween(effectiveDate, plan.exam) > 1;
            return `<div class="pblock ${esc(b.type)} ${done ? 'completed' : ''} ${skipped ? 'skipped' : ''}">
              <span class="pt">${TYPE_LABEL[b.type]}</span>
              <span class="pn"><strong>${esc(b.name)}</strong><small>${esc(b.note)}${sourceDate !== effectiveDate ? ` Moved from ${fmtDay(sourceDate)}.` : ''}</small></span>
              <span class="pm">${b.minutes}m</span>
              <div class="pblock-actions">
                ${b.type === 'mock' ? '<button class="btn quiet" data-act="start-exam">Start</button>' : `<button class="btn quiet" data-act="start-topic" data-topic="${esc(b.topic)}">Drill</button>`}
                <button class="btn quiet completion-toggle" data-act="set-plan-status" data-check="${esc(key)}" data-status="${done ? 'pending' : 'done'}" aria-pressed="${done}">${done ? 'Completed · Undo' : 'Mark done'}</button>
                <button class="btn quiet completion-toggle" data-act="set-plan-status" data-check="${esc(key)}" data-status="${skipped ? 'pending' : 'skipped'}" aria-pressed="${skipped}">${skipped ? 'Skipped · Undo' : 'Skip'}</button>
                ${canMove ? `<button class="btn quiet" data-act="move-plan-block" data-check="${esc(key)}" data-date="${esc(effectiveDate)}" data-origin-date="${esc(sourceDate)}" data-direction="1">Move +1 day</button>` : ''}
                ${sourceDate !== effectiveDate ? `<button class="btn quiet" data-act="move-plan-block" data-check="${esc(key)}" data-date="${esc(effectiveDate)}" data-origin-date="${esc(sourceDate)}" data-direction="-1">Move back</button>` : ''}
              </div>
            </div>`;
          }).join('')}
        </div>`).join('')}`;
    }).join('');
    const progress = blockCount ? Math.round(doneCount / blockCount * 100) : 0;
    return `<header class="page-heading">
        <span class="eyebrow"><i></i> Make time for what matters</span>
        <h1>Your study plan.</h1>
        <p>${plan.days_to_exam} days to your exam · ${plan.study_day_count} study days · ${hm(plan.total_minutes)} planned.${S.report && S.report.overall.answered === 0 ? ' Practise a little, then update the plan: it gets sharper with data.' : ''}</p>
      </header>
      ${S.planNotice ? `<div class="callout plan-notice">${esc(S.planNotice)}</div>` : ''}
      ${S.planError ? `<div class="callout plan-error">${esc(S.planError)}</div>` : ''}
      ${plan.warnings.map((w) => `<div class="callout" style="margin-bottom:10px">${esc(w)}</div>`).join('')}
      <section class="card plan-progress" aria-label="Study plan completion">
        <div><strong>Plan progress</strong><span>${doneCount} complete · ${skippedCount} skipped · ${blockCount} total · ${progress}% complete</span></div>
        <div class="meter" role="progressbar" aria-label="Plan progress" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${progress}"><div class="fill" style="width:${progress}%"></div></div>
      </section>
      <div class="grid two top-align">
        <div>${form}
          <section class="card" style="margin-top:16px"><h2>Where the time goes</h2>
            ${plan.focus.map((f) => `<div class="dom"><div class="dom-head"><strong>${esc(f.name)}</strong><span>${hm(f.minutes)} &middot; now ${pct(f.score)}</span></div><div class="meter"><div class="fill" style="width:${(f.minutes / maxFocus * 100).toFixed(1)}%"></div></div></div>`).join('')}
          </section>
        </div>
        <section class="card"><h2>Day by day</h2>${days}</section>
      </div>`;
  }

  async function buildPlan() {
    let { exam, hours, days } = S.planPrefs;
    if ($('#p-exam')) {  // read the form when it is on screen; otherwise rebuild from saved settings
      exam = $('#p-exam').value; hours = parseFloat($('#p-hours').value);
      days = [...document.querySelectorAll('[data-wd]')].filter((c) => c.checked).map((c) => Number(c.dataset.wd));
    }
    try {
      const q = new URLSearchParams({ learner, exam_date: exam, hours_per_week: String(hours), days: days.join(','), today: isoToday() });
      const nextPlan = await api(`/api/plan?${q}`);
      const previousPlan = S.plan || S.previousPlan;
      let preservedProgress = 0;
      let clearedProgress = 0;
      if (previousPlan) {
        const checks = planChecks();
        const oldKeys = previousPlan.days.flatMap((day) => day.blocks.map((block, index) =>
          planBlockKey(previousPlan.exam, day.date, block, index)));
        const newKeys = new Set(nextPlan.days.flatMap((day) => day.blocks.map((block, index) =>
          planBlockKey(nextPlan.exam, day.date, block, index))));
        const oldProgress = oldKeys.filter((key) => checks[key]
          && (checks[key] === true || checks[key].status === 'done' || checks[key].status === 'skipped'));
        const lostProgress = oldProgress.filter((key) => !newKeys.has(key));
        preservedProgress = oldProgress.length - lostProgress.length;
        clearedProgress = lostProgress.length;
        if (lostProgress.length && !window.confirm(
          `This plan changed. Progress on ${oldProgress.length - lostProgress.length} matching blocks will be kept; ${lostProgress.length} completed or skipped block${lostProgress.length === 1 ? '' : 's'} no longer match and will be cleared. Continue?`
        )) {
          S.planPrefs = { exam, hours, days };
          render();
          return;
        }
        if (lostProgress.length) {
          oldProgress.filter((key) => !newKeys.has(key)).forEach((key) => delete checks[key]);
          store.set('az900.planChecks', JSON.stringify(checks));
        }
      }
      S.plan = nextPlan;
      S.previousPlan = nextPlan;
      store.set('az900.planSnapshot', JSON.stringify(nextPlan));
      S.planPrefs = { exam, hours, days };
      store.set('az900.plan', JSON.stringify(S.planPrefs));
      S.planError = null;
      S.planNotice = previousPlan && preservedProgress
        ? `Kept progress on ${preservedProgress} matching block${preservedProgress === 1 ? '' : 's'}${clearedProgress ? `; reset ${clearedProgress} no-longer-matching block${clearedProgress === 1 ? '' : 's'}` : ''}.`
        : null;
    } catch (e) {
      S.planError = e.message;
      S.planPrefs = { exam, hours, days };
    }
    render();
  }

  // ---------- render + routing ----------
  function render() {
    document.querySelectorAll('.nav').forEach((b) => {
      const on = (S.view === 'dashboard' && b.dataset.nav === 'dashboard') || (S.view === 'learn' && b.dataset.nav === 'learn') || (S.view === 'plan' && b.dataset.nav === 'plan') || ((S.view === 'practice' || S.view === 'quiz' || S.view === 'results') && b.dataset.nav === 'practice');
      if (on) b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current');
    });
    if (S.loading) { app.innerHTML = '<p class="muted">Loading&hellip;</p>'; return; }
    if (S.view === 'dashboard') app.innerHTML = S.report ? renderDashboard() : '<p class="muted">Loading&hellip;</p>';
    else if (S.view === 'practice') app.innerHTML = renderPractice();
    else if (S.view === 'quiz') app.innerHTML = renderQuiz();
    else if (S.view === 'results') app.innerHTML = renderResults();
    else if (S.view === 'plan') app.innerHTML = renderPlan();
    else if (S.view === 'learn') app.innerHTML = S.report && S.meta ? renderLearningPath() : '<p class="muted">Loading&hellip;</p>';
  }

  async function loadReport() {
    S.report = await api(`/api/readiness?learner=${learner}`);
  }

  async function go(view) {
    if (view !== 'quiz' && S.view === 'quiz' && S.quiz) {
      saveSession();
      S.interrupted = loadSession();
    }
    if (view !== 'quiz') { clearInterval(S.timer); S.timer = null; }
    S.view = view;
    if (view === 'dashboard' || view === 'learn') {
      try { await loadReport(); } catch (e) { toast(e.message); }
    }
    if (view === 'plan') {
      try { await loadReport(); } catch (_) { /* optional */ }
      if (S.planPrefs.exam && !S.plan) { await buildPlan(); return; }
    }
    render();
    window.scrollTo({ top: 0 });
  }

  function sessionCount() {
    const count = Number($('#practice-count') && $('#practice-count').value);
    return Number.isInteger(count) && count > 0 ? count : 10;
  }

  async function startQuiz(opts) {
    if (S.interrupted && !window.confirm('Starting a new session will replace the in-progress session saved on this device. Continue?')) return;
    S.loading = true; render();
    try {
      const params = new URLSearchParams({ learner, mode: opts.mode, n: String(opts.n || 10) });
      if (opts.domain) params.set('domain', opts.domain);
      if (opts.topic) params.set('topic', opts.topic);
      if (opts.questionIds) opts.questionIds.forEach((id) => params.append('question_ids', id));
      const [quiz, before] = await Promise.all([api(`/api/quiz?${params}`), api(`/api/readiness?learner=${learner}`)]);
      if (!quiz.questions.length) { toast('No questions available for that choice.'); S.loading = false; S.view = 'practice'; render(); return; }
      S.quiz = {
        mode: opts.mode, items: quiz.questions.map((q) => ({ ...q, order: shuffle([0, 1, 2, 3]) })),
        i: 0, picked: null, sure: true, answered: null, results: [], answers: Array(quiz.questions.length).fill(null), flags: Array(quiz.questions.length).fill(false), busy: false,
        before: before.overall.score, after: null, t0: Date.now(),
        deadline: opts.mode === 'exam' && opts.timed !== false ? Date.now() + 45 * 60 * 1000 : null,
      };
      S.interrupted = null;
      S.view = 'quiz';
      saveSession();
    } catch (e) { toast(e.message); S.view = 'practice'; }
    S.loading = false; render();
    if (S.view === 'quiz') startExamClock();
    window.scrollTo({ top: 0 });
  }

  async function retryQuestions(results) {
    S.loading = true; render();
    try {
      const before = await api(`/api/readiness?learner=${learner}`);
      S.quiz = {
        mode: 'retry',
        items: results.map((result) => ({ ...result.item, order: shuffle([0, 1, 2, 3]) })),
        i: 0, picked: null, sure: true, answered: null, results: [], answers: Array(results.length).fill(null), flags: Array(results.length).fill(false), busy: false,
        before: before.overall.score, after: null, t0: Date.now(), deadline: null,
      };
      S.view = 'quiz';
      saveSession();
    } catch (e) { toast(e.message); S.view = 'results'; }
    S.loading = false; render(); window.scrollTo({ top: 0 });
  }

  async function exportData() {
    const data = await api(`/api/learner/${learner}/export`);
    data.saved = savedIds();
    data.plan = S.planPrefs;
    data.planChecks = planChecks();
    data.planSnapshot = S.plan || S.previousPlan;
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `az900-readiness-${isoToday()}.json`;
    link.click();
    URL.revokeObjectURL(url);
    toast('Backup downloaded');
  }

  async function importData(file) {
    let data;
    try { data = JSON.parse(await file.text()); } catch (_) { throw new Error('That file is not valid JSON.'); }
    if (!data || data.format !== 'az900-readiness-tracker' || data.version !== 1 || !Array.isArray(data.attempts)) {
      throw new Error('This is not a supported AZ-900 Readiness Tracker backup.');
    }
    if (!window.confirm(`Import ${data.attempts.length} answers? This replaces the current practice history.`)) return;
    const result = await api(`/api/learner/${learner}/import`, {
      method: 'POST',
      body: JSON.stringify({ version: data.version, attempts: data.attempts }),
    });
    const saved = Array.isArray(data.saved) ? [...new Set(data.saved.filter((id) => typeof id === 'string'))] : [];
    store.set('az900.saved', JSON.stringify(saved));
    if (data.plan && typeof data.plan === 'object'
      && typeof data.plan.exam === 'string'
      && Number.isFinite(data.plan.hours)
      && Array.isArray(data.plan.days)
      && data.plan.days.every((day) => Number.isInteger(day) && day >= 0 && day <= 6)) {
      S.planPrefs = data.plan;
      store.set('az900.plan', JSON.stringify(data.plan));
    }
    if (data.planChecks && typeof data.planChecks === 'object' && !Array.isArray(data.planChecks)) {
      store.set('az900.planChecks', JSON.stringify(data.planChecks));
    }
    if (data.planSnapshot && Array.isArray(data.planSnapshot.days)
      && typeof data.planSnapshot.exam === 'string') {
      S.previousPlan = data.planSnapshot;
      store.set('az900.planSnapshot', JSON.stringify(data.planSnapshot));
    }
    clearSavedSession();
    S.plan = null;
    toast(`Imported ${result.imported} answers`);
    await go('dashboard');
  }

  async function explainNow() {
    const Q = S.quiz; const out = $('#ai-out');
    const last = Q.results[Q.results.length - 1];
    out.innerHTML = '<div class="ai"><small>Thinking&hellip;</small></div>';
    try {
      const r = await api('/api/explain', { method: 'POST', body: JSON.stringify({ question_id: last.item.id, choice: last.chosen, language: S.lang, style: last.correct ? 'exam-tip' : 'simple' }) });
      const label = r.source === 'builtin' ? 'Claude could not be reached, so this is the built-in explanation' : 'Explanation by Claude';
      out.innerHTML = `<div class="ai"><small>${label}</small>${esc(r.text)}</div>`;
    } catch (e) { out.innerHTML = `<div class="ai">${esc(e.message)}</div>`; }
  }

  // ---------- events ----------
  document.addEventListener('click', async (e) => {
    const el = e.target.closest('[data-nav],[data-act]');
    if (!el) return;
    if (el.dataset.nav) { go(el.dataset.nav); return; }
    const act = el.dataset.act; const Q = S.quiz;
    try {
      switch (act) {
        case 'start-adaptive': await startQuiz({ mode: 'adaptive', n: sessionCount() }); break;
        case 'start-exam': await startQuiz({ mode: 'exam', n: S.meta.exam_size, timed: !$('#timed-exam') || $('#timed-exam').checked }); break;
        case 'start-domain': await startQuiz({ mode: 'domain', n: sessionCount(), domain: $('#dom-sel').value }); break;
        case 'start-topic': await startQuiz({ mode: 'topic', n: sessionCount(), topic: el.dataset.topic }); break;
        case 'start-topic-select': await startQuiz({ mode: 'topic', n: sessionCount(), topic: $('#top-sel').value }); break;
        case 'start-saved': {
          const ids = savedIds();
          if (ids.length) await startQuiz({ mode: 'saved', n: Math.min(ids.length, S.meta.exam_size), questionIds: ids });
          break;
        }
        case 'retry-missed': await retryQuestions(Q.results.filter((result) => !result.correct)); break;
        case 'toggle-save': {
          const saved = toggleSaved(el.dataset.question);
          toast(saved ? 'Saved for later' : 'Removed from saved questions');
          render();
          break;
        }
        case 'clear-saved':
          if (window.confirm('Clear all saved questions?')) { store.set('az900.saved', '[]'); render(); }
          break;
        case 'set-plan-status': {
          const checks = planChecks();
          const previous = checks[el.dataset.check];
          const state = previous && typeof previous === 'object' ? previous : {};
          checks[el.dataset.check] = { ...state, status: el.dataset.status };
          store.set('az900.planChecks', JSON.stringify(checks));
          render();
          break;
        }
        case 'move-plan-block': {
          const checks = planChecks();
          const previous = checks[el.dataset.check];
          const state = previous && typeof previous === 'object' ? previous : {};
          const moved = shiftDate(el.dataset.date, Number(el.dataset.direction));
          if (daysBetween(el.dataset.originDate, moved) < 0 || daysBetween(moved, S.plan.exam) <= 0) {
            toast('That block cannot be moved outside the plan dates.');
            break;
          }
          checks[el.dataset.check] = { ...state, date: moved };
          store.set('az900.planChecks', JSON.stringify(checks));
          render();
          break;
        }
        case 'export': await exportData(); break;
        case 'import': $('#import-file').click(); break;
        case 'resume-session': resumeSession(); break;
        case 'discard-session': clearSavedSession(); render(); break;
        case 'pick':
          if (!Q.answered && !(Q.mode === 'exam' && Q.deadline && Date.now() >= Q.deadline)) {
            Q.picked = Number(el.dataset.k);
            if (Q.mode === 'exam') Q.answers[Q.i] = { picked: Q.picked, sure: Q.sure };
            saveSession(); render(); app.querySelector('.opt.sel')?.focus();
          }
          break;
        case 'conf':
          Q.sure = el.dataset.v === 'sure';
          if (Q.mode === 'exam') Q.answers[Q.i] = Q.picked === null ? null : { picked: Q.picked, sure: Q.sure };
          saveSession(); render();
          app.querySelector(`.seg [data-v="${Q.sure ? 'sure' : 'guess'}"]`)?.focus();
          break;
        case 'submit': { const r = await submitAnswer(); if (r) { render(); $('#feedback-title')?.focus(); } break; }
        case 'submit-next': { const r = await submitAnswer(); if (r) await advance(); break; }
        case 'finish-exam': await submitExam(); break;
        case 'next': await advance(); break;
        case 'previous-question': moveExamQuestion(Q.i - 1); break;
        case 'next-question':
          Q.answers[Q.i] = Q.picked === null ? null : { picked: Q.picked, sure: Q.sure };
          if (Q.i < Q.items.length - 1) moveExamQuestion(Q.i + 1);
          else {
            const firstFlagged = Q.flags.findIndex(Boolean);
            const firstUnanswered = Q.answers.findIndex((answer) => !answer || !Number.isInteger(answer.picked));
            const target = firstFlagged >= 0 ? firstFlagged : firstUnanswered >= 0 ? firstUnanswered : 0;
            if (target !== Q.i) moveExamQuestion(target);
            else { saveSession(); render(); $('.exam-nav-summary')?.focus(); }
          }
          break;
        case 'go-question': moveExamQuestion(Number(el.dataset.index)); break;
        case 'toggle-flag':
          Q.flags[Q.i] = !Q.flags[Q.i]; saveSession(); render(); $('[data-act="toggle-flag"]')?.focus(); break;
        case 'explain': await explainNow(); break;
        case 'lang': S.lang = el.dataset.v; { const keep = $('#ai-out') ? $('#ai-out').innerHTML : ''; render(); if ($('#ai-out')) $('#ai-out').innerHTML = keep; } break;
        case 'quit': if (window.confirm('Quit this session? Answers you already gave are saved.')) { await go('dashboard'); } break;
        case 'go-dashboard': await go('dashboard'); break;
        case 'demo':
          if (!S.report || S.report.overall.answered === 0 || window.confirm('Replace your current history with demo data?')) {
            await api(`/api/demo/seed?learner=${learner}`, { method: 'POST' });
            clearSavedSession();
            toast('Demo data loaded'); await go('dashboard');
          }
          break;
        case 'reset':
          if (window.confirm('Delete all your practice history from this tracker?')) {
            await api(`/api/learner/${learner}`, { method: 'DELETE' });
            clearSavedSession();
            toast('History cleared'); await go('dashboard');
          }
          break;
        default: break;
      }
    } catch (err) {
      S.loading = false;
      if (Q && S.view === 'quiz') { Q.error = err.message; saveSession(); }
      toast(err.message); render();
    }
  });

  document.addEventListener('keydown', (e) => {
    if (S.view !== 'quiz' || !S.quiz || e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.target && /^(SELECT|INPUT|TEXTAREA)$/.test(e.target.tagName)) return;
    const Q = S.quiz;
    const idx = '1234'.indexOf(e.key) >= 0 ? '1234'.indexOf(e.key) : 'abcd'.indexOf(e.key.toLowerCase());
    if (e.key.length === 1 && idx >= 0 && !Q.answered && !(Q.mode === 'exam' && Q.deadline && Date.now() >= Q.deadline)) {
      Q.picked = idx;
      if (Q.mode === 'exam') Q.answers[Q.i] = { picked: Q.picked, sure: Q.sure };
      saveSession(); render(); app.querySelector('.opt.sel')?.focus(); return;
    }
    if (Q.mode === 'exam' && e.key === 'ArrowLeft') { e.preventDefault(); moveExamQuestion(Q.i - 1); return; }
    if (Q.mode === 'exam' && e.key === 'ArrowRight') { e.preventDefault(); moveExamQuestion(Q.i + 1); return; }
    if (e.key === 'Enter') {
      const btn = app.querySelector('[data-act="submit"],[data-act="submit-next"],[data-act="next"],[data-act="next-question"],[data-act="finish-exam"]');
      if (btn && !btn.disabled && e.target.tagName !== 'BUTTON') { e.preventDefault(); btn.click(); }
    }
  });

  document.addEventListener('submit', (e) => {
    if (e.target && e.target.id === 'plan-form') { e.preventDefault(); buildPlan(); }
  });

  document.addEventListener('change', async (e) => {
    if (e.target && e.target.id === 'import-file' && e.target.files && e.target.files[0]) {
      try { await importData(e.target.files[0]); } catch (err) { toast(err.message); }
      e.target.value = '';
    }
  });

  // ---------- boot ----------
  (async function init() {
    S.planPrefs = loadPrefs();
    S.loading = true; render();
    try {
      S.meta = await api('/api/meta');
      await loadReport();
    } catch (e) { toast(e.message); }
    S.loading = false; render();
  })();
})();
