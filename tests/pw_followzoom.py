import asyncio, http.server, socketserver, threading, functools
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
PDF=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8790),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c): return "OK   " if c else "FAIL "

async def main():
    errs=[]
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={"width":900,"height":800})
        pg.on("pageerror",lambda e:errs.append(str(e)))
        await pg.goto("http://127.0.0.1:8790/player.html?direct=1")

        # 默认就是播放模式
        mv=await pg.evaluate("document.getElementById('mode').value")
        print(ok(mv=="play"), f"打开默认播放模式: {mv}")
        print(ok(await pg.evaluate("[...document.getElementById('mode').options].map(o=>o.value)[0]")=="play"),
              "播放是模式列表第一项")
        print(ok(await pg.evaluate("!!document.querySelector('#bar #chkFollow')")), "「跟随滚动」在工具栏里")
        print(ok(await pg.evaluate("!document.querySelector('#menu #chkFollow')")), "已从菜单移除")

        await pg.set_input_files("#fPdf",PDF)
        await pg.wait_for_function("()=>document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=30000)

        await pg.evaluate("$('chkHoriz').checked=false;$('chkHoriz').onchange()"); await pg.wait_for_timeout(200)   # 测纵向分支，先切回纵向

        # 放大到页面明显比视口宽，一行里放 4 个小节（横跨整页宽度）
        await pg.evaluate("""()=>{zoom=3;$('zoom').value=3;applyZoom();
          M=[{page:1,nx:.10,ny:.30,m:1,h:.06},{page:1,nx:.40,ny:.30,m:2,h:.06},
             {page:1,nx:.70,ny:.30,m:3,h:.06},{page:1,nx:.95,ny:.30,m:4,h:.06}];
          E=[{m:1,t:0,src:'tap'},{m:2,t:2,src:'tap'},{m:3,t:4,src:'tap'},{m:4,t:6,src:'tap'}];
          syncNext();layout();wrap.scrollLeft=0;wrap.scrollTop=0;userScrollUntil=0}""")
        await pg.wait_for_timeout(300)
        wide=await pg.evaluate("wrap.scrollWidth>wrap.clientWidth+2")
        print(ok(wide), f"放大 3x 后页面比视口宽（scrollWidth {await pg.evaluate('wrap.scrollWidth')} > clientWidth {await pg.evaluate('wrap.clientWidth')}）")

        async def vis(m):
            return await pg.evaluate("""(m)=>{const d=(byM.get(m)||[])[0];if(!d)return null;
              const r=d.getBoundingClientRect(),w=wrap.getBoundingClientRect();
              return {inView:r.left>=w.left-1&&r.right<=w.right+1, left:Math.round(r.left-w.left),
                      sl:Math.round(wrap.scrollLeft)}}""",m)

        # 跟随到最右那个小节：横向应自动滚过去
        await pg.evaluate("follow((byM.get(4)||[])[0])")
        await pg.wait_for_timeout(200)
        v=await vis(4)
        print(ok(v["inView"]), f"跟随到最右小节4: 在视野内={v['inView']} (相对视口左 {v['left']}px, scrollLeft={v['sl']})")

        # 再跟随回最左：应滚回去
        await pg.evaluate("follow((byM.get(1)||[])[0])")
        await pg.wait_for_timeout(200)
        v1=await vis(1)
        print(ok(v1["inView"]), f"跟随回小节1: 在视野内={v1['inView']} (scrollLeft={v1['sl']})")

        # 关掉跟随后不再滚动
        await pg.evaluate("wrap.scrollLeft=0;document.getElementById('chkFollow').checked=false")
        await pg.evaluate("follow((byM.get(4)||[])[0])")
        await pg.wait_for_timeout(200)
        print(ok(await pg.evaluate("wrap.scrollLeft")==0, ), f"关掉跟随后不滚: scrollLeft={await pg.evaluate('wrap.scrollLeft')}")
        await pg.evaluate("document.getElementById('chkFollow').checked=true")

        # 未放大时（页面窄于视口）不应产生横向滚动
        await pg.evaluate("""()=>{zoom=.5;$('zoom').value=.5;applyZoom();wrap.scrollLeft=0;userScrollUntil=0}""")
        await pg.wait_for_timeout(300)
        await pg.evaluate("follow((byM.get(4)||[])[0])")
        await pg.wait_for_timeout(200)
        print(ok(await pg.evaluate("wrap.scrollLeft")==0), f"页面窄于视口时不横滚: scrollLeft={await pg.evaluate('wrap.scrollLeft')}")

        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
