'use strict';
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const RANK = { 3: '3', 4: '4', 5: '5', 6: '6', 7: '7', 8: '8', 9: '9', 10: '10', 11: 'J', 12: 'Q', 13: 'K', 14: 'A', 15: '2', 0: 'JOKER' };
const SYM = { S: '♠', H: '♥', D: '♦', C: '♣' };
const initial = (name) => esc((String(name).replace(/^CPU\s*/, '')[0]) || '?');
const COLORS = ['#d9534f', '#2b8cd6', '#2fa36b', '#c98a1a', '#8e5bd6', '#d64f9e'];
const MODES = {
  open: { name: '通常モード', desc: 'ホストが追加ルールを設定し、全員に公開して対戦' },
  random: { name: 'ランダム秘匿', desc: '追加ルールがランダムで決まり、誰にも公開されない' },
  secret: { name: 'シークレット', desc: '毎ラウンド身分順に効果を1つ選び、好きな数字に割り振る（非公開）' },
};
const isRedBanner = (b) => /革命|切り|ボンバー|スペ3|反則/.test(b);
const RANK_ORDER = [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15];
const params = new URLSearchParams(location.search);

let ws = null;
let RULE_DEFS = [];
let FINISH_DEFS = [];
const S = {
  room: null, game: null, lastSeq: 0, fresh: true, sel: [], bombSel: [], feed: [], lastChat: 0,
  prevHand: new Set(), modal: null, resultClosed: null, secretSel: null, settingsKey: '', autoCreate: params.get('action'),
};

// ---------------------------------------------------------------- 通信
function token() {
  let t = sessionStorage.getItem('dfg_token');
  if (!t) {
    t = Array.from({ length: 24 }, () => Math.floor(Math.random() * 36).toString(36)).join('');
    sessionStorage.setItem('dfg_token', t);
  }
  return t;
}
function send(obj) {
  if (ws && ws.readyState === 1) ws.send(JSON.stringify(obj));
}
function connect() {
  ws = new WebSocket((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws');
  ws.onopen = () => {
    $('#reconnect').classList.add('hidden');
    send({ t: 'hello', token: token() });
  };
  ws.onmessage = (e) => onMsg(JSON.parse(e.data));
  ws.onclose = () => {
    $('#reconnect').classList.remove('hidden');
    S.fresh = true;
    setTimeout(connect, 2000);
  };
}
function onMsg(m) {
  if (m.t === 'rooms') {
    S.rooms = m.rooms;
    if (!S.room) {
      if (S.autoCreate) {
        const action = S.autoCreate;
        S.autoCreate = null;
        params.delete('action');
        history.replaceState(null, '', '?' + params.toString());
        if (action === 'solo') createRoom(true, +params.get('cpus') || 3);
        else createRoom();
      }
      render();
    }
  } else if (m.t === 'state') {
    S.room = m.room;
    S.game = m.game;
    S.clock = m.clock;
    S.clockAt = performance.now();
    if (!m.game) {
      S.lastSeq = 0;
      S.fresh = false;
      S.feed = S.feed.filter((x) => x.chat);
    }
    handleChat();
    handleEvents();
    render();
  } else if (m.t === 'error') {
    toast(m.msg);
  } else if (m.t === 'left') {
    // アプリから起動した場合は、起動時の画面（ランチャー）まで一度に戻る
    const home = params.get('home');
    if (home) {
      location.href = home;
      return;
    }
    // ブラウザから直接参加した場合はタイトル画面（部屋一覧）へ
    S.room = null;
    S.game = null;
    S.feed = [];
    S.lastChat = 0;
    render();
  }
}

// ---------------------------------------------------------------- 共通UI
let toastTimer;
function toast(msg, kind = '') {
  const t = $('#toast');
  t.textContent = msg;
  t.className = 'toast show ' + kind;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.className = 'toast ' + kind), 2600);
}
const bannerQ = [];
let bannerBusy = false;
function banner(text, red) {
  bannerQ.push({ text, red });
  if (!bannerBusy) nextBanner();
}
function nextBanner() {
  const b = bannerQ.shift();
  const el = $('#banner');
  if (!b) { bannerBusy = false; return; }
  bannerBusy = true;
  el.textContent = b.text;
  el.className = 'banner' + (b.red ? ' red' : '') + (b.text.length > 7 ? ' long' : '');
  void el.offsetWidth;
  el.classList.add('show');
  setTimeout(nextBanner, bannerQ.length ? 900 : 1500);
}
function openModal(kind, html, bind) {
  S.modal = kind;
  $('#modal').classList.remove('top');
  $('#modal-box').innerHTML = html;
  $('#modal').classList.remove('hidden');
  if (bind) bind($('#modal-box'));
}
function closeModal() {
  S.modal = null;
  $('#modal').classList.add('hidden');
}
function show(id) {
  for (const s of document.querySelectorAll('.screen')) s.classList.toggle('hidden', '#' + s.id !== id);
}
function cardHTML(c, extra = '') {
  if (c.s === 'X') {
    return `<div class="card joker ${extra}" data-id="${c.id}"><div class="jk"><div class="star">★</div><span>JOKER</span></div></div>`;
  }
  const red = c.s === 'H' || c.s === 'D' ? 'red' : '';
  const r = RANK[c.r];
  const sym = SYM[c.s];
  const center = c.r >= 11 && c.r <= 13 ? `<div class="face">${r}<small>${sym}</small></div>` : `<div class="pip">${sym}</div>`;
  return `<div class="card ${red} ${extra}" data-id="${c.id}"><div class="corner tl"><b>${r}</b><i>${sym}</i></div>${center}<div class="corner br"><b>${r}</b><i>${sym}</i></div></div>`;
}
function myName() {
  const v = $('#in-name').value.trim();
  if (v) localStorage.setItem('dfg_name', v);
  return v || 'プレイヤー';
}

// ---------------------------------------------------------------- 描画振り分け
function render() {
  if (!S.room) {
    show('#screen-title');
    renderTitle();
    if (S.modal) closeModal();
  } else if (S.room.inGame && S.game) {
    show('#screen-game');
    renderGame();
  } else {
    show('#screen-lobby');
    if (S.modal && S.modal !== 'confirm') closeModal();
    renderLobby();
  }
}

