import asyncio, http.server, socketserver, threading, functools
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
PDF=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8772),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c): return "OK   " if c else "FAIL "

async def main():
    errs=[]
    async with async_playwright() as p:
        b=await p.chromium.launch()
        ctx=await b.new_context(viewport={"width":900,"height":800})
        # IndexedDB 完全不可用（open 直接抛）：应降级成传统 localStorage 模式，不弹库、不报错
        await ctx.add_init_script("Object.defineProperty(window,'indexedDB',{get(){return {open(){throw new Error('IDB blocked')}}},configurable:true})")
        pg=await ctx.new_page()
        pg.on("pageerror",lambda e:errs.append(str(e)))
        await pg.goto("http://127.0.0.1:8772/player.html")
        await asyncio.sleep(0.8)   # 等 boot 的降级提示

        print(ok(await pg.evaluate("idb===null")), "IndexedDB 不可用被探测到（idb=null）")
        print(ok(await pg.evaluate("$('lib').style.display!=='flex'")), "降级后不显示曲目库界面")
        print(ok("传统模式" in await pg.inner_text("#msg")), "降级提示: "+await pg.inner_text("#msg"))
        print(ok(await pg.evaluate("$('bLib').style.display==='none'")), "菜单里隐藏「曲目库」入口")

        # 传统模式功能照常：标点 → localStorage 存档 → 刷新恢复
        await pg.set_input_files("#fPdf",PDF)
        await pg.wait_for_function("()=>document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=30000)
        await pg.select_option("#mode","mark")
        bb=await (await pg.query_selector('.page[data-page="1"]')).bounding_box()
        await pg.mouse.click(bb["x"]+bb["width"]*0.3,bb["y"]+bb["height"]*0.4)
        await asyncio.sleep(0.8)
        print(ok(await pg.evaluate("localStorage.getItem('player:'+pdfName)!==null")), "标注按文件名存进 localStorage")
        await pg.reload()
        await pg.wait_for_function("()=>$('stat').textContent.includes('已标 0')",timeout=10000)
        await pg.set_input_files("#fPdf",PDF)
        await pg.wait_for_function("()=>document.querySelectorAll('.mk').length===1",timeout=30000)
        print(ok(await pg.evaluate("M.length")==1), "刷新后从 localStorage 恢复标注")

        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
