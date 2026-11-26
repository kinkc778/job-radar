(() => {
  'use strict';

  const JOBS = Array.isArray(window.JOBS) ? window.JOBS.filter(j => j && j.title && j.url) : [];
  const META = window.JOB_META || {};

  const LS = {
    saved: 'jobradar.saved.v1',
    applied: 'jobradar.applied.v1',
    theme: 'jobradar.theme.v1',
  };

  const readSet = (k) => {
    try { return new Set(JSON.parse(localStorage.getItem(k) || '[]')); }
    catch { return new Set(); }
  };
  const writeSet = (k, set) => {
    try { localStorage.setItem(k, JSON.stringify([...set])); } catch { /* private mode */ }
  };

  const saved = readSet(LS.saved);
  const applied = readSet(LS.applied);

  const state = {
    q: '',
    families: new Set(),
    source: 'all',
    minScore: 0,
    savedOnly: false,
    sort: 'score',
  };

  const $ = (sel, root = document) => root.querySelector(sel);
  const grid = $('#grid');
  const empty = $('#empty');
  const visibleLabel = $('#visible');
  const hint = $('#hint');

  const ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ESC[c]);
  const safeUrl = (u) => (/^https?:\/\//i.test(String(u || '')) ? String(u) : '#');
  const keyOf = (j) => j.key || `${j.source || 'x'}:${j.external_id || j.url}`;
  const num = (v) => (Number.isFinite(Number(v)) ? Number(v) : 0);

  const toneClass = (s) => (s >= 85 ? 'tone-high' : s >= 70 ? 'tone-mid' : 'tone-low');

  const parseDate = (v) => {
    if (!v) return null;
    const d = new Date(v);
    return Number.isNaN(d.getTime()) ? null : d;
  };
  const daysAgo = (v) => {
    const d = parseDate(v);
    return d ? Math.floor((Date.now() - d.getTime()) / 86400000) : null;
  };
  const isNew = (v) => {
    const d = daysAgo(v);
    return d !== null && d <= 7;
  };
  const fmtDate = (v) => {
    const d = parseDate(v);
    if (!d) return String(v || '');
    return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
  };

  const HAY = new Map();
  JOBS.forEach((j) => {
    HAY.set(
      keyOf(j),
      [j.title, j.company, j.location, j.summary, j.role_family, j.jd]
        .filter(Boolean).join(' ').toLowerCase()
    );
  });

  const list = (v) => (Array.isArray(v) ? v.filter(Boolean) : []);

  // ---------- rendering ----------
  function cardHTML(j) {
    const key = keyOf(j);
    const score = num(j.score);
    const isSaved = saved.has(key);
    const isApplied = applied.has(key);

    const tags = [];
    if (j.role_family) tags.push(`<span class="tag family">${esc(j.role_family)}</span>`);
    if (isNew(j.first_seen)) tags.push('<span class="tag new">New</span>');
    if (j.employment_type && j.employment_type !== 'Full-time') {
      tags.push(`<span class="tag intern">${esc(j.employment_type)}</span>`);
    }
    if (isApplied) tags.push('<span class="tag applied">Applied</span>');

    const postedWhen = j.posted_at || j.posted || '';
    const meta = [
      j.salary ? `<em>${esc(j.salary)}</em>` : '',
      postedWhen ? `<em>Posted ${esc(fmtDate(postedWhen))}</em>` : '',
    ].filter(Boolean).join(' &nbsp;·&nbsp; ');

    const sub = [j.company ? `<b>${esc(j.company)}</b>` : '', j.location ? esc(j.location) : '']
      .filter(Boolean).join(' &nbsp;·&nbsp; ');

    const summary = j.summary || (j.jd ? String(j.jd).slice(0, 220) : '');

    const why = list(j.why_match);
    const gaps = list(j.gaps);
    const whyHTML = why.length
      ? `<div class="detail-block why"><h4>Why it fits</h4><ul>${why.map((w) => `<li>${esc(w)}</li>`).join('')}</ul></div>`
      : '';
    const gapHTML = gaps.length
      ? `<div class="detail-block gap"><h4>Watch out</h4><ul>${gaps.map((g) => `<li>${esc(g)}</li>`).join('')}</ul></div>`
      : '';
    const jdHTML = j.jd
      ? `<div class="detail-block"><h4>Job description</h4><div class="jd">${esc(j.jd)}</div></div>`
      : '';
    const label = (why.length || gaps.length) ? 'Why it fits, gaps &amp; JD' : 'Job description';
    const details = why.length || gaps.length || j.jd
      ? `<details class="more"><summary>${label}</summary>${whyHTML}${gapHTML}${jdHTML}</details>`
      : '';

    const bookmark = `
      <button class="iconbtn save" data-action="save" data-key="${esc(key)}"
        aria-pressed="${isSaved}" aria-label="${isSaved ? 'Remove from saved' : 'Save this role'}"
        title="${isSaved ? 'Saved — click to remove' : 'Save this role'}">
        <svg viewBox="0 0 24 24" width="16" height="16"
          fill="${isSaved ? 'currentColor' : 'none'}" stroke="currentColor"
          stroke-width="1.8" stroke-linejoin="round" aria-hidden="true">
          <path d="M6.5 4.5h11a1 1 0 0 1 1 1v14l-6.5-4-6.5 4v-14a1 1 0 0 1 1-1Z"></path>
        </svg>
      </button>`;

    return `
      <article class="card${isSaved ? ' is-saved' : ''}${isApplied ? ' is-applied' : ''}"
        data-key="${esc(key)}">
        <div class="card-top">
          <div class="ring ${toneClass(score)}" style="--p:${Math.max(0, Math.min(100, score))}"
            role="img" aria-label="Match score ${score} out of 100">
            <span>${score}</span>
          </div>
          <div class="headline">
            <div class="tags">${tags.join('')}</div>
            <h2><a href="${esc(safeUrl(j.url))}" target="_blank" rel="noopener noreferrer">${esc(j.title)}</a></h2>
            ${sub ? `<p class="sub">${sub}</p>` : ''}
            ${meta ? `<p class="meta">${meta}</p>` : ''}
          </div>
          ${bookmark}
        </div>
        ${summary ? `<p class="summary">${esc(summary)}</p>` : ''}
        ${details}
        <div class="actions">
          <a class="btn primary" href="${esc(safeUrl(j.url))}" target="_blank" rel="noopener noreferrer">
            Apply <span aria-hidden="true">↗</span>
          </a>
          <label class="check">
            <input type="checkbox" data-action="applied" data-key="${esc(key)}" ${isApplied ? 'checked' : ''}>
            Applied
          </label>
          <span class="src">${esc(j.source || '')}</span>
        </div>
      </article>`;
  }

  function matches(j) {
    const key = keyOf(j);
    if (state.savedOnly && !saved.has(key)) return false;
    if (state.source !== 'all' && (j.source || '') !== state.source) return false;
    if (num(j.score) < state.minScore) return false;
    if (state.families.size && !state.families.has(j.role_family || 'Other')) return false;

    const q = state.q.trim().toLowerCase();
    if (q) {
      const hay = HAY.get(key) || '';
      const terms = q.split(/\s+/);
      if (!terms.every((t) => hay.includes(t))) return false;
    }
    return true;
  }

  function sortJobs(a, b) {
    if (state.sort === 'newest') {
      return String(b.posted_at || b.first_seen || '')
        .localeCompare(String(a.posted_at || a.first_seen || ''));
    }
    if (state.sort === 'company') {
      return String(a.company || '').localeCompare(String(b.company || ''));
    }
    return num(b.score) - num(a.score);
  }

  function render() {
    const rows = JOBS.filter(matches).sort(sortJobs);
    grid.innerHTML = rows.map(cardHTML).join('');
    empty.hidden = rows.length !== 0;

    visibleLabel.textContent = `${rows.length} of ${JOBS.length} roles`;
    hint.textContent = state.savedOnly
      ? (rows.length ? 'Showing your saved roles.' : 'Nothing saved matches these filters.')
      : 'Bookmark a role to keep it on your shortlist.';

    updateStats();

    const allChip = $('[data-family="__all"]');
    if (allChip) allChip.setAttribute('aria-pressed', String(state.families.size === 0));
    document.querySelectorAll('[data-family]').forEach((chip) => {
      const f = chip.getAttribute('data-family');
      if (f === '__all') return;
      chip.setAttribute('aria-pressed', String(state.families.has(f)));
    });
  }

  function updateStats() {
    const total = JOBS.length;
    const fresh = JOBS.filter((j) => isNew(j.first_seen)).length;
    const savedCount = JOBS.filter((j) => saved.has(keyOf(j))).length;
    $('#statTotal').textContent = total;
    $('#statNew').textContent = fresh;
    $('#statSaved').textContent = savedCount;
  }

  // ---------- controls ----------
  function buildFamilyChips() {
    const counts = new Map();
    JOBS.forEach((j) => {
      const f = j.role_family || 'Other';
      counts.set(f, (counts.get(f) || 0) + 1);
    });
    const order = ['Data Engineering', 'Data Science', 'Data Analytics / BI',
      'AI / ML Engineering', 'Solution Engineering', 'Other'];
    const families = [...counts.keys()].sort((a, b) => {
      const ia = order.indexOf(a);
      const ib = order.indexOf(b);
      if (ia === -1 && ib === -1) return a.localeCompare(b);
      if (ia === -1) return 1;
      if (ib === -1) return -1;
      return ia - ib;
    });

    const html = [`<button class="chip" data-family="__all" aria-pressed="true">All roles<span class="n">${JOBS.length}</span></button>`];
    families.forEach((f) => {
      html.push(`<button class="chip" data-family="${esc(f)}" aria-pressed="false">${esc(f)}<span class="n">${counts.get(f)}</span></button>`);
    });
    $('#familyChips').innerHTML = html.join('');
  }

  function buildSourceOptions() {
    const sources = [...new Set(JOBS.map((j) => j.source).filter(Boolean))].sort();
    const sel = $('#source');
    sources.forEach((s) => {
      const opt = document.createElement('option');
      opt.value = s;
      opt.textContent = s;
      sel.appendChild(opt);
    });
  }

  function clearFilters() {
    state.q = '';
    state.families.clear();
    state.source = 'all';
    state.minScore = 0;
    state.savedOnly = false;
    $('#q').value = '';
    $('#source').value = 'all';
    $('#minScore').value = '0';
    $('#scoreVal').textContent = '0';
    $('#savedOnly').checked = false;
    render();
  }

  function bind() {
    let t;
    $('#q').addEventListener('input', (e) => {
      clearTimeout(t);
      t = setTimeout(() => { state.q = e.target.value; render(); }, 120);
    });

    $('#familyChips').addEventListener('click', (e) => {
      const chip = e.target.closest('[data-family]');
      if (!chip) return;
      const f = chip.getAttribute('data-family');
      if (f === '__all') state.families.clear();
      else if (state.families.has(f)) state.families.delete(f);
      else state.families.add(f);
      render();
    });

    $('#source').addEventListener('change', (e) => { state.source = e.target.value; render(); });
    $('#minScore').addEventListener('input', (e) => {
      state.minScore = Number(e.target.value);
      $('#scoreVal').textContent = String(state.minScore);
      render();
    });
    $('#savedOnly').addEventListener('change', (e) => { state.savedOnly = e.target.checked; render(); });
    $('#sort').addEventListener('change', (e) => { state.sort = e.target.value; render(); });
    $('#clearBtn').addEventListener('click', clearFilters);
    $('#emptyClear').addEventListener('click', clearFilters);

    grid.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-action="save"]');
      if (!btn) return;
      e.preventDefault();
      const key = btn.getAttribute('data-key');
      if (saved.has(key)) saved.delete(key);
      else saved.add(key);
      writeSet(LS.saved, saved);
      render();
    });

    grid.addEventListener('change', (e) => {
      const box = e.target.closest('[data-action="applied"]');
      if (!box) return;
      const key = box.getAttribute('data-key');
      if (box.checked) applied.add(key);
      else applied.delete(key);
      writeSet(LS.applied, applied);
      render();
    });

    document.addEventListener('keydown', (e) => {
      const tag = (document.activeElement && document.activeElement.tagName) || '';
      if (e.key === '/' && !/^(INPUT|TEXTAREA|SELECT)$/.test(tag)) {
        e.preventDefault();
        $('#q').focus();
      }
      if (e.key === 'Escape' && document.activeElement === $('#q')) {
        $('#q').blur();
      }
    });
  }

  function initTheme() {
    const stored = localStorage.getItem(LS.theme);
    const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    document.documentElement.dataset.theme = stored || (prefersDark ? 'dark' : 'light');
    $('#themeBtn').addEventListener('click', () => {
      const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
      document.documentElement.dataset.theme = next;
      try { localStorage.setItem(LS.theme, next); } catch { /* ignore */ }
    });
  }

  function initMeta() {
    const when = META.generated_hkt || (META.generated_at ? fmtDate(META.generated_at) : '');
    $('#updated').textContent = when ? `Updated ${when}` : '';
    $('#generated').textContent = when ? `Data generated ${when} · ${JOBS.length} roles` : '';
  }

  function init() {
    initTheme();
    initMeta();
    buildSourceOptions();
    buildFamilyChips();
    bind();
    render();

    if (!JOBS.length) {
      empty.hidden = false;
      empty.querySelector('h2').textContent = 'No job data yet';
      empty.querySelector('p').textContent = 'Run the scanner to generate docs/data/jobs.js.';
      visibleLabel.textContent = '0 roles';
    }
  }

  init();
})();
