/* SheetPlayer Service Worker：把应用外壳（player.html + pdf.js + 图标）缓存下来，离线可用。
   每次发布改动记得 bump VER，旧缓存会在 activate 时清掉。
   VER 还要跟 player.html 里的 BUILD 一起 bump（同一个号）：菜单里那行「构建 vNN」
   是手机上唯一能看出"跑的是不是新页面"的地方，两边对不上就没法判断 */
const VER='v24';
const CACHE='sheetplayer-'+VER;
const ASSETS=['./','./index.html','./player.html','./manifest.json',
  './lib/pdf.min.js','./lib/pdf.worker.min.js',
  './icon-192.png','./icon-512.png','./icon-512-maskable.png'];

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
    // 页面：网络优先（保证能拿到更新），离线退回缓存的 player.html。
    // cache:'reload' 是关键——不加的话 fetch 仍可能命中浏览器的 HTTP 缓存
    // （GitHub Pages 发的是 max-age=600），于是"网络优先"实际拿到的是十分钟前的旧页面，
    // 表现就是"手机上某个新功能一直没有"。这个 HTML 才 250KB 左右，每次重取不心疼。
    e.respondWith(
      fetch(req,{cache:'reload'}).then(r=>{
        const cp=r.clone();caches.open(CACHE).then(c=>c.put('./player.html',cp));
        return r;
      }).catch(()=>caches.match('./player.html'))
    );
    return;
  }
  // CMap：按需取，取到就存下来。169 个文件共 1.7MB，全丢进 ASSETS 预缓存会让安装又慢又脆
  //（addAll 一个失败就整个 install 失败），而一份谱子实际只用到一两个。
  // 存下来之后离线也画得出中文批注——不存的话每次都要联网，离线排练时汉字又没了
  if(req.url.includes('/cmaps/')){
    e.respondWith(caches.match(req).then(r=>r||fetch(req).then(resp=>{
      if(resp.ok){const cp=resp.clone();caches.open(CACHE).then(c=>c.put(req,cp))}
      return resp;
    })));
    return;
  }
  // 静态资源：缓存优先
  e.respondWith(caches.match(req).then(r=>r||fetch(req)));
});
