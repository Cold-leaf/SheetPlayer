import asyncio, http.server, socketserver, threading, functools
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
PDF=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8788),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c): return "OK   " if c else "FAIL "

async def set_end(pg, m, end):
    await pg.evaluate(f"openPanel({m})")
    await pg.fill("#pEnd", str(end)); await pg.dispatch_event("#pEnd", "change")
    await pg.wait_for_timeout(200)

async def main():
    errs=[]
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={"width":1500,"height":1000})
        pg.on("pageerror",lambda e:errs.append(str(e)))
        await pg.goto("http://127.0.0.1:8788/player.html?direct=1")
        await pg.set_input_files("#fPdf",PDF)
        await pg.wait_for_function("()=>document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=30000)

        # 1,2,3 三个小节（带时间点），把小节 1 覆盖范围设成 6（结束节=6）→ 后面顺位成 7,8
        await pg.evaluate("""()=>{M=[{page:1,nx:.20,ny:.30,m:1,h:.08},{page:1,nx:.35,ny:.30,m:2,h:.08},
            {page:1,nx:.50,ny:.30,m:3,h:.08}];
          E=[{m:1,t:0,src:'tap'},{m:2,t:2,src:'tap'},{m:3,t:4,src:'tap'}];syncNext();layout()}""")
        await set_end(pg, 1, 6)
        Mm=await pg.evaluate("M.map(x=>[x.m,x.span||1])")
        Em=await pg.evaluate("E.map(x=>x.m).sort((a,b)=>a-b)")
        print(ok(await pg.evaluate("M.map(x=>x.m)")==[1,7,8]), f"设结束节=6 后编号顺位: M={await pg.evaluate('M.map(x=>x.m)')}（期望 [1,7,8]）")
        print(ok(await pg.evaluate("M[0].span")==6), "小节 1 的 span=6")
        print(ok(Em==[1,7,8]), f"时间点跟着顺位: E={Em}")
        lab=await pg.evaluate("document.querySelector('.mk[data-m=\"1\"] i').textContent")
        print(ok(lab=="1–6"), f"标签显示范围: '{lab}'（期望 1–6）")
        print(ok(await pg.evaluate("nextM")==9), f"nextM=9（期望 {await pg.evaluate('nextM')}）")

        # 收回成 1 → 顺位退回 2,3
        await set_end(pg, 1, 1)
        print(ok(await pg.evaluate("M.map(x=>x.m)")==[1,2,3]), f"收回结束节=1 后顺位退回: {await pg.evaluate('M.map(x=>x.m)')}（期望 [1,2,3]）")
        print(ok(await pg.evaluate("M[0].span||1")==1), "span 收回为 1")

        # 删掉覆盖 6 小节的那个小节 → 后面退 6
        await pg.evaluate("""()=>{M=[{page:1,nx:.20,ny:.30,m:1,h:.08,span:6},{page:1,nx:.35,ny:.30,m:7,h:.08},
            {page:1,nx:.50,ny:.30,m:8,h:.08}];E=[];syncNext();layout()}""")
        await pg.evaluate("openPanel(1)")
        await pg.click("#pDelMk"); await pg.wait_for_timeout(200)
        print(ok(await pg.evaluate("M.map(x=>x.m)")==[1,2]), f"删覆盖6小节的小节后: {await pg.evaluate('M.map(x=>x.m)')}（期望 [1,2]，7→1,8→2）")

        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
