import asyncio, http.server, socketserver, threading, functools, shutil
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
PDF=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
OTHER=ROOT+"/线谱合集/BW_不忘初心[线][SATB+NA+Pn].pdf"
SAME="/tmp/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"   # 同名但内容不同（另一首谱子）
shutil.copy(OTHER,SAME)
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8775),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c): return "OK   " if c else "FAIL "

async def main():
    errs=[]
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={"width":1500,"height":1000})
        pg.on("pageerror",lambda e:errs.append(str(e)))
        await pg.goto("http://127.0.0.1:8775/player.html")
        await pg.wait_for_function("()=>idb!==null&&$('lib').style.display==='flex'",timeout=15000)

        # 导入原谱，标 3 个小节
        await pg.set_input_files("#fPdf",PDF)
        await pg.wait_for_function("()=>document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=30000)
        await pg.select_option("#mode","mark")
        bb=await (await pg.query_selector('.page[data-page="1"]')).bounding_box()
        for fx in (0.3,0.45,0.6):
            await pg.mouse.click(bb["x"]+bb["width"]*fx,bb["y"]+bb["height"]*0.4)
        await asyncio.sleep(0.8)
        h1=await pg.evaluate("pdfHash")
        print(ok(await pg.evaluate("M.length")==3), "原谱标好 3 个小节")

        # 导入同名但内容不同的 PDF → 应按文件名自动重链接，标注照旧
        await pg.set_input_files("#fPdf",SAME)
        await pg.wait_for_function("()=>M.length===3&&document.querySelectorAll('.mk').length===3",timeout=30000)
        h2=await pg.evaluate("pdfHash")
        print(ok(h2!=h1), "内容确实不同（哈希变了）")
        print(ok(await pg.evaluate("M.length")==3), "重链接后 3 个小节照旧")
        print(ok("已按文件名关联" in await pg.inner_text("#msg")), "提示: "+await pg.inner_text("#msg"))

        # 库里仍只有一条曲目（旧版被清理），且标注还在新哈希下
        await pg.evaluate("$('bLib').onclick()"); await pg.wait_for_timeout(500)
        print(ok(await pg.evaluate("document.querySelectorAll('.libCard').length")==1), "旧版清理：库里只有 1 条曲目")
        print(ok("已标 3 小节" in (await pg.inner_text(".libCard"))), "卡片统计: "+(await pg.inner_text(".libCard")).replace("\n"," | "))
        print(ok(await pg.evaluate("""(h2)=>(async()=>{const db=await new Promise(r=>{const o=indexedDB.open('sheetplayer');o.onsuccess=()=>r(o.result)});
          const a=await new Promise(r=>{db.transaction('anns').objectStore('anns').getAll().onsuccess=e=>r(e.target.result)});
          const t=await new Promise(r=>{db.transaction('tracks').objectStore('tracks').getAll().onsuccess=e=>r(e.target.result)});
          const f=await new Promise(r=>{db.transaction('files').objectStore('files').getAll().onsuccess=e=>r(e.target.result)});
          return a.length===1&&t.length===1&&f.length===1&&a[0].hash===h2&&f[0].kind==='pdf'})()""",h2)), "旧键清理干净（anns/tracks/files 各剩一条且都是新哈希）")

        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
