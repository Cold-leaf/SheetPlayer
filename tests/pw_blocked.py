# 库里还有别的标签页占着旧版本时，升级会被 onblocked 挡住。
# 这时绝不能静默降级成「传统模式」——用户会看着一个空库，把新标注写进另一个存储后端。
# 正确表现：提示关掉其它标签页、库按钮保持可见；关掉之后刷新就正常了。
#
# 模拟方式：同一个浏览器上下文开两个标签页（同源 = 共用一个 IndexedDB）。
# 第 1 页用 ?direct=1（不碰 IndexedDB）手工开一个 v1 连接并一直握着不放，
# 第 2 页正常启动——它要升到 v2，就会被第 1 页挡住。
import asyncio, http.server, socketserver, threading, functools
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8814),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c): return "OK   " if c else "FAIL "

async def main():
    errs=[]
    async with async_playwright() as p:
        b=await p.chromium.launch()
        ctx=await b.new_context(viewport={"width":1500,"height":1000})
        await ctx.route("**raw.githubusercontent.com/**",
                        lambda r: r.fulfill(status=404,content_type="application/json",body="{}"))

        # 第 1 页：开一个 v1 连接并握着不放（等价于"还开着一个旧版本的标签页"）
        old=await ctx.new_page()
        old.on("pageerror",lambda e:errs.append("old:"+str(e)))
        await old.goto("http://127.0.0.1:8814/player.html?direct=1")
        hold=await old.evaluate("""()=>new Promise((res,rej)=>{
          const r=indexedDB.open('sheetplayer',1);
          r.onupgradeneeded=()=>{for(const s of ['files','tracks','anns','spec','meta'])
            if(!r.result.objectStoreNames.contains(s))r.result.createObjectStore(s,{keyPath:'hash'})};
          r.onsuccess=()=>{window.__hold=r.result;res(r.result.version)};
          r.onerror=()=>rej(r.error.name);
        })""")
        print(ok(hold==1), f"第 1 页握着 v1 连接（version={hold}）")

        # 第 2 页：正常启动 → 要升到 v2 → 被挡住
        pg=await ctx.new_page()
        pg.on("pageerror",lambda e:errs.append("new:"+str(e)))
        await pg.goto("http://127.0.0.1:8814/player.html")
        await pg.wait_for_timeout(2500)
        msg=await pg.inner_text("#msg")
        print(ok(await pg.evaluate("idb===null")), "升级被挡住：这次没打开库（idb===null）")
        print(ok("关掉" in msg and "标签页" in msg), "提示让用户关掉其它标签页: "+msg)
        print(ok("不支持 IndexedDB" not in msg), "没有谎报成「此浏览器不支持 IndexedDB」")
        print(ok(await pg.evaluate("$('bLib').style.display!=='none'")), "库按钮保持可见（不是被藏起来假装没有库）")
        print(ok(await pg.evaluate("$('lib').style.display")!="flex"), "没有弹出一个空库界面")

        # 关掉旧标签页的连接 → 刷新就正常了
        await old.evaluate("window.__hold.close()")
        await pg.reload()
        await pg.wait_for_function("()=>idb!==null&&$('lib').style.display==='flex'",timeout=15000)
        print(ok(await pg.evaluate("idb!==null")), "关掉其它标签页后刷新：库正常打开")
        await pg.wait_for_timeout(500)
        print(ok(await pg.evaluate("document.querySelectorAll('.libCard').length")==0), "库是空的（这次真的空）")

        # 顺带确认：传统模式（?direct=1）完全不受影响
        d=await ctx.new_page()
        d.on("pageerror",lambda e:errs.append("direct:"+str(e)))
        await d.goto("http://127.0.0.1:8814/player.html?direct=1")
        await d.wait_for_timeout(800)
        print(ok(await d.evaluate("idb===null") and await d.evaluate("$('bLib').style.display==='none'")),
              "?direct=1 逃生模式照旧：不碰 IndexedDB，库按钮隐藏")

        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
