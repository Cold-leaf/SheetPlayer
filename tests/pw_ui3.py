import asyncio, http.server, socketserver, threading, functools
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
PDF=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8767),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c): return "OK   " if c else "FAIL "

async def main():
    errs=[]
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={"width":1280,"height":900})
        pg.on("pageerror",lambda e:errs.append(str(e)))
        await pg.goto("http://127.0.0.1:8767/player.html?direct=1")
        await pg.evaluate("localStorage.clear()"); await pg.reload()
        await pg.set_input_files("#fPdf",PDF)
        await pg.wait_for_function("()=>cvs[1]&&document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=40000)

        # 默认已横向，显式切回纵向再测切换
        await pg.evaluate("$('chkHoriz').checked=false;$('chkHoriz').onchange()"); await asyncio.sleep(0.2)

        # --- 横向/纵向 按钮 ---
        print(ok(await pg.is_visible("#bHoriz")), "按钮「纵向」可见（默认纵向）")
        print(ok(await pg.inner_text("#bHoriz")=="纵向"), "初始标签:", await pg.inner_text("#bHoriz"))
        print(ok(await pg.evaluate("$('chkHoriz').checked")==False), "chkHoriz 未勾选")
        await pg.click("#bHoriz"); await asyncio.sleep(0.3)
        print(ok(await pg.inner_text("#bHoriz")=="横向"), "点击后标签:", await pg.inner_text("#bHoriz"))
        print(ok(await pg.evaluate("$('chkHoriz').checked") and await pg.evaluate("pagesEl.classList.contains('horiz')")), "切到横向铺开")
        # 横向铺开实际生效：第2页在第1页右侧
        pos=await pg.evaluate("""()=>{const ps=[...document.querySelectorAll('.page')].map(p=>p.getBoundingClientRect());
            return ps[1].left>ps[0].left && Math.abs(ps[1].top-ps[0].top)<2}""")
        print(ok(pos), "页面确实左右铺开")
        await pg.click("#bHoriz"); await asyncio.sleep(0.3)
        print(ok(await pg.inner_text("#bHoriz")=="纵向" and await pg.evaluate("$('chkHoriz').checked")==False), "再点切回纵向")

        # --- stat 单独一行 ---
        rows=await pg.eval_on_selector_all("#bar .row","e=>e.length")
        print(ok(rows==4), f"工具栏现在 {rows} 行（多了一行放统计）")
        statRow=await pg.evaluate("""()=>{const s=document.getElementById('stat');const row=s.closest('.row');
            return [...row.children].filter(c=>c.id==='stat').length}""")
        print(ok(statRow==1), "stat 单独占一行")
        # 统计文本横着排（一行内，不换行）
        wrap=await pg.evaluate("""()=>{const s=document.getElementById('stat');return getComputedStyle(s).whiteSpace}""")
        print(ok(wrap=="nowrap" or wrap=="normal"), f"stat 横排 white-space={wrap}")

        # --- 手机窄屏按钮文本不竖排 ---
        pg2=await b.new_page(viewport={"width":380,"height":800})
        await pg2.goto("http://127.0.0.1:8767/player.html?direct=1")
        await pg2.set_input_files("#fPdf",PDF)
        await pg2.wait_for_function("()=>document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=40000)
        ws=await pg2.evaluate("""()=>{const b=document.getElementById('bUndo');
            return {ws:getComputedStyle(b).whiteSpace, h:b.clientHeight, t:b.textContent}}""")
        print(ok(ws["ws"]=="nowrap"), f"窄屏按钮 white-space={ws['ws']}")
        print(ok(ws["h"]<30), f"「{ws['t']}」按钮高度 {ws['h']}px（正常，非竖排）")
        # 第一行可横滑
        scrollable=await pg2.evaluate("document.querySelector('#bar .row').scrollWidth > document.querySelector('#bar .row').clientWidth")
        print(ok(scrollable), "窄屏第一行可横向滑动")

        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
