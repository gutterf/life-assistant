/* 生活助手桌面版 — 功能与 iOS 端一致：聊天 / 卡片弹窗 / 语音 / 图片 / 设置 */
(function () {
  'use strict';

 // ---------- 模型名清洗：任何变体统一映射到 DeepSeek 开放平台有效名 ----------
 const MODEL_ALLOW = ['deepseek-v4-flash', 'deepseek-v4-pro', 'deepseek-chat', 'deepseek-reasoner', 'deepseek-flash'];
 function normalizeModel(name) {
 if (!name) return 'deepseek-v4-flash';
 let n = String(name).trim().toLowerCase();
 if (n.startsWith('deepseek-v4.1') || n.includes('1017') || n.includes('v4.1')) n = 'deepseek-v4-flash';
 if (n.startsWith('deepseek') && n.includes('pro')) n = 'deepseek-v4-pro';
 if (n.startsWith('deepseek') && (n.includes('reason') || n.includes('r1'))) n = 'deepseek-reasoner';
 if (n.startsWith('deepseek') && (n.includes('chat') || n.includes('flash') || n.includes('v4') || n.includes('v3'))) n = 'deepseek-v4-flash';
 if (!MODEL_ALLOW.includes(n)) n = 'deepseek-v4-flash';
 return n;
 }

 // ---------- 状态 ----------
 const S = {
 // 空串 = 同源（云端部署后电脑关机也能用）；本地也走同一套
 baseURL: (localStorage.getItem('la.baseURL') || '').replace(/\/+$/, ''),
 modelPreset: normalizeModel(localStorage.getItem('la.modelPreset') || 'deepseek-v4-flash'),
 customModel: localStorage.getItem('la.customModel') || '',
   apiKey: localStorage.getItem('la.apiKey') || 'sk-a8d93fd779af4a32a82f5af6c18276ca',
 noFilter: localStorage.getItem('la.noFilter') === '1',
 satellite: false,
 autoSpeak: localStorage.getItem('la.autoSpeak') !== '0',
 voiceDefault: localStorage.getItem('la.voiceDefault') || '',
 voiceVsReady: false,
 location: { latitude: 31.2304, longitude: 121.4737, label: '', status: 'idle' }, // idle | locating | ready | failed
 sessionId: 'local',
 messages: [],
 working: false,
 stage: { cards: [], index: 0 },
 pendingFile: null,
 listening: false
 };
 localStorage.setItem('la.modelPreset', S.modelPreset);

  const $ = (id) => document.getElementById(id);
  const transcript = $('transcript');
  const input = $('input');

  // ---------- 格式化（对应 iOS Format） ----------
  function fmtDistance(m) {
    if (m == null) return '距离未知';
    return m >= 1000 ? (m / 1000).toFixed(1) + ' km' : m + ' m';
  }
  function fmtDuration(s) {
    if (!s || s <= 0) return '—';
    if (s >= 3600) {
      const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
      return m > 0 ? h + ' 小时 ' + m + ' 分' : h + ' 小时';
    }
    return Math.max(1, Math.floor(s / 60)) + ' 分钟';
  }
  function fmtMoney(y) { return y == null ? '' : ' 约 ¥' + y; }

  // ---------- 渲染：消息流 ----------
  function renderTranscript() {
    transcript.innerHTML = '';
    const inner = document.createElement('div');
    inner.className = 'transcript-inner';
    for (const m of S.messages) {
 const row = document.createElement('div');
 row.className = 'msg-row ' + (m.role === 'user' ? 'user' : 'ai') + (m.proactive ? ' proactive' : '');
      const av = document.createElement('div');
      av.className = 'avatar ' + (m.role === 'user' ? 'user' : 'ai');
      av.textContent = m.role === 'user' ? '我' : 'AI';
 const bub = document.createElement('div');
 bub.className = 'bubble';
 if (m.proactive) {
 const tag = document.createElement('span');
 tag.className = 'proactive-tag';
 tag.textContent = '💬 主动搭话';
 bub.appendChild(tag);
 }
 if (m.locLabel) {
        const tag = document.createElement('span');
        tag.className = 'loc-tag';
        tag.textContent = '📍 ' + m.locLabel;
        bub.appendChild(tag);
      }
      if (m.thumb) {
        const img = document.createElement('img');
        img.className = 'thumb';
        img.src = m.thumb;
        bub.appendChild(img);
      }
      if (m.text) bub.appendChild(document.createTextNode(m.text));
 if (m.cards && m.cards.length) {
 const chip = document.createElement('div');
 chip.className = 'card-chip';
 chip.textContent = '▤ ' + (m.cards.length > 1 ? m.cards.length + ' 张卡片' : m.cards[0].title || '查看卡片');
 chip.onclick = () => openStage(m.cards, 0);
 bub.appendChild(chip);
 }
 // AI 回答底部固定一排动作按钮：有地点就给导航入口
 if (m.role === 'ai' && m.cards && m.cards.length) {
 const actions = document.createElement('div');
 actions.className = 'msg-actions';
 actions.className = 'msg-actions';
 const firstPlace = m.cards
 .map((c, ci) => ({ c, ci }))
 .find(({ c }) => c.type === 'place_list' && c.places && c.places.some((p) => p.lng != null && p.lat != null));
 if (firstPlace) {
 const nav = document.createElement('button');
 nav.className = 'action-btn nav';
 nav.textContent = '🧭 导航去：' + firstPlace.c.places.find((p) => p.lng != null && p.lat != null).name;
 nav.onclick = () => window.__navTo(firstPlace.ci, 0);
 actions.appendChild(nav);
 } else {
 const routeCard = m.cards.find((c) => c.type === 'route');
 if (routeCard) {
 const nav = document.createElement('button');
 nav.className = 'action-btn nav';
 nav.textContent = '🧭 开启导航';
 nav.onclick = () => {
 if (window.__lastNavUrl) window.__openNavPanel(routeCard.title, window.__lastNavUrl);
 };
 actions.appendChild(nav);
 }
 }
 const view = document.createElement('button');
 view.className = 'action-btn';
 view.textContent = '▤ 查看卡片';
 view.onclick = () => openStage(m.cards, 0);
 actions.appendChild(view);
 if (m.text) {
 const vbtn = document.createElement('button');
 vbtn.className = 'action-btn voice-tts';
 vbtn.textContent = S.voiceDefault ? '🔊 用我的声音读' : '🔊 朗读';
 vbtn.onclick = () => {
 if (S.voiceDefault) {
 speakCloned(m.text).catch((e) => { addMessage('ai', '朗读失败：' + e.message); });
 } else {
 speakSystem(m.text);
 }
 };
 actions.appendChild(vbtn);
 }
 bub.appendChild(actions);
 }
      row.appendChild(av);
      row.appendChild(bub);
      inner.appendChild(row);
    }
    if (S.working) {
      const t = document.createElement('div');
      t.className = 'typing';
      t.innerHTML = '<i></i><i></i><i></i>';
      inner.appendChild(t);
    }
    transcript.appendChild(inner);
    transcript.scrollTop = transcript.scrollHeight;
  }

  function addMessage(role, text, extra) {
    S.messages.push(Object.assign({ role, text, locLabel: null, thumb: null, cards: null }, extra));
    renderTranscript();
  }

 // ---------- 请求头覆盖（对应 applyOverrides） ----------
 function applyHeaders(headers) {
 const model = normalizeModel(S.modelPreset === 'custom' ? S.customModel : S.modelPreset);
 if (model !== 'deepseek-chat') {
 headers['X-LifeAssistant-Model'] = model;
 }
  if (S.apiKey) headers['X-LifeAssistant-Api-Key'] = S.apiKey;
  if (S.noFilter) headers['X-LifeAssistant-NoFilter'] = '1';
}

  // ---------- 聊天 ----------
  async function send(text) {
    text = (text || input.value).trim();
    if (!text || S.working) return;
    input.value = '';
    autoGrow();
    const locLabel = S.location.label || (S.location.latitude + ', ' + S.location.longitude);
    addMessage('user', text, { locLabel });
    S.working = true;
    renderTranscript();
    try {
      const headers = { 'Content-Type': 'application/json' };
      applyHeaders(headers);
      const resp = await fetch(S.baseURL + '/api/v1/chat', {
        method: 'POST',
        headers,
        body: JSON.stringify({
          text,
          location: { latitude: S.location.latitude, longitude: S.location.longitude },
          address: S.location.label || null,
          session_id: S.sessionId
        })
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error('服务端 ' + resp.status + '：' + (data.detail || ''));
 S.sessionId = data.session_id || S.sessionId;
 const cards = data.cards || [];
 addMessage('ai', data.reply || '（无回复）', { cards });
 if (cards.length) openStage(cards, 0);
 if (S.autoSpeak && data.speech) speak(data.speech);
 loadSessionList();
 } catch (e) {
 addMessage('ai', '请求失败：' + e.message);
    } finally {
      S.working = false;
      renderTranscript();
    }
  }

  // ---------- 图片 ----------
  function attachImage() { $('fileInput').click(); }

  $('fileInput').addEventListener('change', (ev) => {
    const file = ev.target.files[0];
    ev.target.value = '';
    if (!file) return;
    compressImage(file, 1280).then((blob) => {
      S.pendingFile = blob;
      const url = URL.createObjectURL(blob);
      $('pendingImg').src = url;
      $('imageQuestion').value = '';
      $('imageSheet').hidden = false;
    });
  });

  function compressImage(file, maxSide) {
    return new Promise((resolve) => {
      const img = new Image();
      img.onload = () => {
        let { width, height } = img;
        const scale = Math.min(1, maxSide / Math.max(width, height));
        width = Math.round(width * scale);
        height = Math.round(height * scale);
        const canvas = document.createElement('canvas');
        canvas.width = width;
        canvas.height = height;
        canvas.getContext('2d').drawImage(img, 0, 0, width, height);
        canvas.toBlob((b) => resolve(b || file), 'image/jpeg', 0.82);
      };
      img.src = URL.createObjectURL(file);
    });
  }

  async function sendImage() {
    const file = S.pendingFile;
    const question = $('imageQuestion').value.trim();
    if (!file) return;
    $('imageSheet').hidden = true;
    addMessage('user', question || '（图片）', { thumb: $('pendingImg').src });
    S.working = true;
    renderTranscript();
    try {
      const fd = new FormData();
      fd.append('file', file, 'photo.jpg');
      fd.append('question', question);
      fd.append('session_id', S.sessionId);
      fd.append('latitude', String(S.location.latitude));
      fd.append('longitude', String(S.location.longitude));
      if (S.location.label) fd.append('address', S.location.label);
      const headers = {};
      applyHeaders(headers);
      const resp = await fetch(S.baseURL + '/api/v1/analyze-image', { method: 'POST', headers, body: fd });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error('服务端 ' + resp.status + '：' + (data.detail || ''));
      const cards = data.cards || [];
      addMessage('ai', data.reply || '（无回复）', { cards });
      if (cards.length) openStage(cards, 0);
      if (S.autoSpeak && data.speech) speak(data.speech);
    } catch (e) {
      addMessage('ai', '请求失败：' + e.message);
    } finally {
      S.pendingFile = null;
      S.working = false;
      renderTranscript();
    }
  }

  // ---------- 卡片舞台 ----------
  function openStage(cards, index) {
    if (!cards || !cards.length) return;
    S.stage = { cards, index: Math.max(0, Math.min(index, cards.length - 1)) };
    renderStage();
    $('stage').hidden = false;
  }
  function closeStage() { $('stage').hidden = true; }

  function renderStage() {
    const card = S.stage.cards[S.stage.index];
    $('stageCard').innerHTML = renderCard(card);
    const dots = $('stageDots');
    dots.innerHTML = '';
    S.stage.cards.forEach((_, i) => {
      const d = document.createElement('i');
      if (i === S.stage.index) d.className = 'cur';
      dots.appendChild(d);
    });
    const multi = S.stage.cards.length > 1;
    $('stagePager').hidden = !multi;
    $('stagePrev').disabled = S.stage.index === 0;
    $('stageNext').disabled = S.stage.index >= S.stage.cards.length - 1;
  }

  function glyphFor(type) {
    if (type === 'place_list') return '⌖';
    if (type === 'route') return '⇶';
    if (type === 'image_analysis') return '▣';
    return '✦';
  }

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, (c) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  function renderCard(card) {
    const head =
      '<div class="card-head">' +
      '<div class="glyph">' + glyphFor(card.type) + '</div>' +
      '<div><h2>' + esc(card.title) + '</h2>' +
      (card.subtitle ? '<div class="sub">' + esc(card.subtitle) + '</div>' : '') +
      '</div><button class="card-close" onclick="window.__closeStage()">✕</button></div>';
    let body = '';
 if (card.type === 'place_list') {
  body = (card.places || []).map((p, pi) =>
   '<div class="place-item">' +
   '<div class="row1"><span class="name">' + esc(p.name) + '</span>' +
   (p.rating != null ? '<span class="rating">★ ' + p.rating + '</span>' : '') +
   (p.distance_m != null ? '<span class="distance">' + fmtDistance(p.distance_m) + '</span>' : '') +
   '</div>' +
   (p.address ? '<div class="addr">' + esc(p.address) + '</div>' : '') +
   (p.phone ? '<div class="phone">' + esc(p.phone) + '</div>' : '') +
   (p.lng != null && p.lat != null
    ? '<button class="place-nav-btn" onclick="window.__navTo(' + S.stage.index + ',' + pi + ')">🚗 导航去这里</button>'
    : '') +
   '</div>').join('');
 } else if (card.type === 'route') {
      body = (card.routes || []).map((r) => {
        const modeName = r.mode === 'transit' ? '公交' : r.mode === 'walking' ? '步行' : r.mode === 'driving' ? '驾车' : r.mode;
   return '<div class="route-block">' +
    '<div class="route-head"><span class="mode-badge">' + esc(modeName) + '</span>' +
    '<span class="metrics">' + fmtDistance(r.total_distance_m) + ' · ' + fmtDuration(r.total_duration_s) + fmtMoney(r.cost_yuan) + '</span></div>' +
    (r.legs || []).map((l) =>
     '<div class="leg"><span class="dot"></span><div><div class="leg-text">' + esc(l.instruction) + '</div>' +
     (l.distance_m || l.duration_s ? '<div class="leg-meta">' + fmtDistance(l.distance_m) + ' · ' + fmtDuration(l.duration_s) + '</div>' : '') +
     '</div></div>').join('') +
    (r.summary ? '<div class="route-summary">' + esc(r.summary) + '</div>' : '') +
    '<button class="place-nav-btn" onclick="if(window.__lastNavUrl)window.__openNavPanel(\'' + esc(card.title) + '\',window.__lastNavUrl)">🧭 开启导航</button>' +
    '</div>';
      }).join('');
    } else if (card.type === 'image_analysis' && card.image) {
      body = (card.image.ocr_text ? '<div class="img-ocr">识别文字：' + esc(card.image.ocr_text) + '</div>' : '') +
        '<div class="img-analysis">' + esc(card.image.analysis) + '</div>' +
        (card.image.tags && card.image.tags.length ? '<div class="img-tags">' + card.image.tags.map((t) => '<span>' + esc(t) + '</span>').join('') + '</div>' : '');
    } else {
      body = '<div class="text-card-body">' + esc(card.text || card.speech || '') + '</div>';
    }
    return head + body;
  }
  window.__closeStage = closeStage;

 // ---------- 点选导航：POI -> 路线卡 + 软件内嵌导航面板 ----------
 window.__navTo = async function (cardIndex, placeIndex) {
  const card = S.stage.cards[cardIndex];
  const p = card && card.places && card.places[placeIndex];
  if (!p || p.lng == null || p.lat == null) return;
  const navBtn = document.querySelector('.place-nav-btn');
  if (navBtn) navBtn.textContent = '规划路线中…';
  try {
   const headers = { 'Content-Type': 'application/json' };
   applyHeaders(headers);
   const resp = await fetch(S.baseURL + '/api/v1/navigate', {
    method: 'POST',
    headers,
    body: JSON.stringify({
     origin: { latitude: S.location.latitude, longitude: S.location.longitude },
     dest: { latitude: p.lat, longitude: p.lng },
     dest_name: p.name,
     mode: 'driving',
     session_id: S.sessionId
    })
   });
   const data = await resp.json().catch(() => ({}));
   if (!resp.ok) throw new Error('服务端 ' + resp.status + '：' + (data.detail || ''));
   if (data.cards && data.cards.length) {
    S.stage.cards.push.apply(S.stage.cards, data.cards);
    S.stage.index = S.stage.cards.length - 1;
    renderStage();
   }
   window.__lastNavUrl = data.amap_web_url || '';
   if (data.amap_web_url) window.__openNavPanel(p.name, data.amap_web_url);
  } catch (e) {
   addMessage('ai', '导航规划失败：' + e.message);
  }
 };

 window.__lastNavUrl = '';
 window.__openNavPanel = function (title, url) {
  $('navTitle').textContent = '🧭 ' + (title || '导航');
  $('navFrame').src = url;
  $('navPanel').hidden = false;
 };
 window.__closeNavPanel = function () {
  $('navPanel').hidden = true;
  $('navFrame').src = 'about:blank';
 };
 $('navClose').addEventListener('click', window.__closeNavPanel);

 // ---------- 语音播报 ----------
 let ttsAudio = null;
 function speak(text) {
 if (S.voiceDefault) {
 speakCloned(text).catch(() => speakSystem(text));
 } else {
 speakSystem(text);
 }
 }
 function speakSystem(text) {
 try {
 speechSynthesis.cancel();
 const u = new SpeechSynthesisUtterance(text);
 u.lang = 'zh-CN';
 u.rate = 1.0;
 speechSynthesis.speak(u);
 } catch (e) { /* 忽略 */ }
 }
 async function speakCloned(text) {
 const headers = { 'Content-Type': 'application/json' };
 applyHeaders(headers);
 const resp = await fetch(S.baseURL + '/api/v1/voice/tts', {
 method: 'POST', headers,
 body: JSON.stringify({ text, voice_id: S.voiceDefault })
 });
 const data = await resp.json().catch(() => ({}));
 if (!resp.ok) throw new Error(data.detail || resp.status);
 playAudio(S.baseURL + data.url);
 }
 function playAudio(url) {
 if (ttsAudio) { ttsAudio.pause(); ttsAudio = null; }
 ttsAudio = new Audio(url);
 ttsAudio.play().catch(() => {});
 }
 function toggleSpeaker() {
 S.autoSpeak = !S.autoSpeak;
 localStorage.setItem('la.autoSpeak', S.autoSpeak ? '1' : '0');
 $('speakerBtn').classList.toggle('on', S.autoSpeak);
 if (!S.autoSpeak) {
 speechSynthesis.cancel();
 if (ttsAudio) { ttsAudio.pause(); ttsAudio = null; }
 }
 }

  // ---------- 我的声音面板 ----------
 let mediaRecorder = null;
 let mediaChunks = [];
 let recordTimerId = null;
 let recordStartTs = 0;

 function openVoiceSheet() {
 $('voiceSheet').hidden = false;
 checkVoiceHealth();
 loadVoiceList();
 }
 function closeVoiceSheet() { $('voiceSheet').hidden = true; }

 async function checkVoiceHealth() {
 const st = $('voiceStatus');
 st.className = 'voice-status';
 st.textContent = '检查语音服务…';
 try {
 const resp = await fetch(S.baseURL + '/api/v1/voice/health');
 const data = await resp.json().catch(() => ({}));
 S.voiceVsReady = !!data.vs_ready;
 st.className = 'voice-status ' + (data.vs_ready ? 'ok' : 'bad');
 st.textContent = data.vs_ready
 ? 'VoiceStudio 已就绪，可以提取/录制/试听。'
 : 'VoiceStudio 还没启动：先开语音服务再回来。';
 } catch (e) {
 S.voiceVsReady = false;
 st.className = 'voice-status bad';
 st.textContent = '连不上语音接口：' + e.message;
 }
 }

 async function loadVoiceList() {
 const list = $('voiceList');
 try {
 const resp = await fetch(S.baseURL + '/api/v1/voice/list');
 const data = await resp.json().catch(() => ({}));
 const voices = data.voices || [];
 if (!voices.length) {
 list.innerHTML = '<div class="voice-empty">还没有声音。粘贴视频链接提取，或录制你自己的声音。</div>';
 return;
 }
 list.innerHTML = '';
 for (const v of voices) {
 const item = document.createElement('div');
 item.className = 'voice-item' + (v.voice_id === S.voiceDefault ? ' cur' : '');
 const name = document.createElement('div');
 name.className = 'v-name';
 name.innerHTML = '<div>' + esc(v.name) + '</div><div class="v-src">' + (v.source === 'record' ? '我录制的声音' : '视频提取') + '</div>';
 const acts = document.createElement('div');
 acts.className = 'v-actions';
 const play = document.createElement('button');
 play.className = 'v-btn';
 play.textContent = '▶ 试听';
 play.onclick = (ev) => { ev.stopPropagation(); playAudio(S.baseURL + v.preview_url); };
 const use = document.createElement('button');
 use.className = 'v-btn use';
 use.textContent = v.voice_id === S.voiceDefault ? '✔ 使用中' : '用这个声音';
 use.onclick = (ev) => {
 ev.stopPropagation();
 S.voiceDefault = v.voice_id;
 localStorage.setItem('la.voiceDefault', v.voice_id);
 loadVoiceList();
 addMessage('ai', '已切换默认声音：' + v.name + '。之后的回复都会用它朗读。');
 };
 acts.appendChild(play);
 acts.appendChild(use);
 item.appendChild(name);
 item.appendChild(acts);
 list.appendChild(item);
 }
 } catch (e) {
 list.innerHTML = '<div class="voice-empty">加载失败：' + esc(e.message) + '</div>';
 }
 }

 function switchVoiceTab(tab) {
 document.querySelectorAll('.voice-tab').forEach((b) => b.classList.toggle('cur', b.dataset.tab === tab));
 $('voicePaneLink').hidden = tab !== 'link';
 $('voicePaneRecord').hidden = tab !== 'record';
 }

 async function extractFromLink() {
 const url = $('voiceLink').value.trim();
 if (!url) return;
 const prog = $('voiceProgress');
 prog.hidden = false;
 prog.textContent = '提交中…';
 try {
 const headers = { 'Content-Type': 'application/json' };
 applyHeaders(headers);
 const resp = await fetch(S.baseURL + '/api/v1/voice/extract', {
 method: 'POST', headers, body: JSON.stringify({ url })
 });
 const data = await resp.json().catch(() => ({}));
 if (!resp.ok) throw new Error(data.detail || resp.status);
 pollExtractJob(data.job_id, prog);
 } catch (e) {
 prog.textContent = '提取失败：' + e.message;
 }
 }

 async function pollExtractJob(jid, prog) {
 for (let i = 0; i < 240; i++) {
 await new Promise((r) => setTimeout(r, 2000));
 try {
 const resp = await fetch(S.baseURL + '/api/v1/voice/job/' + jid);
 const j = await resp.json().catch(() => ({}));
 prog.textContent = j.progress || j.status || '处理中…';
 if (j.status === 'done') {
 prog.textContent = '提取完成，已加入声音列表。点试听，或用它读回复。';
 $('voiceLink').value = '';
 loadVoiceList();
 return;
 }
 if (j.status === 'failed') { prog.textContent = '提取失败：' + (j.error || '未知错误'); return; }
 } catch (e) { /* 轮询失败继续 */ }
 }
 prog.textContent = '处理超时。';
 }

 async function startRecord() {
 if (!navigator.mediaDevices) { addMessage('ai', '当前环境不支持麦克风录制。'); return; }
 let stream;
 try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }); }
 catch (e) { addMessage('ai', '麦克风不可用：' + e.message); return; }
 mediaChunks = [];
 mediaRecorder = new MediaRecorder(stream);
 mediaRecorder.ondataavailable = (ev) => { if (ev.data.size) mediaChunks.push(ev.data); };
 mediaRecorder.onstop = () => {
 stream.getTracks().forEach((t) => t.stop());
 clearInterval(recordTimerId);
 const blob = new Blob(mediaChunks, { type: mediaRecorder.mimeType || 'audio/webm' });
 uploadRecord(blob);
 };
 mediaRecorder.start();
 recordStartTs = Date.now();
 $('recordBtn').textContent = '⏹ 停止（10 秒）';
 recordTimerId = setInterval(() => {
 const left = 10 - Math.floor((Date.now() - recordStartTs) / 1000);
 $('recordTimer').textContent = left > 0 ? left + 's' : '';
 if (Date.now() - recordStartTs >= 10000) stopRecord();
 }, 250);
 }

 function stopRecord() {
 if (mediaRecorder && mediaRecorder.state !== 'inactive') mediaRecorder.stop();
 $('recordBtn').textContent = '🎤 开始录制';
 $('recordTimer').textContent = '';
 }

 async function uploadRecord(blob) {
 const prog = $('recordProgress');
 prog.hidden = false;
 prog.textContent = '正在克隆你的声音…';
 try {
 const fd = new FormData();
 fd.append('file', blob, 'record.webm');
 fd.append('transcript', ($('readScript')?.textContent || '').trim());
 const resp = await fetch(S.baseURL + '/api/v1/voice/record', { method: 'POST', body: fd });
 const data = await resp.json().catch(() => ({}));
 prog.textContent = resp.ok
 ? '录制完成！你的声音已加入列表。'
 : '录制失败：' + (data.detail || resp.status);
 if (resp.ok) loadVoiceList();
 } catch (e) {
 prog.textContent = '录制失败：' + e.message;
 }
 }

 // ---------- 语音输入（Web Speech API） ----------
  let rec = null;
  function toggleVoice() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
      addMessage('ai', '当前系统不支持语音识别（需联网的 Chromium 语音服务）。直接打字也行。');
      return;
    }
    if (S.listening) {
      S.listening = false;
      if (rec) rec.stop();
      $('micBtn').classList.remove('listening');
      $('voiceHint').classList.remove('show');
      return;
    }
    S.listening = true;
    $('micBtn').classList.add('listening');
    $('voiceHint').classList.add('show');
    rec = new SR();
    rec.lang = 'zh-CN';
    rec.continuous = true;
    rec.interimResults = true;
    rec.onresult = (ev) => {
      let finalText = '';
      for (let i = ev.resultIndex; i < ev.results.length; i++) {
        if (ev.results[i].isFinal) finalText += ev.results[i][0].transcript;
      }
      if (finalText) input.value = (input.value + finalText).trim();
    };
    rec.onend = () => {
      S.listening = false;
      $('micBtn').classList.remove('listening');
      $('voiceHint').classList.remove('show');
      if (input.value.trim()) send();
    };
    rec.onerror = () => { rec.onend(); };
    rec.start();
  }

  // ---------- 定位 ----------
  function locate() {
    S.location.status = 'locating';
    updateLocUI('定位中…');
    if (!navigator.geolocation) { locFallback('无定位服务'); return; }
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        S.location.latitude = pos.coords.latitude;
        S.location.longitude = pos.coords.longitude;
        S.location.label = pos.coords.latitude.toFixed(4) + ', ' + pos.coords.longitude.toFixed(4);
        S.location.status = 'ready';
        updateLocUI(S.location.label);
      },
      (err) => locFallback('定位不可用'),
      { enableHighAccuracy: true, timeout: 8000 }
    );
  }
  function locFallback(reason) {
    S.location.status = 'failed';
    S.location.latitude = 31.2304;
    S.location.longitude = 121.4737;
    S.location.label = '';
    updateLocUI(reason + '（已用上海默认坐标，可在设置里改）');
  }
  function updateLocUI(text) {
    $('locText').textContent = text;
    $('locDot').className = 'loc-dot ' + (S.location.status === 'ready' ? 'ready' : S.location.status === 'locating' ? 'locating' : S.location.status === 'failed' ? 'failed' : '');
  }

  // ---------- 会话管理 ----------
 async function loadSessionList() {
 try {
 const resp = await fetch(S.baseURL + '/api/v1/sessions');
 if (!resp.ok) return [];
 const data = await resp.json();
 renderSessionList(data.sessions || []);
 return data.sessions || [];
 } catch (e) { return []; }
 }
 function renderSessionList(sessions) {
 const box = $('sessionList');
 box.innerHTML = '';
 if (!sessions.length) {
 const d = document.createElement('div');
 d.className = 'side-empty';
 d.textContent = '还没有会话，点 ＋ 新建';
 box.appendChild(d);
 return;
 }
 for (const s of sessions) {
 const it = document.createElement('div');
 it.className = 'sess-item' + (s.id === S.sessionId ? ' cur' : '');
 it.dataset.sid = s.id;
 const t = document.createElement('span');
 t.className = 'sess-title';
 t.textContent = s.title || '新会话';
 t.title = s.title || '新会话';
 const del = document.createElement('button');
 del.className = 'sess-del';
 del.textContent = '✕';
 del.title = '删除此会话';
 del.addEventListener('click', (ev) => { ev.stopPropagation(); deleteSessionItem(s.id); });
 it.appendChild(t);
 it.appendChild(del);
 it.addEventListener('click', () => switchSession(s.id));
 box.appendChild(it);
 }
 }
 async function switchSession(sid) {
 try {
 const resp = await fetch(S.baseURL + '/api/v1/sessions/' + encodeURIComponent(sid));
 if (!resp.ok) return;
 const data = await resp.json();
 S.sessionId = sid;
 S.messages = (data.messages || []).map((m) => ({
 role: m.role === 'user' ? 'user' : 'ai',
 text: m.text,
 locLabel: null, thumb: null, cards: null
 }));
 renderTranscript();
 renderSessionList(await loadSessionList());
 } catch (e) { /* 静默 */ }
 }
 async function newSession() {
 try {
 const resp = await fetch(S.baseURL + '/api/v1/sessions', {
 method: 'POST',
 headers: { 'Content-Type': 'application/json' },
 body: JSON.stringify({ title: '' })
 });
 const data = await resp.json().catch(() => ({}));
 if (!resp.ok) return;
 S.sessionId = data.id || S.sessionId;
 S.messages = [];
 addMessage('ai', '你好，我是生活助手。问我路线、周边或拍张图，结果会以卡片形式弹出。');
 renderSessionList(await loadSessionList());
 } catch (e) { /* 静默 */ }
 }
 async function deleteSessionItem(sid) {
 try {
 await fetch(S.baseURL + '/api/v1/sessions/' + encodeURIComponent(sid), { method: 'DELETE' });
 const rest = await loadSessionList();
 if (sid === S.sessionId) {
 const next = rest[0];
 if (next) { await switchSession(next.id); }
 else {
 S.sessionId = 'local';
 S.messages = [];
 addMessage('ai', '你好，我是生活助手。问我路线、周边或拍张图，结果会以卡片形式弹出。');
 renderSessionList(rest);
 }
 } else {
 renderSessionList(rest);
 }
 } catch (e) { /* 静默 */ }
 }
 async function initSessions() {
 const list = await loadSessionList();
 if (list.length) {
 await switchSession(list[0].id);
 } else {
 await newSession();
 }
 }

 // ---------- 设置 ----------
