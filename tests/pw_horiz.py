import asyncio, http.server, socketserver, threading, functools
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
PDF=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8759),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
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
        await pg.goto("http://127.0.0.1:8759/player.html?direct=1")
        await pg.evaluate("localStorage.clear()"); await pg.reload()
        await pg.set_input_files("#fPdf",PDF)
        await pg.wait_for_function("()=>cvs[1]&&document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=40000)
        np=await pg.evaluate("document.querySelectorAll('.page').length")

        await pg.evaluate("$('chkHoriz').checked=false;$('chkHoriz').onchange()"); await asyncio.sleep(0.2)   # 默认已横向，显式切回纵向再测

        # 纵向默认：页面上下堆叠
        v=await pg.evaluate("""()=>{const ps=[...document.querySelectorAll('.page')].map(p=>p.getBoundingClientRect());
            return {x0:ps[0].left, x1:ps[1].left, y0:ps[0].top, y1:ps[1].top}}""")
        print(ok(abs(v["x0"]-v["x1"])<2 and v["y1"]>v["y0"]), f"纵向：第2页在第1页正下方 (x差 {abs(v['x0']-v['x1']):.0f}px, y下移 {v['y1']-v['y0']:.0f}px)")

        # 开横向展开（方向按钮在菜单「视图」里，不在工具栏上）
        await pg.evaluate("$('menu').style.display='block'"); await asyncio.sleep(0.2)
        await pg.click("#bHoriz"); await asyncio.sleep(0.3)
        await pg.evaluate("$('menu').style.display='none'")
        h=await pg.evaluate("""()=>{const ps=[...document.querySelectorAll('.page')].map(p=>p.getBoundingClientRect());
            return {x0:ps[0].left, x1:ps[1].left, y0:ps[0].top, y1:ps[1].top, sw:wrap.scrollWidth, cw:wrap.clientWidth}}""")
        print(ok(h["x1"]>h["x0"] and abs(h["y0"]-h["y1"])<2), f"横向：第2页在第1页右侧 (x移 {h['x1']-h['x0']:.0f}px, y差 {abs(h['y0']-h['y1']):.0f}px)")
        print(ok(h["sw"]>h["cw"]*2), f"内容横向铺开 {h['sw']}px > 视口 {h['cw']}px 可横滑")

        # 横向滚到最后一页
        await pg.evaluate("wrap.scrollLeft=wrap.scrollWidth")
        await asyncio.sleep(0.6)
        live=await pg.evaluate("document.querySelectorAll('.page canvas').length")
        print(ok(0<live<np), f"横向滚到末尾，懒渲染仍生效: 存活 canvas {live}/{np}")

        # 跟随滚动改左右向
        await pg.evaluate("""()=>{M=[{page:1,nx:.3,ny:.3,m:1,h:.05}];E=[{m:1,t:0}];
            syncNext();layout();aud.pause();aud.currentTime=0}""")
        await pg.evaluate("wrap.scrollLeft=0")
        await pg.evaluate("$('chkFollow').checked=true;follow(byM.get(1)[0],true)")
        await settle(pg)
        sl=await pg.evaluate("wrap.scrollLeft")
        # 原来是 sl>=0——恒真，等于没断言。follow 的目的是把页面拉进视野，就该真的滚了
        print(ok(sl>0), f"横向跟随滚动生效 (scrollLeft={sl:.0f})")

        # 「适应屏幕」= 整页装进视口（取宽度/高度里更小的那条边），这个窗口里由高度决定。
        # 可用高必须减掉工具栏：它是 fixed 浮层，#wrap 仍是整个视口高，
        # 原来不减 barH，量出来的"刚好"其实底部被顶出屏幕一截
        await pg.evaluate("$('bFitW').onclick()"); await asyncio.sleep(0.8)
        ph_=await pg.evaluate("boxes[1].clientHeight"); vh=await pg.evaluate("wrap.clientHeight")
        bh=await pg.evaluate("barHpx()")
        print(ok(ph_<=vh-bh-24+1), f"横向「适应屏幕」整页装进视口: 页高 {ph_}px ≤ 可用高 {vh-bh}px（工具栏 {bh}px 已扣除）")

        # 切回纵向，「适应屏幕」仍要整页装得下（方向只决定翻页往哪边，不参与缩放）
        await pg.evaluate("$('menu').style.display='block'"); await asyncio.sleep(0.2)
        await pg.click("#bHoriz"); await asyncio.sleep(0.3)
        await pg.evaluate("$('menu').style.display='none'")
        await pg.evaluate("$('bFitW').onclick()"); await asyncio.sleep(0.8)
        pw2=await pg.evaluate("boxes[1].clientWidth"); vw=await pg.evaluate("wrap.clientWidth")
        ph2=await pg.evaluate("boxes[1].clientHeight"); vh2=await pg.evaluate("wrap.clientHeight")
        bh2=await pg.evaluate("barHpx()")
        print(ok(pw2<=vw-24+1 and ph2<=vh2-bh2-24+1),
              f"纵向「适应屏幕」整页装进视口: 页 {pw2}×{ph2}px ⊆ 可用 {vw-24}×{vh2-bh2-24}px")

        # 横向模式下缩放仍是滑条
        print(ok(await pg.evaluate("document.getElementById('zoom').type")=="range"), "缩放仍是 range 滑条")

        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
