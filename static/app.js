/* AZ-900 Readiness Tracker (unofficial) - vanilla JS, no build step. */
(() => {
  'use strict';

  // ---------- helpers ----------
  const $ = (sel, el = document) => el.querySelector(sel);
  const app = $('#app');
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const pct = (v) => `${Math.round(v * 100)}%`;
  const shuffle = (a) => { a = a.slice(); for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; };

  const store = {
    get(k) { try { return localStorage.getItem(k); } catch (_) { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (_) { /* private mode */ } },
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

  async function api(path, opts = {}) {
    const res = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...opts });
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
  const S = { view: 'dashboard', meta: null, report: null, quiz: null, lang: 'en', loading: false, plan: null, planError: null, planPrefs: null, timer: null };

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
      return `
        <div class="card empty">
          <h1>See how ready you really are</h1>
          <p>Answer practice questions and this page turns them into an honest estimate of your AZ-900 score, broken down by exam domain and topic, with the next best thing to study.</p>
          <div class="row" style="justify-content:center">
            <button class="btn primary" data-act="start-adaptive">Start practising</button>
            <button class="btn" data-act="demo">Load demo data</button>
            <button class="btn" data-act="import">Import backup</button>
            <input id="import-file" type="file" accept="application/json,.json" hidden>
          </div>
        </div>`;
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
      <h1>Practice</h1>
      <p class="muted">${m.total_questions} original questions across the three exam domains. After every answer you can mark how sure you were; the tracker uses that to tell lucky guesses from real knowledge.</p>
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
    const opts = item.order.map((orig, k) => {
      let cls = 'opt'; let mark = '';
      if (done) {
        if (orig === done.correct_index) { cls += ' right'; mark = '<span class="mk">Correct</span>'; }
        else if (k === Q.picked) { cls += ' wrong'; mark = '<span class="mk">Your answer</span>'; }
      } else if (k === Q.picked) cls += ' sel';
      return `<button class="${cls}" data-act="pick" data-k="${k}" ${done || timeExpired ? 'disabled' : ''} aria-pressed="${k === Q.picked}">
        <span class="let">${LETTERS[k]}</span><span>${esc(item.options[orig])}</span>${mark}</button>`;
    }).join('');

    const last = Q.i === Q.items.length - 1;
    let controls = '';
    if (timeExpired) {
      controls = `<div class="row"><p class="timer-expired" role="status">Time is up. Unanswered questions are left blank.</p><button class="btn primary" data-act="finish-exam">Finish exam</button></div>`;
    } else if (done && !exam) {
      controls = '';  // the Next button follows the feedback panel below
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
          <h3>${done.correct ? 'Correct' : 'Not quite'}</h3>
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
          <button class="btn quiet save-question" data-act="toggle-save" data-question="${esc(item.id)}">${isSaved ? 'Saved' : 'Save for later'}</button>
          <button class="btn quiet" data-act="quit">Quit</button>
        </div>
        <div class="qtext">${esc(item.q)}</div>
        <div class="opts">${opts}</div>
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
      return res;
    } finally { Q.busy = false; }
  }

  async function advance() {
    const Q = S.quiz;
    if (Q.i >= Q.items.length - 1) { await finishQuiz(); return; }
    Q.i += 1; Q.picked = null; Q.answered = null; Q.t0 = Date.now();
    render();
    window.scrollTo({ top: 0 });
  }

  async function finishQuiz() {
    const Q = S.quiz;
    clearInterval(S.timer); S.timer = null;
    try { S.report = await api(`/api/readiness?learner=${learner}`); } catch (e) { toast(`Could not refresh readiness: ${e.message}`); }
    Q.after = S.report ? S.report.overall.score : null;
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
    return `
      <h1>${Q.mode === 'exam' ? 'Mock exam complete' : 'Session complete'}</h1>
      <p class="muted">${Q.mode === 'exam' ? 'Your mock is complete. Review the domain breakdown and revisit missed questions before your next attempt.' : 'A little review now makes this practice session more useful.'}</p>
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
      </section>`;
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
      return `<h1>Study plan</h1>
        <p class="muted">Tell me your exam date and how much time you have. I'll put your time where it raises your estimated score the most, add a mock exam about a week out, and keep the last day light.</p>
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
    return `<h1>Study plan</h1>
      <p class="muted">${plan.days_to_exam} days to your exam &middot; ${plan.study_day_count} study days &middot; ${hm(plan.total_minutes)} planned.${S.report && S.report.overall.answered === 0 ? ' Practise a little, then update the plan: it gets sharper with data.' : ''}</p>
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
    S.planPrefs = { exam, hours, days };
    store.set('az900.plan', JSON.stringify(S.planPrefs));
    S.planError = null;
    try {
      const q = new URLSearchParams({ learner, exam_date: exam, hours_per_week: String(hours), days: days.join(','), today: isoToday() });
      S.plan = await api(`/api/plan?${q}`);
    } catch (e) { S.plan = null; S.planError = e.message; }
    render();
  }

  // ---------- render + routing ----------
  function render() {
    document.querySelectorAll('.nav').forEach((b) => {
      const on = (S.view === 'dashboard' && b.dataset.nav === 'dashboard') || (S.view === 'plan' && b.dataset.nav === 'plan') || ((S.view === 'practice' || S.view === 'quiz' || S.view === 'results') && b.dataset.nav === 'practice');
      if (on) b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current');
    });
    if (S.loading) { app.innerHTML = '<p class="muted">Loading&hellip;</p>'; return; }
    if (S.view === 'dashboard') app.innerHTML = S.report ? renderDashboard() : '<p class="muted">Loading&hellip;</p>';
    else if (S.view === 'practice') app.innerHTML = renderPractice();
    else if (S.view === 'quiz') app.innerHTML = renderQuiz();
    else if (S.view === 'results') app.innerHTML = renderResults();
    else if (S.view === 'plan') app.innerHTML = renderPlan();
  }

  async function loadReport() {
    S.report = await api(`/api/readiness?learner=${learner}`);
  }

  async function go(view) {
    if (view !== 'quiz') { clearInterval(S.timer); S.timer = null; }
    S.view = view;
    if (view === 'dashboard') {
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
        i: 0, picked: null, sure: true, answered: null, results: [], busy: false,
        before: before.overall.score, after: null, t0: Date.now(),
        deadline: opts.mode === 'exam' && opts.timed !== false ? Date.now() + 45 * 60 * 1000 : null,
      };
      S.view = 'quiz';
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
        i: 0, picked: null, sure: true, answered: null, results: [], busy: false,
        before: before.overall.score, after: null, t0: Date.now(), deadline: null,
      };
      S.view = 'quiz';
    } catch (e) { toast(e.message); S.view = 'results'; }
    S.loading = false; render(); window.scrollTo({ top: 0 });
  }

  async function exportData() {
    const data = await api(`/api/learner/${learner}/export`);
    data.saved = savedIds();
    data.plan = S.planPrefs;
    data.planChecks = planChecks();
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
        case 'pick': if (!Q.answered) { Q.picked = Number(el.dataset.k); render(); } break;
        case 'conf': Q.sure = el.dataset.v === 'sure'; render(); break;
        case 'submit': { const r = await submitAnswer(); if (r) render(); break; }
        case 'submit-next': { const r = await submitAnswer(); if (r) await advance(); break; }
        case 'finish-exam': await finishQuiz(); break;
        case 'next': await advance(); break;
        case 'explain': await explainNow(); break;
        case 'lang': S.lang = el.dataset.v; { const keep = $('#ai-out') ? $('#ai-out').innerHTML : ''; render(); if ($('#ai-out')) $('#ai-out').innerHTML = keep; } break;
        case 'quit': if (window.confirm('Quit this session? Answers you already gave are saved.')) { await go('dashboard'); } break;
        case 'go-dashboard': await go('dashboard'); break;
        case 'demo':
          if (!S.report || S.report.overall.answered === 0 || window.confirm('Replace your current history with demo data?')) {
            await api(`/api/demo/seed?learner=${learner}`, { method: 'POST' });
            toast('Demo data loaded'); await go('dashboard');
          }
          break;
        case 'reset':
          if (window.confirm('Delete all your practice history from this tracker?')) {
            await api(`/api/learner/${learner}`, { method: 'DELETE' });
            toast('History cleared'); await go('dashboard');
          }
          break;
        default: break;
      }
    } catch (err) { S.loading = false; toast(err.message); render(); }
  });

  document.addEventListener('keydown', (e) => {
    if (S.view !== 'quiz' || !S.quiz || e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.target && /^(SELECT|INPUT|TEXTAREA)$/.test(e.target.tagName)) return;
    const Q = S.quiz;
    const idx = '1234'.indexOf(e.key) >= 0 ? '1234'.indexOf(e.key) : 'abcd'.indexOf(e.key.toLowerCase());
    if (e.key.length === 1 && idx >= 0 && !Q.answered) { Q.picked = idx; render(); return; }
    if (e.key === 'Enter') {
      const btn = app.querySelector('[data-act="submit"],[data-act="submit-next"],[data-act="next"]');
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
