import asyncio, glob, http.server, socketserver, threading, functools, statistics
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
PDF=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
AUD=glob.glob(ROOT+"/ICT_working/08-Assets/*.mp3")[0]
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8746),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c): return "OK   " if c else "FAIL "

async def main():
    errs=[]
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={"width":1500,"height":1000})
        pg.on("pageerror",lambda e:errs.append(str(e)))
        await pg.goto("http://127.0.0.1:8746/player.html?direct=1")
        await pg.evaluate("localStorage.clear()"); await pg.reload()
        await pg.set_input_files("#fPdf",PDF); await pg.set_input_files("#fAud",AUD)
        await pg.wait_for_function("()=>SPEC!==null",timeout=60000)

        n=await pg.evaluate("SPEC.onsets.length")
        print(ok(n>50), f"真实音频检出 {n} 个起音，提示: \"{await pg.inner_text('#specMsg')}\"")
        # 强度是相对全曲最大谱通量归一的；全局最大那一帧未必被判为峰（可能在平台里），所以 max<=1 即可
        st=await pg.evaluate("({min:+Math.min(...SPEC.onsetStr).toFixed(3),max:+Math.max(...SPEC.onsetStr).toFixed(3)})")
        print(ok(0<st["min"]<=st["max"]<=1.0), f"强度归一化到 (0,1]: {st}")
        gaps=await pg.evaluate("[...SPEC.onsets].slice(1).map((t,i)=>+(t-SPEC.onsets[i]).toFixed(3))")
        print(f"     前 8 个间隔: {gaps[:8]}  中位 {statistics.median(gaps):.3f}s")

        if not await pg.is_visible("#specBox"): await pg.click("#bSpec")
        # 固定播放位置，直接数「开/关起音」两次渲染之间有多少像素变了
        GRAB="""()=>{const c=$('specCv');return [...c.getContext('2d').getImageData(0,0,c.width,c.height).data]}"""
        await pg.evaluate("aud.pause();aud.currentTime=12")
        await pg.evaluate("$('chkOnset').checked=true;specDirty=true"); await asyncio.sleep(0.4)
        onI=await pg.evaluate(GRAB)
        await pg.evaluate("$('chkOnset').checked=false;specDirty=true"); await asyncio.sleep(0.4)
        offI=await pg.evaluate(GRAB)
        diff=sum(1 for i in range(0,len(onI),4) if abs(onI[i]-offI[i])>8)
        brighter=sum(1 for i in range(0,len(onI),4) if onI[i]-offI[i]>8)
        nvis=await pg.evaluate("(()=>{const t0=specT0(),t1=t0+specW()/specPPS;return [...SPEC.onsets].filter(t=>t>=t0&&t<=t1).length})()")
        print(ok(diff>500 and brighter==diff), f"起音刻度渲染: 视野内 {nvis} 个起音，开/关差异 {diff} 像素（全部变亮）")
        await pg.evaluate("$('chkOnset').checked=true;specDirty=true")

        # --- 打点吸附 ---
        await pg.evaluate("""()=>{M=Array.from({length:30},(_,i)=>({page:1,nx:.1,ny:.2,m:i+1}));
          E=[];TEMPO=[{m:1,bpm:120}];METER=[{sig:[4,4],ranges:[]}];FORM=[];syncNext();layout()}""")
        o5=await pg.evaluate("SPEC.onsets[5]")
        await pg.evaluate("$('chkSnap').checked=false")
        await pg.evaluate(f"aud.currentTime={o5}+0.055; tapM=1; tap()")
        noSnap=await pg.evaluate("E[0].t")
        await pg.evaluate("E=[];refresh();$('chkSnap').checked=true;$('snapWin').value=120")
        await pg.evaluate(f"aud.currentTime={o5}+0.055; tapM=1; tap()")
        snapped=await pg.evaluate("E[0]")
        print(ok(abs(noSnap-(o5+0.055))<1e-6), f"关吸附: 打在 {noSnap:.3f}s（音头 {o5:.3f}s，偏 +55ms）")
        print(ok(abs(snapped["t"]-o5)<1e-6), f"开吸附: 吸到 {snapped['t']:.3f}s = 音头，误差 0ms")

        # 窗口外不吸
        await pg.evaluate("E=[];refresh()")
        await pg.evaluate(f"aud.currentTime={o5}+0.5; tapM=1; tap()")
        far=await pg.evaluate("E[0].t")
        print(ok(abs(far-(o5+0.5))<1e-6), f"偏 500ms 超出窗口 -> 不吸附，保持 {far:.3f}s")

        # 窗口不超过小节时长 40%
        cap=await pg.evaluate("$('snapWin').value=5000; snapWinFor(1)")
        print(ok(abs(cap-2*0.4)<1e-9), f"窗口被小节时长限住: 填 5000ms -> 实际 {cap*1000:.0f}ms (小节 2.0s 的 40%)")
        await pg.evaluate("$('snapWin').value=120")

        # --- 第 3 层：全部对齐 ---
        await pg.evaluate("E=[];refresh()")
        await pg.evaluate("$('bGen').click()"); await asyncio.sleep(0.3)
        await pg.fill("#gAncT","0.5"); await pg.dispatch_event("#gAncT","change")
        await pg.click("#gRun"); await asyncio.sleep(0.5)
        gen=await pg.evaluate("E.length")
        print(ok(gen==30), f"先生成 {gen} 个推算点")
        before=await pg.evaluate("E.map(e=>e.t)")
        await pg.click("#bAlign"); await asyncio.sleep(0.5)
        m=await pg.inner_text("#msg")
        after=await pg.evaluate("E.map(e=>({t:e.t,src:e.src}))")
        nsnap=sum(1 for e in after if e["src"]=="snap")
        shifts=[abs(a["t"]-bt) for a,bt in zip(after,before) if a["src"]=="snap"]
        print(ok(nsnap>0), f"全部对齐: {m}")
        print(ok(all(s<=0.121 for s in shifts)), f"移动量都在窗口内: 最大 {max(shifts)*1000:.0f}ms, 中位 {statistics.median(shifts)*1000:.0f}ms")
        # 对齐后每个点确实落在某个音头上
        onerr=await pg.evaluate("""()=>{const O=[...SPEC.onsets];
          return E.filter(e=>e.src==='snap').map(e=>Math.min(...O.map(o=>Math.abs(o-e.t))))}""")
        print(ok(max(onerr)<1e-6), f"对齐后每个点都精确落在音头上（最大偏差 {max(onerr)*1000:.4f}ms）")
        await pg.evaluate("undo()"); await asyncio.sleep(0.3)
        print(ok(await pg.evaluate("E.filter(e=>e.src==='snap').length")==0), "对齐可撤销")

        # 没有可对齐的点
        await pg.evaluate("E=[{m:1,t:1,src:'tap'}];refresh()")
        await pg.click("#bAlign"); await asyncio.sleep(0.3)
        print(ok("没有推算出来的点" in await pg.inner_text("#msg")), f'无可对齐时提示: "{await pg.inner_text("#msg")}"')

        # --- 已吸附的点画成绿色，且当锚点 ---
        await pg.evaluate("E=[{m:1,t:SPEC.onsets[3],src:'snap'}];refresh();aud.currentTime=SPEC.onsets[3];specDirty=true")
        await asyncio.sleep(0.4)
        g=await pg.evaluate("""()=>{const c=$('specCv'),d=c.getContext('2d').getImageData(0,0,c.width,c.height).data;
          let n=0;for(let i=0;i<d.length;i+=4)if(d[i]<130&&d[i+1]>190&&d[i+2]>110&&d[i+2]<170)n++;return n}""")
        print(ok(g>40), f"已吸附点画成绿色: {g}px")
        print(ok(await pg.evaluate("E.filter(e=>e.src!=='gen').length")==1), "已吸附点算作锚点（src!=='gen'）")

        # --- 锚点多时面板用摘要 ---
        await pg.evaluate("E=Array.from({length:40},(_,i)=>({m:i+1,t:i*1.5,src:'snap'}));layout()")
        await pg.evaluate("$('bGen').click()"); await asyncio.sleep(0.4)
        chips=await pg.eval_on_selector_all("#gAncList .anc","e=>e.length")
        txt=await pg.inner_text("#gAncList")
        print(ok(chips<=3 and "40 个" in txt), f'锚点多时用摘要: {chips} 个块, "{txt.strip()[:50]}"')

        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
