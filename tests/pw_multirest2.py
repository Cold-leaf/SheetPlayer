import asyncio, http.server, socketserver, threading, functools
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
PDF=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8763),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c,*_): return "OK   " if c else "FAIL "

async def main():
    errs=[]
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={"width":1200,"height":900})
        pg.on("pageerror",lambda e:errs.append(str(e)))
        await pg.goto("http://127.0.0.1:8763/player.html?direct=1")
        await pg.evaluate("localStorage.clear()"); await pg.reload()
        await pg.set_input_files("#fPdf",PDF)
        await pg.wait_for_function("()=>cvs[1]&&document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=40000)
        # 小节1 在多小节休止左侧，跳号到 7；7、8 接着
        await pg.evaluate("""()=>{M=[{page:1,nx:.20,ny:.30,m:1,h:.08},{page:1,nx:.55,ny:.30,m:7,h:.08},
                                   {page:1,nx:.80,ny:.30,m:8,h:.08}];
          E=[{m:1,t:0,src:'tap'},{m:7,t:12,src:'tap'},{m:8,t:14,src:'tap'}];
          lastH=.08;syncNext();layout();aud.pause()}""")

        # 标签显示范围
        lab=await pg.evaluate("document.querySelector('.mk[data-m=\"1\"] i').textContent")
        print(ok(lab=="1–6"), f"标签显示覆盖范围: 小节1 显示 '{lab}'")

        # gap=1（如删掉误标的小节后剩 1、3）不谎称覆盖：标签仍是各自的小节号
        await pg.evaluate("M=[{page:1,nx:.20,ny:.30,m:1,h:.08},{page:1,nx:.55,ny:.30,m:3,h:.08}];E=[];syncNext();layout()")
        l1=await pg.evaluate("document.querySelector('.mk[data-m=\"1\"] i').textContent")
        l3=await pg.evaluate("document.querySelector('.mk[data-m=\"3\"] i').textContent")
        print(ok(l1=="1" and l3=="3"), f"gap=1 不显示范围: 1→'{l1}' 3→'{l3}'（不是 '1–2'）")
        await pg.evaluate("""()=>{M=[{page:1,nx:.20,ny:.30,m:1,h:.08},{page:1,nx:.55,ny:.30,m:7,h:.08},
            {page:1,nx:.70,ny:.30,m:8,h:.08}];
          E=[{m:1,t:0,src:'tap'},{m:7,t:12,src:'tap'},{m:8,t:14,src:'tap'}];syncNext();layout();aud.pause()}""")

        async def probe(t):
            await pg.evaluate(f"aud.currentTime={t}"); await asyncio.sleep(0.18)
            return await pg.evaluate("""()=>{const i=occIndex(aud.currentTime),o=OCC[i];
              const b=document.getElementById('band'),s=document.getElementById('sweep');
              const cur=document.querySelector('.mk.cur');
              const box=b?b.parentElement:null,W=box?box.clientWidth:1;
              return {m:o.m,band:(b&&b.style.display!=='none'),cur:cur?cur.dataset.m:'无',
                      L:+(b.offsetLeft/W).toFixed(3),R:+((b.offsetLeft+b.offsetWidth)/W).toFixed(3),
                      S:+(s.offsetLeft/W).toFixed(3)} }""")

        r=await probe(0.5)
        print(ok(r["band"] and r["cur"]=="1"), f"t=0.5: 小节{r['m']} 进度带显示 高亮竖线 {r['cur']}")
        # 休止期间（小节 2–6）：进度带和高亮都要在，且扫描线平滑前进
        S=[]
        for t in [2,4,6,8,10]:
            r=await probe(t); S.append((r["S"],r["cur"]))
            assert r["band"], f"t={t} 进度带应该显示"
        print(ok(all(c=="1" for _,c in S)), "休止期间高亮一直停在竖线 1:", [c for _,c in S])
        smooth=all(S[i][0]<S[i+1][0] for i in range(len(S)-1))
        print(ok(smooth), "扫描线平滑前进(不重置):", [round(s,3) for s,_ in S])
        r=await probe(0.5)
        print(ok(abs(r["L"]-.20)<.01 and abs(r["R"]-.55)<.02), f"进度带横跨休止: {r['L']:.3f}→{r['R']:.3f} (期望 .20→.55)")

        # 出了休止：高亮跳到 7
        r=await probe(12.5)
        print(ok(r["cur"]=="7", f"t=12.5: 高亮竖线 {r['cur']} (小节{r['m']})"))

        # --- 跨小节输入 ---
        await pg.evaluate("M=[];E=[];syncNext();layout()")   # 清空重来
        await pg.select_option("#mode","mark")
        bb=await (await pg.query_selector('.page[data-page="1"]')).bounding_box()
        await pg.mouse.click(bb["x"]+bb["width"]*.2, bb["y"]+bb["height"]*.3)   # 标小节1
        print(ok(await pg.evaluate("nextM")==2), f"标小节1 后 nextM={await pg.evaluate('nextM')}")
        await pg.evaluate("$('skipN').value=6;$('bSkip').click()")
        print(ok(await pg.evaluate("nextM")==7), f"填6点「跳」: nextM={await pg.evaluate('nextM')} (期望 7)")
        sv=await pg.evaluate("+$('skipN').value")
        print(ok(sv==1), f"跨小节输入复位: {sv}")
        await pg.mouse.click(bb["x"]+bb["width"]*.55, bb["y"]+bb["height"]*.3)   # 标小节7
        print(ok(await pg.evaluate("M.map(x=>x.m).join(',')")=="1,7"), "标出的编号: "+await pg.evaluate("M.map(x=>x.m).join(',')"))

        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
