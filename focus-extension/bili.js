// 在 B站页面里运行：
// 1) 兜底：如果首页/热门没被规则拦住（比如站内跳转），这里再跳一次
// 2) 视频页：隐藏右侧推荐和播放结束后的推荐，避免一个接一个往下点
(async () => {
  const FOCUS = 'https://prima-bottle.github.io/info-feed/focus/';
  const { passUntil = 0, hideRecs = true } = await chrome.storage.local.get({ passUntil: 0, hideRecs: true });
  const passing = passUntil > Date.now();

  const isFeed = () => {
    const h = location.hostname, p = location.pathname;
    if (/^(www\.)?bilibili\.com$/.test(h) && /^\/(index\.html)?$/.test(p)) return 'home';
    if (h === 'm.bilibili.com' && p === '/') return 'home';
    if (/^(www\.)?bilibili\.com$/.test(h) && /^\/(v\/popular|v\/channel|c\/)/.test(p)) return 'popular';
    return null;
  };
  const check = async () => {
    const f = isFeed(); if (!f) return;
    const { passUntil: p = 0 } = await chrome.storage.local.get({ passUntil: 0 });
    if (p <= Date.now()) location.replace(FOCUS + '?from=' + f);
  };
  check();
  // B站有些跳转不刷新页面，监听地址变化
  let last = location.href;
  setInterval(() => { if (location.href !== last) { last = location.href; check(); } }, 800);

  if (hideRecs && !passing) {
    const css = `
      .recommend-list-v1, .recommend-list-container, .rec-list, #reco_list, .next-play,
      .video-page-card-small, .video-page-operator-card-small, .video-page-special-card-small,
      .bpx-player-ending-related, .bpx-player-ending-content, .bpx-player-ending-panel,
      .video-card-ad-small, .ad-report, .slide-ad-exp, .activity-m-v1, .pop-live-small-mode
      { display: none !important; }`;
    const st = document.createElement('style');
    st.id = 'focus-exit-hide';
    st.textContent = css;
    (document.head || document.documentElement).appendChild(st);
  }
})();
