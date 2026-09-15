/**
 * SheetPlayer ⇄ ownCloud 只读代理（Cloudflare Worker）
 *
 * 为什么需要它：ownCloud 的 WebDAV 响应不带 CORS 头（预检 OPTIONS 带、真响应不带），
 * 所以浏览器里的网页读不到结果（"Failed to fetch"）。这个 Worker 站在中间转发，
 * 顺便把 CORS 头补上。
 *
 * 额外的好处：账号密码存在 Worker 的加密密钥里，**根本不下发到设备**——
 * 比把密码存在浏览器 IndexedDB 里更安全，也不用担心设备丢失。
 *
 * 只读：只转发 PROPFIND（列目录）和 GET（下载），不接受也没实现任何写操作。
 *
 * ── 部署（网页版即可，不用装 wrangler）──────────────────────────
 * 1. 打开 https://dash.cloudflare.com → Workers & Pages → Create → Worker，起个名字。
 * 2. 把本文件内容整个粘进编辑器，Deploy。
 * 3. 进该 Worker → Settings → Variables and Secrets，添加以下 **Secret**（加密）：
 *
 *    DAV_URL       ownCloud 设置页给你的 WebDAV 地址，例：
 *                  https://phdchorus.ucas.ac.cn/owncloud/remote.php/webdav
 *                  （末尾不要带路径，也不要以 / 结尾）
 *    DAV_USER      用户名，例：boher
 *    DAV_PASS      应用密码（不是主密码）
 *    ALLOW_ORIGIN  允许访问的来源，多个用逗号分隔。例：
 *                  https://cold-leaf.github.io
 *    TOKEN         可选。设了的话，客户端请求要带 ?k=同样的值，能挡住知道
 *                  Worker 地址的陌生人拿它当代理（应用里填在「密码」框）。
 *
 * 4. 把 Worker 地址（https://<名字>.<账号>.workers.dev）填进 App 的
 *    ownCloud 面板：方式选「代理（Worker）」。
 */

const JSON_HEADERS = {'Content-Type': 'application/json; charset=utf-8'};

function corsHeaders(req, env) {
  const origin = req.headers.get('Origin') || '';
  const allow = String(env.ALLOW_ORIGIN || '*').split(',').map(s => s.trim()).filter(Boolean);
  // 不在白名单里也回一个白名单里的值，让浏览器自己去拦——不泄露「谁被允许」
  const value = allow.includes('*') ? '*' : (allow.includes(origin) ? origin : (allow[0] || ''));
  return {
    'Access-Control-Allow-Origin': value,
    'Access-Control-Allow-Methods': 'GET,OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Vary': 'Origin',
  };
}

function json(obj, status, cors) {
  return new Response(JSON.stringify(obj), {status, headers: {...cors, ...JSON_HEADERS}});
}

// 密码可能含非 ASCII，Basic 认证要求 UTF-8 后再 base64
function b64utf8(s) {
  const bytes = new TextEncoder().encode(s);
  let bin = '';
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin);
}

function davUrl(env, path) {
  const base = String(env.DAV_URL || '').replace(/\/+$/, '');
  const segs = String(path || '').split('/').filter(Boolean).map(encodeURIComponent);
  return base + (segs.length ? '/' + segs.join('/') : '/');
}

// href 形如 /owncloud/remote.php/webdav/线谱合集/x.pdf（URL 编码，可能是小写十六进制）
function stripPrefix(href, env) {
  let p = href;
  try { p = new URL(href, env.DAV_URL).pathname; } catch (e) { /* 相对路径就用原值 */ }
  p = decodeURIComponent(p);
  const prefix = decodeURIComponent(new URL(env.DAV_URL).pathname).replace(/\/+$/, '');
  if (p.startsWith(prefix)) p = p.slice(prefix.length);
  return p.replace(/^\/+/, '').replace(/\/+$/, '');
}

// Worker 里没有 DOMParser，而 ownCloud 的 XML 结构固定，用正则解析足够稳
function parseList(xml, env) {
  const out = [];
  const re = /<(?:\w+:)?response\b[^>]*>([\s\S]*?)<\/(?:\w+:)?response>/g;
  let m;
  while ((m = re.exec(xml))) {
    const body = m[1];
    const href = (body.match(/<(?:\w+:)?href\b[^>]*>([\s\S]*?)<\/(?:\w+:)?href>/) || [])[1];
    if (href == null) continue;
    const path = stripPrefix(href, env);
    out.push({
      path,
      dir: /<(?:\w+:)?collection\s*\/>/.test(body),
      size: +((body.match(/<(?:\w+:)?getcontentlength\b[^>]*>(\d+)/) || [])[1] || 0),
    });
  }
  return out;
}

export default {
  async fetch(req, env) {
    const cors = corsHeaders(req, env);
    const url = new URL(req.url);

    if (req.method === 'OPTIONS') return new Response(null, {headers: cors});
    if (req.method !== 'GET') return json({error: '只支持 GET（这个代理是只读的）'}, 405, cors);

    if (env.TOKEN && url.searchParams.get('k') !== env.TOKEN) {
      return json({error: '缺少或错误的访问令牌'}, 403, cors);
    }

    const path = (url.searchParams.get('path') || '').replace(/^\/+|\/+$/g, '');
    const auth = 'Basic ' + b64utf8(`${env.DAV_USER}:${env.DAV_PASS}`);
    let r;
    try {
      r = await fetch(davUrl(env, path), url.pathname === '/list'
        ? {method: 'PROPFIND', headers: {Authorization: auth, Depth: '1', 'Content-Type': 'application/xml; charset=utf-8'}}
        : {headers: {Authorization: auth}});
    } catch (e) {
      return json({error: '连不上 ownCloud：' + e.message}, 502, cors);
    }

    if (!r.ok) {
      const hint = r.status === 401 ? '（认证失败：检查 DAV_USER / DAV_PASS，注意要用应用密码）' : '';
      return json({error: `ownCloud 返回 ${r.status}${hint}`}, 502, cors);
    }

    if (url.pathname === '/list') {
      const items = parseList(await r.text(), env).filter(it => {
        if (it.path === path || !it.path) return false;
        const parent = it.path.includes('/') ? it.path.slice(0, it.path.lastIndexOf('/')) : '';
        return parent === path;                      // 只要本层，不要孙辈
      });
      for (const it of items) it.name = it.path.split('/').pop();
      items.sort((a, b) => (b.dir - a.dir) || a.name.localeCompare(b.name, 'zh'));
      return json({items}, 200, cors);
    }

    if (url.pathname === '/file') {
      const h = new Headers(cors);
      h.set('Content-Type', r.headers.get('Content-Type') || 'application/octet-stream');
      const len = r.headers.get('Content-Length');
      if (len) h.set('Content-Length', len);
      h.set('Cache-Control', 'no-store');
      return new Response(r.body, {headers: h});     // 直接透传流：大音频也不占 Worker 内存
    }

    return json({error: '未知路径，只有 /list 和 /file'}, 404, cors);
  },
};
