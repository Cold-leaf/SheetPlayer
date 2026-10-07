# 未嵌入 CJK 字体的批注要画得出来：pdf.js 必须配 cMapUrl。
#
# 这一条是「换了谱子怎么没变」那桩案子的真凶。WPS 加的中文批注用的是没有嵌入的宋体
# （SimSun + GBK-EUC-H），不配 cMapUrl 的话 pdf.js 报 translateFont failed、汉字一个不画，
# 而批注的白色文本框照画——白底落在白纸上看不出来，于是新版看着跟旧版一模一样。
# 换谱其实成功了（哈希/历史/标注全对），只是多出来的中文渲染不出来。
#
# 素材：同一首歌的两版，字节级只差这些批注
#   「… 2.pdf」13 条 FreeText 中文批注（md5 c503d3c8）
#   「….pdf」  0 条（md5 66f30c9a）
# 断言靠两版**对比**，不写死像素阈值：带批注那版在歌词下方那条带里必须明显更"黑"。
import asyncio, http.server, socketserver, threading, functools, base64
from playwright.async_api import async_playwright
ROOT = "/home/xiaoyuanzhu/my-life-db/data/assets"
ANN = ROOT + "/SheetPlayerTests/AD_Anotherdayofsun[线][SATB+NA+Pn] 2.pdf"   # 有中文批注
PLAIN = ROOT + "/SheetPlayerTests/AD_Anotherdayofsun[线][SATB+NA+Pn].pdf"     # 没有

class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
H = functools.partial(Quiet, directory=ROOT + "/SheetPlayer")
socketserver.TCPServer.allow_reuse_address = True
srv = socketserver.TCPServer(("127.0.0.1", 8815), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()

def ok(c): return "OK   " if c else "FAIL "

# 用**应用自己的** openPdf 打开，再数第 4 页歌词带里的深色像素。
# 走 openPdf 而不是自己调 getDocument，才测得到线上那份配置（PDF_OPTS）。
COUNT = """async([b64,page,y0,y1])=>{
  const bytes=Uint8Array.from(atob(b64),c=>c.charCodeAt(0));
  const f=new File([bytes],'x.pdf',{type:'application/pdf'});
  const doc=await openPdf(f);                      // ← 线上那条路径
  const pg=await doc.getPage(page);
  const vp=pg.getViewport({scale:2});
  const c=document.createElement('canvas');c.width=Math.round(vp.width);c.height=Math.round(vp.height);
  const ctx=c.getContext('2d',{willReadFrequently:true});
  ctx.fillStyle='#fff';ctx.fillRect(0,0,c.width,c.height);
  await pg.render({canvasContext:ctx,viewport:vp}).promise;
  const a=Math.round(c.height*y0),b=Math.round(c.height*y1);
  const d=ctx.getImageData(0,a,c.width,b-a).data;
  let dark=0;
  for(let k=0;k<d.length;k+=4){
    const g=(d[k]*299+d[k+1]*587+d[k+2]*114)/1000;
    if(g<110)dark++;
  }
  return {dark,pages:doc.numPages,w:c.width,band:[a,b]};
}"""

async def main():
    errs, warn = [], []
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": 1200, "height": 900})
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("console", lambda m: warn.append(m.text)
              if ("cMap" in m.text or "translateFont" in m.text) else None)
        await pg.goto("http://127.0.0.1:8815/player.html")
        await pg.wait_for_function("()=>!!window.pdfjsLib&&typeof openPdf==='function'", timeout=15000)

        # 配置本身：两个参数都要给，少一个 pdf.js 都不认
        cfg = await pg.evaluate("()=>({url:PDF_OPTS.cMapUrl,packed:PDF_OPTS.cMapPacked})")
        print(ok(bool(cfg["url"]) and cfg["packed"] is True),
              "openPdf 配了 CMap: cMapUrl=%s cMapPacked=%s" % (cfg["url"], cfg["packed"]))

        # cmaps 真的发得出来（放错目录的话这里 404，中文照样不显示）
        st = await pg.evaluate("async(u)=>{const r=await fetch(u+'GBK-EUC-H.bcmap');return {s:r.status,n:(await r.arrayBuffer()).byteLength}}", cfg["url"])
        print(ok(st["s"] == 200 and st["n"] > 1000),
              "GBK-EUC-H.bcmap 取得到（%d, %d 字节）—— WPS 中文批注就用这个编码" % (st["s"], st["n"]))

        warn.clear()
        b64ann = base64.b64encode(open(ANN, "rb").read()).decode()
        b64plain = base64.b64encode(open(PLAIN, "rb").read()).decode()
        a = await pg.evaluate(COUNT, [b64ann, 4, 0.09, 0.18])
        hit_ann = len(warn)
        plain = await pg.evaluate(COUNT, [b64plain, 4, 0.09, 0.18])

        print(ok(a["pages"] == 12 and plain["pages"] == 12), "两版都是 12 页")
        print(ok(hit_ann == 0), "打开带中文批注那版，没有 cMap/translateFont 报错（%d 条）" % hit_ann)
        gain = a["dark"] - plain["dark"]
        print(ok(gain > 400),
              "歌词带里多出的墨点 %d（带批注 %d vs 无批注 %d）—— 中文真的画出来了" % (gain, a["dark"], plain["dark"]))

        print("\npage errors:", errs or "(none)")
        await b.close()

asyncio.run(main())
