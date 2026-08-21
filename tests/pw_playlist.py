# 播放列表：加入 / 排序 / 连播 / 循环 / 每首后暂停 / 音频缺失回退
import asyncio, glob, http.server, socketserver, threading, functools, wave, struct, math
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
P1=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
P2=ROOT+"/线谱合集/BW_不忘初心[线][SATB+NA+Pn].pdf"
def tone(path,sec,freq):
    with wave.open(path,'w') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(22050)
        w.writeframes(b''.join(struct.pack('<h',int(9000*math.sin(2*math.pi*freq*i/22050)))
                               for i in range(int(22050*sec))))
A1="/tmp/pl_a.wav"; A2="/tmp/pl_b.wav"
tone(A1,1.0,440); tone(A2,1.0,330)      # 各 1 秒，方便测自动进下一首
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8802),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c): return "OK   " if c else "FAIL "

async def add_track(pg,pdf,aud):
    await pg.set_input_files("#fPdf",pdf)
    await pg.wait_for_function("()=>document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=60000)
    await pg.set_input_files("#fAud",aud)
    await pg.wait_for_function("()=>$('dlgMode').style.display==='flex'",timeout=8000)
    await pg.click("#dlgModeOk")
    await pg.wait_for_function("()=>track&&track.audios.length>0",timeout=20000)

async def main():
    errs=[]
    async with async_playwright() as p:
        b=await p.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"])
        pg=await b.new_page(viewport={"width":1500,"height":1000})
        pg.on("pageerror",lambda e:errs.append(str(e)))
        await pg.goto("http://127.0.0.1:8802/player.html")
        await pg.wait_for_function("()=>idb!==null",timeout=15000)

        await add_track(pg,P1,A1)
        await add_track(pg,P2,A2)
        await pg.evaluate("$('bLib').onclick()"); await pg.wait_for_timeout(400)
        cards=await pg.evaluate("document.querySelectorAll('.libCard').length")
        print(ok(cards==2), f"库里 {cards} 首曲目")

        # 加入播放列表（两首）
        await pg.evaluate("document.querySelectorAll('.libCard button.pladd').forEach(b=>b.click())")
        await pg.wait_for_function("()=>PL.items.length===2",timeout=10000)
        print(ok(await pg.evaluate("PL.items.length")==2), "两首都加入播放列表")
        rows=await pg.evaluate("document.querySelectorAll('.plRow').length")
        print(ok(rows==2), f"列表面板显示 {rows} 行")

        # 排序：把第 2 首上移
        names0=await pg.evaluate("[...document.querySelectorAll('.plRow .nm')].map(e=>e.textContent)")
        await pg.click('.plRow [data-up="1"]'); await pg.wait_for_timeout(300)
        names1=await pg.evaluate("[...document.querySelectorAll('.plRow .nm')].map(e=>e.textContent)")
        print(ok(names1==[names0[1],names0[0]]), f"上移生效: {names0} → {names1}")

        # 开始播放 → 第 1 首
        await pg.click("#plStart")
        # 等状态条真正刷新（syncPL 在 loadPdfBlob 之后才跑）
        await pg.wait_for_function("()=>plOn&&plIdx===0&&$('plNow').textContent==='列表 1/2'",timeout=30000)
        print(ok(await pg.evaluate("getComputedStyle($('plBox')).display")!="none"), "工具栏显示播放列表状态条")
        now=await pg.evaluate("document.getElementById('plNow').textContent")
        print(ok(now=="列表 1/2"), f"状态: {now}")

        # 1 秒音频放完 → 自动进第 2 首
        await pg.wait_for_function("()=>plIdx===1",timeout=30000)
        print(ok(True), "第 1 首放完自动进第 2 首")
        await pg.wait_for_function("()=>$('plNow').textContent==='列表 2/2'",timeout=15000)
        print(ok(await pg.evaluate("document.getElementById('plNow').textContent")=="列表 2/2"), "状态更新为 2/2")

        # 循环开：第 2 首放完回到第 1 首
        await pg.wait_for_function("()=>plIdx===0",timeout=30000)
        print(ok(True), "循环开：末尾回到第 1 首")

        # 每首后暂停
        await pg.evaluate("aud.pause();PL.pauseEach=true;savePL()")
        await pg.evaluate("plPlay(0,true)")
        await pg.wait_for_function("()=>plIdx===1",timeout=30000)
        await pg.wait_for_timeout(400)
        print(ok(await pg.evaluate("aud.paused")), "「每首后暂停」：进下一首后停住等按播放")

        # 上一首 / 下一首
        await pg.evaluate("$('plPrev').onclick()")
        await pg.wait_for_function("()=>plIdx===0",timeout=20000)
        print(ok(True), "⏮ 上一首")
        await pg.evaluate("$('plNext').onclick()")
        await pg.wait_for_function("()=>plIdx===1",timeout=20000)
        print(ok(True), "⏭ 下一首")

        # 退出播放列表
        await pg.evaluate("$('plStop').onclick()")
        await pg.wait_for_timeout(200)
        print(ok(await pg.evaluate("!plOn") and await pg.evaluate("getComputedStyle($('plBox')).display")=="none"), "✕ 退出播放列表")

        # 音频缺失回退：把条目的 audioHash 改成不存在的
        await pg.evaluate("PL.items[0].audioHash='deadbeef';savePL()")
        await pg.evaluate("plPlay(0,false)")
        await pg.wait_for_function("()=>plIdx===0&&pdf!==null",timeout=30000)
        print(ok(await pg.evaluate("!!audUrl")), "指定音频不在本机时回退到可用音频")

        # 刷新后播放列表还在（存在 IndexedDB）
        await pg.reload()
        await pg.wait_for_function("()=>idb!==null&&PL.items.length===2",timeout=20000)
        print(ok(await pg.evaluate("PL.items.length")==2), "刷新后播放列表仍在")

        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
