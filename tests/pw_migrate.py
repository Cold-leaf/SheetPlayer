import asyncio, http.server, socketserver, threading, functools
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
PDF=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
NAME=PDF.split('/')[-1]
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8773),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c): return "OK   " if c else "FAIL "

async def main():
    errs=[]
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={"width":1500,"height":1000})
        pg.on("pageerror",lambda e:errs.append(str(e)))
        # 预埋旧版 localStorage 存档（v5 载荷，键 = player:<文件名>）
        await pg.goto("http://127.0.0.1:8773/player.html?direct=1")
        await pg.evaluate("""n=>localStorage.setItem('player:'+n,JSON.stringify({v:5,
          M:[{page:1,nx:0.3,ny:0.4,m:1,h:0.05},{page:1,nx:0.45,ny:0.4,m:2,h:0.05}],
          E:[{m:1,t:0.5,src:'tap'}],TEMPO:[{m:1,bpm:120}],METER:[{sig:[4,4],ranges:[]}],
          FORM:[],offset:0,ts:1755630000000}))""",NAME)

        # 新版启动：扫库把老存档搬进曲目库（legacy 曲目，等待导入 PDF）
        await pg.goto("http://127.0.0.1:8773/player.html")
        await pg.wait_for_function("()=>idb!==null&&$('lib').style.display==='flex'",timeout=10000)
        await pg.wait_for_function("()=>document.querySelector('.libCard.legacy')!==null",timeout=10000)
        txt=await pg.inner_text(".libCard.legacy")
        print(ok("已标 2 小节" in txt and "等待导入 PDF" in txt), "老存档扫进曲目库: "+txt.replace("\n"," | "))
        print(ok((await pg.evaluate("n=>localStorage.getItem('player:'+n)!==null",NAME)) is not None and
                 (await pg.evaluate("n=>localStorage.getItem('player:'+n)!==null",NAME))), "哈希解析前老键保留（两头都有，不丢数据）")

        # 打开 legacy 曲目 → 选 PDF → 按哈希解析迁移
        async with pg.expect_file_chooser() as fc:
            await pg.click(".libCard.legacy button.open")
        await (await fc.value).set_files(PDF)
        await pg.wait_for_function("()=>document.querySelectorAll('.mk').length===2",timeout=30000)
        print(ok(await pg.evaluate("M.map(x=>x.m).join(',')")=="1,2" and await pg.evaluate("E.length")==1),
                  "legacy 曲目解析后标注完整恢复（含时间点）")
        print(ok(await pg.evaluate("n=>localStorage.getItem('player:'+n)===null",NAME)), "解析后老 localStorage 键被清理")
        print(ok(await pg.evaluate("""(async()=>{const db=await new Promise(r=>{const o=indexedDB.open('sheetplayer');o.onsuccess=()=>r(o.result)});
          const a=await new Promise(r=>{db.transaction('anns').objectStore('anns').getAll().onsuccess=e=>r(e.target.result)});
          const t=await new Promise(r=>{db.transaction('tracks').objectStore('tracks').getAll().onsuccess=e=>r(e.target.result)});
          return a.every(x=>!x.hash.startsWith('legacy:'))&&t.every(x=>!x.hash.startsWith('legacy:'))})()""")),
              "legacy 记录迁移成哈希键（库里不再有 legacy:*）")

        # 再次标点 → 存档走哈希键；刷新 → 曲目打开后恢复
        await pg.select_option("#mode","mark")
        bb=await (await pg.query_selector('.page[data-page="1"]')).bounding_box()
        await pg.mouse.click(bb["x"]+bb["width"]*0.6,bb["y"]+bb["height"]*0.4)
        await asyncio.sleep(0.8)
        await pg.reload()
        await pg.wait_for_function("()=>idb!==null&&$('lib').style.display==='flex'",timeout=10000)
        await pg.wait_for_timeout(400)
        print(ok("已标 3 小节" in await pg.inner_text(".libCard")), "迁移后继续标注，库卡片统计更新")
        await pg.click(".libCard button.open")
        await pg.wait_for_function("()=>document.querySelectorAll('.mk').length===3",timeout=30000)
        print(ok(await pg.evaluate("M.length")==3 and await pg.evaluate("E.length")==1), "刷新重开完整恢复")

        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
