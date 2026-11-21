// 专注出口：拦截 B站首页/热门，临时放行，到点提醒
const RULESET = 'block';

async function getState() {
  const s = await chrome.storage.local.get({ passUntil: 0, hideRecs: true });
  return s;
}

// 根据放行时间决定拦截规则开还是关
async function sync() {
  const { passUntil } = await getState();
  const passing = passUntil > Date.now();
  await chrome.declarativeNetRequest.updateEnabledRulesets(
    passing ? { disableRulesetIds: [RULESET] } : { enableRulesetIds: [RULESET] }
  );
  if (passing) chrome.alarms.create('passEnd', { when: passUntil });
  chrome.action.setBadgeText({ text: passing ? '放' : '' });
  chrome.action.setBadgeBackgroundColor({ color: '#c2502d' });
}

chrome.runtime.onInstalled.addListener(sync);
chrome.runtime.onStartup.addListener(sync);

chrome.alarms.onAlarm.addListener(async (a) => {
  if (a.name === 'passEnd') {
    await chrome.storage.local.set({ passUntil: 0 });
    await sync();
    chrome.notifications.create('passEnd', {
      type: 'basic', iconUrl: 'icons/128.png',
      title: '10 分钟到了', message: 'B站首页恢复拦截。回去做下一步吧。'
    });
  } else if (a.name.startsWith('remind:')) {
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
      const s = await getState();
      reply({ ok: true, ...s, version: chrome.runtime.getManifest().version });
    } else if (msg.type === 'pass') {
      const min = Math.min(Math.max(+msg.minutes || 10, 1), 30); // 最多 30 分钟
      await chrome.storage.local.set({ passUntil: Date.now() + min * 60000 });
      await sync();
      reply({ ok: true });
    } else if (msg.type === 'remind') {
      const min = Math.min(Math.max(+msg.minutes || 5, 1), 60);
      await chrome.storage.local.set({ remind: { title: msg.title, body: msg.body } });
      chrome.alarms.create('remind:' + Date.now(), { delayInMinutes: min });
      reply({ ok: true });
    } else if (msg.type === 'close') {
      reply({ ok: true });
      if (sender.tab?.id) chrome.tabs.remove(sender.tab.id);
    } else if (msg.type === 'setHideRecs') {
      await chrome.storage.local.set({ hideRecs: !!msg.value });
      reply({ ok: true });
    } else {
      reply({ ok: false });
    }
  })();
  return true; // 异步回复
});
