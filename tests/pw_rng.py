import asyncio, glob, json, http.server, socketserver, threading, functools
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
PDF=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8738),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c): return "OK   " if c else "FAIL "

async def main():
    errs=[]
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={"width":1500,"height":1050})
        pg.on("pageerror",lambda e:errs.append(str(e)))
        await pg.goto("http://127.0.0.1:8738/player.html?direct=1")
        await pg.evaluate("localStorage.clear()"); await pg.reload()
        await pg.set_input_files("#fPdf",PDF)
        await pg.wait_for_function("()=>document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=30000)
        await pg.evaluate("""()=>{M=Array.from({length:28},(_,i)=>
            ({page:1,nx:.10+(i%6)*.15,ny:.18+Math.floor(i/6)*.10,m:i+1}));
            E=[];syncNext();layout();save()}""")
        await asyncio.sleep(0.8)

        # 注入你截图那张 v3 表，验证自动迁移
        old=[{"m":m,"n":n,"d":8,"bpm":74.374} for m,n in
             [(1,6),(2,9),(3,6),(4,9),(5,6),(26,9),(27,6),(28,9)]]
        await pg.evaluate("""s=>{const k='player:'+pdfName;
            const cur=JSON.parse(localStorage.getItem(k));
            cur.v=3;cur.SIG=s;delete cur.TEMPO;delete cur.METER;
            localStorage.setItem(k,JSON.stringify(cur))}""", old)
        await pg.reload(); await pg.set_input_files("#fPdf",PDF)
        await pg.wait_for_function("()=>document.querySelectorAll('.mk').length>0",timeout=30000)
        ME=await pg.evaluate("METER.map(r=>sigText(r.sig)+': '+formText(r.ranges))")
        print(ok(ME==["6/8: 1, 3, 5-25, 27","9/8: 2, 4, 26, 28"]), f"你那 8 行迁移成 {len(ME)} 行: {ME}")
        same=await pg.evaluate("[1,2,3,4,5,6,17,25,26,27,28].map(m=>sigText(meterAt(m)))")
        print(ok(same==["6/8","9/8","6/8","9/8","6/8","6/8","6/8","6/8","9/8","6/8","9/8"]),
              f"逐小节结果与你原表一致: {same}")

        await pg.click("#bGen"); await asyncio.sleep(0.4)
        rows=await pg.eval_on_selector_all("#gMeter .grow","e=>e.length")
        sigs=await pg.eval_on_selector_all("#gMeter input.sig","e=>e.map(x=>x.value)")
        rngs=await pg.eval_on_selector_all("#gMeter input.rng","e=>e.map(x=>x.value)")
        print(ok(rows==2), f"面板 {rows} 行: {list(zip(sigs,rngs))}")
        hint=await pg.inner_text('#gMeter [data-dur="0"]')
        print(ok("管 28 小节" in hint or "管" in hint), f'行内提示: "{hint}"')

        cells=await pg.eval_on_selector_all("#gStrip .cell","e=>e.length")
        decl=await pg.eval_on_selector_all("#gStrip .cell.decl","e=>e.length")
        print(ok(cells==28 and decl==28), f"预览条 {cells} 格，其中 {decl} 格被明确指定")
        print(ok((await pg.inner_text("#gMeterInfo")).strip()==""), "无重叠/缺口告警")

        # --- 编辑区间 ---
        el=await pg.query_selector('#gMeter input.rng')
        await el.fill("1, 3, 5-20, 27"); await pg.dispatch_event('#gMeter input.rng',"change"); await asyncio.sleep(0.3)
        warn=await pg.inner_text("#gMeterInfo")
        print(ok("21,22,23,24,25" in warn and "没有拍号" in warn), f'缩短区间后报缺口: "{warn.strip()[:60]}…"')
        gaps=await pg.eval_on_selector_all("#gStrip .cell.gap","e=>e.map(x=>x.textContent)")
        print(ok(len(gaps)==5), f"预览条标红 {len(gaps)} 格: {gaps}")
        pv=await pg.inner_text("#gPrev")
        print(ok("没有指定拍号" in pv), f'预览挡住生成: "{pv[:48]}…"')

        # --- 兜底行 ---
        await el.fill(""); await pg.dispatch_event('#gMeter input.rng',"change"); await asyncio.sleep(0.3)
        fb=await pg.evaluate("[1,3,17,25,50].map(m=>sigText(meterAt(m)))")
        print(ok(fb==["6/8","6/8","6/8","6/8","6/8"]), f"第一行留空当兜底 -> {fb}")
        print(ok((await pg.inner_text("#gMeterInfo")).strip()==""), "兜底后告警消失")

        # --- 重叠检测 ---
        await el.fill("1-28"); await pg.dispatch_event('#gMeter input.rng',"change"); await asyncio.sleep(0.3)
        w=await pg.inner_text("#gMeterInfo")
        dups=await pg.eval_on_selector_all("#gStrip .cell.dup","e=>e.length")
        print(ok("重复指定" in w and dups==4), f'重叠检出 {dups} 格: "{w.strip()[:50]}…"')

        # --- 非法输入 ---
        await el.fill("1, 8-3"); await pg.dispatch_event('#gMeter input.rng',"change"); await asyncio.sleep(0.3)
        info=await pg.inner_text('#gMeter [data-dur="0"]')
        border=await pg.eval_on_selector('#gMeter input.rng',"e=>e.style.borderColor")
        print(ok("区间反了" in info and border=="rgb(255, 136, 136)"), f'非法区间: "{info}" 边框={border}')
        sg=await pg.query_selector('#gMeter input.sig')
        await el.fill("1, 3, 5-25, 27"); await pg.dispatch_event('#gMeter input.rng',"change")
        await sg.fill("6/7"); await pg.dispatch_event('#gMeter input.sig',"change"); await asyncio.sleep(0.3)
        print(ok("分母只能是" in await pg.inner_text('#gMeter [data-dur="0"]')), "非法拍号被拒")
        await sg.fill("6/8"); await pg.dispatch_event('#gMeter input.sig',"change"); await asyncio.sleep(0.3)

        # --- 加一种拍号 ---
        n0=await pg.evaluate("METER.length")
        await pg.click("#gAddM"); await asyncio.sleep(0.3)
        print(ok(await pg.evaluate("METER.length")==n0+1), f"加一种拍号: {n0} -> {await pg.evaluate('METER.length')} 行")
        await pg.evaluate("METER.pop();drawSig()"); await asyncio.sleep(0.2)

        # --- 生成 + 存档往返 ---
        await pg.fill("#gAncT","0"); await pg.dispatch_event("#gAncT","change"); await asyncio.sleep(0.3)
        await pg.click("#gRun"); await asyncio.sleep(0.5)
        ts=await pg.evaluate("[1,2,3,4,5,6].map(m=>+E.find(e=>e.m===m).t.toFixed(3))")
        print(ok(ts==[0,2.42,6.051,8.471,12.101,14.521]), f"生成时间 小节1-6 = {ts}")
        await pg.evaluate("window.__b=null;URL.createObjectURL=b=>{window.__b=b;return 'blob:x'}")
        await pg.evaluate("$('bExp').onclick()")
        j=json.loads(await pg.evaluate("window.__b.text()"))
        print(ok(j["v"]==5 and j["METER"][0]["ranges"][0]=={"from":1,"to":1}),
              f"导出 v{j['v']} METER={json.dumps(j['METER'],ensure_ascii=False)}")
        await asyncio.sleep(0.7); await pg.reload(); await pg.set_input_files("#fPdf",PDF)
        await pg.wait_for_function("()=>document.querySelectorAll('.mk').length>0",timeout=30000)
        rs=await pg.evaluate("METER.map(r=>sigText(r.sig)+': '+formText(r.ranges))")
        print(ok(rs==ME), f"刷新恢复: {rs}")

        await pg.click("#bGen"); await asyncio.sleep(0.4)
        await pg.screenshot(path="/tmp/meter_rng.png")
        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
