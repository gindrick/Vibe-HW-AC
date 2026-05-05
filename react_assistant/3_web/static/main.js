const queryEl = document.getElementById('query');
const modelDisplayEl = document.getElementById('modelDisplay');
const modeEl = document.getElementById('mode');
const modeMenuEl = document.getElementById('modeMenu');
const modeLabelEl = document.getElementById('modeLabel');
const modeOptionEls = Array.from(document.querySelectorAll('[data-mode-option]'));
const resultRatioValueEl = document.getElementById('resultRatioValue');
const resultRatioMenuEl = document.getElementById('resultRatio');
const resultRatioLabelEl = document.getElementById('resultRatioLabel');
const resultRatioOptionEls = Array.from(document.querySelectorAll('[data-result-ratio-option]'));
const persistDirEl = document.getElementById('persistDir');
const collectionEl = document.getElementById('collection');
const advancedMenuEl = document.getElementById('advancedMenu');
const sourcesMenuEl = document.getElementById('sourcesMenu');
const sourcesInfoEl = document.getElementById('sourcesInfo');
const refreshSourcesBtn = document.getElementById('refreshSourcesBtn');
const askBtn = document.getElementById('askBtn');
const clearChatBtn = document.getElementById('clearChatBtn');
const logoutBtn = document.getElementById('logoutBtn');
const statusEl = document.getElementById('status');
const answerEl = document.getElementById('answer');
const chatFeedEl = document.getElementById('chatFeed');
const layoutGridEl = document.getElementById('layoutGrid');
const railPanelEl = document.getElementById('railPanel');
const railToggleWrapEl = document.getElementById('railToggleWrap');
const railToggleBtn = document.getElementById('railToggleBtn');
const railSettingsBtn = document.getElementById('railSettingsBtn');
const railHistoryBtn = document.getElementById('railHistoryBtn');
const railNavBtnEls = Array.from(document.querySelectorAll('[data-rail-nav-btn]'));
const railLabelEls = Array.from(document.querySelectorAll('[data-rail-label]'));
const sidePanelEl = document.getElementById('sidePanel');
const sidePanelTitleEl = document.getElementById('sidePanelTitle');
const sidePanelCloseBtn = document.getElementById('sidePanelCloseBtn');
const settingsContentEl = document.getElementById('settingsContent');
const historyContentEl = document.getElementById('historyContent');
const chatPanelEl = document.getElementById('chatPanel');
const historyListEl = document.getElementById('historyList');
const clearHistoryBtn = document.getElementById('clearHistoryBtn');
const debugPayloadEl = document.getElementById('debugPayload');
const debugResponseEl = document.getElementById('debugResponse');
const userNameEl = document.getElementById('userName');
const userEmailEl = document.getElementById('userEmail');

const HISTORY_KEY = 'agent_query_history_v1';
const HISTORY_LIMIT = 10;
const SIDEPANEL_KEY = 'agent_side_panel_state_v1';
const SOURCE_NAME_MAX_LEN = 55;
const RAIL_KEY = 'agent_rail_state_v1';

let activeSidePanel = null;
let isRailExpanded = false;

function appBasePath() {
  const segments = String(window.location.pathname || '/')
    .split('/')
    .filter(Boolean);
  if (!segments.length) return '';
  const first = segments[0].toLowerCase();
  if (first === 'auth' || first === 'api' || first === 'static' || first === 'img') return '';
  return `/${segments[0]}`;
}

function appUrl(path) {
  const normalized = path.startsWith('/') ? path : `/${path}`;
  return `${appBasePath()}${normalized}`;
}

function writeRailState(state) {
  try {
    localStorage.setItem(RAIL_KEY, state);
  } catch {
  }
}

function readRailState() {
  try {
    const value = localStorage.getItem(RAIL_KEY);
    if (value === 'expanded' || value === 'collapsed') {
      return value;
    }
  } catch {
  }
  return 'collapsed';
}

