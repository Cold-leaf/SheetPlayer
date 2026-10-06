# 导入入口并排（本机 / ownCloud）都在演奏行的「曲目」「音频」两个下拉里：
#   · 演奏态下菜单里「谱子」段整块在 .editOnly 里被收掉，而手机默认就是演奏态——
#     这两个下拉里的入口是演奏态里**唯一**的谱子导入途径
#   · 动作用完必须复位：停在动作项上，下次点它 value 不变、change 不触发，就点不动了
#   · 「＋ 从本机导入谱子…」必须清掉 pendPid（上次点「换谱」/「打开」设下、又在文件选择器里
#     取消会留下它）——不清的话这份新谱子会被悄悄挂到那个项目头上，当成一次换谱
import asyncio, http.server, socketserver, threading, functools
from playwright.async_api import async_playwright
ROOT = "/home/xiaoyuanzhu/my-life-db/data/assets"
A = ROOT + "/线谱合集/BW_不忘初心[线][SATB+NA+Pn].pdf"
C = ROOT + "/线谱合集/CQ_传奇[线][SATB+NA+Pn][任知超][处理后].pdf"

H = functools.partial(http.server.SimpleHTTPRequestHandler, directory=ROOT + "/SheetPlayer")
socketserver.TCPServer.allow_reuse_address = True
srv = socketserver.TCPServer(("127.0.0.1", 8781), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()

def ok(c): return "OK   " if c else "FAIL "

DB = """(async()=>{const db=await new Promise(r=>{const o=indexedDB.open('sheetplayer');o.onsuccess=()=>r(o.result)});
 const g=(s)=>new Promise(r=>{db.transaction(s).objectStore(s).getAll().onsuccess=e=>r(e.target.result)});
 const P=await g('projects');
 return {n:P.length,pdf:P.map(x=>({id:x.id,hash:x.pdf&&x.pdf.hash,hist:(x.pdfHistory||[]).length}))}})()"""

async def opts(pg, sel):
    return await pg.evaluate("(s)=>[...$(s).options].map(o=>o.value)", sel)

async def main():
    errs = []
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": 390, "height": 844}, has_touch=True, device_scale_factor=2)
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("dialog", lambda d: asyncio.create_task(d.accept()))
        await pg.goto("http://127.0.0.1:8781/player.html")
        await pg.wait_for_function("()=>idb!==null&&$('lib').style.display==='flex'", timeout=15000)

        # 导入第一份谱子，作为「库里已有项目」
        await pg.set_input_files("#fPdf", A)
        await pg.wait_for_function("()=>document.querySelector('.page[data-page=\"1\"]')?.dataset.done", timeout=60000)
        pidA = await pg.evaluate("pid"); hA = await pg.evaluate("pdfHash")
        print(ok(bool(pidA) and pidA[0] == 'p'), "导入第一份谱子，项目 id: " + str(pidA))

        # 手机开机默认就是「演奏态 + 工具栏收起」（pointer:coarse 那条），先确认这两条前提
        print(ok(await pg.evaluate("document.body.classList.contains('perf')")), "手机默认进来就是演奏态")
        print(ok(await pg.evaluate("document.body.classList.contains('hidebar')")), "工具栏默认是收起的")
        await pg.evaluate("setBarHidden(false)"); await asyncio.sleep(0.4)
        print(ok(await pg.evaluate("$('lblPdf').offsetParent===null")),
              "演奏态下菜单里的「导一份新谱子」确实够不着（offsetParent=null）")

        # 两个下拉在演奏态里都露着，且各带导入入口
        vis = await pg.evaluate("(s)=>{const e=$(s);return !!e.offsetParent}", "trackSel")
        print(ok(vis), "演奏态下「曲目」下拉可见")
        t = await opts(pg, "trackSel")
        print(ok(t[:2] == ["__pdf", "__dav"]), "「曲目」下拉头两项是本机 / ownCloud 导入：" + str(t[:3]))
        print(ok(pidA in t and t[2] == pidA), "曲目列表接在导入入口后面，当前曲目仍被选中")
        a = await opts(pg, "audSel")
        print(ok(a[-1] == "__dav"), "「音频」下拉末尾是「＋ 从 ownCloud 添加音频…」：" + str(a))

        # ① 从本机导入：pendPid 里塞一个陈旧值，必须被清掉
        await pg.evaluate("(h)=>pendPid=h", pidA)
        async with pg.expect_file_chooser() as fc:
            await pg.select_option("#trackSel", "__pdf")
        await (await fc.value).set_files(C)
        await pg.wait_for_function("()=>document.querySelector('.page[data-page=\"1\"]')?.dataset.done", timeout=60000)
        await asyncio.sleep(1.0)
        pidC = await pg.evaluate("pid")
        print(ok(pidC != pidA), "陈旧的 pendPid 被清掉了：新谱子没被当成《不忘初心》的换谱")
        d = await pg.evaluate(DB)
        print(ok(d["n"] == 2), f"库里两个项目（没有把第一首换掉）：{d['n']}")
        old = [x for x in d["pdf"] if x["id"] == pidA][0]
        print(ok(old["hash"] == hA and old["hist"] == 0), "第一首的谱子与历史一个字节没动")
        print(ok(await pg.evaluate("$('trackSel').value") == pidC), "下拉复位到当前曲目，没停在动作项上")
        print(ok(await pg.evaluate("$('trackSel').value") != "__pdf"),
              "动作项用完就离开（否则下次点它 change 不触发）")

        # ② 从 ownCloud：两个下拉都该把面板打开
        await pg.select_option("#trackSel", "__dav"); await asyncio.sleep(0.4)
        print(ok(await pg.evaluate("$('davPop').style.display==='flex'")), "「曲目」下拉的 ownCloud 项打开面板")
        print(ok(await pg.evaluate("$('trackSel').value") == pidC), "开完面板下拉也复位了")
        await pg.evaluate("$('davPop').style.display='none'")
        await pg.select_option("#audSel", "__dav"); await asyncio.sleep(0.4)
        print(ok(await pg.evaluate("$('davPop').style.display==='flex'")), "「音频」下拉的 ownCloud 项打开面板")

        print("\npage errors:", errs or "(none)")
        await b.close()

asyncio.run(main())
