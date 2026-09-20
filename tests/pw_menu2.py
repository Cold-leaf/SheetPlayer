import asyncio, http.server, socketserver, threading, functools
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
PDF=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8768),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c): return "OK   " if c else "FAIL "

async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={"width":1200,"height":900})
        await pg.goto("http://127.0.0.1:8768/player.html?direct=1")
        await pg.evaluate("localStorage.clear()"); await pg.reload()
        await pg.set_input_files("#fPdf",PDF)
        await pg.wait_for_function("()=>document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=40000)
        await pg.click("#bMenu"); await asyncio.sleep(0.2)
        # 「导入本曲标注（覆盖）」label 现在是按钮样式
        # 菜单里现在有两个 label.mbtn（「谱子 → 导一份新谱子」在前面），必须指名道姓
        SEL="document.querySelector('#menu label:has(#fMap)')"
        cs=await pg.evaluate(f"""()=>{{const l={SEL};const s=getComputedStyle(l);
            return {{bg:s.backgroundColor,disp:s.display,pad:s.padding,rad:s.borderRadius}}}}""")
        # 桌面（非粗指针）下仍是 inline-block；粗指针会被涂成 inline-flex 好让文字居中
        print(ok(cs["bg"]=="rgb(29, 35, 44)" and cs["disp"]=="inline-block" and cs["rad"]!="0px"),
              f"导入本曲标注 有按钮样式: {cs}")
        # 跟「导出本曲标注」在同一排（y 相近）
        y_imp=await pg.evaluate(f"{SEL}.getBoundingClientRect().top")
        y_exp=await pg.evaluate("document.querySelector('#bExp').getBoundingClientRect().top")
        print(ok(abs(y_imp-y_exp)<2), f"导入本曲标注 和 导出本曲标注 同一排 (y差 {abs(y_imp-y_exp):.0f}px)")
        # 导入仍能工作（点 label 触发文件选择）
        import tempfile
        fp=tempfile.NamedTemporaryFile(suffix=".json",delete=False); fp.write(b'{"M":[],"E":[]}'); fp.close()
        await pg.set_input_files("#fMap",fp.name)
        print(ok(True), "导入本曲标注 文件选择仍可用")
        await b.close()
asyncio.run(main())
