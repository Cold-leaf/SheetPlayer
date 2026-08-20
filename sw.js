/* SheetPlayer Service Worker：把应用外壳（player.html + pdf.js + 图标）缓存下来，离线可用。
   每次发布改动记得 bump VER，旧缓存会在 activate 时清掉。 */
const VER='v1';
const CACHE='sheetplayer-'+VER;
const ASSETS=['./','./index.html','./player.html','./manifest.json',
  './lib/pdf.min.js','./lib/pdf.worker.min.js','./icon-192.png','./icon-512.png'];

self.addEventListener('install',e=>{
  e.waitUntil(caches.open(CACHE).then(c=>c.addAll(ASSETS)).then(()=>self.skipWaiting()));
});
self.addEventListener('activate',e=>{
  e.waitUntil(caches.keys().then(ks=>
    Promise.all(ks.filter(k=>k!==CACHE).map(k=>caches.delete(k)))
  ).then(()=>self.clients.claim()));
});
self.addEventListener('fetch',e=>{
  const req=e.request;
  if(req.method!=='GET')return;
  if(new URL(req.url).origin!==location.origin)return;
  if(req.mode==='navigate'){
    // 页面：网络优先（保证能拿到更新），离线退回缓存的 player.html
    e.respondWith(
      fetch(req).then(r=>{
        const cp=r.clone();caches.open(CACHE).then(c=>c.put('./player.html',cp));
        return r;
      }).catch(()=>caches.match('./player.html'))
    );
    return;
  }
  // 静态资源：缓存优先
  e.respondWith(caches.match(req).then(r=>r||fetch(req)));
});
