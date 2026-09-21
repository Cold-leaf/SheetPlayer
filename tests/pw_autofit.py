import asyncio, http.server, socketserver, threading, functools
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
PDF=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8796),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c): return "OK   " if c else "FAIL "

# 自动适配的判据不是"页宽等于某个像素值"，是三条：
#   1) 整页装得下（高和宽都不超可用区）
#   2) 有一条边**贴住**可用区（否则就是没适配，只是碰巧小）
#   3) 方向只管翻页往哪边，不参与缩放——同一个窗口里切方向，页大小不该变
GEO="""()=>{const b=boxes[1].getBoundingClientRect();
  return {w:Math.round(b.width),h:Math.round(b.height),
          vw:wrap.clientWidth,vh:wrap.clientHeight,bh:barHpx(),
          aw:wrap.clientWidth-24,ah:wrap.clientHeight-barHpx()-24,
          zoom:Math.round(zoom*1000)/1000,autofit:autofit};}"""

def fits(g):
    return (g["w"]<=g["aw"]+3 and g["h"]<=g["ah"]+3 and
            (abs(g["w"]-g["aw"])<=3 or abs(g["h"]-g["ah"])<=3))

async def open_pdf(b,w,h,touch):
    pg=await b.new_page(viewport={"width":w,"height":h},has_touch=touch)
    pg.on("pageerror",lambda e:errs.append(str(e)))
    await pg.goto("http://127.0.0.1:8796/player.html?direct=1")
    await pg.evaluate("localStorage.clear()"); await pg.reload()
    await pg.set_input_files("#fPdf",PDF)
    await pg.wait_for_function("()=>cvs[1]&&document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=40000)
    return pg

errs=[]

async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch()

        # --- 桌面 1440×900：宽度富余，由高度那条边决定 → 页长贴住可用高 ---
        pg=await open_pdf(b,1440,900,False)
        g=await pg.evaluate(GEO)
        print(ok(fits(g) and abs(g["h"]-g["ah"])<=3),
              f"[1440×900 桌面] 进谱面整页装进视口、页长贴住可用高: 页 {g['w']}×{g['h']}px / 可用 {g['aw']}×{g['ah']}px"
              f"（工具栏 {g['bh']}px 已扣除）")

        # 桌面宽度富余，页宽不该贴边——两个都贴边说明算错了（按宽度适配会在窄页上过度放大）
        print(ok(abs(g["w"]-g["aw"])>10 and g["autofit"]),
              f"[1440×900 桌面] 由高度决定、宽度留白（页宽 {g['w']}px < 可用宽 {g['aw']}px），autofit={g['autofit']}")

        # --- 手动缩放之后，窗口再变也不许自动改 ---
        await pg.evaluate("$('zoom').value=2;$('zoom').oninput()"); await pg.wait_for_timeout(300)
        z0=await pg.evaluate("zoom")
        print(ok(await pg.evaluate("autofit")==False), f"动过滑杆后交出控制权 (autofit=False, zoom={z0})")
        await pg.set_viewport_size({"width":1000,"height":900}); await pg.wait_for_timeout(600)
        print(ok(abs(await pg.evaluate("zoom")-z0)<1e-9),
              f"手动缩放后改窗口大小，缩放不被动过: {z0} → {await pg.evaluate('zoom')}")

        # --- 点「适应屏幕」交回控制权，此后窗口变化自动重算 ---
        await pg.evaluate("$('bFitW').onclick()"); await pg.wait_for_timeout(500)
        g2=await pg.evaluate(GEO)
        print(ok(g2["autofit"] and fits(g2)),
              f"「适应屏幕」一键回正并交回自动适配: 页 {g2['w']}×{g2['h']}px / 可用 {g2['aw']}×{g2['ah']}px")
        await pg.set_viewport_size({"width":1440,"height":700}); await pg.wait_for_timeout(600)
        g3=await pg.evaluate(GEO)
        print(ok(g3["autofit"] and fits(g3) and abs(g3["h"]-g3["ah"])<=3),
              f"窗口变矮后自动重算、仍整页装得下: 页 {g3['w']}×{g3['h']}px / 可用 {g3['aw']}×{g3['ah']}px")

        # --- 切方向只换翻页方向，页大小不变（缩放不参与方向） ---
        z_before=await pg.evaluate("zoom")            # 取原始值：GEO 里的 zoom 是四舍五入过的，比不出 1e-9
        await pg.evaluate("$('chkHoriz').checked=false;$('chkHoriz').onchange()"); await pg.wait_for_timeout(400)
        z_after=await pg.evaluate("zoom")
        print(ok(abs(z_after-z_before)<1e-9),
              f"同一窗口里切到纵向，缩放不变: {z_before:.4f} → {z_after:.4f}")

        # --- 收起工具栏：可用高变大，页跟着变大（工具栏高度是适配的一部分） ---
        h_before=await pg.evaluate("boxes[1].clientHeight")
        await pg.evaluate("setBarHidden(true)"); await pg.wait_for_timeout(600)
        g5=await pg.evaluate(GEO)
        print(ok(g5["bh"]==0 and g5["h"]>h_before and fits(g5)),
              f"收起工具栏后按新可用高重算: 页高 {h_before} → {g5['h']}px（可用 {g5['ah']}px，工具栏已收起）")
        await pg.close()

        # --- 手机 390×844：宽度先到顶 → 页宽贴住屏幕宽 ---
        pgm=await open_pdf(b,390,844,True)
        gm=await pgm.evaluate(GEO)
        print(ok(fits(gm) and abs(gm["w"]-gm["aw"])<=3),
              f"[390×844 手机] 进谱面整页装进视口、页宽贴住屏幕宽: 页 {gm['w']}×{gm['h']}px / 可用 {gm['aw']}×{gm['ah']}px"
              f"（工具栏 {gm['bh']}px 已扣除）")

        # 「适应屏幕」在手机上必须真点得到：它跟方向按钮一起住在菜单「视图」里，
        # 工具栏第 1 行在 390px 真实路径下只剩 2px 余量——按钮被挤出菜单，
        # 手动缩放之后就再没有回正的入口了（方向按钮为此搬过三次家）
        await pgm.evaluate("$('menu').style.display='block'"); await pgm.wait_for_timeout(200)
        btn=await pgm.evaluate("""()=>{const b=$('bFitW'),r=b.getBoundingClientRect();
            return {shown:getComputedStyle(b).display!=='none',inMenu:!!b.closest('#menu'),
                    l:Math.round(r.left),r:Math.round(r.right),w:Math.round(r.width),h:Math.round(r.height),
                    vw:innerWidth}}""")
        print(ok(btn["shown"] and btn["inMenu"] and btn["l"]>=0 and btn["r"]<=btn["vw"]+1
                 and btn["w"]>=44 and btn["h"]>=44),
              f"[390 触摸] 「适应屏幕」在菜单里点得到、不出屏: [{btn['l']},{btn['r']}] ⊆ 0–{btn['vw']}，"
              f"命中区 {btn['w']}×{btn['h']}px")
        await pgm.evaluate("$('menu').style.display='none'")

        # --- 转屏：方向按约定不重算（一次会话只算一次），但缩放必须跟着重算，否则整页看不全 ---
        await pgm.set_viewport_size({"width":844,"height":390}); await pgm.wait_for_timeout(700)
        gl=await pgm.evaluate(GEO)
        print(ok(gl["autofit"] and fits(gl)),
              f"[390×844 → 844×390 转屏] 缩放跟着重算、整页仍装得下: 页 {gl['w']}×{gl['h']}px / 可用 {gl['aw']}×{gl['ah']}px")
        await pgm.close()

        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
