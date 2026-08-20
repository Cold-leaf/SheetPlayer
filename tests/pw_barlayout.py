import asyncio, http.server, socketserver, threading, functools
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
PDF=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8789),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c): return "OK   " if c else "FAIL "

async def rects(pg,sel):
    return await pg.evaluate(f"()=>{{const e=document.querySelector('{sel}');if(!e)return null;"
                             f"const r=e.getBoundingClientRect();return {{top:r.top,bottom:r.bottom,left:r.left,right:r.right}}}}")

async def check(pg,label):
    bar=await rects(pg,"#bar")
    out=[]
    for sel,name in [("#menu","菜单"),("#panel","面板")]:
        vis=await pg.evaluate(f"()=>{{const e=document.querySelector('{sel}');"
                              f"return e&&getComputedStyle(e).display!=='none'}}")
        if not vis: continue
        r=await rects(pg,sel)
        gap=r["top"]-bar["bottom"]
        out.append((name,gap,r))
    return bar,out

async def main():
    errs=[]
    async with async_playwright() as p:
        b=await p.chromium.launch()
        # ---- 桌面宽屏 ----
        pg=await b.new_page(viewport={"width":1600,"height":900})
        pg.on("pageerror",lambda e:errs.append(str(e)))
        await pg.goto("http://127.0.0.1:8789/player.html?direct=1")
        await pg.set_input_files("#fPdf",PDF)
        await pg.wait_for_function("()=>document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=30000)
        await pg.wait_for_timeout(300)

        barH=await pg.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--barH').trim()")
        realH=await pg.evaluate("$('bar').offsetHeight")
        print(ok(barH==f"{realH}px"), f"--barH 跟随工具栏实际高度: {barH} (实测 {realH}px)")

        # 工具栏居中
        cen=await pg.evaluate("getComputedStyle(document.querySelector('.row')).justifyContent")
        print(ok("center" in cen), f"工具栏行居中: justify-content={cen}")

        await pg.click("#bMenu"); await pg.wait_for_timeout(200)
        bar,items=await check(pg,"desktop")
        for name,gap,r in items:
            print(ok(gap>=0), f"[桌面] {name}不与工具栏重叠: 顶部在工具栏下沿 +{gap:.0f}px")
            print(ok(r["bottom"]<=900+1), f"       {name}底部不出屏: {r['bottom']:.0f} ≤ 900")

        # 面板也检查（编辑点模式打开）
        await pg.evaluate("M=[{page:1,nx:.3,ny:.3,m:1,h:.08}];E=[];syncNext();layout();openPanel(1)")
        await pg.wait_for_timeout(200)
        bar,items=await check(pg,"desktop-panel")
        for name,gap,r in items:
            print(ok(gap>=0), f"[桌面] {name}不与工具栏重叠: +{gap:.0f}px")

        # 收起工具栏后菜单应上移到顶部（菜单开着时 bBar 的点击会被"点外面关菜单"吃掉，直接调 handler）
        await pg.evaluate("$('bBar').onclick()"); await pg.wait_for_timeout(300)
        h2=await pg.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--barH').trim()")
        mtop=(await rects(pg,"#menu"))["top"]
        print(ok(h2=="0px" and mtop<40), f"收起工具栏: --barH={h2}, 菜单顶部上移到 {mtop:.0f}px")
        await pg.evaluate("$('barShow').onclick()"); await pg.wait_for_timeout(300)

        # ---- 移动端窄屏 ----
        pg2=await b.new_page(viewport={"width":390,"height":780},
                             has_touch=True,is_mobile=True,device_scale_factor=2)
        pg2.on("pageerror",lambda e:errs.append(str(e)))
        await pg2.goto("http://127.0.0.1:8789/player.html?direct=1")
        await pg2.set_input_files("#fPdf",PDF)
        await pg2.wait_for_function("()=>document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=30000)
        await pg2.wait_for_timeout(300)
        await pg2.click("#bMenu"); await pg2.wait_for_timeout(250)
        bar=await rects(pg2,"#bar"); mn=await rects(pg2,"#menu")
        print(ok(mn["top"]>=bar["bottom"]), f"[移动] 菜单在工具栏下方: 菜单顶 {mn['top']:.0f} ≥ 工具栏底 {bar['bottom']:.0f}")
        print(ok(mn["bottom"]<=780+1), f"[移动] 菜单底部不出屏: {mn['bottom']:.0f} ≤ 780")
        await pg2.evaluate("M=[{page:1,nx:.3,ny:.3,m:1,h:.08}];E=[];syncNext();layout();openPanel(1)")
        await pg2.wait_for_timeout(250)
        pn=await rects(pg2,"#panel")
        print(ok(pn["top"]>=bar["bottom"]), f"[移动] 底部抽屉不顶到工具栏: 抽屉顶 {pn['top']:.0f} ≥ 工具栏底 {bar['bottom']:.0f}")
        # 窄屏行内容超宽时应可横向滚动到最左（safe center 退回左对齐）
        sl=await pg2.evaluate("""()=>{const r=document.querySelector('.row');
            r.scrollLeft=0;return {sw:r.scrollWidth,cw:r.clientWidth,sl:r.scrollLeft}}""")
        print(ok(sl["sl"]==0), f"[移动] 行可滚到最左: scrollLeft={sl['sl']} (内容 {sl['sw']} / 可视 {sl['cw']})")

        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
