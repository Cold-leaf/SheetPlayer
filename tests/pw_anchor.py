import asyncio, http.server, socketserver, threading, functools
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
PDF=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8765),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c): return "OK   " if c else "FAIL "

async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={"width":1200,"height":900})
        await pg.goto("http://127.0.0.1:8765/player.html?direct=1")
        await pg.evaluate("localStorage.clear()"); await pg.reload()
        await pg.set_input_files("#fPdf",PDF)
        await pg.wait_for_function("()=>cvs[1]&&document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=40000)
        await pg.evaluate("""()=>{M=[{page:1,nx:.50,ny:.30,m:1,h:.08}];E=[];lastH=.08;syncNext();layout();
            zoom=1.0;$('zoom').value=1;applyZoom();wrap.scrollTop=300}""")
        await asyncio.sleep(0.6)
        # 记录竖线视口位置，以它为锚点放大 1.6 倍
        r0=await pg.evaluate("""()=>{const el=document.querySelector('.mk');const r=el.getBoundingClientRect();
            return {x:r.left+r.width/2, y:r.top+r.height/2}}""")
        await pg.evaluate("""([x,y])=>{const rr=wrap.getBoundingClientRect();
            zoomAt(1.6, x-rr.left, y-rr.top)}""",[r0["x"],r0["y"]])
        await asyncio.sleep(0.5)
        r1=await pg.evaluate("""()=>{const el=document.querySelector('.mk');const r=el.getBoundingClientRect();
            return {x:r.left+r.width/2, y:r.top+r.height/2}}""")
        print(ok(abs(r0["x"]-r1["x"])<6 and abs(r0["y"]-r1["y"])<6),
              f"锚点内容不动: 竖线视口 ({r0['x']:.0f},{r0['y']:.0f}) -> ({r1['x']:.0f},{r1['y']:.0f})")
        print(ok(await pg.evaluate("zoom")==1.6), "zoom 精确到 1.6")
        await b.close()
asyncio.run(main())