// ---------------------------------------------------------------- タイトル
function renderTitle() {
  const list = $('#room-list');
  const rooms = S.rooms || [];
  if (!rooms.length) {
    list.innerHTML = '<div class="empty">公開中の部屋はありません</div>';
    return;
  }
  list.innerHTML = rooms.map((r) => `
    <div class="room-item">
      <div><span class="code">${esc(r.code)}</span>${esc(r.host)} の部屋 <span class="muted">(${r.count}/${r.max})</span>
      ${r.inGame ? '<span class="muted">対戦中</span>' : ''}</div>
      <button class="btn btn-blue" data-code="${esc(r.code)}" ${r.inGame || r.count >= r.max ? 'disabled' : ''} style="padding:5px 12px;font-size:13px">参加</button>
    </div>`).join('');
  list.querySelectorAll('button[data-code]').forEach((b) => (b.onclick = () => joinRoom(b.dataset.code)));
}
function createRoom(solo = false, bots = 3) {
  send({ t: 'create', name: myName(), token: token(), solo, bots });
}
function joinRoom(code) {
  if (!/^\d{4}$/.test(code)) return toast('4桁の部屋番号を入力してください');
  send({ t: 'join', code, name: myName(), token: token() });
}

// ---------------------------------------------------------------- ロビー
function renderLobby() {
  const r = S.room;
  const isHost = r.host === r.me;
  $('#lobby-code').textContent = r.code;
  const ips = params.get('ips');
  $('#lobby-addr').innerHTML = r.solo
    ? '<b style="color:var(--gold)">ソロプレイ</b>（この部屋には他の人は参加できません）'
    : ips
      ? `友達は「部屋に入る」で <b>${esc(ips.split(',').join(' / '))}</b> に接続し、部屋番号 <b>${esc(r.code)}</b> で参加できます`
      : `接続先: <b>${esc(location.host)}</b> ／ 部屋番号 <b>${esc(r.code)}</b>`;
  $('#seat-count').textContent = `${r.members.length}/${r.maxPlayers}`;
  let html = r.members.map((m, i) => `
    <div class="seat ${m.pid === r.me ? 'me' : ''}">
      <div class="avatar" style="--c:${COLORS[i % COLORS.length]};width:38px;height:38px;font-size:16px;border-width:2px">${initial(m.name)}</div>
      <div class="nm">${esc(m.name)}</div>
      ${m.pid === r.host ? '<span class="tag host">ホスト</span>' : ''}
      ${m.bot ? '<span class="tag">CPU</span>' : ''}
      ${!m.online ? '<span class="tag off">切断</span>' : ''}
      ${isHost && m.bot ? `<button class="x" data-rm="${m.pid}" title="外す">✕</button>` : ''}
    </div>`).join('');
  for (let i = r.members.length; i < r.maxPlayers; i++) html += '<div class="seat empty-seat">空席</div>';
  $('#seats').innerHTML = html;
  $('#seats').querySelectorAll('[data-rm]').forEach((b) => (b.onclick = () => send({ t: 'remove_bot', pid: b.dataset.rm })));
  const humans = r.members.filter((m) => !m.bot).length;
  const bots = r.members.length - humans;
  const maxBots = r.maxPlayers - humans;
  $('#bot-row').classList.toggle('hidden', !isHost);
  const bs = $('#sel-bots');
  const opts = Array.from({ length: maxBots + 1 }, (_, k) => `<option value="${k}" ${k === bots ? 'selected' : ''}>${k} 人</option>`).join('');
  if (bs.dataset.key !== opts) {
    bs.dataset.key = opts;
    bs.innerHTML = opts;
  }
  $('#host-only').textContent = isHost ? '' : '（ホストが設定します）';

  const key = JSON.stringify([r.settings, isHost]);
  if (key !== S.settingsKey) {
    S.settingsKey = key;
    renderSettings(r.settings, isHost);
  }
  const st = $('#btn-start');
  st.disabled = !isHost || r.members.length < 2;
  st.textContent = isHost ? (r.members.length < 2 ? '2人以上で開始できます' : '対戦開始') : 'ホストの開始を待っています…';

  const log = $('#lobby-chat-log');
  log.innerHTML = r.chat.map((c) => c.name ? `<div><span class="nm">${esc(c.name)}</span>：${esc(c.text)}</div>` : `<div class="sys">${esc(c.text)}</div>`).join('');
  log.scrollTop = log.scrollHeight;
}

function renderSettings(s, isHost) {
  $('#mode-cards').innerHTML = Object.entries(MODES).map(([k, v]) => `
    <div class="mode-card ${s.mode === k ? 'sel' : ''} ${isHost ? '' : 'ro'}" data-mode="${k}"><b>${v.name}</b><span>${v.desc}</span></div>`).join('');
  if (isHost) $('#mode-cards').querySelectorAll('[data-mode]').forEach((el) => (el.onclick = () => updateSettings({ mode: el.dataset.mode })));
  const sel = $('#sel-rounds');
  sel.innerHTML = Array.from({ length: 10 }, (_, i) => `<option value="${i + 1}" ${s.rounds === i + 1 ? 'selected' : ''}>${i + 1} 回戦</option>`).join('');
  sel.disabled = !isHost;
  sel.onchange = () => updateSettings({ rounds: +sel.value });
  const tl = $('#sel-time');
  const tlv = s.timeLimit ?? 120;
  tl.innerHTML = [[0, 'なし'], [30, '30秒'], [60, '1分'], [120, '2分'], [180, '3分'], [300, '5分']]
    .map(([v, l]) => `<option value="${v}" ${tlv === v ? 'selected' : ''}>${l}</option>`).join('');
  tl.disabled = !isHost;
  tl.onchange = () => updateSettings({ timeLimit: +tl.value });
  const sk = $('#chk-skip');
  sk.checked = s.skipCpu !== false;
  sk.disabled = !isHost;
  sk.onchange = () => updateSettings({ skipCpu: sk.checked });
  renderFinishSettings(s, isHost);

  const area = $('#rule-area');
  if (s.mode === 'random') {
    area.innerHTML = `<div class="hidden-note"><div class="q">？？？</div>追加ルールと上がり方の指定は、開始時にランダムで決まります。<br>
      対戦中のルール確認欄は最初すべて「？」で、関係するカード（8切りなら8）が出た時点で有効／無効が判明します。</div>`;
    return;
  }
  if (s.mode === 'secret') {
    area.innerHTML = `<div class="hidden-note" style="text-align:left"><div class="q" style="text-align:center">？？？</div>
      毎ラウンド、カードが配られた後に<b>大富豪から順に</b>効果を1つ選び、好きな数字に割り振ります（同じ効果は1人だけ）。<br>
      効果は全員に適用されますが、誰が何を選んだかはラウンド終了まで非公開。その後にカード交換を行います。
      <ul style="margin:8px 0 0;padding-left:18px;font-size:12px">
        <li>大富豪：8切り・5スキップ・ジョーカーの枚数</li>
        <li>富豪：上記 ＋ 11バック・革命の枚数（3枚/4枚）</li>
        <li>平民：上記 ＋ 7渡し・10捨て</li>
        <li>貧民：上記 ＋ 12ボンバー</li>
        <li>大貧民：上記 ＋「数字を3つ選んで効果を調べる」</li>
        <li>1回戦は身分がないため、ランダムな順番で全員が平民の選択肢から選びます</li>
      </ul></div>`;
    return;
  }
  const rules = s.rules || {};
  area.innerHTML = '<div class="rule-grid">' + RULE_DEFS.map((d) => {
    const v = rules[d.key];
    const on = !!v;
    let extra = '';
    if (d.kind === 'int') {
      extra = `<select data-num="${d.key}" ${isHost && on ? '' : 'disabled'}>${Array.from({ length: 10 }, (_, i) => `<option value="${i + 1}" ${v === i + 1 ? 'selected' : ''}>+${i + 1}枚</option>`).join('')}</select>`;
    } else if (d.kind === 'lock') {
      extra = `<select data-num="${d.key}" ${isHost && on ? '' : 'disabled'}><option value="2" ${v === 2 ? 'selected' : ''}>2枚</option><option value="3" ${v === 3 ? 'selected' : ''}>3枚</option></select>`;
    }
    return `<div class="rule-item ${on ? 'on' : ''}" title="${esc(d.desc)}">
      <label class="switch"><input type="checkbox" data-key="${d.key}" ${on ? 'checked' : ''} ${isHost ? '' : 'disabled'}><i></i></label>
      <div class="rt"><b>${esc(d.label)}</b><small>${esc(d.desc)}</small></div>${extra}</div>`;
  }).join('') + '</div>';
  if (!isHost) return;
  area.querySelectorAll('input[data-key]').forEach((cb) => (cb.onchange = () => {
    const d = RULE_DEFS.find((x) => x.key === cb.dataset.key);
    const nr = { ...rules };
    nr[d.key] = cb.checked ? (d.kind === 'int' ? 1 : d.kind === 'lock' ? 2 : true) : (d.kind === 'bool' ? false : 0);
    updateSettings({ rules: nr });
  }));
  area.querySelectorAll('select[data-num]').forEach((se) => (se.onchange = () => {
    updateSettings({ rules: { ...rules, [se.dataset.num]: +se.value } });
  }));
}
const SECRET_FINISH_NOTE = `<div class="finish-note">※ シークレットモードでは、上がり方を<b>効果を割り振った数字</b>で判定します。<br>
  例：8切りの効果を<b>6</b>に割り振った場合、<b>6で上がると「8切り上がり禁止」の反則上がり</b>になります（8で上がるのは問題なし）。
  7渡し・10捨て・12ボンバーも同様です。2上がり禁止はカードの「2」で判定します。</div>`;