function setRailExpandedState(expanded) {
  isRailExpanded = Boolean(expanded);

  if (layoutGridEl) {
    layoutGridEl.classList.remove('md:grid-cols-[3.75rem_repeat(11,minmax(0,1fr))]', 'md:grid-cols-[9.75rem_repeat(11,minmax(0,1fr))]');
    layoutGridEl.classList.add(isRailExpanded ? 'md:grid-cols-[9.75rem_repeat(11,minmax(0,1fr))]' : 'md:grid-cols-[3.75rem_repeat(11,minmax(0,1fr))]');
  }

  railLabelEls.forEach((label) => {
    label.classList.toggle('hidden', !isRailExpanded);
  });

  railNavBtnEls.forEach((btn) => {
    btn.classList.toggle('justify-center', !isRailExpanded);
    btn.classList.toggle('justify-start', isRailExpanded);
  });

  if (railToggleBtn) {
    railToggleBtn.setAttribute('aria-expanded', String(isRailExpanded));
  }

  updateSidePanelSpan();
  updateChatPanelSpan();

  writeRailState(isRailExpanded ? 'expanded' : 'collapsed');
}

function toggleRailExpanded() {
  setRailExpandedState(!isRailExpanded);
}

function isSourcesMenuExpanded() {
  return activeSidePanel === 'settings' && Boolean(sourcesMenuEl?.open);
}

function updateSidePanelSpan() {
  if (!sidePanelEl) return;
  sidePanelEl.classList.remove('md:col-span-3', 'md:col-span-4');
  sidePanelEl.classList.add(isSourcesMenuExpanded() ? 'md:col-span-4' : 'md:col-span-3');
}

function normalizeDisplayName(user) {
  const rawName = String(user?.name || '').trim();
  if (rawName) {
    const parts = rawName.split(/\s+/).filter(Boolean);
    if (parts.length >= 2) {
      return `${parts[0]} ${parts[parts.length - 1]}`;
    }
    return parts[0];
  }

  const email = String(user?.email || '').trim();
  if (!email || !email.includes('@')) {
    return 'User';
  }

  const localPart = email.split('@')[0].replace(/[._-]+/g, ' ').trim();
  const tokens = localPart
    .split(/\s+/)
    .filter(Boolean)
    .map((token) => token.charAt(0).toUpperCase() + token.slice(1));

  if (tokens.length >= 2) {
    return `${tokens[0]} ${tokens[tokens.length - 1]}`;
  }
  return tokens[0] || 'User';
}

function renderUser(user) {
  if (userNameEl) {
    userNameEl.textContent = normalizeDisplayName(user);
  }
  if (userEmailEl) {
    const email = String(user?.email || '').trim();
    userEmailEl.textContent = email;
  }
}

function updateChatPanelSpan() {
  chatPanelEl.classList.remove('md:col-span-11', 'md:col-span-10', 'md:col-span-8', 'md:col-span-7', 'md:col-span-6');
  if (!activeSidePanel) {
    chatPanelEl.classList.add('md:col-span-11');
    return;
  }

  chatPanelEl.classList.add(isSourcesMenuExpanded() ? 'md:col-span-7' : 'md:col-span-8');
}

function setRailButtonState(active) {
  const makeActive = (btn, isActive) => {
    btn.classList.toggle('border-sky-500', isActive);
    btn.classList.toggle('bg-sky-500/10', isActive);
  };
  makeActive(railSettingsBtn, active === 'settings');
  makeActive(railHistoryBtn, active === 'history');
}

function writeSidePanelState(state) {
  try {
    localStorage.setItem(SIDEPANEL_KEY, state);
  } catch {
  }
}

function readSidePanelState() {
  try {
    const value = localStorage.getItem(SIDEPANEL_KEY);
    if (value === 'settings' || value === 'history' || value === 'closed') {
      return value;
    }
  } catch {
  }
  return 'settings';
}

function openSidePanel(kind) {
  activeSidePanel = kind;
  sidePanelEl.classList.remove('hidden');

  const isSettings = kind === 'settings';
  settingsContentEl.classList.toggle('hidden', !isSettings);
  historyContentEl.classList.toggle('hidden', isSettings);
  sidePanelTitleEl.textContent = isSettings ? 'Settings' : 'History';

  setRailButtonState(kind);
  updateSidePanelSpan();
  updateChatPanelSpan();
  writeSidePanelState(kind);
}

