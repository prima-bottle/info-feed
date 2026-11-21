chrome.storage.local.get({ passUntil: 0, hideRecs: true }, ({ passUntil, hideRecs }) => {
  const st = document.getElementById('state');
  if (passUntil > Date.now()) {
    const d = new Date(passUntil);
    st.textContent = 'B站放行中，到 ' + String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0') + ' 恢复拦截';
  } else {
    st.textContent = '拦截中：B站首页、热门、分区页';
  }
  const cb = document.getElementById('hide');
  cb.checked = hideRecs;
  cb.onchange = () => chrome.runtime.sendMessage({ type: 'setHideRecs', value: cb.checked });
});
