import asyncio, http.server, socketserver, threading, functools
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
PDF=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8787),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c): return "OK   " if c else "FAIL "

async def main():
    errs=[]
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={"width":1500,"height":1000})
        pg.on("pageerror",lambda e:errs.append(str(e)))
        await pg.goto("http://127.0.0.1:8787/player.html?direct=1")
        await pg.set_input_files("#fPdf",PDF)
        await pg.wait_for_function("()=>document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=30000)

        # 1,2,3 三个小节（带时间点），删中间的小节 2 → 编号和时间点都应顺位成 1,2
        await pg.evaluate("""()=>{M=[{page:1,nx:.20,ny:.30,m:1,h:.08},{page:1,nx:.35,ny:.30,m:2,h:.08},
            {page:1,nx:.50,ny:.30,m:3,h:.08}];
          E=[{m:1,t:0,src:'tap'},{m:2,t:2,src:'tap'},{m:3,t:4,src:'tap'}];syncNext();layout()}""")
        await pg.evaluate("openPanel(2)")
        await pg.click("#pDelMk")
        await pg.wait_for_timeout(200)
        Mm=await pg.evaluate("M.map(x=>x.m)")
        Em=await pg.evaluate("E.map(x=>x.m)")
        print(ok(Mm==[1,2]), f"删中间小节后编号顺位: M={Mm}（期望 [1,2]）")
        print(ok(Em==[1,2]), f"时间点跟着顺位: E={Em}（期望 [1,2]）")
        print(ok(await pg.evaluate("nextM")==3), f"nextM=3（期望 {await pg.evaluate('nextM')}==3）")
        print(ok(await pg.evaluate("!document.querySelector('.mk[data-m=\"3\"]')")), "旧编号 3 的竖线已消失")

        # 删第一个（m=1）→ 后面的 2 顺位成 1
        await pg.evaluate("openPanel(1)")
        await pg.click("#pDelMk")
        await pg.wait_for_timeout(200)
        print(ok(await pg.evaluate("M.map(x=>x.m)")==[1]), "删第一个：剩余编号 [1]")

        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