function closeSidePanel() {
  activeSidePanel = null;
  sidePanelEl.classList.add('hidden');
  setRailButtonState(null);
  updateSidePanelSpan();
  updateChatPanelSpan();
  writeSidePanelState('closed');
}

function toggleSidePanel(kind) {
  if (activeSidePanel === kind) {
    closeSidePanel();
    return;
  }
  openSidePanel(kind);
}

function readHistory() {
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    if (!raw) return [];
    const data = JSON.parse(raw);
    return Array.isArray(data) ? data : [];
  } catch {
    return [];
  }
}

function writeHistory(items) {
  localStorage.setItem(HISTORY_KEY, JSON.stringify(items.slice(0, HISTORY_LIMIT)));
}

function renderHistory() {
  const items = readHistory();
  historyListEl.innerHTML = '';

  if (!items.length) {
    const empty = document.createElement('div');
    empty.className = 'rounded-xl border border-slate-800 bg-slate-950 p-3 text-xs text-slate-500';
    empty.textContent = 'No saved queries yet.';
    historyListEl.appendChild(empty);
    return;
  }

  items.forEach((item) => {
    const dt = item.ts ? new Date(item.ts) : null;
    const timeLabel = dt
      ? dt.toLocaleTimeString('cs-CZ', { hour: '2-digit', minute: '2-digit' })
      : '';
    const queryPreview = (item.query || '').trim();
    const title = queryPreview.length > 44 ? `${queryPreview.slice(0, 44)}…` : queryPreview;

    const row = document.createElement('button');
    row.type = 'button';
    row.className = 'w-full rounded-xl border border-slate-800 bg-slate-950 p-3 text-left hover:border-sky-700 hover:bg-slate-900';
    row.innerHTML = `
      <div class="flex items-center justify-between gap-2">
        <div class="text-sm font-medium text-slate-200">${escapeHtml(title) || 'Untitled'}</div>
        <div class="text-[11px] text-slate-500">${escapeHtml(timeLabel)}</div>
      </div>
      <div class="mt-1 text-xs text-slate-400">${escapeHtml(queryPreview.slice(0, 80)) || '...'}</div>
    `;
    row.addEventListener('click', () => {
      queryEl.value = item.query || '';
      if (item.response_mode) setModeValue(item.response_mode);
      if (item.n_results) setResultRatioValue(item.n_results);
      if (item.persist_dir) persistDirEl.value = item.persist_dir;
      if (item.collection_name) collectionEl.value = item.collection_name;
      setStatus('Query loaded from history.');
    });
    historyListEl.appendChild(row);
  });
}

function saveCurrentToHistory(payload) {
  const query = (payload.query || '').trim();
  if (!query) return;

  const current = readHistory();
  const deduped = current.filter((item) => item.query !== query);
  deduped.unshift({
    query,
    response_mode: payload.response_mode,
    n_results: payload.n_results,
    persist_dir: payload.persist_dir,
    collection_name: payload.collection_name,
    ts: Date.now(),
  });
  writeHistory(deduped);
  renderHistory();
}

async function loadConfig() {
  const res = await fetch(appUrl('/api/config'), { credentials: 'include' });
  if (res.status === 401) {
    window.location.href = appUrl('/auth/login');
    return;
  }
  if (!res.ok) {
    throw new Error(`Config load failed (${res.status})`);
  }
  const cfg = await res.json();
  persistDirEl.value = cfg.persist_dir || '';
  collectionEl.value = cfg.collection_name || '';
  modelDisplayEl.value = cfg.agent_model || 'oai-gpt-4.1-nano';
  renderUser(cfg.user);
  if (logoutBtn) {
    logoutBtn.classList.toggle('hidden', !cfg.auth_enabled);
  }
}

function applyReadonlyInputOverflowStyles() {
  [persistDirEl, collectionEl, modelDisplayEl].forEach((el) => {
    if (!el) return;
    el.style.overflow = 'hidden';
    el.style.textOverflow = 'ellipsis';
    el.style.whiteSpace = 'nowrap';
  });
}