function renderFinishSettings(s, isHost) {
  const area = $('#finish-area');
  if (s.mode === 'random') {
    area.innerHTML = '<div class="hidden-note" style="padding:10px">上がり方の指定もランダムで決まります（対戦中に判明）</div>';
    return;
  }
  const fin = s.finish || {};
  area.innerHTML = '<div class="rule-grid">' + FINISH_DEFS.map((d) => `
    <div class="rule-item ${fin[d.key] ? 'on' : ''}" title="${esc(d.desc)}">
      <label class="switch"><input type="checkbox" data-fin="${d.key}" ${fin[d.key] ? 'checked' : ''} ${isHost ? '' : 'disabled'}><i></i></label>
      <div class="rt"><b>${esc(d.label)}${d.default ? ' <span class="muted small">(初期ON)</span>' : ''}</b><small>${esc(d.desc)}</small></div>
    </div>`).join('') + '</div>' + (s.mode === 'secret' ? SECRET_FINISH_NOTE : '');
  if (!isHost) return;
  area.querySelectorAll('input[data-fin]').forEach((cb) => (cb.onchange = () => {
    updateSettings({ finish: { ...fin, [cb.dataset.fin]: cb.checked } });
  }));
}

// 対戦中いつでも見られるルール確認欄
function renderRulePanel(g) {
  const el = $('#rule-panel');
  const b = g.board;
  if (!b) { el.innerHTML = ''; return; }
  let collapsed = false;
  try { collapsed = localStorage.getItem('dfg_panel') === '0'; } catch (e) { /* 保存できない環境 */ }
  const cls = (st) => (st.startsWith('？') ? 'q' : st === '禁止' || st === '無効' ? 'off' : 'on');
  const fin = b.finish.map((x) => `<span class="rp-item ${x.status === '禁止' ? 'ban' : cls(x.status)}" title="${esc(x.desc)}">${esc(x.label)}<b>${esc(x.status)}</b></span>`).join('');
  let rules = '';
  if (b.rules) {
    rules = b.rules.length
      ? b.rules.map((x) => `<span class="rp-item ${cls(x.status)}" title="${esc(x.desc)}">${esc(x.label)}<b>${esc(x.status)}</b></span>`).join('')
      : '<span class="muted">なし</span>';
  } else {
    rules = '<span class="muted">効果は非公開（ラウンド終了時に公開）</span>';
  }
  el.innerHTML = `<div class="rp-head" id="rp-toggle">ルール確認 ${collapsed ? '▸' : '▾'}</div>
    ${collapsed ? '' : `<div class="rp-sec">上がり方${g.mode === 'secret' ? '（効果を割り振った数字で判定。例：8切りを6に→6で上がると反則）' : ''}</div><div class="rp-list">${fin}</div>
    <div class="rp-sec">追加ルール</div><div class="rp-list">${rules}</div>`}`;
  $('#rp-toggle').onclick = () => {
    try { localStorage.setItem('dfg_panel', collapsed ? '1' : '0'); } catch (e) { /* 保存できない環境 */ }
    renderRulePanel(g);
  };
}

function updateSettings(patch) {
  const s = { ...S.room.settings, ...patch };
  send({ t: 'settings', settings: s });
}

// ---------------------------------------------------------------- イベント・チャット
function handleChat() {
  for (const c of S.room.chat) {
    if (c.id <= S.lastChat) continue;
    S.lastChat = c.id;
    S.feed.push({ chat: true, name: c.name, text: c.text });
    if (S.game && c.name && !S.fresh) {
      S.chatTicker = { text: `💬 ${c.name}：${c.text}`, until: Date.now() + 5000 };
      setTimeout(() => S.game && S.room && S.room.inGame && renderGame(), 5100);
    }
  }
}
function handleEvents() {
  const g = S.game;
  if (!g) return;
  const evs = g.events;
  const maxSeq = evs.length ? evs[evs.length - 1].seq : 0;
  if (maxSeq < S.lastSeq) S.lastSeq = 0;
  const fresh = S.fresh;
  S.fresh = false;
  let skipped = false;
  for (const e of evs) {
    if (e.seq <= S.lastSeq) continue;
    S.feed.push(e);
    if (fresh) continue;
    if (e.kind === 'fastforward') {
      skipped = true;
      banner('CPUのみ スキップ');
      continue;
    }
    if (skipped) continue; // スキップ中に起きた演出はまとめて省略
    if (e.kind === 'round') banner(e.text.replace(' 開始！', ''));
    else if (e.kind === 'finish') banner((e.by === g.me ? 'あなた' : g.players[e.by].name) + ' 上がり！');
    else if (e.banner) {
      banner(e.banner + '！', isRedBanner(e.banner));
      if (e.banner2) banner(e.banner2, isRedBanner(e.banner));
    } else if (e.kind === 'timeout' && e.by === g.me) banner('時間切れ', true);
    if (e.kind === 'private') toast(e.text, 'info');
  }
  S.lastSeq = Math.max(S.lastSeq, maxSeq);
  if (S.feed.length > 300) S.feed = S.feed.slice(-300);
}

