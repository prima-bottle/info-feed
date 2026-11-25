// 德语剧播放器：从本地剧集文件夹读 mp4，记进度，加载同名外挂字幕；看完一集就停
const $ = s => document.querySelector(s);
const esc = t => String(t ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const pad = n => String(n).padStart(2, '0');
const today = (() => { const d = new Date(); return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()); })();
const fmt = s => { s = Math.floor(s || 0); const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60); return (h ? h + ':' + pad(m) : m) + ':' + pad(s % 60); };
const VIDEO = /\.(mp4|m4v|webm|mkv)$/i, SUB = /\.(srt|vtt)$/i;
const coll = new Intl.Collator('de', { numeric: true, sensitivity: 'base' });

/* ---------- 文件夹句柄存在 IndexedDB 里，下次不用重新选 ---------- */
const idb = (() => {
  const open = () => new Promise((res, rej) => { const r = indexedDB.open('series', 1); r.onupgradeneeded = () => r.result.createObjectStore('kv'); r.onsuccess = () => res(r.result); r.onerror = () => rej(r.error); });
  return {
    async get(k) { const db = await open(); return new Promise(res => { const r = db.transaction('kv').objectStore('kv').get(k); r.onsuccess = () => res(r.result); r.onerror = () => res(null); }); },
    async set(k, v) { const db = await open(); return new Promise(res => { const t = db.transaction('kv', 'readwrite'); t.objectStore('kv').put(v, k); t.oncomplete = res; }); }
  };
})();

/* ---------- 进度和观看时长存在扩展存储里 ---------- */
let prog = {}, watch = {};
const saveProg = () => chrome.storage.local.set({ seriesProg: prog });
const saveWatch = () => chrome.storage.local.set({ seriesWatch: watch });

let root = null, seasons = [];   // seasons: [{name, eps:[{key,name,label,file,subs:[]}]}]
let cur = null, subTrack = null;

/* ---------- 启动 ---------- */
(async () => {
  const s = await chrome.storage.local.get({ seriesProg: {}, seriesWatch: {} });
  prog = s.seriesProg; watch = s.seriesWatch;
  renderToday();
  if (!window.showDirectoryPicker) { gate('这个浏览器不支持读取本地文件夹，请用新版 Chrome 或 Edge。', null); return; }
  root = await idb.get('root');
  if (!root) { gate('第一次用：选一下放德语剧的文件夹（桌面上的「剧集研究」）。以后会记住。', '选择剧集文件夹', pick); return; }
  const perm = await root.queryPermission({ mode: 'read' });
  if (perm === 'granted') await load();
  else gate('浏览器要你点一下，才能继续读「' + root.name + '」。', '打开剧集文件夹', async () => {
    if (await root.requestPermission({ mode: 'read' }) === 'granted') await load();
  }, '弹窗里选「每次访问时都允许」，以后就不用再点了。');
})();

function renderToday() {
  const sec = watch[today] || 0;
  $('#today').textContent = sec >= 60 ? '今天看了 ' + Math.round(sec / 60) + ' 分钟德语剧' : '今天还没看';
}
function gate(text, btn, fn, note) {
  $('#gate').hidden = false; $('#library').hidden = true;
  $('#gateText').textContent = text;
  $('#gateBtn').hidden = !btn; $('#gateBtn').textContent = btn || ''; $('#gateBtn').onclick = fn;
  $('#gateNote').textContent = note || '';
}
async function pick() {
  try {
    root = await window.showDirectoryPicker({ id: 'deutsch-serien', mode: 'read', startIn: 'desktop' });
    await idb.set('root', root); await load();
  } catch (e) { /* 取消了 */ }
}
$('#repick').onclick = pick;

