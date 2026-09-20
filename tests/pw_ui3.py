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

        # --- 横向/纵向：菜单「视图」里的一个**按钮**（一眼找得到的入口）。
        # 状态本体是紧挨着的 hidden #chkHoriz，按钮只是它的 .click() 壳（跟 #fPdf ↔ label 同一套） ---
        await pg.evaluate("$('menu').style.display='block'"); await asyncio.sleep(0.2)
        print(ok(await pg.is_visible("#bHoriz")), "菜单「视图」里能看到方向按钮")
        print(ok(await pg.evaluate("!!$('bHoriz').closest('#menu')")), "方向按钮在菜单里，工具栏上没有第二个入口")
        # 文案显示的是**当前**方向（不是点了会变成什么），所以横竖都读得出自己的状态
        print(ok(await pg.evaluate("$('bHoriz').textContent")=="纵向堆叠"), "按钮文案显示当前方向（刚切成纵向）")
        print(ok(await pg.evaluate("$('chkHoriz').checked")==False), "切回纵向后 chkHoriz 未勾选")
        print(ok(not await pg.evaluate("pagesEl.classList.contains('horiz')")), "纵向：没有 horiz 类")
        await pg.click("#bHoriz"); await asyncio.sleep(0.3)
        print(ok(await pg.evaluate("$('chkHoriz').checked") and await pg.evaluate("pagesEl.classList.contains('horiz')")), "点一下切到横向铺开")
        # 横向铺开实际生效：第2页在第1页右侧
        pos=await pg.evaluate("""()=>{const ps=[...document.querySelectorAll('.page')].map(p=>p.getBoundingClientRect());
            return ps[1].left>ps[0].left && Math.abs(ps[1].top-ps[0].top)<2}""")
        print(ok(pos), "页面确实左右铺开")
        print(ok(await pg.evaluate("$('bHoriz').textContent")=="横向铺开"), "按钮文案跟着状态变")
        await pg.click("#bHoriz"); await asyncio.sleep(0.3)
        print(ok(await pg.evaluate("$('chkHoriz').checked")==False and not await pg.evaluate("pagesEl.classList.contains('horiz')")), "再点一下切回纵向")
        await pg.evaluate("$('menu').style.display='none'")

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
        # 方向按钮收进菜单，窄屏（≤700px）照样点得到——它从工具栏搬走正是因为第 1 行
        # 390px 下只剩 2px 余量、放不下第二个入口，而不是"手机上不需要改方向"
        await pg2.evaluate("$('menu').style.display='block'"); await asyncio.sleep(0.2)
        bh=await pg2.evaluate("""()=>{const b=$('bHoriz'),r=b.getBoundingClientRect();
            return {shown:getComputedStyle(b).display!=='none', inMenu:!!b.closest('#menu'),
                    l:Math.round(r.left), rr:Math.round(r.right), vw:innerWidth, on:$('chkHoriz').checked}}""")
        print(ok(bh["shown"] and bh["inMenu"] and bh["l"]>=0 and bh["rr"]<=bh["vw"]+1),
              f"窄屏 380 菜单里的方向按钮在、且横向不出屏: [{bh['l']},{bh['rr']}] ⊆ 0–{bh['vw']}")
        print(ok(bh["on"]==False), f"窄屏 380 初始就是纵向堆叠: chkHoriz={bh['on']}")
        await pg2.click("#bHoriz"); await asyncio.sleep(0.3)
        print(ok(await pg2.evaluate("$('chkHoriz').checked")),
              "窄屏 380 点菜单里的按钮真的切得动方向")
        await pg2.click("#bHoriz"); await asyncio.sleep(0.3)
        await pg2.evaluate("$('menu').style.display='none'")
        # 窄屏横滑：第 1 行精简之后（PDF 收进菜单，方向键没再加回工具栏），
        # 380px 下已经放得下、不再溢出——该断言的是"每行都是横滑容器"，而不是"第一行一定溢出"
        rows2=await pg2.evaluate("""()=>[...document.querySelectorAll('#bar .row')].map(r=>
            ({ox:getComputedStyle(r).overflowX, sw:r.scrollWidth, cw:r.clientWidth}))""")
        print(ok(all(r["ox"]=="auto" for r in rows2)), f"窄屏每行都是横滑容器: {[r['ox'] for r in rows2]}")
        over=[r for r in rows2 if r["sw"]>r["cw"]]
        print(ok(len(over)>0), f"内容放不下的行确实溢出（{len(over)}/{len(rows2)} 行）")
        sc=await pg2.evaluate("""()=>{const r=[...document.querySelectorAll('#bar .row')]
              .find(r=>r.scrollWidth>r.clientWidth);if(!r)return -1;r.scrollLeft=9999;return r.scrollLeft}""")
        print(ok(sc>0), f"溢出的行真的能横滑: scrollLeft={sc}")

        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