// ---------------------------------------------------------------- ゲーム画面
function renderGame() {
  const g = S.game;
  const me = g.me;
  const n = g.players.length;
  const members = S.room.members;
  const reversed = g.revolution !== g.elevenBack;

  // トップバー
  $('#g-round').textContent = `第${g.round || 1}回戦 / ${g.totalRounds}`;
  const mb = $('#g-mode');
  mb.textContent = MODES[g.mode].name;
  mb.className = 'mode-badge ' + (g.mode === 'open' ? 'open' : '');
  const chips = [];
  if (g.revolution) chips.push('<span class="chip rev">革命中</span>');
  if (g.elevenBack) chips.push('<span class="chip eleven">バック中</span>');
  if (g.lock) chips.push(`<span class="chip lock">縛り ${g.lock.join('')}</span>`);
  if (g.direction < 0) chips.push('<span class="chip dir">逆回り ↺</span>');
  for (const nt of g.notes || []) {
    chips.push(nt.type === 'bomber'
      ? `<span class="chip note bomb" data-notes>💣 ${esc(nt.name)}：${esc(nt.ranks)}</span>`
      : `<span class="chip note" data-notes>🗑 ${esc(nt.name)} ${nt.cards.length}枚（確認）</span>`);
  }
  if (!chips.length) chips.push(`<span class="chip plain">${g.mode === 'open' ? '通常' : 'ルール非公開'}</span>`);
  $('#g-status').innerHTML = chips.join('');
  $('#g-status').querySelectorAll('[data-notes]').forEach((el) => (el.onclick = openNotes));
  $('#table').classList.toggle('reversed', reversed);

  // 相手
  const opp = [];
  const k = n - 1;
  for (let j = 0; j < k; j++) {
    const i = (me + 1 + j) % n;
    const t = (j + 1) / (k + 1);
    const th = Math.PI * (1 - t);
    const x = 50 + 42 * Math.cos(th);
    const y = 55 - 33 * Math.sin(th);
    opp.push(oppHTML(g, i, x, y, members[i]));
  }
  $('#opponents').innerHTML = opp.join('');

  // 場
  const fc = $('#field-cards');
  const fieldKey = g.field ? g.field.cards.map((c) => c.id).join(',') : '';
  if (fc.dataset.key !== fieldKey) {
    fc.dataset.key = fieldKey;
    fc.innerHTML = g.field ? g.field.cards.map((c) => cardHTML(c)).join('') : '';
  }
  if (!g.field) {
    let msg = '';
    if (g.phase === 'secret_pick') msg = 'ルール選択中…';
    else if (g.phase === 'exchange') msg = 'カード交換中…';
    else if (g.phase === 'play') msg = '場';
    fc.innerHTML = msg ? `<div class="field-empty">${msg}</div>` : '';
  }
  $('#pile').innerHTML = (g.pile || []).map((p, idx) => {
    const rot = ((idx * 47 + p.cards.length * 13) % 24) - 12;
    const dx = ((idx * 31) % 60) - 30;
    return `<div class="group" style="transform:translate(${dx}px,${-6 - idx * 3}px) rotate(${rot}deg)">${p.cards.map((c) => cardHTML(c)).join('')}</div>`;
  }).join('');
  $('#field-owner').textContent = g.field ? `${g.field.owner === me ? 'あなた' : g.players[g.field.owner].name} のカード` : '';

  // 自分
  const p = g.players[me];
  const myTurn = g.phase === 'play' && g.current === me;
  const pend = g.pending;
  $('#my-plate').className = 'my-plate' + (myTurn ? ' turn' : '');
  $('#my-plate').innerHTML = `
    <div class="avatar-wrap"><div class="avatar" style="--c:${COLORS[me % COLORS.length]}">${initial(p.name)}</div>
    ${p.foul ? '<div class="place-badge foul">反則</div>' : p.place ? `<div class="place-badge">${p.place}位</div>` : ''}
    ${p.passed ? `<div class="bubble ${p.passed === 'スキップ' ? 'skip' : ''}">${p.passed}</div>` : ''}</div>
    <div class="plate">${p.title ? `<span class="title-badge t-${p.title}">${p.title}</span>` : ''}<span class="nm">${esc(p.name)}</span><span class="sub">${p.points}pt ・ 残り${p.count}枚</span><span class="clock" data-seat="${me}"></span></div>`;
  $('#turn-indicator').innerHTML = `あなたの番です <span class="clock" data-seat="${me}"></span>`;
  $('#turn-indicator').classList.toggle('hidden', !myTurn || !!pend);
  renderHand(g, myTurn, pend);
  $('#btn-play').disabled = !myTurn || !S.sel.length;
  $('#btn-pass').disabled = !myTurn || !g.field;

  // 選択プロンプト
  const pr = $('#prompt');
  if (pend && ['seven', 'ten', 'exchange'].includes(pend.type)) {
    const label = pend.type === 'seven' ? `${esc(pend.name)}：${esc(pend.to)} に渡すカードを ${pend.count} 枚選択`
      : pend.type === 'ten' ? `${esc(pend.name)}：捨てるカードを ${pend.count} 枚選択`
        : `カード交換：${esc(pend.to)} に渡すカードを ${pend.count} 枚選択`;
    $('#prompt-text').innerHTML = `${label} <span class="muted">(${S.sel.length}/${pend.count})</span> <span class="clock" data-seat="${me}"></span>`;
    $('#btn-prompt-ok').disabled = S.sel.length !== pend.count;
    pr.classList.remove('hidden');
  } else {
    pr.classList.add('hidden');
  }

  renderRulePanel(g);

  // シークレット情報（自分の選択・調査結果・選択済みの効果）
  const sb = $('#secret-box');
  const sec = g.secret;
  if (sec && ['secret_pick', 'exchange', 'play', 'action'].includes(g.phase)) {
    let h = '';
    if (g.phase === 'secret_pick') {
      h += '<div class="sb-title">効果の選択順</div><ol class="sb-order">' + sec.order.map((o, k) =>
        `<li class="${k < sec.pos ? 'done' : k === sec.pos ? 'now' : ''}"><span class="title-badge t-${o.title}">${o.title}</span> ${o.i === me ? 'あなた' : esc(g.players[o.i].name)}${k < sec.pos ? ' ✓' : ''}</li>`).join('') + '</ol>';
      if (sec.taken.length) h += `<div class="sb-line">選択済み：${sec.taken.map(esc).join('・')}</div>`;
    }
    if (sec.mine) h += `<div class="sb-line"><b>あなたの効果</b>：${esc(sec.mine)}</div>`;
    if (sec.intel) h += '<div class="sb-line"><b>調査結果</b><br>' + sec.intel.map(esc).join('<br>') + '</div>';
    sb.innerHTML = h;
    sb.classList.toggle('hidden', !h);
  } else {
    sb.classList.add('hidden');
  }

  // ティッカー
  const ticker = $('#ticker');
  ticker.textContent = S.chatTicker && S.chatTicker.until > Date.now() ? S.chatTicker.text : statusLine(g);

  // ログ
  if (!$('#log-panel').classList.contains('hidden')) renderLog();

  // モーダル
  syncModal(g);
  $('#btn-result').classList.toggle('hidden', !['round_end', 'game_end'].includes(g.phase) || S.modal === 'result');
  updateClocks();
}

