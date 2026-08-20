import asyncio, http.server, socketserver, threading, functools, shutil, json
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
PDF=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
PDF2="/tmp/换个名字.pdf"                       # 同一内容不同文件名，测哈希去重
shutil.copy(PDF,PDF2)
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8770),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c): return "OK   " if c else "FAIL "

async def main():
    errs=[]
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={"width":1500,"height":1000})
        pg.on("pageerror",lambda e:errs.append(str(e)))
        await pg.goto("http://127.0.0.1:8770/player.html")
        await pg.wait_for_function("()=>idb!==null&&$('lib').style.display==='flex'",timeout=10000)

        # 导入谱子 → 标点 → 换名再导入同一份 → 哈希去重
        await pg.set_input_files("#fPdf",PDF)
        await pg.wait_for_function("()=>document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=30000)
        await pg.select_option("#mode","mark")
        bb=await (await pg.query_selector('.page[data-page="1"]')).bounding_box()
        for fx in (0.3,0.45,0.6):
            await pg.mouse.click(bb["x"]+bb["width"]*fx,bb["y"]+bb["height"]*0.4)
        await asyncio.sleep(0.8)
        await pg.set_input_files("#fPdf",PDF2)   # 内容相同、名字不同
        # 旧页面的 dataset.done/M 在 resetTrack 前仍存在，等「新曲名 + 恢复完成」才不算竞态
        await pg.wait_for_function("()=>pdfName==='换个名字.pdf'&&M.length===3",timeout=30000)
        print(ok(await pg.evaluate("M.length")==3), "换名再导入同一 PDF：标注按哈希匹配保留")
        await pg.evaluate("$('bLib').onclick()"); await pg.wait_for_timeout(500)
        print(ok(await pg.evaluate("document.querySelectorAll('.libCard').length")==1), "哈希去重：曲目没有重复建")
        print(ok("换个名字" in await pg.inner_text(".libCard .nm")), "显示名跟随最新文件名")

        # 批量导出 → 清库 → 批量导入（跨设备同步的闭环）
        await pg.evaluate("window.__b=null;URL.createObjectURL=b=>{window.__b=b;return 'blob:x'}")
        await pg.evaluate("$('libExpAll').onclick()"); await asyncio.sleep(0.3)
        j=json.loads(await pg.evaluate("window.__b.text()"))
        print(ok(j["app"]=="sheetplayer" and len(j["items"])==1 and j["items"][0]["data"]["M"] and len(j["items"][0]["data"]["M"])==3),
              "批量导出包含标注数据")
        await pg.evaluate("indexedDB.deleteDatabase('sheetplayer')")
        await pg.reload()
        await pg.wait_for_function("()=>idb!==null&&$('lib').style.display==='flex'",timeout=10000)
        await pg.wait_for_timeout(400)
        print(ok(await pg.evaluate("document.querySelectorAll('.libCard').length")==0), "清库后列表为空")
        with open('/tmp/batch_ann.json','w') as f: json.dump(j,f)
        pg.once("dialog",lambda d:asyncio.create_task(d.accept()))
        await pg.set_input_files("#libImpAll","/tmp/batch_ann.json")
        await pg.wait_for_timeout(800)
        print(ok(await pg.evaluate("document.querySelectorAll('.libCard').length")==1), "批量导入重建曲目")
        print(ok("等待导入 PDF" in await pg.inner_text(".libCard")), "导入的曲目先作为 stub（等待导入 PDF）")
        await pg.click(".libCard button.open")   # stub 打开 → 选 PDF 按哈希对上
        await pg.set_input_files("#fPdf",PDF)
        await pg.wait_for_function("()=>document.querySelectorAll('.mk').length===3",timeout=30000)
        print(ok(await pg.evaluate("M.length")==3 and await pg.evaluate("E.length")==0), "stub 解析后标注恢复")

        # 删除曲目：标注/文件/track 全部级联清掉
        await pg.evaluate("$('bLib').onclick()"); await pg.wait_for_timeout(500)
        pg.once("dialog",lambda d:asyncio.create_task(d.accept()))
        await pg.click(".libCard button.del")
        await pg.wait_for_timeout(800)
        print(ok(await pg.evaluate("document.querySelectorAll('.libCard').length")==0), "删除后列表为空")
        print(ok(await pg.evaluate("""(async()=>{const db=await new Promise(r=>{const o=indexedDB.open('sheetplayer');o.onsuccess=()=>r(o.result)});
          const n={};
          for(const s of ['tracks','anns','files'])n[s]=await new Promise(r=>{db.transaction(s).objectStore(s).getAll().onsuccess=e=>r(e.target.result.length)});
          return n.tracks===0&&n.anns===0&&n.files===0})()""")), "级联删除：tracks/anns/files 全清")

        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
