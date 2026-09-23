import asyncio, json, hashlib, http.server, socketserver, threading, functools
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
PDF=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
# 和 player.html 的 sha256Hex 同款：前 1MB 的 SHA-256。用它当 payload 里的 pdfHash，
# 最后再本机导入这份 PDF，验证「同步下来的 stub 能被认回」。
PH=hashlib.sha256(open(PDF,'rb').read()[:1<<20]).hexdigest()
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8774),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c): return "OK   " if c else "FAIL "

def mk(n):
    return [{"page":1,"nx":0.1+0.1*i,"ny":0.3,"m":i+1,"h":0.05} for i in range(n)]

# v1 老格式：条目没有 id，靠 name / pdfHash 落回本地项目（读取端要一直兼容它，
# 因为仓库里那份 annotations.json 就是老版本导出的）
def payload(ts, nbars, phash=PH):
    return {"app":"sheetplayer","v":1,"items":[
        {"name":"测试曲目","pdfHash":phash,"data":{"v":5,"M":mk(nbars),"E":[],
         "TEMPO":[{"m":1,"bpm":120}],"METER":[{"sig":[4,4],"ranges":[]}],
         "FORM":[],"offset":0,"ts":ts}}]}

# v2 格式：条目带 id / aka / pdfHistory
def payload2(ts, nbars, name="测试曲目", pid="p-远端", aka=None, phash=PH):
    return {"app":"sheetplayer","v":2,"items":[
        {"id":pid,"name":name,"aka":aka or [],"pdf":phash,"pdfHistory":[],
         "data":{"v":6,"M":mk(nbars),"modes":{"标准":{"E":[],"TEMPO":[{"m":1,"bpm":120}],
          "METER":[{"sig":[4,4],"ranges":[]}],"FORM":[],"offset":0}},"activeMode":"标准","ts":ts}}]}

DB="""(async()=>{const db=await new Promise(r=>{const o=indexedDB.open('sheetplayer');o.onsuccess=()=>r(o.result)});
 const g=s=>new Promise(r=>{db.transaction(s).objectStore(s).getAll().onsuccess=e=>r(e.target.result)});
 return {P:await g('projects'),M:await g('marks')}})()"""