function statusLine(g) {
  const me = g.me;
  const nm = (i) => (i === me ? 'あなた' : g.players[i].name);
  if (g.phase === 'secret_pick') {
    const w = g.waiting[0];
    if (w == null) return '';
    if (w === me) return 'あなたが効果を選ぶ番です';
    const o = g.secret.order[g.secret.pos];
    return `${o ? o.title + ' ' : ''}${nm(w)} が効果を選択中…（${g.secret.pos + 1}/${g.secret.order.length}）`;
  }
  if (g.phase === 'exchange') return g.pending ? '渡すカードを選んでください' : 'カード交換中…';
  if (g.phase === 'action') return !g.waiting.length ? '' : g.waiting[0] === me ? '効果の対象を選んでください' : `${nm(g.waiting[0])} が選択中…`;
  if (g.phase === 'play' && g.current != null) {
    const last = [...g.events].reverse().find((e) => ['play', 'pass', 'clear', 'eight'].includes(e.kind));
    return (last ? last.text + '　→　' : '') + `${nm(g.current)} の番`;
  }
  if (g.phase === 'round_end') return 'ラウンド終了';
  if (g.phase === 'game_end') return '対戦終了';
  return '';
}

function oppHTML(g, i, x, y, member) {
  const p = g.players[i];
  const turn = g.waiting.includes(i) && (g.phase === 'play' || g.phase === 'action' || g.phase === 'exchange' || g.phase === 'secret_pick');
  const backs = Array.from({ length: Math.min(p.count, 10) }, (_, k) => `<div class="back" style="transform:rotate(${(k - Math.min(p.count, 10) / 2) * 5}deg)"></div>`).join('');
  return `<div class="opp ${turn && (g.phase === 'play' || g.phase === 'secret_pick') ? 'turn' : ''} ${p.place ? 'done' : ''}" style="left:${x}%;top:${y}%">
    <div class="avatar-wrap"><div class="avatar" style="--c:${COLORS[i % COLORS.length]}">${initial(p.name)}</div>
      <div class="count-badge">${p.count}</div>
      ${p.foul ? '<div class="place-badge foul">反則</div>' : p.place ? `<div class="place-badge">${p.place}位</div>` : ''}
      ${p.passed ? `<div class="bubble ${p.passed === 'スキップ' ? 'skip' : ''}">${p.passed}</div>` : ''}
    </div>
    <div class="plate">${p.title ? `<span class="title-badge t-${p.title}">${p.title}</span>` : ''}<span class="nm">${esc(p.name)}</span><span class="sub">${p.points}pt</span><span class="clock" data-seat="${i}"></span></div>
    <div class="mini-hand">${backs}</div>
    ${turn ? '<div class="thinking">考え中…</div>' : ''}
    ${member && !member.online ? '<div class="off-tag">切断中（CPU代打ち）</div>' : ''}
  </div>`;
}

function renderHand(g, myTurn, pend) {
  const hand = g.hand;
  const ids = new Set(hand.map((c) => c.id));
  S.sel = S.sel.filter((id) => ids.has(id));
  const el = $('#hand');
  const probe = document.createElement('div');
  probe.className = 'card';
  el.appendChild(probe);
  const cw = probe.offsetWidth || 70;
  probe.remove();
  const avail = window.innerWidth * 0.62;
  const nCards = hand.length;
  const step = nCards > 1 ? Math.min(cw * 0.66, (avail - cw) / (nCards - 1)) : cw;
  const ml = step - cw;
  el.innerHTML = hand.map((c, k) => cardHTML(c, (S.sel.includes(c.id) ? 'sel ' : '') + (S.prevHand.size && !S.prevHand.has(c.id) ? 'new' : '')))
    .join('');
  el.querySelectorAll('.card').forEach((c, k) => {
    if (k > 0) c.style.marginLeft = ml + 'px';
    c.onclick = () => toggleCard(c.dataset.id);
  });
  S.prevHand = ids;
  el.classList.toggle('disabled', !(myTurn || (pend && pend.type !== 'bomber')));
}

function toggleCard(id) {
  const g = S.game;
  const i = S.sel.indexOf(id);
  if (i >= 0) S.sel.splice(i, 1);
  else {
    const pend = g.pending;
    if (pend && pend.count && ['seven', 'ten', 'exchange'].includes(pend.type) && S.sel.length >= pend.count) {
      S.sel.shift();
    }
    S.sel.push(id);
  }
  renderGame();
}

function renderLog() {
  const el = $('#game-log');
  el.innerHTML = S.feed.map((e) => {
    if (e.chat) return e.name ? `<div>💬 <span class="nm">${esc(e.name)}</span>：${esc(e.text)}</div>` : `<div class="sys">${esc(e.text)}</div>`;
    const cls = e.kind === 'play' ? 'ev-play' : e.kind === 'private' ? 'ev-private' : e.banner || e.kind === 'round' ? 'ev-special' : 'sys';
    return `<div class="${cls}">${esc(e.text)}</div>`;
  }).join('');
  el.scrollTop = el.scrollHeight;
}

// ---------------------------------------------------------------- モーダル
function syncModal(g) {
  const pend = g.pending;
  let want = null;
  if (pend && pend.type === 'secret') want = 'secret';
  else if (pend && pend.type === 'bomber') want = 'bomber';
  else if ((g.phase === 'round_end' || g.phase === 'game_end') && S.resultClosed !== g.phase + g.round) want = 'result';
  const auto = ['secret', 'bomber', 'result'];
  if (want === S.modal) {
    if (want === 'result') openResult(g);
    return;
  }
  if (want) {
    if (want === 'secret') openSecret();
    else if (want === 'bomber') openBomber(pend);
    else openResult(g);
  } else if (auto.includes(S.modal)) closeModal();
}