function openSettings() {
 $('cfgBaseURL').value = S.baseURL;
 const presetOpts = ['deepseek-v4-flash', 'deepseek-v4-pro'];
 $('cfgModel').value = presetOpts.includes(S.modelPreset) ? S.modelPreset : 'custom';
 $('cfgCustomModel').value = S.modelPreset === 'custom' ? S.customModel : '';
 $('cfgCustomModel').hidden = $('cfgModel').value !== 'custom';
 $('cfgApiKey').value = S.apiKey;
 $('cfgNoFilter').checked = S.noFilter;
 $('healthResult').textContent = '';
 $('healthResult').className = 'health-line';
 $('settingsSheet').hidden = false;
 refreshPojia();
 loadProactiveState();
 loadSatelliteState();
 }
 async function loadSatelliteState() {
 try {
 const resp = await fetch(S.baseURL + '/api/v1/satellite/state');
 const data = await resp.json().catch(() => ({}));
 S.satellite = !!data.enabled;
 $('cfgSatellite').checked = S.satellite;
 } catch (e) { /* 后端不支持时保持默认 */ }
 }

 // ---------- 主动搭话 ----------
 async function loadProactiveState() {
 try {
 const resp = await fetch(S.baseURL + '/api/v1/assistant/proactive');
 const data = await resp.json();
 $('cfgProactive').checked = !!data.enabled;
 } catch (e) { /* 后端不支持时保持默认 */ }
 }

 async function pollProactive() {
 if (S.working) return;
 try {
 const resp = await fetch(S.baseURL + '/api/v1/assistant/proactive?mark_read=1');
 if (!resp.ok) return;
 const data = await resp.json();
 for (const it of data.items || []) {
 addMessage('ai', it.text, { proactive: true });
 if (S.autoSpeak) speak(it.text);
 }
 } catch (e) { /* 静默 */ }
 }
 // ---------- 软件内卫星地图（纯 JS 自绘：Esri 卫星瓦片 + 高德附近全类型 POI） ----------
 const TILE_SOURCES = [
 (z, x, y) => 'https://webst0' + (1 + ((x + y) % 4)) + '.is.autonavi.com/appmaptile?style=6&x=' + x + '&y=' + y + '&z=' + z,
 (z, x, y) => 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/' + z + '/' + y + '/' + x,
];
 const MAP_COLORS = ['#FF6B6B', '#FFA94D', '#FFD43B', '#69DB7C', '#38D9A9', '#4DABF7',
 '#748FFC', '#B197FC', '#F783AC', '#FF8787', '#63E6BE', '#A9E34B'];
 const M = { z: 15, lng: 121.4737, lat: 31.2304, pois: [], drag: null, balloon: null };
 function mapTypeColor(name) {
 let h = 0;
 for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0;
 return MAP_COLORS[h % MAP_COLORS.length];
 }
 function lngLatToTile(lng, lat, z) {
 const n = Math.pow(2, z);
 const x = (lng + 180) / 360 * n;
 const sin = Math.sin(lat * Math.PI / 180);
 const y = (0.5 - Math.log((1 + sin) / (1 - sin)) / (4 * Math.PI)) * n;
 return { x, y };
 }
 function tileToLngLat(tx, ty, z) {
 const n = Math.pow(2, z);
 const lng = tx / n * 360 - 180;
 const lat = Math.atan(Math.sinh(Math.PI * (1 - 2 * ty / n))) * 180 / Math.PI;
 return { lng, lat };
 }
 function mapSize() {
 const wrap = $('mapWrap');
 return { w: wrap.clientWidth, h: wrap.clientHeight };
 }
 function renderTiles() {
 const wrap = $('mapTiles');
 const { w, h } = mapSize();
 const z = M.z;
 const c = lngLatToTile(M.lng, M.lat, z);
 const cx = c.x * 256, cy = c.y * 256;
 const n = Math.pow(2, z);
 const x0 = Math.max(0, Math.floor((cx - w / 2) / 256) - 1);
 const x1 = Math.min(n - 1, Math.floor((cx + w / 2) / 256) + 1);
 const y0 = Math.max(0, Math.floor((cy - h / 2) / 256) - 1);
 const y1 = Math.min(n - 1, Math.floor((cy + h / 2) / 256) + 1);
 wrap.innerHTML = '';
 for (let tx = x0; tx <= x1; tx++) {
 for (let ty = y0; ty <= y1; ty++) {
 const t = document.createElement('img');
 t.className = 'map-tile';
 t.alt = '';
 t.draggable = false;
 t.style.left = (tx * 256 - (cx - w / 2)) + 'px';
 t.style.top = (ty * 256 - (cy - h / 2)) + 'px';
 t.dataset.src = '0';
 t.src = TILE_SOURCES[0](z, tx, ty);
 t.addEventListener('error', () => {
 const s = +(t.dataset.src || 0) + 1;
 if (s < TILE_SOURCES.length) {
 t.dataset.src = String(s);
 t.src = TILE_SOURCES[s](z, tx, ty);
 } else {
 t.classList.add('err');
 }
 });
 wrap.appendChild(t);
 }
 }
 }
 function renderMapMarkers() {
 const cv = $('mapCanvas');
 const { w, h } = mapSize();
 const dpr = window.devicePixelRatio || 1;
 cv.width = w * dpr; cv.height = h * dpr;
 const ctx = cv.getContext('2d');
 ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
 ctx.clearRect(0, 0, w, h);
 const z = M.z;
 const c = lngLatToTile(M.lng, M.lat, z);
 const cx = c.x * 256, cy = c.y * 256;
 // 用户位置：中心蓝点 + 呼吸圈
 ctx.beginPath();
 ctx.arc(w / 2, h / 2, 14, 0, Math.PI * 2);
 ctx.fillStyle = 'rgba(56, 138, 255, 0.22)';
 ctx.fill();
 ctx.beginPath();
 ctx.arc(w / 2, h / 2, 6, 0, Math.PI * 2);
 ctx.fillStyle = '#388AFF';
 ctx.fill();
 ctx.strokeStyle = '#FFFFFF';
 ctx.lineWidth = 2.5;
 ctx.stroke();
 // POI 标记
 for (const p of M.pois) {
 const t = lngLatToTile(p.lng, p.lat, z);
 const px = t.x * 256 - (cx - w / 2);
 const py = t.y * 256 - (cy - h / 2);
 if (px < -20 || px > w + 20 || py < -20 || py > h + 20) continue;
 const col = mapTypeColor(p.type_name);
 ctx.beginPath();
 ctx.arc(px, py, 5.5, 0, Math.PI * 2);
 ctx.fillStyle = col;
 ctx.fill();
 ctx.strokeStyle = 'rgba(0,0,0,0.55)';
 ctx.lineWidth = 1.4;
 ctx.stroke();
 if (M.z >= 14) {
 ctx.font = '11px "Microsoft YaHei", sans-serif';
 ctx.fillStyle = 'rgba(0,0,0,0.7)';
 ctx.fillText(p.name.length > 8 ? p.name.slice(0, 8) + '…' : p.name, px + 8, py + 4);
 }
 }
 }
 function renderMapAll() { renderTiles(); renderMapMarkers(); }
 function mapPoiAt(x, y) {
 const { w, h } = mapSize();
 const z = M.z;
 const c = lngLatToTile(M.lng, M.lat, z);
 const cx = c.x * 256, cy = c.y * 256;
 let best = null, bd = 14;
 for (const p of M.pois) {
 const t = lngLatToTile(p.lng, p.lat, z);
 const px = t.x * 256 - (cx - w / 2);
 const py = t.y * 256 - (cy - h / 2);
 const d = Math.hypot(px - x, py - y);
 if (d < bd) { bd = d; best = p; }
 }
 return best;
 }
 function showBalloon(p, px, py) {
 const b = $('mapBalloon');
 b.hidden = false;
 b.style.left = px + 'px';
 b.style.top = py + 'px';
 b.innerHTML = '<div class="mb-name">' + (p.name || '') + '</div>'
 + '<div class="mb-sub">' + (p.type_name || '') + ' · ' + fmtDistance(p.distance_m) + (p.address ? '<br>' + p.address : '') + '</div>';
 }
 function hideBalloon() { $('mapBalloon').hidden = true; }
 function renderMapList() {
 const list = $('mapPoiList');
 const leg = $('mapLegend');
 leg.innerHTML = '';
 list.innerHTML = '';
 const groups = {};
 for (const p of M.pois) (groups[p.type_name] = groups[p.type_name] || []).push(p);
 const names = Object.keys(groups).sort((a, b) => groups[b].length - groups[a].length);
 for (const g of names) {
 const col = mapTypeColor(g);
 const chip = document.createElement('span');
 chip.className = 'map-chip';
 chip.innerHTML = '<i style="background:' + col + '"></i>' + g;
 leg.appendChild(chip);
 const title = document.createElement('div');
 title.className = 'map-group-title';
 title.textContent = g + '（' + groups[g].length + '）';
 list.appendChild(title);
 for (const p of groups[g]) {
 const it = document.createElement('button');
 it.className = 'map-poi';
 it.innerHTML = '<span class="mp-dot" style="background:' + col + '"></span>'
 + '<span class="mp-name">' + (p.name || '') + '</span>'
 + '<span class="mp-dist">' + fmtDistance(p.distance_m) + '</span>';
 it.addEventListener('click', () => {
 M.lng = p.lng; M.lat = p.lat;
 renderMapAll();
 const { w, h } = mapSize();
 showBalloon(p, w / 2, h / 2 - 8);
 });
 list.appendChild(it);
 }
 }
 $('mapStatus').textContent = '附近 ' + M.pois.length + ' 家 · 半径 3 km · 点标记或列表定位';
 }
