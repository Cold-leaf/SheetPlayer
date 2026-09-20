import asyncio, json, hashlib, http.server, socketserver, threading, functools
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
PDF=ROOT+"/SheetPlayerTests/SK_斯卡布罗集市[线][TTBB+NA+WO]_0_1787155482878.pdf"
ANN=json.load(open(ROOT+"/SheetPlayer/annotations.json"))
# 该 PDF 的真实标注：页2 各行的小节号与 nx（用于断言自动补齐的 nx 对齐到印刷线）
TRUTH=next(x for x in ANN["items"] if "斯卡布罗" in x["name"])
def row_of(page,ny):
    return [(m["nx"],m["m"]) for m in TRUTH["data"]["M"]
            if m["page"]==page and abs(m["ny"]-ny)<0.02]
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8783),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c): return "OK   " if c else "FAIL "

async def click_row(pg, page, nx, ny):
    await pg.evaluate("""async(n)=>{if(!boxes[n])return;
        while(tasks.has(n))await tasks.get(n).promise.catch(()=>{});
        delete boxes[n].dataset.done;visible.add(n);await renderPage(n);}""",page)
    await pg.wait_for_function("(n)=>boxes[n]&&boxes[n].dataset.done",arg=page,timeout=60000)
    await pg.evaluate("(n)=>boxes[n].scrollIntoView({block:'center'})",page)
    await asyncio.sleep(0.3)
    bb=await (await pg.query_selector(f'.page[data-page="{page}"]')).bounding_box()
    await pg.mouse.click(bb["x"]+bb["width"]*nx, bb["y"]+bb["height"]*ny)

async def main():
    errs=[]
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={"width":1600,"height":1000})
        pg.on("pageerror",lambda e:errs.append(str(e)))
        await pg.goto("http://127.0.0.1:8783/player.html?direct=1")
        await pg.evaluate("localStorage.clear()"); await pg.reload()
        await pg.set_input_files("#fPdf",PDF)
        await pg.wait_for_function("()=>pdf&&boxes.length>1",timeout=60000)
        await pg.evaluate("io&&io.disconnect();zoom=1.6;$('zoom').value=1.6;setPageSizes()")
        # 「半自动」不再是独立模式，改成「标小节」里的一个开关（☰ 菜单 → 小节 → 整行补齐）
        modes=await pg.evaluate("[...$('mode').options].map(o=>o.value)")
        print(ok("autobar" not in modes), f"模式下拉里不再有独立的半自动项: {modes}")
        await pg.select_option("#mode","mark")
        print(ok(not await pg.evaluate("$('chkAutoRow').checked")), "「整行补齐」默认关闭")
        # 关着的时候：点一下只加一个（这就是原来的「标小节」）
        gt9=row_of(2,0.267)
        await click_row(pg,2,gt9[0][0],0.33)
        await pg.wait_for_timeout(500)
        n1=await pg.evaluate("M.length")
        print(ok(n1==1), f"关掉「整行补齐」时点一下只加 1 个（加了 {n1} 个）")
        await pg.evaluate("M=[];syncNext();layout();save()")
        await pg.evaluate("$('menu').style.display='block';$('chkAutoRow').checked=true;$('menu').style.display='none'")
        await pg.wait_for_timeout(200)

        # 行 2（真实 m=13..18，连续无多小节休止、无标注污染）：点头首 → 补齐整行
        gt2=row_of(2,0.267)
        await click_row(pg,2,gt2[0][0],0.33)         # 点在第一小节的印刷位置（谱表上）
        await pg.wait_for_timeout(600)
        M=await pg.evaluate("M.map(x=>({m:x.m,nx:+x.nx.toFixed(3),ny:+x.ny.toFixed(3)}))")
        print(ok(len(M)==len(gt2)), f"行2 补齐 {len(M)} 个（真实 {len(gt2)} 个）")
        print(ok(all(any(abs(m["nx"]-g[0])<0.006 for g in gt2) for m in M)),
              f"  检出的 nx 都对齐到印刷线: {[m['nx'] for m in M]}")
        print(ok([m["m"] for m in M]==list(range(1,len(gt2)+1))), f"  编号连续: {[m['m'] for m in M]}")
        print(ok("已补齐整行" in await pg.inner_text("#msg")), "提示: "+await pg.inner_text("#msg"))
        print(ok(await pg.evaluate("nextM")==len(gt2)+1), f"  nextM 推进到 {await pg.evaluate('nextM')}（下一行接着编）")

        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