const FX_NAT = { cut: 8, skip: 5, back: 11, pass: 7, discard: 10, bomber: 12 };
const FX_SUFFIX = { cut: '切り', skip: 'スキップ', back: 'バック', pass: '渡し', discard: '捨て', bomber: 'ボンバー' };
const numLabel = (r) => (r === 14 ? 'A' : r === 15 ? '2' : String(r));

function secretSummary(sel) {
  const k = sel.key;
  if (!k) return null;
  if (k in FX_NAT) return `「${numLabel(sel.rank[k])}${FX_SUFFIX[k]}」`;
  if (k === 'jokers') return `ジョーカー${sel.jokers}枚`;
  if (k === 'revolution') return `革命${sel.revolution}枚から`;
  return sel.intel.length === 3 ? `${sel.intel.map((r) => RANK[r]).join('・')} を調べる` : null;
}

function openSecret() {
  const g = S.game;
  const pend = g.pending;
  if (!S.secretSel || S.secretSel.round !== g.round) {
    S.secretSel = { round: g.round, key: null, rank: { ...FX_NAT }, jokers: 1, revolution: 3, intel: [] };
  }
  const draw = () => {
    const sel = S.secretSel;
    const rankChips = (key, chosen, multi) => `<div class="rank-chips">${RANK_ORDER.map((r) =>
      `<button class="rchip ${(multi ? chosen.includes(r) : chosen === r) ? 'sel' : ''}" data-k="${key}" data-r="${r}">${RANK[r]}</button>`).join('')}</div>`;
    const items = pend.options.map((o) => {
      let ctl = '';
      if (o.kind === 'rank') ctl = rankChips(o.key, sel.rank[o.key], false);
      else if (o.kind === 'jokers') ctl = `<select data-jk>${Array.from({ length: 12 }, (_, k) => `<option value="${k}" ${sel.jokers === k ? 'selected' : ''}>${k}枚</option>`).join('')}</select>`;
      else if (o.kind === 'revolution') ctl = `<div class="rank-chips">${[3, 4].map((v) => `<button class="rchip wide ${sel.revolution === v ? 'sel' : ''}" data-rev="${v}">${v}枚から</button>`).join('')}</div>`;
      else ctl = rankChips('intel', sel.intel, true) + `<small>3つ選択（${sel.intel.length}/3）</small>`;
      return `<div class="pick-item ${o.taken ? 'taken' : ''} ${sel.key === o.key ? 'sel' : ''}" data-key="${o.key}">
        <div class="pick-head"><b>${esc(o.label)}</b>${o.taken ? '<span class="taken-tag">選択済み</span>' : ''}</div>
        <small>${esc(o.desc)}</small>${o.taken ? '' : `<div class="pick-ctl">${ctl}</div>`}</div>`;
    }).join('');
    const sum = secretSummary(sel);
    const scroll = S.modal === 'secret' ? $('#modal-box').scrollTop : 0;
    setTimeout(() => ($('#modal-box').scrollTop = scroll), 0);
    openModal('secret', `<h3>効果を選択 <span class="title-badge t-${pend.title}" style="font-size:14px;vertical-align:middle">${pend.title}</span> <span class="clock" data-seat="${g.me}"></span></h3>
      <p class="muted" style="text-align:center;margin:-6px 0 10px">手札を見ながら効果を1つ選び、好きな数字に割り振ってください。他のプレイヤーには公開されません。</p>
      <div class="pick-list">${items}</div>
      <div class="modal-btns"><button id="secret-ok" class="btn btn-gold" ${sum ? '' : 'disabled'}>${sum ? esc(sum) + ' に決定' : '効果を選んでください'}</button></div>`, (box) => {
      box.querySelectorAll('.pick-item:not(.taken)').forEach((el) => (el.onclick = () => { sel.key = el.dataset.key; draw(); }));
      box.querySelectorAll('.rchip[data-r]').forEach((b) => (b.onclick = (e) => {
        e.stopPropagation();
        const k = b.dataset.k;
        const r = +b.dataset.r;
        sel.key = k;
        if (k === 'intel') {
          const i = sel.intel.indexOf(r);
          if (i >= 0) sel.intel.splice(i, 1);
          else {
            if (sel.intel.length >= 3) sel.intel.shift();
            sel.intel.push(r);
          }
        } else sel.rank[k] = r;
        draw();
      }));
      box.querySelectorAll('[data-rev]').forEach((b) => (b.onclick = (e) => { e.stopPropagation(); sel.key = 'revolution'; sel.revolution = +b.dataset.rev; draw(); }));
      const jk = box.querySelector('[data-jk]');
      if (jk) {
        jk.onclick = (e) => e.stopPropagation();
        jk.onchange = () => { sel.key = 'jokers'; sel.jokers = +jk.value; draw(); };
      }
      box.querySelector('#secret-ok').onclick = () => {
        const k = sel.key;
        const value = k in FX_NAT ? sel.rank[k] : k === 'jokers' ? sel.jokers : k === 'revolution' ? sel.revolution : sel.intel;
        send({ t: 'secret', key: k, value });
      };
    });
    $('#modal').classList.add('top');
  };
  draw();
}

function openBomber(pend) {
  S.bombSel = [];
  const ranks = [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 0];
  const draw = () => openModal('bomber', `<h3>${esc(pend.name)}！ <span class="clock" data-seat="${S.game.me}"></span></h3>
    <p style="text-align:center">全員が捨てる数字を <b>${pend.count}</b> つ選んでください</p>
    <div class="rank-btns">${ranks.map((r) => `<button class="rank-btn ${S.bombSel.includes(r) ? 'sel' : ''}" data-r="${r}" style="${r === 0 ? 'font-size:12px' : ''}">${RANK[r]}</button>`).join('')}</div>
    <div class="modal-btns"><button id="bomb-ok" class="btn btn-gold" ${S.bombSel.length === pend.count ? '' : 'disabled'}>決定</button></div>`, (box) => {
    box.querySelectorAll('.rank-btn').forEach((b) => (b.onclick = () => {
      const r = +b.dataset.r;
      const i = S.bombSel.indexOf(r);
      if (i >= 0) S.bombSel.splice(i, 1);
      else {
        if (S.bombSel.length >= pend.count) S.bombSel.shift();
        S.bombSel.push(r);
      }
      draw();
    }));
    box.querySelector('#bomb-ok').onclick = () => send({ t: 'action', ranks: S.bombSel });
  });
  draw();
}

