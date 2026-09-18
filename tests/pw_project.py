# 项目生命周期：先建空项目（自己起名）→ 补谱子 → 标注 → 换谱 → 改名。
# 名字是项目的对外身份，PDF 只是附件。
import asyncio, http.server, socketserver, threading, functools
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
A=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
B=ROOT+"/线谱合集/BW_不忘初心[线][SATB+NA+Pn].pdf"
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8811),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
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
        await pg.goto("http://127.0.0.1:8811/player.html")
        await pg.wait_for_function("()=>idb!==null&&$('lib').style.display==='flex'",timeout=15000)

        # 「＋ 新建项目」：先起名，还没有谱子
        await pg.click("#libNew")
        await dlg(pg,"我的排练曲")
        await pg.wait_for_function("()=>document.querySelectorAll('.libCard').length===1",timeout=8000)
        txt=await pg.inner_text(".libCard")
        print(ok("等待导入谱子" in txt), "空项目的卡片提示等待导入谱子: "+txt.replace("\n"," | "))
        print(ok(await pg.evaluate("!track||!track.pdf")), "此时还没有谱子")
        print(ok(await pg.evaluate("!document.querySelector('.libCard button.repl')")), "没有谱子就不给「换谱」按钮")

        # 重名硬拦
        await pg.click("#libNew")
        await dlg(pg,"我的排练曲")
        await pg.wait_for_timeout(300)
        print(ok("已经有叫" in await pg.inner_text("#msg")), "重名被拦下: "+await pg.inner_text("#msg"))
        print(ok(await pg.evaluate("document.querySelectorAll('.libCard').length")==1), "重名没有建出第二个项目")

        # 点「打开」→ 选谱子 → 挂到这个项目上（名字保持用户起的，不跟文件名走）
        async with pg.expect_file_chooser() as fc:
            await pg.click(".libCard button.open")
        await (await fc.value).set_files(A)
        await pg.wait_for_function("()=>document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=60000)
        print(ok(await pg.evaluate("track.name")=="我的排练曲"), "项目名保持用户起的: "+await pg.evaluate("track.name"))
        print(ok(await pg.evaluate("track.pdf.hash===pdfHash")), "谱子挂上去了（pdf.hash === pdfHash）")
        pid0=await pg.evaluate("pid")

        # 标 3 个小节
        await pg.select_option("#mode","mark")
        bb=await (await pg.query_selector('.page[data-page="1"]')).bounding_box()
        for fx in (0.3,0.45,0.6):
            await pg.mouse.click(bb["x"]+bb["width"]*fx,bb["y"]+bb["height"]*0.4)
        await asyncio.sleep(0.9)
        print(ok(await pg.evaluate("M.length")==3), "标好 3 个小节")

        # 换谱 → 标注还在
        await pg.evaluate("$('bLib').onclick()"); await pg.wait_for_timeout(500)
        pg.once("dialog",lambda dlg:asyncio.create_task(dlg.accept()))
        async with pg.expect_file_chooser() as fc:
            await pg.click(".libCard button.repl")
        await (await fc.value).set_files(B)
        await pg.wait_for_function("()=>document.querySelectorAll('.mk').length===3",timeout=60000)
        await pg.wait_for_timeout(300)
        print(ok(await pg.evaluate("pid")==pid0), "换谱后还是同一个项目")
        print(ok(await pg.evaluate("M.map(x=>x.m).join(',')")=="1,2,3"), "换谱后 3 个小节还在")
        print(ok(await pg.evaluate("track.name")=="我的排练曲"), "换谱不改名")
        print(ok(await pg.evaluate("track.pdfHistory.length")==1), "旧谱子进了 pdfHistory")
        print(ok(await pg.evaluate("track.pdf.name")==B.split('/')[-1]), "当前谱子是换上去的那份")

        # 手工改名 → 卡片显示新名
        await pg.evaluate("$('bLib').onclick()"); await pg.wait_for_timeout(400)
        await pg.click(".libCard button.ren")
        await dlg(pg,"排练曲（新名）")
        await pg.wait_for_timeout(400)
        print(ok("排练曲（新名）" in await pg.inner_text(".libCard")), "卡片显示新名字: "+(await pg.inner_text(".libCard .nm")))
        print(ok(await pg.evaluate("track.name")=="排练曲（新名）"), "打开着的这份也改了名（不用重开）")
        print(ok(await pg.evaluate("track.aka.join(',')")=="我的排练曲"), "原名进了 aka: "+await pg.evaluate("track.aka.join(',')"))

        # 刷新后名字和标注都还在
        await pg.reload()
        await pg.wait_for_function("()=>idb!==null&&$('lib').style.display==='flex'",timeout=15000)
        await pg.wait_for_timeout(500)
        print(ok("排练曲（新名）" in await pg.inner_text(".libCard")), "刷新后名字还在")
        await pg.click(".libCard button.open")
        await pg.wait_for_function("()=>document.querySelectorAll('.mk').length===3",timeout=60000)
        print(ok(await pg.evaluate("M.length")==3), "刷新后标注还在")

        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