/* ---------- 扫描文件夹：每个子文件夹算一季，最多往下两层 ---------- */
async function scanDir(dir, name, out, depth) {
  const files = [], subs = [];
  for await (const [n, h] of dir.entries()) {
    if (h.kind === 'directory') { if (depth < 2) subs.push([n, h]); }
    else files.push([n, h]);
  }
  const vids = files.filter(([n]) => VIDEO.test(n)).sort((a, b) => coll.compare(a[0], b[0]));
  if (vids.length) {
    const subFiles = files.filter(([n]) => SUB.test(n));
    out.push({
      name, eps: vids.map(([n, h]) => {
        const base = n.replace(VIDEO, '');
        const m = n.match(/S(\d+)\s*E(\d+)/i) || n.match(/E(?:p(?:isode)?)?\s*(\d+)/i) || n.match(/(\d+)/);
        const label = m ? '第 ' + (+(m[2] || m[1])) + ' 集' : base;
        // 同名字幕，德语优先：Folge01.srt、Folge01.de.srt、Folge01.deu.srt …
        const subs = subFiles.filter(([s]) => s.startsWith(base)).sort(([a], [b]) => (/\.(de|deu|ger|german)\./i.test(b) ? 1 : 0) - (/\.(de|deu|ger|german)\./i.test(a) ? 1 : 0));
        return { key: name + '/' + n, name: base, label, handle: h, subs: subs.map(x => x[1]) };
      })
    });
  }
  subs.sort((a, b) => coll.compare(a[0], b[0]));
  for (const [n, h] of subs) await scanDir(h, name ? name + ' / ' + n : n, out, depth + 1);
}
async function load() {
  $('#gate').hidden = true;
  seasons = []; await scanDir(root, '', seasons, 0);
  seasons.forEach(s => { if (!s.name) s.name = root.name; });
  $('#rootName').textContent = root.name;
  if (!seasons.length) { gate('「' + root.name + '」里没找到 mp4 视频。', '换一个文件夹', pick); return; }
  renderLibrary();
}

/* ---------- 列表 ---------- */
const all = () => seasons.flatMap(s => s.eps.map(e => ({ ...e, season: s.name })));
function nextUp() {
  const eps = all();
  const started = eps.filter(e => prog[e.key] && !prog[e.key].w).sort((a, b) => prog[b.key].at - prog[a.key].at)[0];
  if (started) return { ep: started, resume: true };
  const lastW = eps.filter(e => prog[e.key]?.w).sort((a, b) => prog[b.key].at - prog[a.key].at)[0];
  if (lastW) { const i = eps.findIndex(e => e.key === lastW.key); const nx = eps.slice(i + 1).find(e => !prog[e.key]?.w); if (nx) return { ep: nx }; }
  const first = eps.find(e => !prog[e.key]?.w);
  return first ? { ep: first } : null;
}
function renderLibrary() {
  $('#library').hidden = false;
  const nu = nextUp();
  $('#resume').innerHTML = nu
    ? '<div class="resume"><span class="muted">' + (nu.resume ? '继续看' : '下一集') + ' · ' + esc(nu.ep.season) + '</span><br><b>' + esc(nu.ep.label) + '</b>'
      + (nu.resume ? ' <span class="muted">从 ' + fmt(prog[nu.ep.key].t) + ' 接着看</span>' : '') + '</div><div class="row"><button class="primary" id="playNext">▶ 播放</button></div>'
    : '<p>这里的剧都看完了。可以往文件夹里放新的一季。</p>';
  if (nu) $('#playNext').onclick = () => play(nu.ep);
  $('#seasons').innerHTML = seasons.map((s, si) => '<div class="season"><h3>' + esc(s.name) + '</h3><ul class="eps">' + s.eps.map((e, ei) => {
    const p = prog[e.key];
    const pct = p && p.d ? Math.min(100, p.t / p.d * 100) : 0;
    return '<li data-s="' + si + '" data-e="' + ei + '" class="' + (p?.w ? 'watched' : '') + '"><span class="name">' + esc(e.label) + (e.label !== e.name ? ' <span class="muted">' + esc(e.name) + '</span>' : '') + '</span>'
      + (p && !p.w ? '<span class="prog"><i style="width:' + pct + '%"></i></span>' : '') + '<span class="tick">' + (p?.w ? '✓ 看过' : '') + '</span></li>';
  }).join('') + '</ul></div>').join('');
  $('#seasons').querySelectorAll('li').forEach(li => li.onclick = () => { const s = seasons[+li.dataset.s]; play({ ...s.eps[+li.dataset.e], season: s.name }); });
}