function resultTable(g, final) {
  const n = g.players.length;
  if (final) {
    const order = g.players.map((p, i) => ({ ...p, i })).sort((a, b) => b.points - a.points);
    return `<table class="res-table"><tr><th>順位</th><th>プレイヤー</th>${g.history.map((_, k) => `<th>${k + 1}回戦</th>`).join('')}<th>合計</th></tr>
      ${order.map((p, idx) => `<tr><td class="rank-no">${idx + 1}</td><td class="l">${esc(p.name)}</td>
        ${g.history.map((h) => { const r = h.find((x) => x.i === p.i); return `<td><span class="title-badge t-${r.title}">${r.title}</span></td>`; }).join('')}
        <td><b>${p.points}pt</b></td></tr>`).join('')}</table>`;
  }
  const last = g.history[g.history.length - 1] || [];
  return `<table class="res-table"><tr><th>順位</th><th>プレイヤー</th><th>称号</th><th>獲得</th><th>合計</th></tr>
    ${last.map((r, idx) => `<tr><td class="rank-no">${idx + 1}</td><td class="l">${esc(r.name)}${r.i === g.me ? '（あなた）' : ''}</td>
      <td><span class="title-badge t-${r.title}">${r.title}</span></td><td>+${r.gain}</td><td>${g.players[r.i].points}pt</td></tr>`).join('')}</table>`;
}

function picksHTML(g, final) {
  const hist = (g.secret && g.secret.history) || [];
  const rounds = final ? hist.map((h, k) => [k, h]) : hist.length ? [[hist.length - 1, hist[hist.length - 1]]] : [];
  if (!rounds.length) return '';
  return `<div class="reveal"><b>効果の割り振り公開！</b>${rounds.map(([k, h]) => `
    ${final ? `<div style="margin-top:6px;color:var(--muted)">第${k + 1}回戦</div>` : ''}
    <ul>${h.map((p) => `<li><span class="title-badge t-${p.title}">${p.title}</span> ${esc(p.name)}：${esc(p.text)}</li>`).join('')}</ul>`).join('')}</div>`;
}

function revealHTML(g) {
  if (g.mode === 'secret') return picksHTML(g, true);
  if (!g.rules) return '';
  const fin = (g.rules.finish || []).length ? g.rules.finish.join('・') : 'なし';
  const rules = (g.rules.rules.length ? `<ul>${g.rules.rules.map((r) => `<li>${esc(r)}</li>`).join('')}</ul>` : '<div>追加ルールなし</div>')
    + `<div style="margin-top:6px"><b>上がり方の禁止</b>：${esc(fin)}</div>`;
  const picks = g.rules.picks ? `<div style="margin-top:8px"><b>各プレイヤーの選択</b><ul>${g.rules.picks.map((p) => `<li>${esc(p.name)}：${esc(p.rule)}</li>`).join('')}</ul></div>` : '';
  return `<div class="reveal"><b>${g.mode === 'open' ? '適用ルール' : '今回の隠しルール公開！'}</b>${rules}${picks}</div>`;
}

function openResult(g) {
  const isHost = S.room.host === S.room.me;
  const final = g.phase === 'game_end';
  const btn = final
    ? (isHost ? '<button id="res-next" class="btn btn-gold">ロビーへ戻る</button>' : '<span class="muted">ホストがロビーに戻るのを待っています</span>')
    : (isHost ? '<button id="res-next" class="btn btn-gold">次のラウンドへ</button>' : '<span class="muted">ホストが次のラウンドを開始します</span>');
  const html = `<h3>${final ? '最終結果' : `第${g.round}回戦 結果`}</h3>${resultTable(g, final)}${final ? revealHTML(g) : g.mode === 'secret' ? picksHTML(g, false) : ''}
    <div class="modal-btns">${btn}<button id="res-close" class="btn btn-dark">閉じる</button></div>`;
  if (S.modal === 'result' && $('#modal-box').dataset.key === html) return;
  openModal('result', html, (box) => {
    box.dataset.key = html;
    const nx = box.querySelector('#res-next');
    if (nx) nx.onclick = () => send({ t: final ? 'to_lobby' : 'next_round' });
    box.querySelector('#res-close').onclick = () => { S.resultClosed = g.phase + g.round; closeModal(); renderGame(); };
  });
}

function openRules() {
  const g = S.game;
  const defs = Object.fromEntries(RULE_DEFS.map((d) => [d.label, d.desc]));
  let body = '<ul class="rule-list"><li><b>基本ルール</b><small>革命あり（同じ数字4枚以上）／ 階段は同じスート3枚から ／ ジョーカー1枚（単体では最強）／ スペ3返し（ジョーカー単体に♠3を出せる。その場で場が流れる）</small></li></ul>';
  if (g.rules) {
    body += '<h4 style="color:var(--gold);margin:14px 0 6px">追加ルール</h4>';
    body += g.rules.rules.length
      ? '<ul class="rule-list">' + g.rules.rules.map((r) => `<li><b>${esc(r)}</b><small>${esc(defs[r.replace(/（.*）/, '')] || '')}</small></li>`).join('') + '</ul>'
      : '<div class="muted">追加ルールなし</div>';
  } else if (g.mode === 'secret') {
    body += `<div class="hidden-note" style="margin-top:14px;text-align:left"><div class="q" style="text-align:center">？？？</div>
      毎ラウンド、大富豪から順に効果を1つずつ数字に割り振ります（誰が何を選んだかは非公開）。<br>
      大富豪：8切り・5スキップ・ジョーカー枚数 ／ 富豪：＋11バック・革命枚数 ／ 平民：＋7渡し・10捨て ／ 貧民：＋12ボンバー ／ 大貧民：＋効果を調べる</div>`;
    if (g.secret.mine) body += `<div style="text-align:center">あなたの効果：<b style="color:var(--gold)">${esc(g.secret.mine)}</b></div>`;
    if (g.secret.intel) body += `<div style="text-align:center;margin-top:6px">調査結果：${g.secret.intel.map(esc).join(' ／ ')}</div>`;
  } else if (g.board && g.board.rules) {
    body += '<h4 style="color:var(--gold);margin:14px 0 6px">追加ルール <span class="muted small">（関係するカードが出ると判明）</span></h4>';
    body += '<ul class="rule-list">' + g.board.rules.map((x) => `<li><b>${esc(x.label)}：${esc(x.status)}</b><small>${esc(x.desc)}</small></li>`).join('') + '</ul>';
  }
  if (g.board) {
    body += '<h4 style="color:var(--gold);margin:14px 0 6px">上がり方 <span class="muted small">（禁止された上がり方をすると最下位）</span></h4>';
    body += '<ul class="rule-list">' + g.board.finish.map((x) => `<li><b>${esc(x.label)}：${esc(x.status)}</b><small>${esc(x.desc)}</small></li>`).join('') + '</ul>';
    if (g.mode === 'secret') body += SECRET_FINISH_NOTE;
  }
  openModal('rules', `<h3>ルール</h3>${body}<div class="modal-btns"><button class="btn btn-dark" id="m-close">閉じる</button></div>`,
    (box) => (box.querySelector('#m-close').onclick = closeModal));
}