function renderSourcesInfo(payload) {
  if (!sourcesInfoEl) return;

  const sources = Array.isArray(payload?.sources) ? payload.sources : [];
  if (!sources.length) {
    const emptyText = payload?.error
      ? `No sources available (${payload.error})`
      : 'No sources available.';
    sourcesInfoEl.textContent = emptyText;
    return;
  }

  const visible = sources.slice(0, 80);
  const links = visible.map((item) => {
    const rawFileName = String(item?.file_name || 'unknown');
    const displayFileName = rawFileName.length > SOURCE_NAME_MAX_LEN ? `${rawFileName.slice(0, SOURCE_NAME_MAX_LEN)}...` : rawFileName;
    const fileName = escapeHtml(displayFileName);
    const fullFileName = escapeHtml(rawFileName);
    const fileUrl = item?.file_url;
    if (fileUrl) {
      const resolvedFileUrl = String(fileUrl).startsWith('/') ? appUrl(fileUrl) : String(fileUrl);
      const href = escapeHtml(resolvedFileUrl);
      return `<li class="min-w-0 leading-5" title="${fullFileName}"><a href="${href}" target="_blank" rel="noopener noreferrer" class="block max-w-full text-sky-300 hover:text-sky-200 hover:underline">${fileName}</a></li>`;
    }
    return `<li class="min-w-0 leading-5" title="${fullFileName}"><span class="block max-w-full text-slate-300">${fileName}</span></li>`;
  });

  if (sources.length > 80) {
    links.push(`<li class="text-slate-500">...and ${sources.length - 80} more</li>`);
  }

  sourcesInfoEl.innerHTML = `<ul class="min-w-0 list-disc space-y-1 overflow-x-hidden overflow-y-auto pl-4 pr-1 max-h-[10.5rem]">${links.join('')}</ul>`;
}

async function loadSourcesInfo() {
  if (!sourcesInfoEl) return;
  sourcesInfoEl.textContent = 'Loading sources...';

  try {
    const res = await fetch(appUrl('/api/sources'), { credentials: 'include' });
    if (res.status === 401) {
      window.location.href = appUrl('/auth/login');
      return;
    }
    if (!res.ok) {
      throw new Error(`Sources load failed (${res.status})`);
    }
    const data = await res.json();
    renderSourcesInfo(data);
  } catch (err) {
    sourcesInfoEl.textContent = `No sources available (${err.message})`;
  }
}

function setStatus(text, danger = false) {
  statusEl.textContent = text;
  statusEl.className = danger ? 'text-xs text-rose-400' : 'text-xs text-slate-400';
}

function setModeValue(value) {
  const allowed = ['short', 'detailed', 'citations'];
  const next = allowed.includes(value) ? value : 'short';
  modeEl.value = next;
  modeLabelEl.textContent = next;

  modeOptionEls.forEach((optionEl) => {
    const selected = optionEl.dataset.modeOption === next;
    optionEl.classList.toggle('border-sky-500', selected);
    optionEl.classList.toggle('text-sky-300', selected);
  });
}

function setResultRatioValue(value) {
  const parsed = Number(value);
  const next = Number.isInteger(parsed) ? Math.min(10, Math.max(1, parsed)) : 3;
  resultRatioValueEl.value = String(next);
  resultRatioLabelEl.textContent = String(next);

  resultRatioOptionEls.forEach((optionEl) => {
    const selected = Number(optionEl.dataset.resultRatioOption) === next;
    optionEl.classList.toggle('border-sky-500', selected);
    optionEl.classList.toggle('text-sky-300', selected);
  });
}

function setDebugPayload(payload) {
  debugPayloadEl.textContent = JSON.stringify(payload, null, 2);
}

function setDebugResponse(status, data, rawText = null) {
  const content = {
    status,
    data,
    rawText,
    ts: new Date().toISOString(),
  };
  debugResponseEl.textContent = JSON.stringify(content, null, 2);
}

