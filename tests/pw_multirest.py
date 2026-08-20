import asyncio, http.server, socketserver, threading, functools
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
PDF=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8761),H); threading.Thread(target=srv.serve_forever,daemon=True).start()

async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={"width":1200,"height":900})
        await pg.goto("http://127.0.0.1:8761/player.html?direct=1")
        await pg.evaluate("localStorage.clear()"); await pg.reload()
        await pg.set_input_files("#fPdf",PDF)
        await pg.wait_for_function("()=>cvs[1]&&document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=40000)
        # 按我之前教的做法：小节1 在多小节休止左侧，跳号到 7 标在右侧
        await pg.evaluate("""()=>{M=[{page:1,nx:.20,ny:.30,m:1,h:.08},{page:1,nx:.55,ny:.30,m:7,h:.08},
                                   {page:1,nx:.80,ny:.30,m:8,h:.08}];
          E=[{m:1,t:0,src:'tap'},{m:7,t:12,src:'tap'},{m:8,t:14,src:'tap'}];
          lastH=.08;syncNext();layout();aud.pause()}""")
        print("OCC（插值把 2–6 补出来了）:", await pg.evaluate("OCC.map(o=>o.m+'@'+o.t.toFixed(1)).join(' ')"))
        print("nextM =", await pg.evaluate("nextM"), "（maxM+1）")
        print()
        for t in [0.5, 3.0, 6.0, 9.0, 12.5]:
            await pg.evaluate(f"aud.currentTime={t}")
            await asyncio.sleep(0.18)
            r=await pg.evaluate("""()=>{const i=occIndex(aud.currentTime),o=OCC[i];
              const b=document.getElementById('band');
              const cur=document.querySelector('.mk.cur');
              return {m:o?o.m:null, band:(b&&b.style.display!=='none')?'显示':'隐藏',
                      cur:cur?cur.dataset.m:'无', now:$('nowBox').textContent}}""")
            print(f"  t={t:>4}s  当前小节 {str(r['m']):>2}  进度带:{r['band']}  高亮竖线:{r['cur']:>2}  指示:{r['now']}")
        await b.close()
asyncio.run(main())
