import asyncio, http.server, socketserver, threading, functools
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
PDF=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8739),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c): return "OK   " if c else "FAIL "

async def main():
    errs=[]
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={"width":1500,"height":1050})
        pg.on("pageerror",lambda e:errs.append(str(e)))
        await pg.goto("http://127.0.0.1:8739/player.html?direct=1")
        await pg.evaluate("localStorage.clear()"); await pg.reload()
        await pg.set_input_files("#fPdf",PDF)
        await pg.wait_for_function("()=>document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=30000)
        await pg.evaluate("""()=>{M=Array.from({length:40},(_,i)=>
            ({page:1,nx:.10+(i%6)*.15,ny:.16+Math.floor(i/6)*.08,m:i+1}));
            E=[];TEMPO=[{m:1,bpm:120}];METER=[{sig:[3,4],ranges:[]}];syncNext();layout()}""")

        # --- 0 个实测点：只能手动 ---
        await pg.evaluate("$('bGen').click()"); await asyncio.sleep(0.4)
        print(ok(await pg.evaluate("$('gAncTap').disabled")), "0 个实测点 -> 「用实测点」禁用")
        print(ok(await pg.is_visible("#gManRow")), "手动输入行可见")
        print(ok("还没有手动卡过" in await pg.inner_text("#gAncList")), "列表提示:", await pg.inner_text("#gAncList"))

        # --- 有实测点：手动行应隐藏，改为列出锚点 ---
        await pg.click("#gCancel")
        await pg.evaluate("""E=[{m:1,t:0,src:'tap'},{m:20,t:28.5,src:'tap'},{m:40,t:58.5,src:'tap'}];layout()""")
        await pg.evaluate("$('bGen').click()"); await asyncio.sleep(0.4)
        vis=await pg.is_visible("#gManRow")
        print(ok(not vis), f"选「用实测点」时手动行隐藏: visible={vis}  ← 你指出的死控件")
        chips=await pg.eval_on_selector_all("#gAncList .anc","e=>e.map(x=>x.textContent.replace('×',''))")
        print(ok(chips==["小节 1 = 0.00s","小节 20 = 28.50s","小节 40 = 58.50s"]), f"锚点列出来了: {chips}")

        # --- 段间比值 ---
        lnk=await pg.eval_on_selector_all("#gAncList .lnk","e=>e.map(x=>x.textContent)")
        # 3/4 @120 = 1.5s/小节；1->20 预测 28.5s 实际 28.5 -> x1.000；20->40 预测 30 实际 30 -> x1.000
        print(ok(lnk==["──×1.000──","──×1.000──"]), f"段间比值(全准): {lnk}")
        off=await pg.eval_on_selector_all("#gAncList .lnk.off","e=>e.length")
        print(ok(off==0), f"无异常标记: {off}")

        # --- 卡错一个点 -> 比值立刻暴露 ---
        await pg.evaluate("E[1].t=20; layout(); drawSig()"); await asyncio.sleep(0.3)
        lnk=await pg.eval_on_selector_all("#gAncList .lnk","e=>e.map(x=>x.textContent)")
        off=await pg.eval_on_selector_all("#gAncList .lnk.off","e=>e.map(x=>x.textContent)")
        warn=await pg.inner_text("#gAncList")
        print(ok(len(off)==2), f"把小节20卡到20s -> 两段都标黄: {lnk}")
        print(ok("多半是某个锚点卡错了" in warn), "并给出解释")

        # --- 删掉坏锚点 ---
        await pg.evaluate("E[1].t=28.5; layout(); drawSig()"); await asyncio.sleep(0.3)
        n0=await pg.evaluate("E.length")
        await pg.click('#gAncList .anc:nth-child(3) button'); await asyncio.sleep(0.4)
        n1=await pg.evaluate("E.length")
        chips=await pg.eval_on_selector_all("#gAncList .anc","e=>e.map(x=>x.textContent.replace('×',''))")
        print(ok(n1==n0-1 and len(chips)==2), f"点×删锚点: E {n0}->{n1}, 剩 {chips}")
        await pg.evaluate("undo()"); await asyncio.sleep(0.3)
        print(ok(await pg.evaluate("E.length")==n0), f"删除可撤销: E={await pg.evaluate('E.length')}")

        # --- 对不上播放顺序的点要标出来 ---
        await pg.evaluate("drawSig()")
        await pg.fill("#gForm","1-10"); await pg.dispatch_event("#gForm","input"); await asyncio.sleep(0.4)
        bad=await pg.eval_on_selector_all("#gAncList .anc.bad","e=>e.map(x=>x.textContent.replace('×',''))")
        print(ok(len(bad)==2 and "对不上播放顺序" in bad[0]), f"播放顺序只到10 -> 标出对不上的: {bad}")
        await pg.fill("#gForm",""); await pg.dispatch_event("#gForm","input"); await asyncio.sleep(0.3)

        # --- 切到手动：列表变灰划掉，手动行出现 ---
        await pg.click("#gAncMan"); await asyncio.sleep(0.3)
        cls=await pg.get_attribute("#gAncList","class")
        vis=await pg.is_visible("#gManRow")
        txt=await pg.inner_text("#gAncManTxt")
        print(ok(cls=="dim" and vis), f'切手动: 列表 class="{cls}" 手动行可见={vis} 标签="{txt}"')

        # --- 手动模式真的生效（丢弃实测点）---
        await pg.fill("#gAncM","1"); await pg.fill("#gAncT","5")
        await pg.dispatch_event("#gAncT","change"); await asyncio.sleep(0.3)
        pv=await pg.inner_text("#gPrev")
        print(ok("手动指定 1 个" in pv), f'预览确认用手动锚点: "{[l for l in pv.splitlines() if "锚点" in l][0]}"')
        await pg.click("#gRun"); await asyncio.sleep(0.5)
        t=await pg.evaluate("[1,2].map(m=>+E.find(e=>e.m===m).t.toFixed(2))")
        ntap=await pg.evaluate("E.filter(e=>e.src!=='gen').length")
        print(ok(t==[5,6.5] and ntap==0), f"手动锚点生成: 小节1,2={t}, 剩余实测点={ntap}")

        # --- 回到实测点模式并生成 ---
        await pg.evaluate("""E=[{m:1,t:0,src:'tap'},{m:40,t:60,src:'tap'}];layout()""")
        await pg.evaluate("$('bGen').click()"); await asyncio.sleep(0.4)
        print(ok(await pg.evaluate("$('gAncTap').checked")), "有实测点时默认选中「用实测点」")
        await pg.click("#gRun"); await asyncio.sleep(0.5)
        t=await pg.evaluate("[1,20,40].map(m=>+E.find(e=>e.m===m).t.toFixed(4))")
        print(ok(t==[0,round(60*19/39,4),60]), f"两锚点拉伸生成: {t}")

        await pg.evaluate("$('bGen').click()"); await asyncio.sleep(0.4)
        await pg.screenshot(path="/tmp/anchor_new.png")
        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
