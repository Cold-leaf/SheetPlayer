import asyncio, glob, http.server, socketserver, threading, functools
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
PDF=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
AUD=glob.glob(ROOT+"/ICT_working/08-Assets/*.mp3")[0]
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8745),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c): return "OK   " if c else "FAIL "

async def main():
    errs=[]
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={"width":1500,"height":1000})
        pg.on("pageerror",lambda e:errs.append(str(e)))
        await pg.goto("http://127.0.0.1:8745/player.html")
        await pg.evaluate("localStorage.clear()"); await pg.reload()
        await pg.set_input_files("#fPdf",PDF); await pg.set_input_files("#fAud",AUD)
        await pg.wait_for_function("()=>SPEC!==null",timeout=60000)
        await pg.evaluate("""()=>{M=Array.from({length:42},(_,i)=>({page:1,nx:.1+(i%6)*.14,ny:.15+Math.floor(i/6)*.07,m:i+1}));
          E=[];TEMPO=[{m:1,bpm:120}];METER=[{sig:[4,4],ranges:[]}];FORM=[];syncNext();layout()}""")

        # --- 你截图的场景 ---
        await pg.evaluate("$('bGen').click()"); await asyncio.sleep(0.3)
        await pg.fill("#gForm","1-32, 1-32, 33-42"); await pg.dispatch_event("#gForm","input"); await asyncio.sleep(0.3)
        print(ok("3 段" in await pg.inner_text("#gFormInfo")), "解析:", await pg.inner_text("#gFormInfo"))
        await pg.fill("#gAncT","0"); await pg.dispatch_event("#gAncT","change")
        await pg.click("#gRun"); await asyncio.sleep(0.5)
        chips=await pg.eval_on_selector_all(".chip","e=>e.map(x=>x.textContent)")
        print(ok(len(chips)==3), f"段落条 {len(chips)} 段: {chips}")

        # 修正一个点（制造陈旧 seg），再重新生成
        await pg.evaluate("aud.currentTime=31.5; addTime(17, stamp()); refresh()")
        seg=await pg.evaluate("E.find(e=>e.m===17&&e.src==='tap').seg")
        await pg.evaluate("$('bGen').click()"); await asyncio.sleep(0.3)
        await pg.click("#gRun"); await asyncio.sleep(0.5)
        chips=await pg.eval_on_selector_all(".chip","e=>e.map(x=>x.textContent)")
        print(ok(len(chips)==3), f"修正小节17(seg={seg})后重新生成，仍 {len(chips)} 段: {chips}")

        # --- 时间轴不再超音频 ---
        await pg.evaluate("""E=[{m:1,t:0,src:'tap'},{m:17,t:32,src:'tap'},{m:18,t:45,src:'tap'}];layout()""")
        await pg.evaluate("$('bGen').click()"); await asyncio.sleep(0.4)
        pv=await pg.inner_text("#gPrev")
        r=await pg.evaluate("(()=>{const o=genOpts();const x=genTimeline(o.manual,o.ignoreTaps);return {span:x.span,scales:x.scales,gs:x.gs}})()")
        dur=await pg.evaluate("aud.duration")
        # 用旧的"相邻段比例外推"会把末尾放大到 ×6.5；现在两端走全局比例
        oldEnd=45+(42-18)*2*6.5
        print(ok(r["span"][1]<oldEnd*0.7),
              f"总长 {r['span'][1]:.0f}s（旧实现会外推到 {oldEnd:.0f}s），各段比例 {[round(s,2) for s in r['scales']]}")
        print(ok("比音频还长" in pv), f'超长告警: {[l for l in pv.splitlines() if "比音频还长" in l]}')
        print(ok("偏离 1 太多" in pv), f'坏比例告警: {[l for l in pv.splitlines() if "偏离" in l]}')
        print(ok("音频长" in pv), "预览里带上了音频长度")

        # --- 删掉对不上的点 ---
        await pg.fill("#gForm","1-10"); await pg.dispatch_event("#gForm","input"); await asyncio.sleep(0.4)
        btn=await pg.query_selector("#gDropBad")
        print(ok(btn is not None), f"出现「删掉对不上的点」按钮: {await btn.text_content() if btn else None}")
        n0=await pg.evaluate("E.length")
        await btn.click(); await asyncio.sleep(0.4)
        print(ok(await pg.evaluate("E.length")<n0), f"点掉后 E {n0} -> {await pg.evaluate('E.length')}")
        await pg.evaluate("undo()"); await asyncio.sleep(0.2)
        print(ok(await pg.evaluate("E.length")==n0), "可撤销")
        await pg.click("#gCancel")

        # --- 频谱拖动走带 ---
        await pg.evaluate("E=[{m:1,t:5,src:'tap'}];layout();aud.pause();aud.currentTime=40")
        if not await pg.is_visible("#specBox"): await pg.click("#bSpec")
        await asyncio.sleep(0.3)
        cv=await pg.query_selector("#specCv"); r2=await cv.bounding_box()
        pps=await pg.evaluate("specPPS")
        cx,cy=r2["x"]+r2["width"]*0.7, r2["y"]+r2["height"]/2
        t0=await pg.evaluate("aud.currentTime")
        await pg.mouse.move(cx,cy); await pg.mouse.down()
        for dx in range(-20,-201,-20):
            await pg.mouse.move(cx+dx,cy); await asyncio.sleep(0.02)
        mid=await pg.evaluate("aud.currentTime")
        await pg.mouse.up()
        end=await pg.evaluate("aud.currentTime")
        print(ok(abs(end-(t0+200/pps))<0.3), f"往左拖 200px -> {t0:.2f}s 到 {end:.2f}s (期望 {t0+200/pps:.2f}s，往左=往后)")
        print(ok(abs(mid-end)<1e-6), "拖动过程中连续跟随（松手不再额外跳）")

        # 往右拖 = 往前
        t0=await pg.evaluate("aud.currentTime")
        await pg.mouse.move(cx,cy); await pg.mouse.down()
        for dx in range(20,161,20):
            await pg.mouse.move(cx+dx,cy); await asyncio.sleep(0.02)
        await pg.mouse.up()
        end=await pg.evaluate("aud.currentTime")
        print(ok(abs(end-(t0-160/pps))<0.3), f"往右拖 160px -> {t0:.2f}s 到 {end:.2f}s (期望 {t0-160/pps:.2f}s)")

        # 单击仍然定位
        await pg.evaluate("aud.currentTime=40")
        before=await pg.evaluate("aud.currentTime"); w=await pg.evaluate("specW()")
        await pg.mouse.click(r2["x"]+r2["width"]*0.25, cy)
        after=await pg.evaluate("aud.currentTime")
        want=before-(w/2)/pps+(w*0.25)/pps
        print(ok(abs(after-want)<0.2), f"单击仍定位: {before:.2f} -> {after:.2f} (期望 {want:.2f})")

        # 滚轮走带
        await pg.evaluate("aud.currentTime=40")
        await pg.mouse.move(cx,cy); await pg.mouse.wheel(0,240); await asyncio.sleep(0.2)
        print(ok(abs(await pg.evaluate("aud.currentTime")-(40+240/pps))<0.3),
              f"滚轮走带 -> {await pg.evaluate('aud.currentTime'):.2f}s (期望 {40+240/pps:.2f}s)")

        # 拖竖线仍然优先于走带
        await pg.evaluate("aud.currentTime=5;E=[{m:1,t:5,src:'gen'}];refresh();specDirty=true")
        await asyncio.sleep(0.3)
        t0=await pg.evaluate("aud.currentTime")
        xm=r2["x"]+r2["width"]/2
        await pg.mouse.move(xm,cy); await pg.mouse.down()
        await pg.mouse.move(xm+60,cy,steps=5); await pg.mouse.up(); await asyncio.sleep(0.3)
        e=await pg.evaluate("E[0]")
        print(ok(abs(e["t"]-(5+60/pps))<0.05 and abs(await pg.evaluate("aud.currentTime")-t0)<1e-6),
              f"拖竖线优先: t {5.0} -> {e['t']:.3f}, 播放位置没动 ({await pg.evaluate('aud.currentTime'):.2f})")

        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