function escapeHtml(text) {
  return String(text || '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function scrollChatToBottom() {
  chatFeedEl.scrollTop = chatFeedEl.scrollHeight;
}

function formatMessageTime(ts = Date.now()) {
  return new Date(ts).toLocaleTimeString('cs-CZ', {
    hour: '2-digit',
    minute: '2-digit',
  });
}

function renderInitialAssistantMessage() {
  chatFeedEl.innerHTML = '';
  appendMessage('assistant', 'Hello! Ask a question and I will answer based on the Chroma knowledge base.', Date.now());
}

function createAssistantAvatar() {
  const avatar = document.createElement('div');
  avatar.className = 'mt-1 h-9 w-9 flex-none overflow-hidden rounded-full border border-sky-400/50 bg-[linear-gradient(155deg,rgba(14,116,144,0.35),rgba(2,6,23,0.95)_55%,rgba(15,23,42,0.86))] p-[1px] shadow-[0_0_0_1px_rgba(14,165,233,0.25),0_0_10px_rgba(14,165,233,0.18)]';

  const img = document.createElement('img');
  img.src = `${appUrl('/img/kryten2.jpg')}?v=${Date.now()}`;
  img.alt = 'AI avatar';
  img.className = 'h-full w-full rounded-full object-cover';
  img.style.imageRendering = 'auto';
  img.style.objectPosition = '50% 23%';
  img.style.transform = 'scale(1.45)';
  img.addEventListener('error', () => {
    avatar.className = 'mt-1 h-8 w-8 flex-none rounded-full bg-sky-500/30 text-center text-sm leading-8 text-sky-300';
    avatar.textContent = 'AI';
  }, { once: true });

  avatar.appendChild(img);
  return avatar;
}

function appendMessage(role, text, ts = Date.now()) {
  const wrapper = document.createElement('div');
  wrapper.className = role === 'user' ? 'flex justify-end gap-3' : 'flex gap-3';

  if (role !== 'user') {
    wrapper.appendChild(createAssistantAvatar());
  }

  const bubble = document.createElement('div');
  bubble.className =
    role === 'user'
      ? 'max-w-[85%] rounded-2xl bg-sky-500/90 px-4 py-3 text-sm text-slate-950 shadow-lg shadow-sky-500/10'
      : 'max-w-[85%] rounded-2xl border border-slate-800 bg-slate-950 px-4 py-3 text-sm text-slate-200';
  bubble.innerHTML = `
    <div class="whitespace-pre-wrap">${escapeHtml(text)}</div>
    <div class="mt-2 text-[11px] ${role === 'user' ? 'text-slate-800/80' : 'text-slate-500'}">${escapeHtml(formatMessageTime(ts))}</div>
  `;
  wrapper.appendChild(bubble);
  chatFeedEl.appendChild(wrapper);
  scrollChatToBottom();
  return bubble;
}

function setTypingIndicator(bubble) {
  bubble.innerHTML = `
    <div class="flex items-center gap-1 py-1">
      <span class="h-2 w-2 rounded-full bg-slate-400/80 animate-bounce" style="animation-delay:0ms"></span>
      <span class="h-2 w-2 rounded-full bg-slate-400/80 animate-bounce" style="animation-delay:120ms"></span>
      <span class="h-2 w-2 rounded-full bg-slate-400/80 animate-bounce" style="animation-delay:240ms"></span>
    </div>
    <div class="mt-2 text-[11px] text-slate-500">${escapeHtml(formatMessageTime())}</div>
  `;
}

async function askAgent() {
  const query = queryEl.value.trim();
  if (!query) {
    setStatus('Enter a query.', true);
    return;
  }

  askBtn.disabled = true;
  askBtn.classList.add('opacity-60');
  setStatus('Analyzing...');
  answerEl.textContent = '';
  appendMessage('user', query, Date.now());
  const assistantBubble = appendMessage('assistant', '');
  setTypingIndicator(assistantBubble);

  try {
    const payload = {
      query,
      response_mode: modeEl.value,
      n_results: Number(resultRatioValueEl.value || 3),
      persist_dir: persistDirEl.value.trim() || null,
      collection_name: collectionEl.value.trim() || null,
      user_message: '{"user_id":"web_user"}'
    };
    setDebugPayload(payload);

    const res = await fetch(appUrl('/api/ask'), {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    let data = null;
    let rawText = null;
    const contentType = res.headers.get('content-type') || '';
    if (contentType.includes('application/json')) {
      data = await res.json();
    } else {
      rawText = await res.text();
      try {
        data = JSON.parse(rawText);
      } catch {
        data = { success: false, error: rawText || 'Internal Server Error' };
      }
    }
    setDebugResponse(res.status, data, rawText);

    if (res.status === 401) {
      window.location.href = appUrl('/auth/login');
      return;
    }

    if (!res.ok || !data.success) {
      const err = data.error || data.detail || 'Unknown error';
      setStatus(`Error: ${err}`, true);
      answerEl.textContent = '';
      assistantBubble.innerHTML = `
        <div class="whitespace-pre-wrap">${escapeHtml(`Error: ${err}`)}</div>
        <div class="mt-2 text-[11px] text-slate-500">${escapeHtml(formatMessageTime())}</div>
      `;
      return;
    }

    answerEl.textContent = data.answer || '';
    assistantBubble.innerHTML = `
      <div class="whitespace-pre-wrap">${escapeHtml(data.answer || 'No answer returned.')}</div>
      <div class="mt-2 text-[11px] text-slate-500">${escapeHtml(formatMessageTime())}</div>
    `;
    saveCurrentToHistory(payload);
    setStatus('Done');
    queryEl.value = '';
  } catch (err) {
    setDebugResponse(0, { success: false, error: err.message }, null);
    setStatus(`Error: ${err.message}`, true);
    assistantBubble.innerHTML = `
      <div class="whitespace-pre-wrap">${escapeHtml(`Error: ${err.message}`)}</div>
      <div class="mt-2 text-[11px] text-slate-500">${escapeHtml(formatMessageTime())}</div>
    `;
  } finally {
    askBtn.disabled = false;
    askBtn.classList.remove('opacity-60');
  }
}

askBtn.addEventListener('click', askAgent);
modeOptionEls.forEach((optionEl) => {
  optionEl.addEventListener('click', () => {
    const value = optionEl.dataset.modeOption;
    setModeValue(value);
    modeMenuEl.open = false;
  });
});

resultRatioOptionEls.forEach((optionEl) => {
  optionEl.addEventListener('click', () => {
    const value = optionEl.dataset.resultRatioOption;
    setResultRatioValue(value);
    resultRatioMenuEl.open = false;
  });
});

queryEl.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    askAgent();
  }
});

