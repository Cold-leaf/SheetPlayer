import asyncio, glob, json, http.server, socketserver, threading, functools
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
PDF=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
AUD=glob.glob(ROOT+"/ICT_working/08-Assets/*.mp3")[0]
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8748),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c): return "OK   " if c else "FAIL "

async def main():
    errs=[]
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={"width":1500,"height":1000})
        pg.on("pageerror",lambda e:errs.append(str(e)))
        await pg.goto("http://127.0.0.1:8748/player.html")
        await pg.evaluate("localStorage.clear()"); await pg.reload()
        await pg.set_input_files("#fPdf",PDF)
        await pg.wait_for_function("()=>document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=30000)

        # --- 标小节：现在是竖线，带默认高度 ---
        await pg.select_option("#mode","mark")
        bb=await (await pg.query_selector('.page[data-page="1"]')).bounding_box()
        for i in range(4):
            await pg.mouse.click(bb["x"]+bb["width"]*(0.15+i*0.18), bb["y"]+bb["height"]*0.30)
        mk=await pg.evaluate("M.map(x=>({m:x.m,h:+x.h.toFixed(4)}))")
        print(ok(all(x["h"]==0.05 for x in mk)), f"新标记带默认高度: {mk}")
        geo=await pg.evaluate("""()=>{const d=document.querySelector('.mk'),b=d.querySelector('b');
          return {w:d.clientWidth,bw:b.clientWidth,h:d.clientHeight,lab:d.querySelector('i').textContent}}""")
        pageH=await pg.evaluate("boxes[1].clientHeight")
        print(ok(geo["w"]==44 and geo["bw"]<=4 and abs(geo["h"]-pageH*0.05)<2),
              f"竖线: 命中带{geo['w']}px + 可见线{geo['bw']}px 高{geo['h']}px, 编号'{geo['lab']}'")

        # --- 拖中段挪位置 ---
        await pg.select_option("#mode","edit")
        m0=await pg.evaluate("({nx:M[0].nx,ny:M[0].ny,h:M[0].h})")
        el=await pg.query_selector('.mk[data-m="1"]'); r=await el.bounding_box()
        midx,midy=r["x"]+r["width"]/2, r["y"]+r["height"]/2
        await pg.mouse.move(midx,midy); await pg.mouse.down()
        await pg.mouse.move(midx+90,midy+40,steps=6); await pg.mouse.up(); await asyncio.sleep(0.2)
        m1=await pg.evaluate("({nx:M[0].nx,ny:M[0].ny,h:M[0].h})")
        pw_,ph_=await pg.evaluate("[boxes[1].clientWidth,boxes[1].clientHeight]")
        print(ok(abs((m1["nx"]-m0["nx"])*pw_-90)<3 and abs((m1["ny"]-m0["ny"])*ph_-40)<3 and abs(m1["h"]-m0["h"])<1e-9),
              f"拖中段: 位移 ({(m1['nx']-m0['nx'])*pw_:.0f},{(m1['ny']-m0['ny'])*ph_:.0f})px，高度不变")

        # --- 拖下端改长度 ---
        el=await pg.query_selector('.mk[data-m="1"]'); r=await el.bounding_box()
        h0=await pg.evaluate("M[0].h"); ny0=await pg.evaluate("M[0].ny")
        await pg.mouse.move(r["x"]+r["width"]/2, r["y"]+r["height"]-1); await pg.mouse.down()
        await pg.mouse.move(r["x"]+r["width"]/2, r["y"]+r["height"]+70,steps=6); await pg.mouse.up(); await asyncio.sleep(0.2)
        h1=await pg.evaluate("M[0].h"); ny1=await pg.evaluate("M[0].ny")
        print(ok(abs((h1-h0)*ph_-70)<4 and abs(ny1-ny0)<1e-9),
              f"拖下端: 高度 {h0*ph_:.0f} -> {h1*ph_:.0f}px (+{(h1-h0)*ph_:.0f})，顶端不动")

        # --- 拖上端：顶端走，底端钉住 ---
        el=await pg.query_selector('.mk[data-m="1"]'); r=await el.bounding_box()
        bot0=await pg.evaluate("M[0].ny+M[0].h")
        await pg.mouse.move(r["x"]+r["width"]/2, r["y"]+1); await pg.mouse.down()
        await pg.mouse.move(r["x"]+r["width"]/2, r["y"]-30,steps=5); await pg.mouse.up(); await asyncio.sleep(0.2)
        bot1=await pg.evaluate("M[0].ny+M[0].h")
        print(ok(abs(bot1-bot0)<0.002), f"拖上端: 底端钉住 ({bot0*ph_:.0f} -> {bot1*ph_:.0f}px)")
        await pg.evaluate("undo();undo();undo()"); await asyncio.sleep(0.2)

        # --- 新点沿用上次高度 ---
        await pg.evaluate("M[0].h=0.11;lastH=0.11;styleMk(M[0])")
        await pg.select_option("#mode","mark")
        await pg.mouse.click(bb["x"]+bb["width"]*0.15, bb["y"]+bb["height"]*0.60)
        print(ok(abs(await pg.evaluate("M[M.length-1].h")-0.11)<1e-9),
              f"新点沿用上次高度: {await pg.evaluate('M[M.length-1].h')}")

        # --- 面板改高度 + 应用到全部 ---
        await pg.select_option("#mode","edit")
        el=await pg.query_selector('.mk[data-m="2"]'); r=await el.bounding_box()
        await pg.mouse.click(r["x"]+r["width"]/2, r["y"]+r["height"]/2); await asyncio.sleep(0.3)
        print(ok(await pg.is_visible("#pH")), f"面板出现高度输入: {await pg.input_value('#pH')}px")
        await pg.fill("#pH","80"); await pg.dispatch_event("#pH","change"); await asyncio.sleep(0.2)
        print(ok(abs(await pg.evaluate("M.find(x=>x.m===2).h")*ph_-80)<2), f"改单条: {await pg.evaluate('M.find(x=>x.m===2).h')*ph_:.0f}px")
        await pg.click("#pHAll"); await asyncio.sleep(0.3)
        hs=await pg.evaluate("M.map(x=>Math.round(x.h*boxes[1].clientHeight))")
        # 现在按钮是「应用到整行」：只有同一行（同 ny）的竖线一起变
        print(ok(hs==[80,80,80,80,120]), f"应用到整行: {hs} (同行的变 80，异行的 120 不动)")
        await pg.evaluate("undo()"); await asyncio.sleep(0.2)
        print(ok(len(set(await pg.evaluate('M.map(x=>x.h)')))>1), "可撤销")
        await pg.click("#pHAll"); await asyncio.sleep(0.3)

        # --- 命中测试沿整条线都有效 ---
        el=await pg.query_selector('.mk[data-m="3"]'); r=await el.bounding_box()
        for frac,name in [(0.05,"上端"),(0.5,"中段"),(0.95,"下端")]:
            hit=await pg.evaluate("""([x,y])=>{const box=document.querySelector('.page[data-page="1"]');
              const rr=box.getBoundingClientRect();
              const g={page:1,r:rr,nx:(x-rr.left)/rr.width,ny:(y-rr.top)/rr.height};
              const mk=near(g);return mk?mk.m:null}""",[r["x"]+r["width"]/2, r["y"]+r["height"]*frac])
            print(ok(hit==3), f"  命中{name}: 小节{hit}")

        # --- 保存/恢复带高度 ---
        await pg.evaluate("save()"); await asyncio.sleep(0.7)
        await pg.evaluate("window.__b=null;URL.createObjectURL=b=>{window.__b=b;return 'blob:x'}")
        await pg.evaluate("$('bExp').onclick()")
        j=json.loads(await pg.evaluate("window.__b.text()"))
        print(ok("h" in j["M"][0]), f"导出含高度: {j['M'][0]}")
        await pg.reload(); await pg.set_input_files("#fPdf",PDF)
        await pg.wait_for_function("()=>document.querySelectorAll('.mk').length>0",timeout=30000)
        print(ok(abs(await pg.evaluate("M[0].h")*ph_-80)<2), f"刷新恢复高度: {await pg.evaluate('M[0].h')*ph_:.0f}px")

        # --- 老数据（无 h）用默认值 ---
        await pg.evaluate("M=[{page:1,nx:.2,ny:.3,m:1}];layout()")
        d=await pg.evaluate("document.querySelector('.mk').clientHeight")
        print(ok(abs(d-ph_*0.05)<2), f"老数据无 h -> 默认 {d}px")

        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
