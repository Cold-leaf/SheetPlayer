import asyncio, glob, http.server, socketserver, threading, functools
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
PDF=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8735),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page()
        await pg.goto("http://127.0.0.1:8735/player.html")
        await pg.evaluate("localStorage.clear()"); await pg.reload()
        await pg.set_input_files("#fPdf",PDF)
        await pg.wait_for_function("()=>document.querySelectorAll('.page').length>0",timeout=30000)
        # 40 小节，只打首尾两个点（3/4 ♩=120 -> 每小节 1.5s，39 小节 = 58.5s）
        await pg.evaluate("""()=>{
          M=Array.from({length:40},(_,i)=>({page:1,nx:.1+(i%8)*.1,ny:.2+Math.floor(i/8)*.08,m:i+1}));
          E=[{m:1,t:0},{m:40,t:58.5}]; syncNext(); layout();
        }""")
        occ=await pg.evaluate("OCC.length")
        times=await pg.evaluate("[5,20,40].map(m=>OCC.find(o=>o.m===m).t)")
        exact=await pg.evaluate("OCC.filter(o=>o.exact).length")
        grey=await pg.evaluate("document.querySelectorAll('.mk.noT').length")
        print(f"只打 2 个点 -> OCC 覆盖 {occ}/40 小节, 实测点 {exact} 个")
        print(f"推算时间: 小节5={times[0]:.2f}s 小节20={times[1]:.2f}s 小节40={times[2]:.2f}s")
        print(f"理论值(1.5s/小节): 小节5=6.00 小节20=28.50 小节40=58.50")
        print(f"误差: {[round(a-b,6) for a,b in zip(times,[6.0,28.5,58.5])]}")
        print(f"→ 但谱面上显示为'无时间'的灰点: {grey}/40 个")
        await b.close()
asyncio.run(main())
