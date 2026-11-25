// 在 B站页面里运行（规则已经拦掉了绝大部分，这里是第二道关）：
// 只有白名单 UP 主的视频页和个人空间能留下，其余一律跳到「先停一下」。
// 视频页先把页面藏起来，认出 UP 主是白名单里的才显示；认不出就当不在白名单。
(() => {
  const FOCUS = 'https://prima-bottle.github.io/info-feed/focus/?from=bili';
  const hide = document.createElement('style');
  hide.textContent = 'html{visibility:hidden!important}';
  (document.head || document.documentElement).appendChild(hide);
  const leave = () => location.replace(FOCUS);
  const show = () => hide.remove();

  chrome.storage.local.get({ ups: [], hideRecs: true }, ({ ups, hideRecs }) => {
    const mids = new Set(ups.map(u => String(u.mid)));
    if (!mids.size) { leave(); return; }

    if (hideRecs) {
      const st = document.createElement('style');
      st.textContent = `
        .recommend-list-v1, .recommend-list-container, .rec-list, #reco_list, .next-play,
        .video-page-card-small, .video-page-operator-card-small, .video-page-special-card-small,
        .bpx-player-ending-related, .bpx-player-ending-content, .bpx-player-ending-panel,
        .video-card-ad-small, .ad-report, .slide-ad-exp, .activity-m-v1, .pop-live-small-mode
        { display: none !important; }`;
      (document.head || document.documentElement).appendChild(st);
    }

    let timer = null;
    function check() {
      clearInterval(timer);
      const h = location.hostname, p = location.pathname;
      const space = h === 'space.bilibili.com' && p.match(/^\/(\d+)/);
      if (space) { mids.has(space[1]) ? show() : leave(); return; }
      if (!/^\/video\//.test(p)) { leave(); return; }
      // 视频页：在页面上找 UP 主链接（单人或合作视频）
      const started = Date.now();
      timer = setInterval(() => {
        const found = [...document.querySelectorAll(
          '.up-panel-container a[href*="space.bilibili.com/"], .up-info-container a[href*="space.bilibili.com/"], a.up-name, .membersinfo-upcard a[href*="space.bilibili.com/"], .staff-info a[href*="space.bilibili.com/"]'
        )].map(a => (a.href.match(/space\.bilibili\.com\/(\d+)/) || [])[1]).filter(Boolean);
        if (found.length) {
          clearInterval(timer);
          found.some(m => mids.has(m)) ? show() : leave();
        } else if (Date.now() - started > 10000) {
          clearInterval(timer); leave();
        }
      }, 300);
    }
    check();
    // 站内跳转不刷新页面，地址变了就重新核对
    let last = location.href;
    setInterval(() => {
      if (location.href !== last) {
        last = location.href;
        (document.head || document.documentElement).appendChild(hide);
        check();
      }
    }, 500);
  });
})();
