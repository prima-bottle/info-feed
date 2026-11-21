// 在「先停一下」页里运行：把网页的请求转给扩展后台，再把结果传回网页
window.addEventListener('message', (e) => {
  if (e.source !== window || !e.data || e.data.src !== 'focus-page') return;
  const { type, id } = e.data;
  chrome.runtime.sendMessage(e.data, (res) => {
    if (chrome.runtime.lastError) return;
    window.postMessage({ src: 'focus-ext', type, id, ...(res || {}) }, location.origin);
  });
});
// 页面可能先于本脚本发了 hello，这里主动报到一次
chrome.runtime.sendMessage({ type: 'hello' }, (res) => {
  if (chrome.runtime.lastError) return;
  const post = () => window.postMessage({ src: 'focus-ext', type: 'hello', ...(res || {}) }, location.origin);
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', post); else post();
});