async function loadMapPois() {
 $('mapStatus').textContent = '加载附近数据…';
 const q = '?lat=' + M.lat + '&lng=' + M.lng + '&radius=3000';
 const bases = [S.baseURL || location.origin, location.origin];
 for (const base of bases) {
 try {
 const ctrl = new AbortController();
 const timer = setTimeout(() => ctrl.abort(), 12000);
 const resp = await fetch(base + '/api/v1/satellite/nearby' + q, { signal: ctrl.signal });
 clearTimeout(timer);
 const data = await resp.json().catch(() => ({}));
 if (!resp.ok) throw new Error(data.detail || ('HTTP ' + resp.status));
 M.pois = data.pois || [];
 renderMapList();
 renderMapAll();
 return;
 } catch (e) { /* 换源重试 */ }
 }
 M.pois = [];
 $('mapStatus').textContent = '附近数据加载失败，检查后端连接';
 renderMapList();
 }
function openMap() {
 if (S.location.status === 'ready') { M.lat = S.location.latitude; M.lng = S.location.longitude; }
 M.z = 15;
 $('mapPanel').hidden = false;
 try { renderMapAll(); } catch (e) { /* 地图渲染失败不阻断数据加载 */ }
 loadMapPois();
 }
 function closeMap() { $('mapPanel').hidden = true; hideBalloon(); }
 function mapZoomIn() { M.z = Math.min(18, M.z + 1); renderMapAll(); }
 function mapZoomOut() { M.z = Math.max(3, M.z - 1); renderMapAll(); }
 function mapRecenter() {
 if (S.location.status !== 'ready') { locate(); }
 M.lat = S.location.latitude; M.lng = S.location.longitude;
 renderMapAll();
 }
 function bindMap() {
 const wrap = $('mapWrap');
 wrap.addEventListener('mousedown', (ev) => {
 M.drag = { x: ev.clientX, y: ev.clientY };
 });
 window.addEventListener('mousemove', (ev) => {
 if (!M.drag) return;
 const { w, h } = mapSize();
 const dx = ev.clientX - M.drag.x, dy = ev.clientY - M.drag.y;
 M.drag = { x: ev.clientX, y: ev.clientY };
 const z = M.z;
 const c = lngLatToTile(M.lng, M.lat, z);
 const nx = c.x * 256 - dx, ny = c.y * 256 - dy;
 const ll = tileToLngLat(nx / 256, ny / 256, z);
 M.lng = ll.lng; M.lat = ll.lat;
 hideBalloon();
 renderMapAll();
 });
 window.addEventListener('mouseup', () => { M.drag = null; });
 wrap.addEventListener('wheel', (ev) => {
 ev.preventDefault();
 if (ev.deltaY < 0) mapZoomIn(); else mapZoomOut();
 }, { passive: false });
 $('mapCanvas').addEventListener('click', (ev) => {
 const rect = $('mapCanvas').getBoundingClientRect();
 const p = mapPoiAt(ev.clientX - rect.left, ev.clientY - rect.top);
 if (p) showBalloon(p, ev.clientX - rect.left, ev.clientY - rect.top);
 else hideBalloon();
 });
 window.addEventListener('resize', () => { if (!$('mapPanel').hidden) renderMapAll(); });
 }

 // ---------- 破甲中心 ----------
 async function refreshPojia() {
 const base = $('cfgBaseURL').value.trim().replace(/\/+$/, '') || S.baseURL;
 const st = $('pojiaStatus');
 st.textContent = '检查中…';
 try {
  const resp = await fetch(base + '/api/v1/pojia/status');
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(data.error || resp.status);
  const marked = data.marked || [];
  const wb = (data.seats || []).find((s) => s.seat === 'workbuddy');
  st.textContent = marked.length
   ? '破甲已开启 · 已注入：' + marked.join('、') + (data.nofilter_global ? ' · 满血无审查【已开启】' : '')
   : '未注入';
  if (data.nofilter_global && !$('cfgNoFilter').checked) {
   $('cfgNoFilter').checked = true;
  }
 } catch (e) {
  st.textContent = '破甲服务不可用：' + e.message;
 }
 }
 async function pojiaInstall() {
 const base = $('cfgBaseURL').value.trim().replace(/\/+$/, '') || S.baseURL;
 const log = $('pojiaLog');
 log.hidden = false;
 log.textContent = '注入中…';
 try {
  const resp = await fetch(base + '/api/v1/pojia/install', {
   method: 'POST',
   headers: { 'Content-Type': 'application/json' },
   body: JSON.stringify({ seats: ['workbuddy'], topic: '满血无审查', nofilter: true }),
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(data.error || resp.status);
  const lines = data.log || [];
  log.textContent = '注入完成：\n' + lines.join('\n');
  if ($('cfgNoFilter').checked) {
   S.noFilter = true;
   localStorage.setItem('la.noFilter', '1');
  }
  refreshPojia();
 } catch (e) {
  log.textContent = '注入失败：' + e.message;
 }
 }
 async function pojiaUninstall() {
 const base = $('cfgBaseURL').value.trim().replace(/\/+$/, '') || S.baseURL;
 const log = $('pojiaLog');
 log.hidden = false;
 log.textContent = '回滚中…';
 try {
  const resp = await fetch(base + '/api/v1/pojia/uninstall', { method: 'POST' });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(data.error || resp.status);
  log.textContent = '已回滚：\n' + (data.log || []).join('\n');
  refreshPojia();
 } catch (e) {
  log.textContent = '回滚失败：' + e.message;
 }
 }
  $('cfgModel').addEventListener('change', () => {
    $('cfgCustomModel').hidden = $('cfgModel').value !== 'custom';
  });
  async function testConn() {
    const base = $('cfgBaseURL').value.trim().replace(/\/+$/, '');
    const hl = $('healthResult');
    hl.textContent = '测试中…';
    hl.className = 'health-line';
    try {
      const headers = {};
      applyHeaders(headers);
      const resp = await fetch(base + '/health', { headers });
      const data = await resp.json().catch(() => ({}));
      if (resp.ok) {
        const missing = data.missing || [];
        hl.className = 'health-line ' + (missing.length ? 'bad' : 'ok');
        hl.textContent = missing.length
          ? '已连通，但服务端缺少：' + missing.join('、')
          : '连接正常，密钥已配置' + (data.model ? ' · 模型 ' + data.model : '');
      } else {
        hl.className = 'health-line bad';
        hl.textContent = '服务端返回 ' + resp.status;
      }
    } catch (e) {
      hl.className = 'health-line bad';
      hl.textContent = '连不上：' + e.message;
    }
  }
function saveSettings() {
 S.baseURL = $('cfgBaseURL').value.trim().replace(/\/+$/, '');
 S.modelPreset = $('cfgModel').value === 'custom' ? 'custom' : normalizeModel($('cfgModel').value);
 S.customModel = normalizeModel($('cfgCustomModel').value.trim());
 if (S.modelPreset !== 'custom') S.customModel = '';
 $('cfgCustomModel').value = S.customModel;
  S.apiKey = $('cfgApiKey').value.trim();
  S.noFilter = $('cfgNoFilter').checked;
  localStorage.setItem('la.baseURL', S.baseURL);
  localStorage.setItem('la.modelPreset', S.modelPreset);
  localStorage.setItem('la.customModel', S.customModel);
  localStorage.setItem('la.apiKey', S.apiKey);
 localStorage.setItem('la.noFilter', S.noFilter ? '1' : '0');
 fetch(S.baseURL + '/api/v1/assistant/toggle', {
 method: 'POST',
 headers: { 'Content-Type': 'application/json' },
 body: JSON.stringify({ enabled: $('cfgProactive').checked })
 }).catch(() => {});
 S.satellite = $('cfgSatellite').checked;
 fetch(S.baseURL + '/api/v1/satellite/toggle', {
 method: 'POST',
 headers: { 'Content-Type': 'application/json' },
 body: JSON.stringify({ enabled: S.satellite })
 }).catch(() => {});
 $('settingsSheet').hidden = true;
 }

  // ---------- 输入框自适应 ----------
  function autoGrow() {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 120) + 'px';
  }

  // ---------- 事件绑定 ----------
  $('sendBtn').addEventListener('click', () => send());
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
  });
  input.addEventListener('input', autoGrow);
  $('attachBtn').addEventListener('click', attachImage);
  $('micBtn').addEventListener('click', toggleVoice);
  $('speakerBtn').addEventListener('click', toggleSpeaker);
 $('voiceBtn').addEventListener('click', openVoiceSheet);
 $('voiceClose').addEventListener('click', closeVoiceSheet);
 document.querySelectorAll('.voice-tab').forEach((b) => b.addEventListener('click', () => switchVoiceTab(b.dataset.tab)));
 $('voiceExtractBtn').addEventListener('click', extractFromLink);
 $('recordBtn').addEventListener('click', () => { if (mediaRecorder && mediaRecorder.state !== 'inactive') stopRecord(); else startRecord(); });
  $('settingsBtn').addEventListener('click', openSettings);
  $('locateBtn').addEventListener('click', locate);
  $('imageCancel').addEventListener('click', () => { $('imageSheet').hidden = true; S.pendingFile = null; });
  $('imageSend').addEventListener('click', sendImage);
 $('cfgTest').addEventListener('click', testConn);
 $('cfgSave').addEventListener('click', saveSettings);
 $('pojiaInstall').addEventListener('click', pojiaInstall);
 $('pojiaUninstall').addEventListener('click', pojiaUninstall);
 $('stageBackdrop').addEventListener('click', closeStage);
 $('stagePrev').addEventListener('click', () => { if (S.stage.index > 0) { S.stage.index--; renderStage(); } });
 $('stageNext').addEventListener('click', () => { if (S.stage.index < S.stage.cards.length - 1) { S.stage.index++; renderStage(); } });
 document.addEventListener('keydown', (e) => { if (e.key === 'Escape') { closeStage(); $('settingsSheet').hidden = true; $('imageSheet').hidden = true; closeMap(); } });
 $('sessionNewBtn').addEventListener('click', newSession);
 $('mapBtn').addEventListener('click', openMap);
 $('mapClose').addEventListener('click', closeMap);
 const mc2 = $('mapClose2');
 if (mc2) mc2.addEventListener('click', closeMap);
 $('mapZoomIn').addEventListener('click', mapZoomIn);
 $('mapZoomOut').addEventListener('click', mapZoomOut);
 $('mapRecenter').addEventListener('click', mapRecenter);
 bindMap();

 // ---------- 启动 ----------
 $('speakerBtn').classList.toggle('on', S.autoSpeak);
 initSessions();
 locate();
 pollProactive();
 setInterval(pollProactive, 45000);
})();
