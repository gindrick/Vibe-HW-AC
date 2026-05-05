const chatEl = document.getElementById('chat');
const qEl = document.getElementById('q');
const statusText = document.getElementById('statusText');
const statusPill = document.getElementById('statusPill');

function setStatus(text) {
  statusText.textContent = text;
}

function scrollToBottom() {
  chatEl.scrollTop = chatEl.scrollHeight;
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function formatTimestamp(d) {
  try {
    return new Intl.DateTimeFormat('cs-CZ', {
      dateStyle: 'short',
      timeStyle: 'short'
    }).format(d);
  } catch {
    return d.toLocaleString();
  }
}

function renderMessage(role, content, sources=null, ts=null) {
  const wrap = document.createElement('div');
  wrap.className = 'msg ' + (role === 'user' ? 'user' : 'assistant');

  const tsDate = ts ? new Date(ts) : new Date();
  wrap.dataset.ts = tsDate.toISOString();

  const avatar = document.createElement('div');
  avatar.className = 'avatar';
  avatar.textContent = role === 'user' ? '🙂' : '🤖';

  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  const contentEl = document.createElement('div');
  contentEl.className = 'content';
  contentEl.innerHTML = escapeHtml(content);
  bubble.appendChild(contentEl);

  if (role === 'assistant' && sources) {
    const meta = document.createElement('div');
    meta.className = 'meta';

    const d = document.createElement('details');
    const s = document.createElement('summary');
    s.textContent = 'Zdroje (' + sources.length + ')';
    d.appendChild(s);

    const pre = document.createElement('div');
    pre.className = 'src';
    pre.textContent = JSON.stringify(sources, null, 2);
    d.appendChild(pre);

    meta.appendChild(d);
    bubble.appendChild(meta);
  }

  const timeEl = document.createElement('div');
  timeEl.className = 'time';
  timeEl.textContent = formatTimestamp(tsDate);
  bubble.appendChild(timeEl);

  wrap.appendChild(avatar);
  wrap.appendChild(bubble);
  chatEl.appendChild(wrap);
  scrollToBottom();
}

function saveChat() {
  const items = Array.from(chatEl.querySelectorAll('.msg')).map(m => {
    const role = m.classList.contains('user') ? 'user' : 'assistant';
    const content = m.querySelector('.content');
    const text = content ? content.innerText : '';
    const ts = m.dataset.ts || null;
    return { role, text, ts };
  });
  localStorage.setItem('kb_chat_history', JSON.stringify(items));
}

function loadChat() {
  const raw = localStorage.getItem('kb_chat_history');
  if (!raw) {
    renderMessage('assistant',
`Ahoj! Zeptej se na cokoliv, co je v KB (.md).\n
Tip: zkus režim „Max 3 věty“ nebo „Pouze citace“.`);
    return;
  }
  try {
    const items = JSON.parse(raw);
    if (!items.length) throw new Error();
    items.forEach(i => renderMessage(i.role, i.text, null, i.ts));
  } catch {
    localStorage.removeItem('kb_chat_history');
    loadChat();
  }
}

async function send() {
  const q = qEl.value.trim();
  if (!q) return;

  const mode = document.getElementById('mode').value;

  renderMessage('user', q);
  qEl.value = '';
  autoGrow();

  setStatus('Thinking…');

  const placeholderId = 'ph_' + Math.random().toString(16).slice(2);
  renderMessage('assistant', '…'); // jednoduchý placeholder
  const lastBubble = chatEl.querySelector('.msg.assistant:last-child .bubble');
  const lastContent = chatEl.querySelector('.msg.assistant:last-child .content');

  try {
    const r = await fetch('/api/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: q, mode })
    });

    const data = await r.json();

    // aktualizace placeholderu
    if (lastContent) {
      lastContent.innerHTML = escapeHtml(data.answer || '');
    }

    // zdroje
    if (data.sources) {
      const meta = document.createElement('div');
      meta.className = 'meta';
      const d = document.createElement('details');
      const s = document.createElement('summary');
      s.textContent = 'Zdroje (' + data.sources.length + ')';
      d.appendChild(s);
      const pre = document.createElement('div');
      pre.className = 'src';
      pre.textContent = JSON.stringify(data.sources, null, 2);
      d.appendChild(pre);
      meta.appendChild(d);
      lastBubble.appendChild(meta);
    }

    setStatus('Ready');
    saveChat();
    scrollToBottom();
  } catch (e) {
    if (lastContent) {
      lastContent.innerHTML = 'Chyba při volání API.';
    }
    setStatus('Error');
  }
}

async function reloadIndex() {
  setStatus('Reindex…');
  try {
    const r = await fetch('/api/reload', { method: 'POST' });
    const data = await r.json();
    setStatus(data.ok ? 'Reindex OK (' + data.chunks + ' chunků)' : 'Reindex error');
  } catch {
    setStatus('Reindex error');
  }
}

function clearChat() {
  chatEl.innerHTML = '';
  localStorage.removeItem('kb_chat_history');
  loadChat();
}

function insertExample() {
  const examples = [
    "V jakých produktových řadách mohou být ABS hrany?",
    "Jaké jsou limity / podmínky v dokumentu PPD?",
    "Shrň prosím pravidla z kapitoly o reklamaci."
  ];
  const pick = examples[Math.floor(Math.random() * examples.length)];
  qEl.value = pick;
  autoGrow();
  qEl.focus();
}

function autoGrow() {
  qEl.style.height = 'auto';
  qEl.style.height = Math.min(qEl.scrollHeight, 180) + 'px';
}

qEl.addEventListener('input', autoGrow);

qEl.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    send();
  }
});

async function loadMeta() {
  try {
    const r = await fetch('/api/meta');
    const data = await r.json();
    document.getElementById('modelName').textContent = data.model;
    document.getElementById('topK').textContent = data.top_k;
    document.getElementById('minScore').textContent = data.min_score;
  } catch {
    document.getElementById('modelName').textContent = 'unknown';
    document.getElementById('topK').textContent = '—';
    document.getElementById('minScore').textContent = '—';
  }
}

loadChat();
autoGrow();
loadMeta();
