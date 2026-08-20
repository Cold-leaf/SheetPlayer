import asyncio, pathlib, http.server, socketserver, threading, functools, json
from playwright.async_api import async_playwright

ROOT = "/home/xiaoyuanzhu/my-life-db/data/assets"
PDF  = ROOT + "/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
AUD  = ROOT + "/ICT_working/陈致逸,HOYO-MiX - Dawn Winery Theme 晨曦酒庄.mp3"
import glob
AUD = glob.glob(ROOT + "/ICT_working/08-Assets/*.mp3")[0]

Handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address = True
srv = socketserver.TCPServer(("127.0.0.1", 8731), Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()

async def main():
    logs, errs = [], []
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width":1440,"height":900})
        pg.on("console", lambda m: logs.append(f"[{m.type}] {m.text}"))
        pg.on("pageerror", lambda e: errs.append(str(e)))
        await pg.goto("http://127.0.0.1:8731/player.html")

        await pg.set_input_files("#fPdf", PDF)
        await pg.set_input_files("#fAud", AUD)
        await pg.wait_for_function("()=>document.querySelectorAll('.page').length>0", timeout=30000)
        await pg.wait_for_function("()=>document.querySelector('.page[data-page=\"1\"]')?.dataset.done", timeout=30000)
        npages = await pg.evaluate("document.querySelectorAll('.page').length")
        print("pages:", npages)
        print("worker mode:", "FAKE(主线程)" if any("fake worker" in l.lower() for l in logs) else "REAL worker")

        # 检查 DPR 渲染：backing store 应 = CSS 尺寸 * DPR
        dims = await pg.evaluate("""()=>{const b=document.querySelector('.page'),c=b.querySelector('canvas');
            return {css:[b.clientWidth,b.clientHeight],back:[c.width,c.height],dpr:window.devicePixelRatio}}""")
        print("page css/backing/dpr:", dims)

        # 1) 标小节：在第一页点 6 个点
        box = await pg.query_selector('.page[data-page="1"]')
        bb  = await box.bounding_box()
        for i in range(6):
            await pg.mouse.click(bb["x"]+120+i*90, bb["y"]+200+ (i%2)*40)
        print("markers:", await pg.evaluate("M.length"), "| nextM:", await pg.evaluate("nextM"))
        await pg.screenshot(path="/tmp/shot1_mark.png")

        # 2) 键盘打点：切到打时间模式，播放，空格连打
        await pg.select_option("#mode", "time")
        await pg.evaluate("aud.play()")
        await pg.evaluate("document.body.focus()")
        for i in range(6):
            await pg.keyboard.press(" ")
            await asyncio.sleep(0.35)
        E = await pg.evaluate("E")
        print("keyboard taps ->", len(E), "个时间点, m序列:", [e["m"] for e in E])
        print("tapM after taps:", await pg.evaluate("tapM"))

        # 3) 补偿 offset 生效？
        await pg.fill("#off", "200"); await pg.dispatch_event("#off","change")
        t_before = await pg.evaluate("aud.currentTime")
        await pg.evaluate("tapM=1; addTime(tapM, stamp()); refresh()")
        t_rec = await pg.evaluate("E.find(e=>e.m===1).t")
        print(f"offset 200ms: audio t={t_before:.2f} recorded={t_rec:.2f} delta={t_before-t_rec:.3f}")

        # 4) 撤销栈：删标记后撤销能恢复
        before = await pg.evaluate("[M.length,E.length]")
        await pg.evaluate("snap(); M=M.filter(x=>x.m!==3); E=E.filter(x=>x.m!==3); syncNext(); layout()")
        mid = await pg.evaluate("[M.length,E.length]")
        await pg.evaluate("undo()")
        after = await pg.evaluate("[M.length,E.length]")
        print("undo:", before, "->", mid, "-> undo ->", after, "OK" if before==after else "FAIL")

        # 5) play 模式点击跳转
        await pg.select_option("#mode", "play")
        await pg.evaluate("aud.pause(); aud.currentTime=0")
        mk = await pg.query_selector('.mk[data-m="5"]')
        r = await mk.bounding_box()
        await pg.mouse.click(r["x"]+r["width"]/2, r["y"]+r["height"]/2)
        print("seek to 小节5 ->", round(await pg.evaluate("aud.currentTime"),2), "s")

        # 6) 高亮：设 currentTime 后 .cur 应落在正确小节
        await pg.evaluate("aud.currentTime=E.find(e=>e.m===4).t+0.05")
        await asyncio.sleep(0.3)
        print("highlighted:", await pg.evaluate("document.querySelector('.mk.cur')?.dataset.m"))

        # 7) 缩放：marker 用百分比定位，应随页面等比缩放
        p_before = await pg.evaluate("""()=>{const d=document.querySelector('.mk[data-m="2"]'),b=d.parentElement;
            return [d.offsetLeft/b.clientWidth, d.offsetTop/b.clientHeight]}""")
        await pg.evaluate("$('zoom').value=2;$('zoom').oninput()")
        await asyncio.sleep(1.2)
        p_after = await pg.evaluate("""()=>{const d=document.querySelector('.mk[data-m="2"]'),b=d.parentElement;
            return [d.offsetLeft/b.clientWidth, d.offsetTop/b.clientHeight]}""")
        w2 = await pg.evaluate("document.querySelector('.page').clientWidth")
        print(f"zoom 130%->200%: 页宽 {w2}px, marker 相对位置 {p_before} -> {p_after}",
              "OK" if all(abs(a-b)<0.004 for a,b in zip(p_before,p_after)) else "DRIFT")
        await pg.screenshot(path="/tmp/shot2_zoom.png")

        # 8) 存档：刷新后自动恢复
        await pg.evaluate("$('zoom').value=1.3;$('zoom').oninput()")
        await asyncio.sleep(0.5)
        snapshot = await pg.evaluate("[M.length,E.length]")
        await asyncio.sleep(0.8)
        await pg.reload()
        await pg.set_input_files("#fPdf", PDF)
        await pg.wait_for_function("()=>document.querySelectorAll('.mk').length>0", timeout=30000)
        restored = await pg.evaluate("[M.length,E.length]")
        print("localStorage restore:", snapshot, "->", restored, "OK" if snapshot==restored else "FAIL")
        print("restore msg:", await pg.inner_text("#msg"))
        await pg.screenshot(path="/tmp/shot3_restore.png")

        # 9) 内存回收：滚到最后，前面的 canvas 应被释放
        await pg.evaluate("wrap.scrollTop=wrap.scrollHeight")
        await asyncio.sleep(1.5)
        live = await pg.evaluate("document.querySelectorAll('.page canvas').length")
        print(f"共 {npages} 页，滚到底部时存活 canvas 数:", live)

        # 10) 导出格式
        await pg.evaluate("window.__blob=null; URL.createObjectURL=(b)=>{window.__blob=b;return 'blob:x'}")
        await pg.evaluate("$('bExp').onclick()")
        out = await pg.evaluate("window.__blob.text()")
        j = json.loads(out)
        print("export keys:", list(j.keys()), "| E 已按时间排序:", j["E"]==sorted(j["E"],key=lambda x:x["t"]))
        print("export M[0]:", j["M"][0])

        print("\n--- page errors ---"); print("\n".join(errs) or "(none)")
        bad=[l for l in logs if l.startswith("[error]") or l.startswith("[warning]")]
        print("--- console warn/err ---"); print("\n".join(bad) or "(none)")
        await b.close()

asyncio.run(main())
