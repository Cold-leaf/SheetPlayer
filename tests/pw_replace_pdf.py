# 换谱：PDF 是项目的附件，标注绑在项目上。
# 1) 「加完笔记重新导出的 PDF」：内容变了、文件名没变 → 按名字认回原项目，标注照旧
# 2) 「换谱」按钮：换成一份完全不同的谱子 → 标注照旧，旧谱子进 pdfHistory
import asyncio, http.server, socketserver, threading, functools, shutil
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
A=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
B=ROOT+"/线谱合集/BW_不忘初心[线][SATB+NA+Pn].pdf"
C=ROOT+"/线谱合集/CQ_传奇[线][SATB+NA+Pn][任知超][处理后].pdf"
SAME="/tmp/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"   # 同名、内容是另一首 = 加笔记重导出的最小模型
shutil.copy(B,SAME)
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8775),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c): return "OK   " if c else "FAIL "

DB="""(async()=>{const db=await new Promise(r=>{const o=indexedDB.open('sheetplayer');o.onsuccess=()=>r(o.result)});
 const g=(s)=>new Promise(r=>{db.transaction(s).objectStore(s).getAll().onsuccess=e=>r(e.target.result)});
 const P=await g('projects'),M=await g('marks'),F=await g('files'),T=await g('tracks'),N=await g('anns');
 return {p:P,m:M,f:F,t:T,a:N}})()"""

async def marks(pg):
    return await pg.evaluate("M.map(x=>x.m).join(',')")

async def main():
    errs=[]
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={"width":1500,"height":1000})
        pg.on("pageerror",lambda e:errs.append(str(e)))
        await pg.goto("http://127.0.0.1:8775/player.html")
        await pg.wait_for_function("()=>idb!==null&&$('lib').style.display==='flex'",timeout=15000)

        # 导入原谱，标 3 个小节
        await pg.set_input_files("#fPdf",A)
        await pg.wait_for_function("()=>document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=60000)
        pid0=await pg.evaluate("pid"); h1=await pg.evaluate("pdfHash")
        print(ok(bool(pid0) and pid0[0]=='p'), "项目 id 以 p 开头: "+str(pid0))
        name0=await pg.evaluate("track.name")
        await pg.select_option("#mode","mark")
        bb=await (await pg.query_selector('.page[data-page="1"]')).bounding_box()
        for fx in (0.3,0.45,0.6):
            await pg.mouse.click(bb["x"]+bb["width"]*fx,bb["y"]+bb["height"]*0.4)
        await asyncio.sleep(0.9)
        print(ok(await pg.evaluate("M.length")==3), "原谱标好 3 个小节")

        # ① 同名不同内容（加完笔记重新导出的那份）→ 按文件名认回同一个项目
        await pg.set_input_files("#fPdf",SAME)
        await pg.wait_for_function("(h)=>pdfHash!==h&&M.length===3&&document.querySelectorAll('.mk').length===3",
                                   arg=h1,timeout=60000)
        h2=await pg.evaluate("pdfHash")
        print(ok(h2!=h1), "内容确实不同（哈希变了）")
        print(ok(await pg.evaluate("pid")==pid0), "认回的是同一个项目（pid 没变）")
        print(ok(await pg.evaluate("track.name")==name0), "文件名命中不是改名：项目名照旧 "+name0)
        print(ok(await marks(pg)=="1,2,3"), "换谱后 3 个小节还在: "+await marks(pg))
        m=await pg.inner_text("#msg")
        print(ok("按文件名认回" in m), "提示: "+m)

        await pg.evaluate("$('bLib').onclick()"); await pg.wait_for_timeout(500)
        print(ok(await pg.evaluate("document.querySelectorAll('.libCard').length")==1), "没有重复建项目：库里 1 张卡")
        d=await pg.evaluate(DB)
        print(ok(len(d["p"])==1 and len(d["m"])==1), f"projects={len(d['p'])} marks={len(d['m'])}")
        print(ok(d["p"][0]["pdf"]["hash"]==h2), "项目的当前谱子已换成新哈希")
        print(ok([x["hash"] for x in d["p"][0]["pdfHistory"]]==[h1]), "旧谱子进了 pdfHistory（1 条，是原谱）")
        print(ok(len([f for f in d["f"] if f["kind"]=="pdf"])==2), "两份 PDF 文件都在库里（内容不同，各存一份）")
        print(ok(len(d["t"])==0 and len(d["a"])==0), "老的 tracks/anns 表不再被写入（原样留着好回滚）")

        # 先塞一个时间点：它属于「标注」那一半，换谱必须连它一起留住
        await pg.evaluate("E=[{m:1,t:12.5,src:'tap'}];save()")
        await asyncio.sleep(0.6)

        # ② 「换谱」按钮：换成一份完全不同的谱子，标注一个字都不能少
        pg.once("dialog",lambda dlg:asyncio.create_task(dlg.accept()))
        async with pg.expect_file_chooser() as fc:
            await pg.click(".libCard button.repl")
        await (await fc.value).set_files(C)
        await pg.wait_for_function("()=>document.querySelectorAll('.mk').length===3",timeout=60000)
        await pg.wait_for_timeout(300)
        h3=await pg.evaluate("pdfHash")
        print(ok(h3 not in (h1,h2)), "确实换成了第三份谱子")
        print(ok(await pg.evaluate("pid")==pid0), "还是同一个项目")
        print(ok(await marks(pg)=="1,2,3"), "换谱后 3 个小节还在: "+await marks(pg))
        print(ok(await pg.evaluate("E.length")==1 and await pg.evaluate("E[0].t")==12.5),
              "时间点也原样保留（它属于标注那一半）")
        d=await pg.evaluate(DB)
        print(ok(len(d["p"])==1 and len(d["m"])==1), "库里仍然只有 1 个项目 / 1 份标注")
        print(ok([x["hash"] for x in d["p"][0]["pdfHistory"]]==[h2,h1]),
              "pdfHistory 2 条（最近的在前）: "+str([x["hash"][:8] for x in d["p"][0]["pdfHistory"]]))
        print(ok(d["p"][0]["pdf"]["hash"]==h3), "项目的当前谱子是第三份")

        # 换回上一份：走 ② 历史谱子那条路
        await pg.evaluate("$('bLib').onclick()"); await pg.wait_for_timeout(400)
        pg.once("dialog",lambda dlg:asyncio.create_task(dlg.accept()))   # 确认"用它换回"
        await pg.set_input_files("#fPdf",SAME)
        await pg.wait_for_function("(h)=>pdfHash===h&&M.length===3",arg=h2,timeout=60000)
        print(ok(await marks(pg)=="1,2,3"), "换回用过的谱子：标注照旧")
        d=await pg.evaluate(DB)
        print(ok(len(d["p"])==1), "换回去也还是同一个项目，没有多出来")

        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
