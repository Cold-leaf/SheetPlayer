# 改名 = 无损操作：老名字进 aka 别名表。
# 1) 改名 → 导出 → 清库 → 导入：在新设备上仍然是 1 个项目，名字跟着走
# 2) 对端还按老名字同步回来：按 aka 认领成同一个项目，不新建、不覆盖本地名
# 3) 改名之后重新导入老文件名的谱子：仍然认回这个项目
import asyncio, json, http.server, socketserver, threading, functools, shutil
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
A=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
B=ROOT+"/线谱合集/BW_不忘初心[线][SATB+NA+Pn].pdf"
FILE=A.split('/')[-1]                      # SK_斯卡布罗集市[线][TTBB+NA+WO].pdf
ORIG=FILE[:-4]                             # 项目名是文件名去掉 .pdf（导入时按显示名起名）
SAME="/tmp/"+FILE                          # 同名、内容是另一首 = 改名后重新导出的那份
shutil.copy(B,SAME)
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8812),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c): return "OK   " if c else "FAIL "

async def dlg(pg,text):
    await pg.wait_for_function("()=>$('dlg').style.display==='flex'",timeout=8000)
    await pg.fill("#dlgInp",text)
    await pg.click("#dlgOk")

async def main():
    errs=[]
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={"width":1500,"height":1000})
        pg.on("pageerror",lambda e:errs.append(str(e)))
        await pg.goto("http://127.0.0.1:8812/player.html")
        await pg.wait_for_function("()=>idb!==null&&$('lib').style.display==='flex'",timeout=15000)

        # 导入 + 标 3 小节 + 改名
        await pg.set_input_files("#fPdf",A)
        await pg.wait_for_function("()=>document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=60000)
        await pg.select_option("#mode","mark")
        bb=await (await pg.query_selector('.page[data-page="1"]')).bounding_box()
        for fx in (0.3,0.45,0.6):
            await pg.mouse.click(bb["x"]+bb["width"]*fx,bb["y"]+bb["height"]*0.4)
        await asyncio.sleep(0.9)
        await pg.evaluate("$('bLib').onclick()"); await pg.wait_for_timeout(400)
        await pg.click(".libCard button.ren")
        await dlg(pg,"斯卡布罗")
        await pg.wait_for_timeout(400)
        print(ok(await pg.evaluate("track.aka")==[ORIG]), "改名后原名进 aka: "+json.dumps(await pg.evaluate("track.aka"),ensure_ascii=False))
        print(ok("斯卡布罗" in await pg.inner_text(".libCard .nm")), "卡片显示新名")

        # 改名后重新导入老文件名的谱子 → 靠 aka 认回同一个项目
        await pg.set_input_files("#fPdf",SAME)
        await pg.wait_for_function("()=>M.length===3&&track&&track.pdf&&track.pdf.name!==null&&pdfHash.length===64",timeout=60000)
        await pg.wait_for_timeout(300)
        print(ok(await pg.evaluate("track.name")=="斯卡布罗"), "recognize 后名字还是改过的那个: "+await pg.evaluate("track.name"))
        await pg.evaluate("$('bLib').onclick()"); await pg.wait_for_timeout(400)
        print(ok(await pg.evaluate("document.querySelectorAll('.libCard').length")==1), "靠 aka 认领：没有多出第二个项目")

        # 导出 → 清库 → 导入（模拟换设备的闭环）
        await pg.evaluate("window.__b=null;URL.createObjectURL=b=>{window.__b=b;return 'blob:x'}")
        await pg.evaluate("$('libExpAll').onclick()"); await asyncio.sleep(0.3)
        j=json.loads(await pg.evaluate("window.__b.text()"))
        it=j["items"][0]
        print(ok(it["name"]=="斯卡布罗" and it["aka"]==[ORIG] and str(it["id"]).startswith("p")),
              "导出条目带 id/aka: "+json.dumps({k:v for k,v in it.items() if k not in ("data","pdfHistory","pdf")},ensure_ascii=False))
        print(ok(len(it["pdfHistory"])==1), "导出条目带 pdfHistory（换过的那份谱子）")

        await pg.evaluate("indexedDB.deleteDatabase('sheetplayer')")
        await pg.reload()
        await pg.wait_for_function("()=>idb!==null&&$('lib').style.display==='flex'",timeout=15000)
        await pg.wait_for_timeout(500)
        print(ok(await pg.evaluate("document.querySelectorAll('.libCard').length")==0), "清库后是空的")

        with open('/tmp/aka_ann.json','w') as f: json.dump(j,f,ensure_ascii=False)
        pg.once("dialog",lambda d:asyncio.create_task(d.accept()))
        await pg.set_input_files("#libImpAll","/tmp/aka_ann.json")
        await pg.wait_for_timeout(900)
        print(ok(await pg.evaluate("document.querySelectorAll('.libCard').length")==1), "导入后重建 1 个项目（名字跟随导出里的新名）")
        print(ok("斯卡布罗" in await pg.inner_text(".libCard .nm")), "名字跟随: "+await pg.inner_text(".libCard .nm"))
        print(ok(await pg.evaluate("""(async()=>{const db=await new Promise(r=>{const o=indexedDB.open('sheetplayer');o.onsuccess=()=>r(o.result)});
          const g=s=>new Promise(r=>{db.transaction(s).objectStore(s).getAll().onsuccess=e=>r(e.target.result)});
          const P=await g('projects'),M=await g('marks');return P.length===1&&M.length===1&&M[0].pid===P[0].id})()""")),
              "标注挂在同一个项目上")

        # 对端还按老名字同步回来 → 按 aka 认领，不新建、不覆盖本地名
        old=json.loads(json.dumps(j))
        old["items"][0]["id"]="p-另一台设备"
        old["items"][0]["name"]=ORIG                  # 对端没改名，报的还是老名字
        old["items"][0]["aka"]=[]
        old["items"][0]["data"]["ts"]=int(old["items"][0]["data"]["ts"])+999999   # 对端的更新
        with open('/tmp/aka_ann2.json','w') as f: json.dump(old,f,ensure_ascii=False)
        pg.once("dialog",lambda d:asyncio.create_task(d.accept()))
        await pg.set_input_files("#libImpAll","/tmp/aka_ann2.json")
        await pg.wait_for_timeout(900)
        print(ok(await pg.evaluate("document.querySelectorAll('.libCard').length")==1), "对端的老名字按 aka 认领：仍然只有 1 个项目")
        print(ok("斯卡布罗" in await pg.inner_text(".libCard .nm")), "本地名字没有被对端的老名字覆盖")
        print(ok(await pg.evaluate("""(async()=>{const db=await new Promise(r=>{const o=indexedDB.open('sheetplayer');o.onsuccess=()=>r(o.result)});
          const P=await new Promise(r=>{db.transaction('projects').objectStore('projects').getAll().onsuccess=e=>r(e.target.result)});
          return P.length===1&&P[0].aka.includes('"""+ORIG+"""')})()""")),
              "对端名字进了 aka，下次它再报同一个名字也认得出")

        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
