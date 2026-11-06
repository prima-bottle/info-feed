// 阅读器离线缓存：页面每次优先取最新版；PDF.js 等库文件取一次后长期用缓存
const C='reader-v1';
self.addEventListener('install',e=>self.skipWaiting());
self.addEventListener('activate',e=>e.waitUntil(self.clients.claim()));
self.addEventListener('fetch',e=>{
  const r=e.request;if(r.method!=='GET')return;
  const u=new URL(r.url);if(u.origin!==location.origin)return;
  if(u.pathname.includes('/reader/lib/')){
    e.respondWith(caches.match(r).then(m=>m||fetch(r).then(res=>{const c=res.clone();caches.open(C).then(x=>x.put(r,c));return res})));
  }else if(r.mode==='navigate'||u.pathname.endsWith('/reader/')||u.pathname.endsWith('.html')){
    e.respondWith(fetch(r,{cache:'no-store'}).then(res=>{const c=res.clone();caches.open(C).then(x=>x.put(r,c));return res}).catch(()=>caches.match(r)));
  }
});
