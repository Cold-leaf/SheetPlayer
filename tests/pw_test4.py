import asyncio, glob, http.server, socketserver, threading, functools
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
PDF=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
AUD=glob.glob(ROOT+"/ICT_working/08-Assets/*.mp3")[0]
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8734),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c): return "OK   " if c else "FAIL "

async def main():
    errs=[]
    async with async_playwright() as p:
        b=await p.chromium.launch()
        pg=await b.new_page(viewport={"width":1600,"height":950})
        pg.on("pageerror",lambda e:errs.append(str(e)))
        await pg.goto("http://127.0.0.1:8734/player.html?direct=1")
        await pg.evaluate("localStorage.clear()"); await pg.reload()
        await pg.set_input_files("#fPdf",PDF); await pg.set_input_files("#fAud",AUD)
        await pg.wait_for_function("()=>document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=30000)

        # 铺 8 个标记 + 一个"1–8 反复回 3"的时间轴
        await pg.evaluate("""()=>{
          const pts=[[.13,.255],[.40,.255],[.66,.255],[.13,.345],[.42,.345],[.70,.345],[.13,.435],[.45,.435]];
          M=pts.map(([nx,ny],i)=>({page:1,nx,ny,m:i+1}));
          E=[{m:1,t:0},{m:3,t:4},{m:8,t:14},{m:3,t:16},{m:8,t:26}];
          syncNext();layout();
        }""")
        await pg.select_option("#mode","play")

        n=await pg.eval_on_selector_all(".chip","els=>els.map(e=>e.textContent)")
        print(ok(len(n)==2), "段落条:", n)
        print(ok("2 段" in await pg.inner_text("#stat")), "状态栏:", await pg.inner_text("#stat"))

        async def tap(m, times=1, gap=0.05):
            el=await pg.query_selector(f'.mk[data-m="{m}"]'); r=await el.bounding_box()
            for _ in range(times):
                await pg.mouse.click(r["x"]+r["width"]/2, r["y"]+r["height"]/2)
                await asyncio.sleep(gap)
            return round(await pg.evaluate("aud.currentTime"),2)

        # --- 段落上下文选遍 ---
        await pg.evaluate("aud.pause(); aud.currentTime=10")   # ①段中
        t=await tap(5); print(ok(t==8.0), f"在①段(t=10)点小节5 -> {t}s (期望 8.0 = ①段的5)")
        await pg.evaluate("aud.currentTime=22")                # ②段中
        t=await tap(5); print(ok(t==20.0), f"在②段(t=22)点小节5 -> {t}s (期望 20.0 = ②段的5)")

        # --- 关键回归：①段末点回小节3，不该被②段"时间更近"抢走 ---
        await pg.evaluate("aud.currentTime=13")
        t=await tap(3); print(ok(t==4.0), f"在①段末(t=13)点小节3 -> {t}s (期望 4.0；取时间最近会跳到 16.0)")

        # --- 连点切换（无键盘）---
        await pg.evaluate("aud.currentTime=10; lastSeek=null")
        seq=[await tap(5)]
        for _ in range(3): seq.append(await tap(5, gap=0.3))
        print(ok(seq==[8.0,20.0,8.0,20.0]), f"连点同一小节循环切遍: {seq} (期望 [8,20,8,20])")
        print("   提示:", await pg.inner_text("#msg"))
        # 超过 2 秒后再点 -> 回到"当前段落"而非继续轮换
        await pg.evaluate("aud.currentTime=10")
        await asyncio.sleep(2.2)
        t=await tap(5); print(ok(t==8.0), f"隔 2 秒以上再点 -> 回到当前段落: {t}s (期望 8.0)")

        # --- 点段落 chip 跳转 + 高亮 ---
        await pg.click('.chip[data-k="1"]'); await asyncio.sleep(0.25)
        t=round(await pg.evaluate("aud.currentTime"),2)
        on=await pg.eval_on_selector_all(".chip.on","e=>e.map(x=>x.dataset.k)")
        print(ok(t==16.0 and on==["1"]), f"点②段 chip -> {t}s, 高亮 chip={on}")
        print(ok("②" in await pg.inner_text("#nowBox")), "现在指示:", await pg.inner_text("#nowBox"))
        # 跳段后再点小节，应落在②段
        t=await tap(6); print(ok(t==22.0), f"跳②段后点小节6 -> {t}s (期望 22.0)")

        # --- A-B 循环 ---
        await pg.click("#bA"); armed=await pg.get_attribute("#bA","class")
        print(ok("arm" in armed), f'按「设A」进入待命: class="{armed}"')
        before=round(await pg.evaluate("aud.currentTime"),2)
        await tap(4)                                  # 待命中点小节：只设 A，不该跳转
        after=round(await pg.evaluate("aud.currentTime"),2)
        print(ok(before==after), f"待命中点小节不跳转: {before} -> {after}")
        await pg.click("#bB"); await tap(6)
        print(ok(not await pg.get_attribute("#bA","class") or "arm" not in (await pg.get_attribute("#bA","class") or "")),
              "设完自动解除待命")
        txt=await pg.inner_text("#loopTxt")
        R=await pg.evaluate("loopRange()")
        print(ok(R["m0"]==4 and R["m1"]==6 and abs(R["t1"]-24)<0.01), f"A-B 范围: {txt} | {R} (t1 应=小节7起点 24)")

        await pg.click("#bLoop")
        print(ok("on" in (await pg.get_attribute("#bLoop","class") or "")), "循环已开")
        jumped=await pg.evaluate("""async()=>{ aud.currentTime=loopRange().t1-0.3; await aud.play();
          const t0=performance.now();
          while(performance.now()-t0<3000){ await new Promise(r=>setTimeout(r,50));
            if(aud.currentTime<loopRange().t0+1) return true }
          return false }""")
        pos=round(await pg.evaluate("aud.currentTime"),2)
        print(ok(jumped), f"播到终点自动弹回起点: {jumped}, 现在 {pos}s (区间 {R['t0']}–{R['t1']})")
        await pg.evaluate("aud.pause()")
        await pg.click("#bLoopClr")
        print(ok(await pg.inner_text("#loopTxt")=="未设区间"), "清除循环区间:", await pg.inner_text("#loopTxt"))

        # --- 待命时自动切到播放模式 ---
        await pg.select_option("#mode","time"); await pg.click("#bA")
        print(ok(await pg.input_value("#mode")=="play"), "待命自动切到播放模式:", await pg.input_value("#mode"))
        await pg.click("#bA")
        await pg.select_option("#mode","mark")
        print(ok(await pg.evaluate("arm")is None), "切模式会清掉待命")

        # --- 无反复时段落条隐藏 ---
        await pg.evaluate("E=[{m:1,t:0},{m:8,t:20}]; refresh()")
        vis=await pg.is_visible("#chipWrap")
        print(ok(not vis), f"只有一段时段落条隐藏: visible={vis}")

        await pg.evaluate("E=[{m:1,t:0},{m:3,t:4},{m:8,t:14},{m:3,t:16},{m:8,t:26}]; refresh(); aud.currentTime=18")
        await asyncio.sleep(0.3)
        await pg.evaluate("wrap.scrollTop=0")
        await pg.screenshot(path="/tmp/player_shot2.png",clip={"x":0,"y":0,"width":1600,"height":700})
        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
