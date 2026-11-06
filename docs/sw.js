// 页面每次都从网络取最新版，不用浏览器缓存；离线时才用旧的
self.addEventListener('install',e=>self.skipWaiting());
self.addEventListener('activate',e=>e.waitUntil(self.clients.claim()));
self.addEventListener('fetch',e=>{
  const r=e.request;
  if(r.mode==='navigate'||r.url.endsWith('.html')||r.url.endsWith('/')||r.url.endsWith('work.enc')){
    e.respondWith(fetch(r,{cache:'no-store'}).then(res=>{const c=res.clone();caches.open('v1').then(x=>x.put(r,c));return res}).catch(()=>caches.match(r)));
  }
});
