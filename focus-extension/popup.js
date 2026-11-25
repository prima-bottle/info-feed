chrome.storage.local.get({ ups: [], hideRecs: true }, ({ ups, hideRecs }) => {
  document.getElementById('state').textContent = ups.length
    ? 'B站全站拦截中；白名单 ' + ups.length + ' 位 UP 主：' + ups.map(u => u.name || u.mid).join('、')
    : 'B站全站拦截中（白名单为空）';
  const cb = document.getElementById('hide');
  cb.checked = hideRecs;
  cb.onchange = () => chrome.runtime.sendMessage({ type: 'setHideRecs', value: cb.checked });
});
