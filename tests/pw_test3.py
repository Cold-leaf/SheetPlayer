import asyncio, glob, http.server, socketserver, threading, functools
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
PDF=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
AUD=glob.glob(ROOT+"/ICT_working/08-Assets/*.mp3")[0]
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8733),H)
threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c):return "OK  " if c else "FAIL"

async def main():
    errs=[]
    async with async_playwright() as p:
        b=await p.chromium.launch()
        pg=await b.new_page(viewport={"width":1500,"height":940},device_scale_factor=2)
        pg.on("pageerror",lambda e:errs.append(str(e)))
        await pg.goto("http://127.0.0.1:8733/player.html?direct=1")
        await pg.evaluate("localStorage.clear()"); await pg.reload()
        await pg.set_input_files("#fPdf",PDF); await pg.set_input_files("#fAud",AUD)
        await pg.wait_for_function("()=>document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=30000)

        # 导入消息不再被残留消息吞掉
        await pg.select_option("#mode","edit")   # 故意留下一条模式提示
        open("/tmp/i1.json","w").write('{"M":[{"page":1,"nx":0.2,"ny":0.25,"m":1},{"page":1,"nx":0.45,"ny":0.25,"m":2}],"E":[{"m":1,"t":1},{"m":2,"t":3}]}')
        await pg.set_input_files("#fMap","/tmp/i1.json"); await asyncio.sleep(0.3)
        m=await pg.inner_text("#msg")
        print(ok("已导入" in m), f'导入提示: "{m}"')

        # 存档恢复提示不再被"共 N 页"覆盖
        await asyncio.sleep(0.8); await pg.reload()
        await pg.set_input_files("#fPdf",PDF)
        await pg.wait_for_function("()=>document.querySelectorAll('.mk').length>0",timeout=30000)
        m=await pg.inner_text("#msg")
        print(ok("已恢复本地存档" in m), f'恢复提示: "{m}"')

        # 出一张成品图：标一排点 + 打上时间 + 高亮
        await pg.set_input_files("#fAud",AUD)
        bb=await (await pg.query_selector('.page[data-page="1"]')).bounding_box()
        await pg.evaluate("M=[];E=[];syncNext();layout()")
        await pg.select_option("#mode","mark")
        pts=[(0.13,0.255),(0.40,0.255),(0.66,0.255),(0.13,0.345),(0.42,0.345),(0.70,0.345),
             (0.13,0.435),(0.45,0.435),(0.13,0.525),(0.48,0.525)]
        for x,y in pts: await pg.mouse.click(bb["x"]+bb["width"]*x, bb["y"]+bb["height"]*y)
        await pg.evaluate("E=[{m:1,t:0.5},{m:2,t:2.4},{m:3,t:4.3},{m:4,t:6.2},{m:5,t:8.1},{m:6,t:10.0}];refresh()")
        await pg.select_option("#mode","time")
        await pg.evaluate("setTap(7); aud.currentTime=6.4")
        await asyncio.sleep(0.4)
        await pg.evaluate("wrap.scrollTop=0")
        await pg.screenshot(path="/tmp/player_shot.png",clip={"x":0,"y":0,"width":1500,"height":760})
        print("stat:",await pg.inner_text("#stat"))
        print("page errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
