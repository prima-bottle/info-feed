// 专注出口：B站全站拦截（白名单 UP 主除外），提醒，打开德语剧播放器
const RULESET = 'block';

// 读白名单，生成放行规则：有白名单时放行视频页（再由 bili.js 核对 UP 主）和这些 UP 主的个人空间
async function sync() {
  let ups = [];
  try {
    const wl = await (await fetch(chrome.runtime.getURL('whitelist.json'))).json();
    ups = (wl.ups || []).filter(u => /^\d+$/.test(String(u.mid)));
  } catch (e) { /* 白名单读不到就按空处理：全拦 */ }
  await chrome.storage.local.set({ ups, passUntil: 0 });

  const old = await chrome.declarativeNetRequest.getDynamicRules();
  const addRules = [];
  if (ups.length) {
    addRules.push({
      id: 100, priority: 2, action: { type: 'allow' },
      condition: { regexFilter: '^https?://(www\\.|m\\.)?bilibili\\.com/video/', resourceTypes: ['main_frame'] }
    });
    ups.forEach((u, i) => addRules.push({
      id: 101 + i, priority: 2, action: { type: 'allow' },
      condition: { regexFilter: '^https?://space\\.bilibili\\.com/' + u.mid + '([/?#]|$)', resourceTypes: ['main_frame'] }
    }));
  }
  await chrome.declarativeNetRequest.updateDynamicRules({ removeRuleIds: old.map(r => r.id), addRules });
  // 旧版本的「放行 10 分钟」可能把规则关掉了，这里确保打开
  await chrome.declarativeNetRequest.updateEnabledRulesets({ enableRulesetIds: [RULESET] });
  chrome.action.setBadgeText({ text: '' });
  chrome.alarms.clear('passEnd');
}

chrome.runtime.onInstalled.addListener(sync);
chrome.runtime.onStartup.addListener(sync);

chrome.alarms.onAlarm.addListener(async (a) => {
  if (a.name.startsWith('remind:')) {
    const { remind } = await chrome.storage.local.get('remind');
    chrome.notifications.create('remind', {
      type: 'basic', iconUrl: 'icons/128.png',
      title: remind?.title || '时间到了', message: remind?.body || ''
    });
  }
});

chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  (async () => {
    if (msg.type === 'hello' || msg.type === 'status') {
      const { ups = [], hideRecs = true } = await chrome.storage.local.get({ ups: [], hideRecs: true });
      reply({ ok: true, ups: ups.length, hideRecs, player: true, version: chrome.runtime.getManifest().version });
    } else if (msg.type === 'remind') {
      const min = Math.min(Math.max(+msg.minutes || 5, 1), 60);
      await chrome.storage.local.set({ remind: { title: msg.title, body: msg.body } });
      chrome.alarms.create('remind:' + Date.now(), { delayInMinutes: min });
      reply({ ok: true });
    } else if (msg.type === 'close') {
      reply({ ok: true });
      if (sender.tab?.id) chrome.tabs.remove(sender.tab.id);
    } else if (msg.type === 'openPlayer') {
      const url = chrome.runtime.getURL('player.html');
      if (sender.tab?.id) chrome.tabs.update(sender.tab.id, { url }); else chrome.tabs.create({ url });
      reply({ ok: true });
    } else if (msg.type === 'setHideRecs') {
      await chrome.storage.local.set({ hideRecs: !!msg.value });
      reply({ ok: true });
    } else {
      reply({ ok: false });
    }
  })();
  return true; // 异步回复
});
