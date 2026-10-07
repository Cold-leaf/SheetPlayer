# 卡片上的两个"要导一份谱子"的动作（「＋ 导入谱子」/「换谱」）都能从 ownCloud 拿，
# 而且下载完直接挂回**这张卡片**的项目（弹窗预选它，不用自己翻列表找）。
#
# 为什么不加第六个按钮：卡片操作行是一行五个按钮的预算（pw_libgrid 钉着），
# 所以来源折进同一次点击里问；工具栏/菜单的入口照旧直接开文件选择器，不受影响。
# 这里用桩替换 davList/davGet，不联网、不碰真服务器（跟 pw_davfilter 一个路子）。
import asyncio, http.server, socketserver, threading, functools, base64
from playwright.async_api import async_playwright
ROOT = "/home/xiaoyuanzhu/my-life-db/data/assets"
A = ROOT + "/线谱合集/BW_不忘初心[线][SATB+NA+Pn].pdf"
B = ROOT + "/线谱合集/CQ_传奇[线][SATB+NA+Pn][任知超][处理后].pdf"

class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
H = functools.partial(Quiet, directory=ROOT + "/SheetPlayer")
socketserver.TCPServer.allow_reuse_address = True
srv = socketserver.TCPServer(("127.0.0.1", 8802), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()

def ok(c): return "OK   " if c else "FAIL "

DB = """(async()=>{const g=(s)=>new Promise(r=>{idb.transaction(s).objectStore(s).getAll().onsuccess=e=>r(e.target.result)});
 const P=await g('projects');
 return {n:P.length,p:P.map(x=>({id:x.id,name:x.name,pdf:x.pdf&&x.pdf.hash,hist:(x.pdfHistory||[]).length}))}})()"""

# 面板里的下载全部走桩：列一个 PDF + 把它当成本地那份真文件交出来
STUB = """([b64,name])=>{
  DAV={base:'https://example.test/owncloud',kind:'webdav',user:'u',pass:'p'};
  const bytes=Uint8Array.from(atob(b64),c=>c.charCodeAt(0));
  window.davList=async()=>[{name,path:name,dir:false,size:bytes.length}];
  window.davGet=async()=>new File([bytes],name,{type:'application/pdf'});
}"""

async def card_click(pg, name, sel):
    return await pg.evaluate("""([nm,sel])=>{
      const c=[...document.querySelectorAll('.libCard')].find(c=>{const n=c.querySelector('.nm');
        return ((n.title||'')+' '+n.textContent).includes(nm)});
      if(!c)return 'no-card';
      const b=c.querySelector(sel);if(!b)return 'no-btn';
      b.click();return 'ok'}""", [name, sel])

async def highlighted(pg):
    return await pg.evaluate("(document.querySelector('#dlgProjList .pjRow.on .pjName')||{}).textContent||''")

async def main():
    errs = []
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": 1400, "height": 950})
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("dialog", lambda d: asyncio.create_task(d.accept()))
        await pg.goto("http://127.0.0.1:8802/player.html")
        await pg.wait_for_function("()=>idb!==null&&$('lib').style.display==='flex'", timeout=15000)

        # 一份有谱子的项目 + 一个刚建好、还没有谱子的项目
        await pg.set_input_files("#fPdf", A)
        await pg.wait_for_function("()=>document.querySelector('.page[data-page=\"1\"]')?.dataset.done", timeout=60000)
        pidA = await pg.evaluate("pid"); hA = await pg.evaluate("pdfHash")
        idE = await pg.evaluate("""async()=>{const p={id:newId(),name:'新项目_待导谱',aka:[],pdf:null,pdfHistory:[],
            audios:[],lastAudio:null,createdAt:Date.now(),updatedAt:Date.now()};
            await idbPut(idb,'projects',p);await drawLib();return p.id}""")
        await pg.evaluate("showLib(true)"); await asyncio.sleep(0.6)
        print(ok(await pg.evaluate("document.querySelectorAll('.libCard').length") == 2), "库里两张卡（一张有谱子、一张等着导）")
        print(ok(await card_click(pg, '新项目_待导谱', 'button.open') == 'ok'), "空项目的按钮是「＋ 导入谱子」")

        # ① 问来源：取消 = 什么都不做
        await asyncio.sleep(0.4)
        print(ok(await pg.evaluate("$('dlgPick').style.display==='flex'")), "点了先问「从哪来」")
        btns = await pg.evaluate("[...$('dlgPickBtns').querySelectorAll('button')].map(b=>b.textContent)")
        print(ok(len(btns) == 2 and '本机' in btns[0] and 'ownCloud' in btns[1]), "两个选项：本机 / ownCloud " + str(btns))
        await pg.click("#dlgPick", position={"x": 5, "y": 5})       # 点遮罩取消
        await asyncio.sleep(0.3)
        print(ok(await pg.evaluate("$('davPop').style.display!=='flex'")), "取消后什么都没打开")
        print(ok(await pg.evaluate("pendPid") == ''), "取消也没留下 pendPid")

        # ② 本机那条：照旧直接开文件选择器，且指向这张卡片的项目
        await card_click(pg, '新项目_待导谱', 'button.open'); await asyncio.sleep(0.4)
        async with pg.expect_file_chooser() as fc:
            await pg.click("#dlgPickBtns button >> nth=0")
        print(ok(await pg.evaluate("pendPid") == idE), "选「本机」→ 文件选择器打开，pendPid 指向这张卡片")
        await (await fc.value).set_files(A)
        await pg.wait_for_function("()=>pdfHash&&pid", timeout=60000)
        await asyncio.sleep(0.6)
        d = await pg.evaluate(DB)
        e = [x for x in d["p"] if x["id"] == idE][0]
        print(ok(e["pdf"] == hA), "本机那份挂到了空项目上（不是按文件名新建）")

        # ③ 已经有本地谱子的项目：点「打开」直接开，不再多问一句（本地导入是常态）
        await pg.evaluate("showLib(true)"); await asyncio.sleep(0.5)
        await card_click(pg, '新项目_待导谱', 'button.open'); await asyncio.sleep(0.8)
        print(ok(await pg.evaluate("$('dlgPick').style.display!=='flex'")), "谱子在本机的项目：一键直接打开，不弹来源")
        print(ok(await pg.evaluate("pid") == idE), "打开的正是那个项目")

        # ④ ownCloud 那条：另起一个还没谱子的项目
        idE2 = await pg.evaluate("""async()=>{const p={id:newId(),name:'新项目_待导谱2',aka:[],pdf:null,pdfHistory:[],
            audios:[],lastAudio:null,createdAt:Date.now(),updatedAt:Date.now()};
            await idbPut(idb,'projects',p);await drawLib();return p.id}""")
        await pg.evaluate("showLib(true)"); await asyncio.sleep(0.5)
        await card_click(pg, '新项目_待导谱2', 'button.open'); await asyncio.sleep(0.4)
        await pg.click("#dlgPickBtns button >> nth=1"); await asyncio.sleep(0.6)
        print(ok(await pg.evaluate("$('davPop').style.display==='flex'")), "选「ownCloud」→ 面板打开")
        print(ok(await pg.evaluate("davTarget") == idE2), "面板记着要挂到哪张卡片")
        print(ok('新项目_待导谱2' in (await pg.inner_text("#davTip"))), "提示写明给谁拿：" + (await pg.inner_text("#davTip")))

        # ⑤ 下载完的弹窗预选这张卡片（这是本轮的正题）
        await pg.evaluate(STUB, [base64.b64encode(open(B, "rb").read()).decode(), "CQ_传奇[线][SATB+NA+Pn][任知超][处理后].pdf"])
        await pg.evaluate("davRender()"); await asyncio.sleep(0.5)
        await pg.click("#davList .dRow")
        await pg.wait_for_function("()=>$('dlgProj').style.display==='flex'", timeout=60000)
        await asyncio.sleep(0.4)
        print(ok(await highlighted(pg) == '新项目_待导谱2'), "弹窗预选的是那张卡片：" + (await highlighted(pg)))
        await pg.click("#dlgProjOk")
        await pg.wait_for_function("()=>pdfHash&&pid", timeout=60000)
        await asyncio.sleep(0.8)
        print(ok(await pg.evaluate("pid") == idE2), "确认后挂到那个项目上")

        # ⑥ 有谱子的卡片「换谱」也走这条：下载完预选它、换完标注照旧
        await pg.evaluate("showLib(true)"); await asyncio.sleep(0.5)
        await pg.evaluate("""async(h)=>{await idbPut(idb,'marks',{pid:h,data:{v:6,M:[{page:1,nx:.3,ny:.4,m:1,h:.09}],
            modes:{'标准':{E:[]}},activeMode:'标准',ts:Date.now()}})}""", pidA)
        await asyncio.sleep(0.5)
        await card_click(pg, 'BW_不忘初心', 'button.repl'); await asyncio.sleep(0.4)
        print(ok(await pg.evaluate("$('dlgPick').style.display==='flex'")), "「换谱」也先问来源")
        await pg.click("#dlgPickBtns button >> nth=1"); await asyncio.sleep(0.6)
        print(ok(await pg.evaluate("davTarget") == pidA), "记下的是被点的那张卡片")
        await pg.evaluate("davRender()"); await asyncio.sleep(0.5)
        await pg.click("#davList .dRow")
        await pg.wait_for_function("()=>$('dlgProj').style.display==='flex'", timeout=60000)
        await asyncio.sleep(0.4)
        print(ok(await highlighted(pg) == 'BW_不忘初心[线][SATB+NA+Pn]'), "换谱的弹窗也预选那张卡片：" + (await highlighted(pg)))
        await pg.click("#dlgProjOk")
        await pg.wait_for_function("(h)=>pdfHash!==h", arg=hA, timeout=60000)
        await asyncio.sleep(0.8)
        d = await pg.evaluate(DB)
        a = [x for x in d["p"] if x["id"] == pidA][0]
        print(ok(a["pdf"] != hA), "谱子确实换了")
        print(ok(a["hist"] == 1), f"旧谱子进历史（{a['hist']} 条）")
        print(ok(await pg.evaluate("M.length") == 1), "标注原样保留（换谱只换 PDF 那一半）")
        print(ok(await pg.evaluate("davTarget") == ''), "下载完目标就清掉了，不粘着")
        print(ok(await pg.evaluate("$('davTip').textContent") == '点文件名下载并导入；下载完会让你选挂到哪个项目（音频不必先打开曲目）。'),
              "面板提示回到通版说法")

        # ⑦ 工具栏/菜单的入口**不**受影响：照旧一击开文件选择器
        await pg.evaluate("showLib(false);$('menu').style.display='block'"); await asyncio.sleep(0.3)
        async with pg.expect_file_chooser() as fc:
            await pg.click("#lblPdf")
        print(ok(True), "菜单「导一份新谱子」仍是一击直接开选择器（没有多问一句）")

        print("\npage errors:", errs or "(none)")
        await b.close()

asyncio.run(main())