function openNotes() {
  const g = S.game;
  const notes = g.notes || [];
  const body = notes.length ? notes.map((nt) => {
    if (nt.type === 'ten') {
      return `<div class="note-block"><b>🗑 ${esc(nt.name)}</b>（${esc(nt.by)}）が捨てたカード
        <div class="note-cards">${nt.cards.map((c) => cardHTML(c)).join('')}</div></div>`;
    }
    const lost = nt.lost.length ? nt.lost.map((l) => `<div class="note-sub">${esc(l.name)}：<div class="note-cards">${l.cards.map((c) => cardHTML(c)).join('')}</div></div>`).join('')
      : '<div class="note-sub muted">捨てたカードはありませんでした</div>';
    return `<div class="note-block"><b>💣 ${esc(nt.name)}</b>（${esc(nt.by)}）が「<b>${esc(nt.ranks)}</b>」を指定${lost}</div>`;
  }).join('') : '<div class="muted" style="text-align:center">場が流れたため記録はありません</div>';
  openModal('notes', `<h3>この場で捨てられたカード</h3>${body}
    <p class="muted small" style="text-align:center">場が流れると記録は消えます</p>
    <div class="modal-btns"><button class="btn btn-dark" id="m-close">閉じる</button></div>`,
  (box) => (box.querySelector('#m-close').onclick = closeModal));
}

// 持ち時間表示（サーバーから受け取った値を受信時刻からの経過で減らして表示）
function fmtTime(sec) {
  const s = Math.max(0, Math.ceil(sec));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}
function updateClocks() {
  const c = S.clock;
  const dt = (performance.now() - (S.clockAt || 0)) / 1000;
  document.querySelectorAll('.clock[data-seat]').forEach((el) => {
    const st = c && c.seats[+el.dataset.seat];
    if (!st || !S.game || ['round_end', 'game_end'].includes(S.game.phase)) {
      el.textContent = '';
      return;
    }
    let text;
    let cls = 'clock';
    if (st.active) {
      const bank = st.bank - dt;
      if (bank > 0) {
        text = `⏱ ${fmtTime(bank)}`;
        cls += ' active';
      } else {
        text = `⏱ 残り${Math.max(0, Math.ceil(st.left - dt))}秒`;
        cls += ' byo';
      }
    } else {
      text = st.bank > 0 ? `⏱ ${fmtTime(st.bank)}` : `⏱ 毎手番${c.byo}秒`;
    }
    el.textContent = text;
    el.className = cls;
  });
}
setInterval(updateClocks, 200);

function openScore() {
  const g = S.game;
  const body = g.history.length ? resultTable(g, true) : '<div class="muted" style="text-align:center">まだ結果がありません</div>';
  openModal('score', `<h3>成績</h3>${body}<div class="modal-btns"><button class="btn btn-dark" id="m-close">閉じる</button></div>`,
    (box) => (box.querySelector('#m-close').onclick = closeModal));
}

function confirmLeave() {
  openModal('confirm', `<h3>退室しますか？</h3><p style="text-align:center">対戦中に退室すると、以降はCPUが代わりにプレイします。</p>
    <div class="modal-btns"><button class="btn btn-gold" id="c-yes">退室する</button><button class="btn btn-dark" id="c-no">キャンセル</button></div>`, (box) => {
    box.querySelector('#c-yes').onclick = () => { closeModal(); send({ t: 'leave' }); };
    box.querySelector('#c-no').onclick = closeModal;
  });
}

// ---------------------------------------------------------------- 入力
function bindUI() {
  $('#in-name').value = params.get('name') || localStorage.getItem('dfg_name') || '';
  $('#btn-create').onclick = createRoom;
  $('#btn-join').onclick = () => joinRoom($('#in-code').value.trim());
  $('#in-code').onkeydown = (e) => { if (e.key === 'Enter') joinRoom($('#in-code').value.trim()); };
  $('#btn-refresh').onclick = () => send({ t: 'list' });
  const home = params.get('home');
  if (home) {
    $('#link-home').classList.remove('hidden');
    $('#link-home').href = home;
  }
  $('#btn-leave').onclick = () => send({ t: 'leave' });
  $('#sel-bots').onchange = () => send({ t: 'set_bots', count: +$('#sel-bots').value });
  $('#btn-solo').onclick = () => createRoom(true, +$('#sel-solo-cpus').value);
  $('#btn-start').onclick = () => send({ t: 'start' });
  for (const f of ['#lobby-chat-form', '#game-chat-form']) {
    $(f).onsubmit = (e) => {
      e.preventDefault();
      const inp = $(f).querySelector('input');
      if (inp.value.trim()) send({ t: 'chat', text: inp.value.trim() });
      inp.value = '';
    };
  }
  $('#btn-play').onclick = () => { if (S.sel.length) send({ t: 'play', cards: S.sel }); };
  $('#btn-pass').onclick = () => send({ t: 'pass' });
  $('#btn-clear').onclick = () => { S.sel = []; renderGame(); };
  $('#btn-prompt-ok').onclick = () => {
    const pend = S.game && S.game.pending;
    if (!pend) return;
    send({ t: pend.type === 'exchange' ? 'exchange' : 'action', cards: S.sel });
  };
  $('#btn-rules').onclick = openRules;
  $('#btn-score').onclick = openScore;
  $('#btn-result').onclick = () => { S.resultClosed = null; renderGame(); };
  $('#btn-log').onclick = () => { $('#log-panel').classList.toggle('hidden'); renderLog(); };
  $('#btn-log-close').onclick = () => $('#log-panel').classList.add('hidden');
  $('#btn-game-leave').onclick = confirmLeave;
  $('#modal').onclick = (e) => {
    if (e.target.id === 'modal' && ['rules', 'score', 'confirm', 'notes'].includes(S.modal)) closeModal();
  };
  document.addEventListener('keydown', (e) => {
    if (!S.game || e.target.tagName === 'INPUT') return;
    if (e.key === 'Enter' && !$('#btn-play').disabled) $('#btn-play').click();
    if ((e.key === 'p' || e.key === 'P') && !$('#btn-pass').disabled) $('#btn-pass').click();
  });
  window.addEventListener('resize', () => { if (S.game && S.room && S.room.inGame) renderGame(); });
}

async function main() {
  bindUI();
  try {
    RULE_DEFS = await (await fetch('/rules')).json();
    FINISH_DEFS = await (await fetch('/finish_rules')).json();
  } catch (e) {
    RULE_DEFS = [];
  }
  connect();
}
main();
