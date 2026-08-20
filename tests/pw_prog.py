import asyncio, glob, http.server, socketserver, threading, functools
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
PDF=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
AUD=glob.glob(ROOT+"/ICT_working/08-Assets/*.mp3")[0]
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8749),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c): return "OK   " if c else "FAIL "

async def main():
    errs=[]
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={"width":1500,"height":1000})
        pg.on("pageerror",lambda e:errs.append(str(e)))
        await pg.goto("http://127.0.0.1:8749/player.html?direct=1")
        await pg.evaluate("localStorage.clear()"); await pg.reload()
        await pg.set_input_files("#fPdf",PDF); await pg.set_input_files("#fAud",AUD)
        await pg.wait_for_function("()=>SPEC!==null",timeout=60000)
        await pg.wait_for_function("()=>boxes.length>1&&document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=60000)
        # 同一行 4 个小节 + 下一行 1 个
        await pg.evaluate("""()=>{M=[
            {page:1,nx:.15,ny:.30,m:1,h:.08},{page:1,nx:.35,ny:.30,m:2,h:.08},
            {page:1,nx:.55,ny:.30,m:3,h:.08},{page:1,nx:.75,ny:.30,m:4,h:.08},
            {page:1,nx:.15,ny:.45,m:5,h:.08}];
          E=[{m:1,t:0,src:'tap'},{m:2,t:2,src:'tap'},{m:3,t:4,src:'tap'},
             {m:4,t:6,src:'tap'},{m:5,t:8,src:'tap'}];
          lastH=.08;syncNext();layout();aud.pause()}""")

        async def prog(t):
            await pg.evaluate(f"aud.currentTime={t}")
            await asyncio.sleep(0.12)
            return await pg.evaluate("""()=>{const b=document.getElementById('band'),s=document.getElementById('sweep');
              if(!b||b.style.display==='none')return null;
              const box=b.parentElement,W=box.clientWidth,H=box.clientHeight;
              return {L:+(b.offsetLeft/W).toFixed(4),W:+(b.offsetWidth/W).toFixed(4),
                      T:+(b.offsetTop/H).toFixed(4),H:+(b.offsetHeight/H).toFixed(4),
                      S:+(s.offsetLeft/W).toFixed(4),page:+box.dataset.page}}""")

        r=await prog(0.0)
        if r is None:
            print("DEBUG:", await pg.evaluate("""({t:aud.currentTime,lastT,dirty,occ:OCC.length,
              i:occIndex(aud.currentTime),band:!!document.getElementById('band'),
              bandEl:!!bandEl,chk:$('chkProg').checked,mk:[...mkByM.keys()],
              M:M.length,boxes:boxes.length,mkEl:mkEl.size,dom:document.querySelectorAll('.mk').length,
              disp:document.getElementById('band')?.style.display})"""))
        print(ok(abs(r["L"]-.15)<.005 and abs(r["W"]-.20)<.005), f"小节1 开头: 高亮带 x={r['L']}→{r['L']+r['W']:.3f} (期望 .15→.35), 扫描线 {r['S']}")
        print(ok(abs(r["T"]-.30)<.005 and abs(r["H"]-.08)<.005), f"高亮带用竖线的纵向范围: top={r['T']} h={r['H']} (期望 .30/.08)")
        r=await prog(1.0)
        print(ok(abs(r["S"]-.25)<.006), f"小节1 中点: 扫描线 {r['S']} (期望 .25)")
        r=await prog(1.9)
        print(ok(abs(r["S"]-.34)<.008), f"小节1 末尾: 扫描线 {r['S']} (期望 ~.34)")
        r=await prog(2.1)
        print(ok(abs(r["L"]-.35)<.005), f"跨到小节2: 高亮带跳到 x={r['L']} (期望 .35)")

        # 最后一个同行小节 -> 扫到行尾
        r=await prog(6.5)
        # 行末小节精确检测行末终止线（约 .935），不再拿中位间距(.20)猜成 .95
        print(ok(abs(r["L"]-.75)<.005 and abs(r["L"]+r["W"]-.935)<.01),
              f"小节4（下一小节换行）: 带子收在 x={r['L']}→{r['L']+r['W']:.3f} (期望 .75→.935，精确检测终止线)")
        r=await prog(8.2)
        print(ok(abs(r["L"]-.15)<.005 and abs(r["T"]-.45)<.005), f"小节5 换行: x={r['L']} top={r['T']} (期望 .15/.45)")

        # 单调推进
        xs=[(await prog(t))["S"] for t in [0.2,0.6,1.0,1.4,1.8]]
        print(ok(all(xs[i]<xs[i+1] for i in range(4))), f"扫描线单调右移: {xs}")

        # 开关
        await pg.evaluate("$('chkProg').checked=false;$('chkProg').onchange()")
        await pg.evaluate("aud.currentTime=1.5"); await asyncio.sleep(0.2)
        print(ok(await prog(1.0) is None), "关掉「小节进度」后隐藏")
        await pg.evaluate("$('chkProg').checked=true;$('chkProg').onchange()")
        print(ok(await prog(1.0) is not None), "重新打开恢复")

        # 没有标记的小节现在由前一根竖线覆盖（多小节休止），照常显示进度
        await pg.evaluate("M=M.filter(x=>x.m!==3);layout()")
        r=await prog(4.5)
        print(ok(r is not None), "没标的小节 3 由前一根覆盖，进度带照常显示")
        print(ok(await prog(0.5) is not None), "其他小节照常")

        # 播放中平滑推进
        await pg.evaluate("M=[{page:1,nx:.15,ny:.30,m:1,h:.08},{page:1,nx:.75,ny:.30,m:2,h:.08}];E=[{m:1,t:0},{m:2,t:4}];layout();aud.currentTime=0")
        await pg.evaluate("aud.play()")
        seen=[]
        for _ in range(6):
            await asyncio.sleep(0.25)
            seen.append(await pg.evaluate("document.getElementById('sweep').offsetLeft"))
        await pg.evaluate("aud.pause()")
        print(ok(all(seen[i]<=seen[i+1] for i in range(5)) and seen[-1]>seen[0]),
              f"真实播放中平滑推进: {seen}")

        await pg.evaluate("aud.currentTime=1.4"); await asyncio.sleep(0.3)
        await pg.evaluate("wrap.scrollTop=0")
        el=await pg.query_selector('.page[data-page="1"]'); pb=await el.bounding_box()
        await pg.screenshot(path="/tmp/prog.png",clip={"x":pb["x"],"y":pb["y"]+pb["height"]*0.22,"width":pb["width"],"height":pb["height"]*0.30})
        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