async def main():
    errs=[]
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={"width":1500,"height":1000})
        pg.on("pageerror",lambda e:errs.append(str(e)))
        state={"status":200,"body":payload(1000,2)}
        async def route_handler(route):
            await route.fulfill(status=state["status"],content_type="application/json",
                                body=json.dumps(state["body"]))
        await pg.route("**raw.githubusercontent.com/**", route_handler)
        await pg.goto("http://127.0.0.1:8774/player.html")
        await pg.wait_for_function("()=>idb!==null&&$('lib').style.display==='flex'",timeout=15000)

        # 首次同步：拉到一个项目（2 小节）。v1 条目没有 id，靠名字建出「等待导入谱子」的项目
        await pg.click("#bSync")
        await pg.wait_for_function("()=>document.querySelectorAll('.libCard').length===1",timeout=10000)
        print(ok("已标 2 小节" in await pg.inner_text(".libCard")), "从 GitHub 同步到 1 个项目（已标 2 小节）")
        print(ok("等待导入谱子" in await pg.inner_text(".libCard")), "v1 条目（没有 id）按名字落成一个等待导入谱子的项目")
        print(ok("同步完成：导入 1 个项目" in await pg.inner_text("#msg")), "同步提示: "+await pg.inner_text("#msg"))
        d=await pg.evaluate(DB)
        print(ok(len(d["P"])==1 and len(d["M"])==1 and d["M"][0]["pid"]==d["P"][0]["id"]),
              "标注挂在同一个项目上")

        # 较新数据 → 覆盖
        state["body"]=payload(2000,3)
        await pg.click("#bSync")
        await pg.wait_for_function("()=>document.querySelector('.libCard')?.innerText.includes('已标 3 小节')",timeout=10000)
        print(ok("已标 3 小节" in await pg.inner_text(".libCard")), "时间戳较新 → 覆盖（3 小节）")

        # 较旧数据 → 不再静默跳过，而是先问一句「本机较新，要不要用对方那份覆盖」
        state["body"]=payload(500,1)
        await pg.click("#bSync")
        await pg.wait_for_selector("#dlgPick",state="visible",timeout=8000)
        pm=await pg.inner_text("#dlgPickMsg")
        btns=await pg.eval_on_selector_all("#dlgPickBtns button","e=>e.map(b=>b.textContent)")
        print(ok("1 个项目本机的标注更新" in pm and "测试曲目" in pm and "500" not in pm),
              "本机较新时先问一句、并列出项目名: "+pm.replace("\n"," | ")[:70])
        print(ok(btns==["覆盖本机","保留本机"]), f"两个出路（默认保留本机）: {btns}")
        await pg.click("#dlgPickBtns button:has-text('保留本机')")
        await pg.wait_for_timeout(700)
        print(ok("已标 3 小节" in await pg.inner_text(".libCard")), "选「保留本机」→ 不覆盖（仍是 3 小节）")
        print(ok("跳过 1 个" in await pg.inner_text("#msg")), "跳过提示: "+await pg.inner_text("#msg"))
        print(ok(await pg.evaluate("document.querySelectorAll('.libCard').length")==1), "老格式来回同步不会多建项目")

        # 同一个弹窗里选「覆盖本机」→ 真的用旧版盖掉（2026-09-23 加的口子：
        # 有时候就是要覆盖，光按时间戳替用户决定不够）
        state["body"]=payload(400,1)
        await pg.click("#bSync")
        await pg.wait_for_selector("#dlgPick",state="visible",timeout=8000)
        await pg.click("#dlgPickBtns button:has-text('覆盖本机')")
        await pg.wait_for_function("()=>document.querySelector('.libCard')?.innerText.includes('已标 1 小节')",timeout=10000)
        print(ok("已标 1 小节" in await pg.inner_text(".libCard")), "选「覆盖本机」→ 用仓库版盖掉（1 小节）")
        print(ok("导入 1 个项目" in await pg.inner_text("#msg")), "覆盖那次不算跳过: "+await pg.inner_text("#msg"))
        # 覆盖之后两边一样新，再同步一次不该再弹（没有冲突就别打扰）
        await pg.click("#bSync"); await pg.wait_for_timeout(800)
        print(ok(await pg.is_hidden("#dlgPick")), "没有冲突时不再弹窗")
        # 把本机改回 3 小节那份，后面的用例还按 3 小节往下走
        state["body"]=payload(2000,3)
        await pg.click("#bSync")
        await pg.wait_for_function("()=>document.querySelector('.libCard')?.innerText.includes('已标 3 小节')",timeout=10000)
        print(ok("已标 3 小节" in await pg.inner_text(".libCard")), "换回较新的那份（3 小节），继续后面的用例")

        # v2 格式：换台设备改了名（对端报的是新名字 + 老名字在 aka 里）→ 按名字/别名认领，不新建
        old=await pg.evaluate("(async()=>{const P=(await %s).P;return P[0].id})()"%DB)
        state["body"]=payload2(9000,5,name="测试曲目（改过名）",pid="p-另一台设备",
                               aka=["测试曲目"],phash=PH)
        await pg.click("#bSync")
        await pg.wait_for_function("()=>document.querySelector('.libCard')?.innerText.includes('已标 5 小节')",timeout=10000)
        print(ok(await pg.evaluate("document.querySelectorAll('.libCard').length")==1),
              "v2 条目按 aka 认领成同一个项目，没有分叉")
        d=await pg.evaluate(DB)
        print(ok(len(d["P"])==1 and d["P"][0]["id"]==old), "项目 id 没变（本地项目被认领，不是新建）")
        print(ok("测试曲目（改过名）" in d["P"][0]["aka"]), "对端名字并进了 aka: "+str(d["P"][0]["aka"]))
        print(ok("已标 5 小节" in await pg.inner_text(".libCard")), "对端的更新生效")
        print(ok(PH in [h["hash"] for h in d["P"][0]["pdfHistory"]]),
              "同步下来的 pdfHash 记成了认领线索（pdfHistory）")

        # 本机导入这份谱子：靠那条线索挂到同步来的项目上，而不是又建一个
        await pg.set_input_files("#fPdf",PDF)
        await pg.wait_for_function("()=>document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=60000)
        await pg.wait_for_timeout(300)
        await pg.evaluate("$('bLib').onclick()"); await pg.wait_for_timeout(500)
        print(ok(await pg.evaluate("document.querySelectorAll('.libCard').length")==1),
              "导入谱子后被认回同步来的项目：库里还是 1 个")
        txt=await pg.inner_text(".libCard")
        print(ok("等待导入谱子" not in txt and "已标 5 小节" in txt),
              "同步来的标注还在，卡片提示也换了: "+txt.replace("\n"," | ")[:80])
        d=await pg.evaluate(DB)
        print(ok(d["P"][0]["pdf"] and d["P"][0]["pdf"]["hash"]==PH), "项目的当前谱子指向这份 PDF")

        # 404：仓库里还没有文件
        state["status"]=404; state["body"]="404: Not Found"
        await pg.click("#bSync")
        await pg.wait_for_timeout(800)
        print(ok("annotations.json" in await pg.inner_text("#msg")), "404 给出友好提示: "+await pg.inner_text("#msg"))

        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
