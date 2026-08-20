import asyncio, glob, http.server, socketserver, threading, functools, json, os
from playwright.async_api import async_playwright

ROOT = "/home/xiaoyuanzhu/my-life-db/data/assets"
PDF  = ROOT + "/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
AUD  = glob.glob(ROOT + "/ICT_working/08-Assets/*.mp3")[0]

Handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address = True
srv = socketserver.TCPServer(("127.0.0.1", 8732), Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()

def ok(c): return "OK  " if c else "FAIL"

async def main():
    errs=[]
    async with async_playwright() as p:
        b = await p.chromium.launch()
        # 模拟 2x 高清屏，走 DPR 分支
        pg = await b.new_page(viewport={"width":1440,"height":900}, device_scale_factor=2)
        pg.on("pageerror", lambda e: errs.append(str(e)))
        await pg.goto("http://127.0.0.1:8732/player.html?direct=1")
        await pg.evaluate("localStorage.clear()")
        await pg.reload()

        await pg.set_input_files("#fPdf", PDF)
        await pg.set_input_files("#fAud", AUD)
        await pg.wait_for_function("()=>document.querySelector('.page[data-page=\"1\"]')?.dataset.done", timeout=30000)

        d = await pg.evaluate("""()=>{const b=document.querySelector('.page'),c=b.querySelector('canvas');
            return {cssW:b.clientWidth,backW:c.width,dpr:window.devicePixelRatio}}""")
        print(ok(d["backW"]==round(d["cssW"]*d["dpr"])), f"DPR 渲染: CSS {d['cssW']}px, 背板 {d['backW']}px, dpr={d['dpr']}")

        bb = await (await pg.query_selector('.page[data-page="1"]')).bounding_box()
        for i in range(4):
            await pg.mouse.click(bb["x"]+120+i*100, bb["y"]+200)

        # --- 打时间模式：没点中标记要有提示（旧版是静默无反应）---
        await pg.select_option("#mode","time")
        await asyncio.sleep(0.3)   # 频谱条自动展开会压缩谱面区，点击位置要落在仍可见的范围内
        await pg.mouse.click(bb["x"]+600, bb["y"]+520)
        m1 = await pg.inner_text("#msg")
        cls = await pg.get_attribute("#msg","class")
        print(ok("没点中" in m1 and cls=="err"), f'漏点提示: "{m1}"')

        # --- offset 补偿（用干净的小节验证）---
        await pg.evaluate("$('off').value=250;$('off').onchange()")
        await pg.evaluate("aud.currentTime=30; E=[]")
        await pg.evaluate("tapM=4; tap()")
        t = await pg.evaluate("E.find(e=>e.m===4).t")
        print(ok(abs(t-29.75)<0.02), f"补偿 250ms: 音频 30.00s -> 记录 {t:.3f}s")

        # --- Shift+点击轮换第 N 遍（反复段）---
        await pg.evaluate("E=[{m:1,t:5},{m:4,t:9},{m:1,t:20},{m:4,t:24}]; refresh()")
        rep = await pg.inner_text("#stat")
        print(ok("2 段" in rep), f'段落计数显示: "{rep}"')
        await pg.select_option("#mode","play")
        mk = await pg.query_selector('.mk[data-m="1"]'); r = await mk.bounding_box()
        cx,cy = r["x"]+r["width"]/2, r["y"]+r["height"]/2
        await pg.evaluate("aud.pause(); aud.currentTime=0")
        seq=[]
        await pg.keyboard.down("Shift")
        for i in range(3):
            await pg.mouse.click(cx,cy)
            seq.append(round(await pg.evaluate("aud.currentTime"),1))
        await pg.keyboard.up("Shift")
        print(ok(seq==[5.0,20.0,5.0]), f"Shift+点击轮换遍数: {seq} (期望 [5.0, 20.0, 5.0])")
        await pg.evaluate("aud.currentTime=19")
        await pg.mouse.click(cx,cy)
        near = round(await pg.evaluate("aud.currentTime"),1)
        print(ok(near==20.0), f"普通点击跳最近一遍 (t=19 时点小节1): {near}s (期望 20.0)")

        # --- 撤销覆盖拖动 ---
        await pg.select_option("#mode","edit")
        mk = await pg.query_selector('.mk[data-m="2"]'); r = await mk.bounding_box()
        p0 = await pg.evaluate("M.find(x=>x.m===2).nx")
        # 竖线上下两端是改长度的手柄，挪位置要抓中段
        cy0=r["y"]+r["height"]/2
        await pg.mouse.move(r["x"]+1, cy0); await pg.mouse.down()
        await pg.mouse.move(r["x"]+201, cy0+60, steps=8); await pg.mouse.up()
        p1 = await pg.evaluate("M.find(x=>x.m===2).nx")
        await pg.evaluate("undo()")
        p2 = await pg.evaluate("M.find(x=>x.m===2).nx")
        print(ok(abs(p1-p0)>0.05 and abs(p2-p0)<1e-9), f"拖动可撤销: {p0:.3f} -> {p1:.3f} -> undo -> {p2:.3f}")

        # --- 导入老格式 ---
        for name, payload in [
            ("老格式 {小节:时间}", '{"1":0.5,"2":1.5,"3":2.5}'),
            ("老格式 数组带t",     '[{"page":1,"nx":0.2,"ny":0.3,"m":1,"t":4},{"page":1,"nx":0.4,"ny":0.3,"m":2,"t":8}]'),
        ]:
            fp=f"/tmp/imp_{abs(hash(name))}.json"; open(fp,"w").write(payload)
            await pg.set_input_files("#fMap", fp)
            await asyncio.sleep(0.3)
            got = await pg.evaluate("[M.length,E.length]")
            print(ok(got[1]>0), f"{name} 导入 -> M={got[0]} E={got[1]}, msg=\"{await pg.inner_text('#msg')}\"")

        # --- 页码越界要警告 ---
        fp="/tmp/imp_bad.json"; open(fp,"w").write('{"M":[{"page":99,"nx":0.1,"ny":0.1,"m":1}],"E":[]}')
        await pg.set_input_files("#fMap", fp); await asyncio.sleep(0.3)
        m2 = await pg.inner_text("#msg")
        print(ok("超出当前 PDF" in m2), f'越界页码告警: "{m2}"')

        # --- 焦点在输入框时不该触发打点 ---
        await pg.evaluate("localStorage.clear()"); await pg.reload()
        await pg.set_input_files("#fPdf", PDF)
        await pg.wait_for_function("()=>document.querySelectorAll('.page').length>0", timeout=30000)
        await pg.evaluate("M=[{page:1,nx:.2,ny:.2,m:1},{page:1,nx:.4,ny:.2,m:2}]; E=[]; syncNext(); layout()")
        await pg.select_option("#mode","time")
        await pg.click("#mode"); await pg.keyboard.press(" ")   # 缩放滑条已隐藏，用可见的 #mode 测焦点在控件内时空格不打点
        n_in = await pg.evaluate("E.length")
        await pg.evaluate("document.activeElement.blur()"); await pg.keyboard.press(" ")
        n_out = await pg.evaluate("E.length")
        print(ok(n_in==0 and n_out==1), f"输入框内空格不打点: 框内后 E={n_in}, 失焦后 E={n_out}")

        print("\npage errors:", errs or "(none)")
        await b.close()

asyncio.run(main())
