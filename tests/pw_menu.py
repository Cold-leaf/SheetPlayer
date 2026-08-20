import asyncio, http.server, socketserver, threading, functools
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
PDF=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8766),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c): return "OK   " if c else "FAIL "

async def main():
    errs=[]
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={"width":1280,"height":900})
        pg.on("pageerror",lambda e:errs.append(str(e)))
        await pg.goto("http://127.0.0.1:8766/player.html?direct=1")
        await pg.evaluate("localStorage.clear()"); await pg.reload()
        await pg.set_input_files("#fPdf",PDF)
        await pg.wait_for_function("()=>cvs[1]&&document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=40000)

        # --- 缩放不设限 ---
        lo=await pg.evaluate("+document.getElementById('zoom').min")
        hi=await pg.evaluate("+document.getElementById('zoom').max")
        print(ok(lo<=0.05 and hi>=10), f"滑条范围 {lo}–{hi}（旧的是 0.35–3）")
        # zoomAt 能超过 3、低于 0.35
        await pg.evaluate("zoomAt(6, 300, 300)"); await asyncio.sleep(0.6)
        print(ok(await pg.evaluate("zoom")==6), f"zoomAt 到 6x（旧上限 3）: {await pg.evaluate('zoom')}")
        # 超大缩放 canvas 封顶 4096，不爆
        await pg.evaluate("zoomAt(10, 0, 0)"); await asyncio.sleep(0.8)
        cw=await pg.evaluate("cvs[1].width"); ch=await pg.evaluate("cvs[1].height")
        print(ok(max(cw,ch)<=4096), f"10x 渲染封顶: canvas {cw}x{ch}（≤4096）")
        await pg.evaluate("zoomAt(0.05, 0, 0)"); await asyncio.sleep(0.6)
        print(ok(await pg.evaluate("zoom")==0.05), f"zoomAt 到 0.05x（旧下限 0.35）: {await pg.evaluate('zoom')}")
        # 还原
        await pg.evaluate("zoomAt(1.3,0,0);applyZoom()")

        # --- 菜单 ---
        print(ok(await pg.is_visible("#menu")==False), "菜单初始隐藏")
        await pg.click("#bMenu"); await asyncio.sleep(0.2)
        print(ok(await pg.is_visible("#menu")), "点 ☰ 打开菜单")
        # 菜单里的控件在 DOM 里、事件仍绑定
        for iid in ["nextN","skipN","bSkip","bClr","off","shift","bShift","chkFollow","chkNum","chkProg","chkAlignY","chkSnapX","barWin","bGen","bExp","fMap","bWipe","bHelp"]:
            ex=await pg.evaluate(f"!!document.getElementById('{iid}')")
            if not ex: print("  MISSING", iid)
        # 点菜单里的「清空时间」不关菜单（在菜单内点击不关闭）
        await pg.evaluate("E=[{m:1,t:1,src:'tap'}];refresh()")
        await pg.click("#bClr"); await asyncio.sleep(0.2)
        print(ok(await pg.is_visible("#menu")), "点菜单内控件后菜单仍开（可连续调整）")
        print(ok(await pg.evaluate("E.length")==0), "「清空时间」在菜单里照常工作")
        # 点菜单外关闭
        await pg.mouse.click(640, 850); await asyncio.sleep(0.2)
        print(ok(await pg.is_visible("#menu")==False), "点菜单外关闭")

        # 工具栏行数：现在第一行精简，旧控件都进了菜单
        rows=await pg.eval_on_selector_all("#bar .row","e=>e.length")
        print(ok(rows==4), f"工具栏 {rows} 行（第一行精简 + 单独统计行）")

        # 关键工作流仍可用：标小节 + 打时间 + 撤销 + 频谱
        await pg.select_option("#mode","mark")
        bb=await (await pg.query_selector('.page[data-page="1"]')).bounding_box()
        await pg.mouse.click(bb["x"]+bb["width"]*.3, bb["y"]+bb["height"]*.3)
        print(ok(await pg.evaluate("M.length")==1), "标小节仍可用")
        await pg.click("#bUndo"); await asyncio.sleep(0.2)
        print(ok(await pg.evaluate("M.length")==0), "撤销仍可用")
        await pg.click("#bSpec"); await asyncio.sleep(0.2)
        print(ok(await pg.is_visible("#specBox")), "频谱仍可用")

        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
