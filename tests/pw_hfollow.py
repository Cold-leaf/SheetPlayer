import asyncio, http.server, socketserver, threading, functools
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
PDF=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8762),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={"width":900,"height":800})
        await pg.goto("http://127.0.0.1:8762/player.html")
        await pg.evaluate("localStorage.clear()"); await pg.reload()
        await pg.set_input_files("#fPdf",PDF)
        await pg.wait_for_function("()=>cvs[1]&&document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=40000)
        await pg.click("#bHoriz"); await asyncio.sleep(0.2)
        await pg.click("#bFitW"); await asyncio.sleep(0.8)
        # 每页 4 小节，铺满 6 页，让播放确实要跨页横滚
        await pg.evaluate("""()=>{
          M=[];let k=1;
          for(let pg=1;pg<=6;pg++) for(const ny of [.28,.46,.64])
            for(let i=0;i<3;i++) M.push({page:pg,nx:.16+i*.18,ny,m:k++,h:.06});
          E=M.map(x=>({m:x.m,t:(x.m-1)*1.0,src:'tap'}));
          lastH=.06;syncNext();layout();aud.pause();
        }""")
        await pg.evaluate("wrap.scrollLeft=0;aud.currentTime=0")
        seq=[]
        for m in range(1,54):
            await pg.evaluate(f"aud.currentTime={m-1}+0.4")
            await asyncio.sleep(0.08)
            seq.append(round(await pg.evaluate("wrap.scrollLeft")))
        zig=sum(1 for i in range(1,len(seq)) if seq[i]<seq[i-1]-5)
        # 单调不减：只有前进，没有往回
        mono=all(seq[i]>=seq[i-1]-5 for i in range(1,len(seq)))
        pages=len(await pg.evaluate("boxes"))-1
        print(f"scrollLeft 轨迹（{pages} 页，逐小节）:", seq)
        print(f"单调前进: {mono} | 回退次数: {zig}")
        # 每次跟随后，当前小节所在的页应完整可见
        okall=True
        for m in [1,10,19,28,37,46,53]:
            await pg.evaluate(f"aud.currentTime={m-1}+0.4"); await asyncio.sleep(0.15)
            v=await pg.evaluate("""()=>{const el=byM.get(OCC[occIndex(aud.currentTime)].m)?.[0];
                const box=el&&el.closest('.page');if(!box)return null;
                const r=box.getBoundingClientRect(),w=wrap.getBoundingClientRect();
                return {L:Math.round(r.left),R:Math.round(r.right),vw:Math.round(w.width)}}""")
            okk=v and v["L"]>=-1 and v["R"]<=v["vw"]+1
            okall=okall and okk
            print(f"  小节{m}: 页范围 [{v['L']},{v['R']}] vs 视口宽 {v['vw']}  {'OK' if okk else 'FAIL'}")
        print("当前页完整可见:", okall)
        await b.close()
asyncio.run(main())
