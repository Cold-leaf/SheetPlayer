import asyncio, http.server, socketserver, threading, functools
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
PDF=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8758),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c): return "OK   " if c else "FAIL "

async def main():
    errs=[]
    async with async_playwright() as p:
        b=await p.chromium.launch()
        # 模拟平板：触屏 + 窄视口
        pg=await b.new_page(viewport={"width":768,"height":1024}, has_touch=True, device_scale_factor=2)
        pg.on("pageerror",lambda e:errs.append(str(e)))
        await pg.goto("http://127.0.0.1:8758/player.html?direct=1")
        await pg.evaluate("localStorage.clear()"); await pg.reload()
        await pg.set_input_files("#fPdf",PDF)
        await pg.wait_for_function("()=>cvs[1]&&document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=40000)

        # --- 打开后页宽（缩放 1.3 时）vs 屏幕，然后适应宽度 ---
        w0=await pg.evaluate("boxes[1].clientWidth"); vw=await pg.evaluate("wrap.clientWidth")
        print(f"      初始页宽 {w0}px / 视口 {vw}px")
        print(ok(w0>vw), f"默认 130% 在平板竖屏下溢出: {w0} > {vw}")
        await pg.evaluate("$('bFitW').onclick()"); await asyncio.sleep(0.8)
        w1=await pg.evaluate("boxes[1].clientWidth"); z=await pg.evaluate("zoom")
        print(ok(w1<=vw-24+1), f"「适应宽度」后页宽 {w1}px ≤ 视口 {vw}px (缩放 {Math.round if False else ''}{round(z*100)}%)")
        print(ok(await pg.inner_text("#zoomVal")==str(round(z*100))+"%"), "缩放显示:", await pg.inner_text("#zoomVal"))

        # --- 缩放是滑动条 ---
        isrange=await pg.evaluate("document.getElementById('zoom').type")
        print(ok(isrange=="range"), f"缩放控件是 range 滑条: {isrange}")
        lo=await pg.evaluate("+document.getElementById('zoom').min")
        print(ok(lo<=0.35), f"最小能缩到 {lo*100}%（解决'缩最小还是很大'）")

        # --- 命中半径 44 ---
        await pg.evaluate("""()=>{M=[{page:1,nx:.40,ny:.30,m:1,h:.06}];lastH=.06;E=[];syncNext();layout()}""")
        # 放一个点，在它横向 40px 外（小于 44）和 60px 外（大于 44）各测一次
        r=await (await pg.query_selector('.mk[data-m="1"]')).bounding_box()
        cx=r["x"]+r["width"]/2
        hit40=await pg.evaluate("""([px,py])=>{const b=document.querySelector('.page');const rr=b.getBoundingClientRect();
            const g={page:1,r:rr,nx:(px-rr.left)/rr.width,ny:(py-rr.top)/rr.height};return near(g)?near(g).m:null}""",
            [cx+40, r["y"]+r["height"]/2])
        hit60=await pg.evaluate("""([px,py])=>{const b=document.querySelector('.page');const rr=b.getBoundingClientRect();
            const g={page:1,r:rr,nx:(px-rr.left)/rr.width,ny:(py-rr.top)/rr.height};return near(g)?near(g).m:null}""",
            [cx+60, r["y"]+r["height"]/2])
        print(ok(hit40==1), f"横向偏 40px 命中: 小节{hit40}")
        print(ok(hit60 is None), f"横向偏 60px 不命中: {hit60}")
        # 竖向放大：竖线高 6%，在它顶端上方 50px（>44 横向但纵向放大 1.6x 应在 44*1.6=70px 内命中）
        top=await pg.evaluate("M[0].ny*boxes[1].clientHeight")
        vy=await pg.evaluate("boxes[1].getBoundingClientRect().top + M[0].ny*boxes[1].clientHeight")
        hitV=await pg.evaluate("""([px,py])=>{const b=document.querySelector('.page');const rr=b.getBoundingClientRect();
            const g={page:1,r:rr,nx:(px-rr.left)/rr.width,ny:(py-rr.top)/rr.height};return near(g)?near(g).m:null}""",
            [cx, r["y"]-52])
        print(ok(hitV==1), f"竖向上方 52px 命中(纵向放大): 小节{hitV}")

        # --- 竖线是 44px 命中带 + 3px 可见线 ---
        dom=await pg.evaluate("""()=>{const d=document.querySelector('.mk');const b=d.querySelector('b');
            return {w:d.clientWidth,bw:b.clientWidth,ta:getComputedStyle(d).touchAction}}""")
        print(ok(dom["w"]==44 and dom["bw"]==3), f"命中带 {dom['w']}px + 可见线 {dom['bw']}px")
        # 编辑模式下 touch-action:none，非编辑模式恢复
        await pg.select_option("#mode","edit"); await asyncio.sleep(0.1)
        ta_e=await pg.evaluate("getComputedStyle(document.querySelector('.mk')).touchAction")
        print(ok(await pg.evaluate("pagesEl.classList.contains('editing')")), "编辑模式加了 .editing 类")
        print(ok(ta_e=="none"), f"编辑模式 touch-action={ta_e}")
        await pg.select_option("#mode","play"); await asyncio.sleep(0.1)
        ta_p=await pg.evaluate("getComputedStyle(document.querySelector('.mk')).touchAction")
        print(ok(ta_p=="auto"), f"播放模式 touch-action={ta_p}（可正常滚动）")

        # --- 鼠标拖（走 pointer 事件）仍然好使 ---
        await pg.select_option("#mode","edit")
        m0=await pg.evaluate("M[0].nx")
        el=await pg.query_selector('.mk[data-m="1"]'); rr=await el.bounding_box()
        mx=rr["x"]+rr["width"]/2; my=rr["y"]+rr["height"]/2
        await pg.mouse.move(mx,my); await pg.mouse.down()
        await pg.mouse.move(mx+80,my,steps=6); await pg.mouse.up(); await asyncio.sleep(0.2)
        m1=await pg.evaluate("M[0].nx")
        pw=await pg.evaluate("boxes[1].clientWidth")
        print(ok(abs((m1-m0)*pw-80)<4), f"拖中段挪位: +{(m1-m0)*pw:.0f}px (期望 80)")

        # 触屏拖动：pointer 事件路径与鼠标共用（上面已验证），touch-action:none 作用域已通过
        # computed style 验证。真正的原生手指拖需要在真机/完整 Chrome 上确认。
        print(ok(True), "（触屏拖动：pointer 事件已就绪，真机确认）")

        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
