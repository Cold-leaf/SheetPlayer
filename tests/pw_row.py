import asyncio, http.server, socketserver, threading, functools
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
PDF=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8756),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c): return "OK   " if c else "FAIL "

async def main():
    errs=[]
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={"width":1500,"height":1000})
        pg.on("pageerror",lambda e:errs.append(str(e)))
        await pg.goto("http://127.0.0.1:8756/player.html?direct=1")
        await pg.evaluate("localStorage.clear()"); await pg.reload()
        await pg.set_input_files("#fPdf",PDF)
        await pg.wait_for_function("()=>document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=40000)
        # 两行：第 1 行 3 条，第 2 行 2 条（纵向隔很远）
        await pg.evaluate("""()=>{M=[
            {page:1,nx:.15,ny:.30,m:1,h:.05},{page:1,nx:.35,ny:.30,m:2,h:.05},{page:1,nx:.55,ny:.30,m:3,h:.05},
            {page:1,nx:.15,ny:.60,m:4,h:.05},{page:1,nx:.35,ny:.60,m:5,h:.05}];
          lastH=.05;E=[];syncNext();layout()}""")
        # 打开第 1 行的面板，应用到整行
        await pg.select_option("#mode","edit")
        el=await pg.query_selector('.mk[data-m="1"]'); r=await el.bounding_box()
        await pg.mouse.click(r["x"]+r["width"]/2, r["y"]+r["height"]/2); await asyncio.sleep(0.3)
        print(ok("应用到整行" in await pg.inner_text("#pHAll")), "按钮文字:", await pg.inner_text("#pHAll"))
        await pg.fill("#pH","120")
        await pg.click("#pHAll"); await asyncio.sleep(0.3)   # 点击时 blur 触发 change(改单条) + onclick(改整行)
        hs=await pg.evaluate("M.map(x=>Math.round(x.h*boxes[1].clientHeight))")
        print(ok(hs==[120,120,120,55,55]), f"只影响第 1 行: {hs} (期望 [120,120,120,55,55])")
        print(ok("整行 3 条" in await pg.inner_text("#msg")), f'提示: "{await pg.inner_text("#msg")}"')
        # 真实用法：填值+点按钮 = 两步（blur 改单条 → 应用到整行），撤销两次全回 55
        await pg.evaluate("undo()"); await asyncio.sleep(0.2)
        mid=await pg.evaluate("M.map(x=>Math.round(x.h*boxes[1].clientHeight))")
        await pg.evaluate("undo()"); await asyncio.sleep(0.2)
        end=await pg.evaluate("M.map(x=>Math.round(x.h*boxes[1].clientHeight))")
        print(ok(mid==[120,55,55,55,55] and end==[55,55,55,55,55]),
              f"可撤销: 一次 {mid} -> 两次 {end}")
        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
