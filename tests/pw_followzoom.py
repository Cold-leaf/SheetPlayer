import asyncio, http.server, socketserver, threading, functools
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
PDF=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8790),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c): return "OK   " if c else "FAIL "

# follow() 现在走平滑滚动（glide），位移是异步的——量位置之前先等它真的停下。
# 判据是"连续 8 帧位置不变"。踩过两次坑，都不是"多等一会"能解决的：
#   · 3 帧太少——缓动起步那一两帧本来就不动，会被当成已经停稳（follow 回小节1 这么假绿过）
#   · scrollend 会串台——紧挨着的一次普通滚动（比如 wrap.scrollLeft=0）也会发 scrollend，
#     监听挂上去时它正好到达，于是立刻返回，读到的还是动画开始前的位置
async def settle(pg):
    await pg.evaluate("""()=>new Promise(r=>{let last=-1,n=0,t=0;
      const f=()=>{const v=wrap.scrollTop+'/'+wrap.scrollLeft;
        if(v===last){if(++n>=8)return r()}else n=0;
        last=v;if(++t>240)return r();                 // 兜底：最多等约 4 秒
        requestAnimationFrame(f)};
      requestAnimationFrame(f)})""")

async def main():
    errs=[]
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={"width":900,"height":800})
        pg.on("pageerror",lambda e:errs.append(str(e)))
        await pg.goto("http://127.0.0.1:8790/player.html?direct=1")

        # 默认就是播放模式
        mv=await pg.evaluate("document.getElementById('mode').value")
        print(ok(mv=="play"), f"打开默认播放模式: {mv}")
        print(ok(await pg.evaluate("[...document.getElementById('mode').options].map(o=>o.value)[0]")=="play"),
              "播放是模式列表第一项")
        print(ok(await pg.evaluate("!!document.querySelector('#bar #chkFollow')")), "「跟随滚动」在工具栏里")
        print(ok(await pg.evaluate("!document.querySelector('#menu #chkFollow')")), "已从菜单移除")

        await pg.set_input_files("#fPdf",PDF)
        await pg.wait_for_function("()=>document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=30000)

        await pg.evaluate("$('chkHoriz').checked=false;$('chkHoriz').onchange()"); await pg.wait_for_timeout(200)   # 测纵向分支，先切回纵向

        # 放大到页面明显比视口宽，一行里放 4 个小节（横跨整页宽度）
        await pg.evaluate("""()=>{zoom=3;$('zoom').value=3;applyZoom();
          M=[{page:1,nx:.10,ny:.30,m:1,h:.06},{page:1,nx:.40,ny:.30,m:2,h:.06},
             {page:1,nx:.70,ny:.30,m:3,h:.06},{page:1,nx:.95,ny:.30,m:4,h:.06}];
          E=[{m:1,t:0,src:'tap'},{m:2,t:2,src:'tap'},{m:3,t:4,src:'tap'},{m:4,t:6,src:'tap'}];
          syncNext();layout();wrap.scrollLeft=0;wrap.scrollTop=0;userScrollUntil=0}""")
        await pg.wait_for_timeout(300)
        wide=await pg.evaluate("wrap.scrollWidth>wrap.clientWidth+2")
        print(ok(wide), f"放大 3x 后页面比视口宽（scrollWidth {await pg.evaluate('wrap.scrollWidth')} > clientWidth {await pg.evaluate('wrap.clientWidth')}）")

        async def vis(m):
            return await pg.evaluate("""(m)=>{const d=(byM.get(m)||[])[0];if(!d)return null;
              const r=d.getBoundingClientRect(),w=wrap.getBoundingClientRect();
              return {inView:r.left>=w.left-1&&r.right<=w.right+1, left:Math.round(r.left-w.left),
                      sl:Math.round(wrap.scrollLeft)}}""",m)

        # 跟随到最右那个小节：横向应自动滚过去
        await pg.evaluate("follow((byM.get(4)||[])[0])")
        await settle(pg)
        v=await vis(4)
        print(ok(v["inView"]), f"跟随到最右小节4: 在视野内={v['inView']} (相对视口左 {v['left']}px, scrollLeft={v['sl']})")

        # 再跟随回最左：应滚回去
        await pg.evaluate("follow((byM.get(1)||[])[0])")
        await settle(pg)
        v1=await vis(1)
        print(ok(v1["inView"]), f"跟随回小节1: 在视野内={v1['inView']} (scrollLeft={v1['sl']})")

        # 关掉跟随后不再滚动
        await pg.evaluate("wrap.scrollLeft=0;document.getElementById('chkFollow').checked=false")
        await pg.evaluate("follow((byM.get(4)||[])[0])")
        await pg.wait_for_timeout(400)                  # 关掉后续不该滚，但要给动画留出"如果真滚了"的时间
        print(ok(await pg.evaluate("wrap.scrollLeft")==0, ), f"关掉跟随后不滚: scrollLeft={await pg.evaluate('wrap.scrollLeft')}")
        await pg.evaluate("document.getElementById('chkFollow').checked=true")

        # 未放大时（页面窄于视口）不应产生横向滚动
        await pg.evaluate("""()=>{zoom=.5;$('zoom').value=.5;applyZoom();wrap.scrollLeft=0;userScrollUntil=0}""")
        await pg.wait_for_timeout(300)
        await pg.evaluate("follow((byM.get(4)||[])[0])")
        await pg.wait_for_timeout(400)
        print(ok(await pg.evaluate("wrap.scrollLeft")==0), f"页面窄于视口时不横滚: scrollLeft={await pg.evaluate('wrap.scrollLeft')}")

        # 整页在屏幕内时，**一行一行走完**一次都不该横移。
        # 上面那条只跟一个小节，而且是在 900 宽的视口里跟一个 298 宽的小页面——±40px 那条边
        # 根本够不着，漏掉了真正的症状。用户 2026-09-21 报的"行末直接跳到下一行行首"，
        # 得在手机这种「页面宽度和视口是同一个量级」的几何下才现形：
        # 判横向跟随的前置条件原来写成 wrap.scrollWidth>clientWidth，而 #pages 有
        # calc(90vw-20px) 横向留白 → 恒真 → 每行行末横移一次、下一行行首又横移回来。
        await pg.set_viewport_size({"width":390,"height":844})
        await pg.evaluate("""()=>{setBarHidden(true);$('chkHoriz').checked=false;$('chkHoriz').onchange();
          $('bFitW').onclick();M=[];E=[];let k=1;
          for(const ny of [.12,.42,.72]) for(const nx of [.12,.38,.63,.86]){
            M.push({page:1,nx,ny,m:k,h:.10});E.push({m:k,t:k*2.5,src:'tap'});k++;}
          syncNext();layout();userScrollUntil=0;scrollHome()}""")
        await pg.wait_for_timeout(500)
        await pg.evaluate("window.__settle=()=>new Promise(r=>{let last=-1,n=0,t=0;"
                          "const f=()=>{const v=wrap.scrollTop+'/'+wrap.scrollLeft;"
                          "if(v===last){if(++n>=8)return r()}else n=0;"
                          "last=v;if(++t>240)return r();requestAnimationFrame(f)};"
                          "requestAnimationFrame(f)})")
        d=await pg.evaluate("""()=>{
          const wr=wrap.getBoundingClientRect(),pgb=boxes[1].getBoundingClientRect();
          const moves=[];
          return (async()=>{
          for(let m=1;m<=M.length;m++){
            const el=(byM.get(m)||[])[0];if(!el)continue;
            const sl0=wrap.scrollLeft;follow(el);
            await __settle();                       // 平滑滚动是异步的，等停稳再比
            if(wrap.scrollLeft!==sl0)moves.push({m,dx:Math.round(wrap.scrollLeft-sl0)});
          }
          return {pageW:Math.round(pgb.width),vw:Math.round(wr.width),n:M.length,moves};})();}""")
        print(ok(d["pageW"]<=d["vw"]+2 and not d["moves"]),
              f"[390 手机] 整页在屏幕内（页宽 {d['pageW']}px ≤ 视口 {d['vw']}px）时，"
              f"一页 {d['n']} 个小节逐个跟随 0 次横移"
              + (f" —— 实际横移 {d['moves']}" if d["moves"] else ""))

        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
