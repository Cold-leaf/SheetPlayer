import asyncio, http.server, socketserver, threading, functools
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
PDF=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8764),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c): return "OK   " if c else "FAIL "

async def main():
    errs=[]
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={"width":1200,"height":900})
        pg.on("pageerror",lambda e:errs.append(str(e)))
        await pg.goto("http://127.0.0.1:8764/player.html")
        await pg.evaluate("localStorage.clear()"); await pg.reload()
        await pg.set_input_files("#fPdf",PDF)
        await pg.wait_for_function("()=>cvs[1]&&document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=40000)

        # --- 工具栏收起/展开 ---
        print(ok(await pg.is_visible("#bar")), "初始工具栏可见")
        await pg.click("#bBar"); await asyncio.sleep(0.2)
        print(ok(not await pg.is_visible("#bar")), "点 ▲ 后工具栏隐藏")
        print(ok(await pg.is_visible("#barShow")), "浮动 ▼ 按钮出现")
        wrap_h_before=await pg.evaluate("wrap.clientHeight")
        print(ok(wrap_h_before>0), f"谱面区高度 {wrap_h_before}px")
        await pg.click("#barShow"); await asyncio.sleep(0.2)
        print(ok(await pg.is_visible("#bar")), "点 ▼ 恢复工具栏")

        # --- 桌面 ctrl+wheel 缩放（锚定鼠标位置）---
        z0=await pg.evaluate("zoom")
        wrap2=await pg.query_selector("#wrap"); r=await wrap2.bounding_box()
        # ctrl+wheel 放大（锚定细节由 pw_anchor.py 单独验证）
        await pg.evaluate("wrap.scrollTop=0;wrap.scrollLeft=0")
        cx,cy=r["x"]+r["width"]*0.5, r["y"]+r["height"]*0.5
        await pg.keyboard.down("Control")
        await pg.mouse.move(cx,cy)
        for _ in range(8):
            await pg.mouse.wheel(0,-40)   # 放大
            await asyncio.sleep(0.03)
        await pg.keyboard.up("Control")
        await asyncio.sleep(0.4)
        z1=await pg.evaluate("zoom")
        print(ok(z1>z0+0.05), f"ctrl+wheel 放大: zoom {z0:.2f} -> {z1:.2f}")

        # 普通 wheel（无 ctrl）不触发缩放
        z2=await pg.evaluate("zoom")
        await pg.mouse.move(cx,cy); await pg.mouse.wheel(0,-100); await asyncio.sleep(0.3)
        print(ok(abs(await pg.evaluate("zoom")-z2)<1e-9), "普通滚轮不缩放 PDF（只滚动）")

        # --- 双指捏合（合成 touch 事件）---
        await pg.evaluate("zoom=1.0;$('zoom').value=1;$('zoomVal').textContent='100%'")
        zp0=await pg.evaluate("zoom")
        pinch=await pg.evaluate("""()=>{
          const w=wrap;
          function mkT(id,x,y){return new Touch({identifier:id,target:w,clientX:x,clientY:y})}
          let a=mkT(1,400,300), b=mkT(2,500,300);
          w.dispatchEvent(new TouchEvent('touchstart',{touches:[a,b],changedTouches:[a,b],bubbles:true,cancelable:true}));
          for(let i=1;i<=5;i++){
            b=mkT(2,500+i*40,300);
            w.dispatchEvent(new TouchEvent('touchmove',{touches:[a,b],changedTouches:[b],bubbles:true,cancelable:true}));
          }
          w.dispatchEvent(new TouchEvent('touchend',{touches:[],changedTouches:[a,b],bubbles:true,cancelable:true}));
          return true;
        }""")
        await asyncio.sleep(0.3)
        zp1=await pg.evaluate("zoom")
        print(ok(pinch and zp1>zp0+0.1), f"双指捏合放大: zoom {zp0} -> {zp1:.2f} (两指距离从 100px 拉到 300px)")

        # 捏合缩小
        await pg.evaluate("zoom=1.6;$('zoom').value=1.6")
        zq0=await pg.evaluate("zoom")
        await pg.evaluate("""()=>{
          const w=wrap;
          function mkT(id,x,y){return new Touch({identifier:id,target:w,clientX:x,clientY:y})}
          let a=mkT(1,400,300), b=mkT(2,700,300);
          w.dispatchEvent(new TouchEvent('touchstart',{touches:[a,b],changedTouches:[a,b],bubbles:true,cancelable:true}));
          for(let i=1;i<=5;i++){
            b=mkT(2,700-i*60,300);
            w.dispatchEvent(new TouchEvent('touchmove',{touches:[a,b],changedTouches:[b],bubbles:true,cancelable:true}));
          }
          w.dispatchEvent(new TouchEvent('touchend',{touches:[],changedTouches:[a,b],bubbles:true,cancelable:true}));
        }""")
        await asyncio.sleep(0.3)
        zq1=await pg.evaluate("zoom")
        print(ok(zq1<zq0-0.1), f"双指捏合缩小: zoom {zq0} -> {zq1:.2f}")

        # 缩放限幅已放宽到 0.05–10
        z=await pg.evaluate("zoom")
        print(ok(0.05<=z<=10), f"缩放限幅(0.05–10): {z}")

        # 单指不缩放（照常滚动由浏览器处理）
        zs0=await pg.evaluate("zoom")
        await pg.evaluate("""()=>{const w=wrap;
          function mkT(id,x,y){return new Touch({identifier:id,target:w,clientX:x,clientY:y})}
          let a=mkT(9,400,300);
          w.dispatchEvent(new TouchEvent('touchstart',{touches:[a],changedTouches:[a],bubbles:true,cancelable:true}));
          w.dispatchEvent(new TouchEvent('touchend',{touches:[],changedTouches:[a],bubbles:true,cancelable:true}));
        }""")
        await asyncio.sleep(0.2)
        print(ok(abs(await pg.evaluate("zoom")-zs0)<1e-9), "单指触摸不缩放")

        # touch-action 已设置（浏览器不在 PDF 上捏合缩放页面）
        ta=await pg.evaluate("getComputedStyle(wrap).touchAction")
        print(ok(ta=="pan-x pan-y"), f"wrap touch-action={ta} (浏览器不在 PDF 区捏合缩放)")

        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