clearHistoryBtn.addEventListener('click', () => {
  localStorage.removeItem(HISTORY_KEY);
  renderHistory();
  setStatus('History cleared.');
});

clearChatBtn.addEventListener('click', () => {
  answerEl.textContent = '';
  renderInitialAssistantMessage();
  setStatus('Chat cleared.');
});

railSettingsBtn.addEventListener('click', () => toggleSidePanel('settings'));
railHistoryBtn.addEventListener('click', () => toggleSidePanel('history'));
sidePanelCloseBtn.addEventListener('click', closeSidePanel);
if (railToggleBtn) {
  railToggleBtn.addEventListener('click', toggleRailExpanded);
}

if (logoutBtn) {
  logoutBtn.addEventListener('click', () => {
    window.location.href = appUrl('/auth/logout');
  });
}

loadConfig().catch((err) => {
  setStatus(`Error: ${err.message}`, true);
});
applyReadonlyInputOverflowStyles();
loadSourcesInfo();
renderHistory();
renderInitialAssistantMessage();
setRailExpandedState(readRailState() === 'expanded');
setModeValue(modeEl.value);
const savedSidePanelState = readSidePanelState();
if (savedSidePanelState === 'history') {
  openSidePanel('history');
} else if (savedSidePanelState === 'closed') {
  closeSidePanel();
} else {
  openSidePanel('settings');
}
setDebugPayload({ note: 'No request sent yet.' });
setDebugResponse(0, { note: 'No response yet.' }, null);
setResultRatioValue(resultRatioValueEl.value);

if (refreshSourcesBtn) {
  refreshSourcesBtn.addEventListener('click', () => {
    loadSourcesInfo();
  });
}

if (sourcesMenuEl) {
  sourcesMenuEl.addEventListener('toggle', () => {
    updateSidePanelSpan();
    updateChatPanelSpan();
  });
}

if (advancedMenuEl) {
  advancedMenuEl.addEventListener('toggle', () => {
    updateSidePanelSpan();
    updateChatPanelSpan();
  });
}