/* ---------- 播放 ---------- */
const V = $('#video');
async function srtToVtt(fileHandle) {
  const buf = await (await fileHandle.getFile()).arrayBuffer();
  let text;
  try { text = new TextDecoder('utf-8', { fatal: true }).decode(buf); } catch (e) { text = new TextDecoder('windows-1252').decode(buf); }
  text = text.replace(/^\uFEFF/, '').replace(/\r/g, '');
  if (!/^WEBVTT/.test(text)) text = 'WEBVTT\n\n' + text.replace(/(\d\d:\d\d:\d\d),(\d\d\d)/g, '$1.$2');
  return URL.createObjectURL(new Blob([text], { type: 'text/vtt' }));
}
async function play(ep) {
  cur = ep;
  $('#ended').hidden = true; $('#library').hidden = true; $('#stage').hidden = false;
  $('#nowTitle').textContent = ep.label; $('#nowSeason').textContent = ep.season;
  document.title = ep.label + ' · ' + ep.season;
  if (V.src) URL.revokeObjectURL(V.src);
  V.querySelectorAll('track').forEach(t => t.remove()); subTrack = null;
  V.src = URL.createObjectURL(await ep.handle.getFile());
  if (ep.subs.length) {
    const t = document.createElement('track');
    t.kind = 'subtitles'; t.label = 'Deutsch'; t.srclang = 'de'; t.default = true;
    t.src = await srtToVtt(ep.subs[0]);
    V.appendChild(t); subTrack = t;
  }
  $('#subBtn').hidden = !subTrack; $('#subBtn').textContent = '字幕：开';
  const p = prog[ep.key];
  V.onloadedmetadata = () => { if (p && !p.w && p.t < V.duration - 10) V.currentTime = p.t; V.play().catch(() => {}); };
  window.scrollTo({ top: 0 });
}
// 每 5 秒存一次进度，并累计今天看了多久
let lastT = null, lastSave = 0;
V.ontimeupdate = () => {
  if (!cur) return;
  const t = V.currentTime;
  if (lastT !== null && !V.paused && t > lastT && t - lastT < 2) { watch[today] = (watch[today] || 0) + (t - lastT); }
  lastT = t;
  if (Date.now() - lastSave > 5000) { lastSave = Date.now(); store(false); }
};
V.onseeking = () => { lastT = null; };
V.onpause = () => store(false);
V.onended = () => {
  store(true);
  $('#stage').hidden = true; $('#ended').hidden = false;
  const nu = nextUp();
  $('#endedText').textContent = '今天看了 ' + Math.round((watch[today] || 0) / 60) + ' 分钟德语。现在停，正好。';
  $('#endNext').hidden = !nu; if (nu) { $('#endNext').textContent = '还是再看一集（' + nu.ep.label + '）'; $('#endNext').onclick = () => play(nu.ep); }
};
function store(watched) {
  if (!cur) return;
  const old = prog[cur.key] || {};
  prog[cur.key] = { t: V.currentTime || 0, d: V.duration || old.d || 0, w: watched || old.w || (V.duration && V.currentTime > V.duration * 0.92), at: Date.now() };
  saveProg(); saveWatch(); renderToday();
}
function backToList() { store(false); V.pause(); $('#stage').hidden = true; $('#ended').hidden = true; cur = null; renderLibrary(); document.title = '德语剧 · 专注出口'; }
function closeTab() { store(false); V.pause(); chrome.tabs.getCurrent(t => t ? chrome.tabs.remove(t.id) : window.close()); }
$('#closeBtn').onclick = closeTab;
$('#endBack').onclick = closeTab;
document.querySelectorAll('[data-rate]').forEach(b => b.onclick = () => {
  V.playbackRate = +b.dataset.rate;
  document.querySelectorAll('[data-rate]').forEach(x => x.classList.toggle('on', x === b));
});
$('#back10').onclick = () => { V.currentTime = Math.max(0, V.currentTime - 10); };
function toggleSub() {
  if (!subTrack) return;
  const tr = subTrack.track; tr.mode = tr.mode === 'showing' ? 'hidden' : 'showing';
  $('#subBtn').textContent = '字幕：' + (tr.mode === 'showing' ? '开' : '关');
}
$('#subBtn').onclick = toggleSub;
document.addEventListener('keydown', e => {
  if ($('#stage').hidden || /INPUT|TEXTAREA/.test(e.target.tagName)) return;
  if (e.key === ' ' && e.target !== V) { e.preventDefault(); V.paused ? V.play() : V.pause(); }
  else if (e.key === 'ArrowLeft' && e.target !== V) { V.currentTime = Math.max(0, V.currentTime - 5); }
  else if (e.key === 'ArrowRight' && e.target !== V) { V.currentTime += 5; }
  else if (e.key === 's' || e.key === 'S') toggleSub();
  else if (e.key === 'Escape') backToList();
});
window.addEventListener('beforeunload', () => store(false));
