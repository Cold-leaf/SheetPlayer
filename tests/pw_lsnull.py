import asyncio, http.server, socketserver, threading, functools
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
PDF=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8760),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c): return "OK   " if c else "FAIL "

async def main():
    errs=[]
    async with async_playwright() as p:
        b=await p.chromium.launch()
        ctx=await b.new_context(viewport={"width":900,"height":800})
        # 模拟 iPad 隐私模式 / 阻止 Cookie：localStorage 变成 null
        await ctx.add_init_script("Object.defineProperty(window,'localStorage',{get(){return null},configurable:true})")
        pg=await ctx.new_page()
        pg.on("pageerror",lambda e:errs.append(str(e)))
        await pg.goto("http://127.0.0.1:8760/player.html")
        await pg.set_input_files("#fPdf",PDF)
        await pg.wait_for_function("()=>cvs[1]&&document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=40000)

        print(ok(await pg.evaluate("LS===null")), "探测到 localStorage 不可用 (LS=null)")

        # 标几个点触发多次 save，不该报错、不该刷屏
        await pg.select_option("#mode","mark")
        bb=await (await pg.query_selector('.page[data-page="1"]')).bounding_box()
        for i in range(4):
            await pg.mouse.click(bb["x"]+bb["width"]*(0.2+i*0.15), bb["y"]+bb["height"]*0.3)
            await asyncio.sleep(0.5)   # 等 debounce 触发 save
        # 警告只触发一次（lsWarned 门控），且没有抛 uncaught 错误
        print(ok(await pg.evaluate("lsWarned")==True), "检测到不可用后已置 lsWarned（不再反复 warn）")
        # 直接看警告文案（在它被后续消息覆盖前单独验证一次）
        await pg.evaluate("lsWarned=false; warnLS()")
        print(ok("本地存储" in await pg.inner_text("#msg") and "导出JSON" in await pg.inner_text("#msg")),
              "警告文案明确: \""+ (await pg.inner_text("#msg")) +"\"")
        print(ok(await pg.evaluate("M.length")>=4), f"没有本地存储时功能照常（已标 {await pg.evaluate(chr(39)+chr(39)) if False else chr(0)}" if False else "没有本地存储时功能照常（标记仍能加）")

        # 清除存档按钮安全降级
        await pg.click("#bWipe")
        print(ok("没有存档可删" in await pg.inner_text("#msg")), "「清除存档」: "+await pg.inner_text("#msg"))

        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
