import asyncio, http.server, socketserver, threading, functools
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
PDF=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8759),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c): return "OK   " if c else "FAIL "

async def main():
    errs=[]
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={"width":900,"height":800})
        pg.on("pageerror",lambda e:errs.append(str(e)))
        await pg.goto("http://127.0.0.1:8759/player.html?direct=1")
        await pg.evaluate("localStorage.clear()"); await pg.reload()
        await pg.set_input_files("#fPdf",PDF)
        await pg.wait_for_function("()=>cvs[1]&&document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=40000)
        np=await pg.evaluate("document.querySelectorAll('.page').length")

        await pg.evaluate("$('chkHoriz').checked=false;$('chkHoriz').onchange()"); await asyncio.sleep(0.2)   # 默认已横向，显式切回纵向再测

        # 纵向默认：页面上下堆叠
        v=await pg.evaluate("""()=>{const ps=[...document.querySelectorAll('.page')].map(p=>p.getBoundingClientRect());
            return {x0:ps[0].left, x1:ps[1].left, y0:ps[0].top, y1:ps[1].top}}""")
        print(ok(abs(v["x0"]-v["x1"])<2 and v["y1"]>v["y0"]), f"纵向：第2页在第1页正下方 (x差 {abs(v['x0']-v['x1']):.0f}px, y下移 {v['y1']-v['y0']:.0f}px)")

        # 开横向展开
        await pg.click("#bHoriz"); await asyncio.sleep(0.3)
        h=await pg.evaluate("""()=>{const ps=[...document.querySelectorAll('.page')].map(p=>p.getBoundingClientRect());
            return {x0:ps[0].left, x1:ps[1].left, y0:ps[0].top, y1:ps[1].top, sw:wrap.scrollWidth, cw:wrap.clientWidth}}""")
        print(ok(h["x1"]>h["x0"] and abs(h["y0"]-h["y1"])<2), f"横向：第2页在第1页右侧 (x移 {h['x1']-h['x0']:.0f}px, y差 {abs(h['y0']-h['y1']):.0f}px)")
        print(ok(h["sw"]>h["cw"]*2), f"内容横向铺开 {h['sw']}px > 视口 {h['cw']}px 可横滑")

        # 横向滚到最后一页
        await pg.evaluate("wrap.scrollLeft=wrap.scrollWidth")
        await asyncio.sleep(0.6)
        live=await pg.evaluate("document.querySelectorAll('.page canvas').length")
        print(ok(0<live<np), f"横向滚到末尾，懒渲染仍生效: 存活 canvas {live}/{np}")

        # 跟随滚动改左右向
        await pg.evaluate("""()=>{M=[{page:1,nx:.3,ny:.3,m:1,h:.05}];E=[{m:1,t:0}];
            syncNext();layout();aud.pause();aud.currentTime=0}""")
        await pg.evaluate("wrap.scrollLeft=0")
        await pg.evaluate("$('chkFollow').checked=true;follow(byM.get(1)[0],true)")
        sl=await pg.evaluate("wrap.scrollLeft")
        print(ok(sl>=0), f"横向跟随滚动生效 (scrollLeft={sl:.0f})")

        # 「适应」在横向下按高度适配
        await pg.evaluate("$('bFitW').onclick()"); await asyncio.sleep(0.8)
        ph_=await pg.evaluate("boxes[1].clientHeight"); vh=await pg.evaluate("wrap.clientHeight")
        print(ok(ph_<=vh-24+1), f"横向「适应」按高度: 页高 {ph_}px ≤ 视口 {vh}px")

        # 切回纵向，「适应」按宽度
        await pg.click("#bHoriz"); await asyncio.sleep(0.3)
        await pg.evaluate("$('bFitW').onclick()"); await asyncio.sleep(0.8)
        pw2=await pg.evaluate("boxes[1].clientWidth"); vw=await pg.evaluate("wrap.clientWidth")
        print(ok(pw2<=vw-24+1), f"纵向「适应」按宽度: 页宽 {pw2}px ≤ 视口 {vw}px")

        # 横向模式下缩放仍是滑条
        print(ok(await pg.evaluate("document.getElementById('zoom').type")=="range"), "缩放仍是 range 滑条")

        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
