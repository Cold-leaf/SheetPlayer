import asyncio, http.server, socketserver, threading, functools
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
PDF=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8769),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c): return "OK   " if c else "FAIL "

async def main():
    errs=[]
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={"width":1500,"height":1000})
        pg.on("pageerror",lambda e:errs.append(str(e)))
        await pg.goto("http://127.0.0.1:8769/player.html")
        await pg.wait_for_function("()=>idb!==null",timeout=10000)
        await pg.wait_for_function("()=>$('lib').style.display==='flex'",timeout=10000)

        # 启动即显示曲目库；空库有引导文案
        print(ok(await pg.evaluate("idb!==null")), "IndexedDB 曲目库已启用")
        print(ok(await pg.evaluate("$('lib').style.display==='flex'")), "启动即显示曲目库界面")
        print(ok("还没有曲目" in await pg.inner_text("#libList")), "空库引导文案")

        # 走真实用户路径：点「＋ 导入谱子」→ 文件选择器 → 选 PDF
        async with pg.expect_file_chooser() as fc:
            await pg.click("#libAdd")
        await (await fc.value).set_files(PDF)
        await pg.wait_for_function("()=>document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=30000)
        print(ok(await pg.evaluate("$('lib').style.display==='none'")), "选完 PDF 自动进入谱面（库界面收起）")
        print(ok(await pg.evaluate("!!track&&!!pdfHash&&pdfHash.length===64")), "曲目按内容哈希建立 (64 位 hex)")
        print(ok("《" in await pg.inner_text("#stat")), "状态栏显示曲名: "+await pg.inner_text("#stat"))

        # 标 2 个小节 → 防抖落盘 → 回库看卡片统计
        await pg.select_option("#mode","mark")
        bb=await (await pg.query_selector('.page[data-page="1"]')).bounding_box()
        await pg.mouse.click(bb["x"]+bb["width"]*0.3,bb["y"]+bb["height"]*0.4)
        await pg.mouse.click(bb["x"]+bb["width"]*0.45,bb["y"]+bb["height"]*0.4)
        await asyncio.sleep(0.8)   # > 400ms 防抖
        await pg.evaluate("$('bLib').onclick()")
        await pg.wait_for_timeout(500)
        card=await pg.query_selector(".libCard")
        print(ok(card is not None), "曲目卡片出现")
        txt=await card.inner_text()
        print(ok("已标 2 小节" in txt and "音频 0" in txt), "卡片统计: "+txt.replace("\n"," | "))

        # 刷新页面 → 库还在、标注还在（IndexedDB 往返）
        await pg.reload()
        await pg.wait_for_function("()=>idb!==null&&$('lib').style.display==='flex'",timeout=10000)
        await pg.wait_for_timeout(400)
        print(ok(await pg.evaluate("document.querySelectorAll('.libCard').length")==1), "刷新后曲目还在")
        await pg.click(".libCard button.open")
        await pg.wait_for_function("()=>document.querySelectorAll('.mk').length===2",timeout=30000)
        print(ok(await pg.evaluate("M.map(x=>x.m).join(',')")=="1,2"), "打开曲目后标注恢复 (M=1,2)")
        print(ok((await pg.evaluate("$('stat').textContent")).find("已标 2 小节")>0), "状态栏与恢复数据一致")

        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
