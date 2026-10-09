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

        # 行 2：点头首 → 补齐整行。
        # ⚠ 这里的真值口径是**召回**，不是「数量相等」。annotations.json 里那一行的 6 根是
        # 「用户点过的那几根」，不是这一行印刷线的总数——按 2026-09 定下的规矩（用户只点一部分，
        # 「多补」不算误检，只有召回能看）。实测：同一行独立扫描（同阈值 175、≥90% 暗）能找到
        # **13** 条竖线，标注只有 6 条 → 检出 9 条比标注更接近真相，拿 6 当"完整真值"比是在罚它做对了。
        # 所以断言写成：标注的每一根都得在检出里；编号连续；nextM 接着往下走。多出来的只报数、不判红。
        gt2=row_of(2,0.267)
        await click_row(pg,2,gt2[0][0],0.33)         # 点在第一小节的印刷位置（谱表上）
        await pg.wait_for_timeout(600)
        M=await pg.evaluate("M.map(x=>({m:x.m,nx:+x.nx.toFixed(3)}))")
        miss=[g for g in gt2 if not any(abs(m["nx"]-g[0])<0.006 for m in M)]
        extra=[m["nx"] for m in M if not any(abs(m["nx"]-g[0])<0.006 for g in gt2)]
        print(ok(len(M)>0 and not miss),
              f"行2 补齐 {len(M)} 根（标注里这一行有 {len(gt2)} 根）：标注的 {len(gt2)-len(miss)}/{len(gt2)} 都在检出里"
              f"{'' if not miss else '，漏了 '+str([round(g[0],3) for g in miss])}")
        print(ok(all(M[i]["nx"]>M[i-1]["nx"] for i in range(1,len(M)))),
              f"  检出的 nx 按阅读顺序递增（多补的 {len(extra)} 根只报数不判红）: {[m['nx'] for m in M]}")
        print(ok([m["m"] for m in M]==list(range(1,len(M)+1))), f"  编号从 1 连续: {[m['m'] for m in M]}")
        print(ok("已补齐整行" in await pg.inner_text("#msg")), "提示: "+await pg.inner_text("#msg"))
        print(ok(await pg.evaluate("nextM")==len(M)+1), f"  nextM 推进到 {await pg.evaluate('nextM')}（= 这一行末尾+1，下一行接着编）")

        # ---------- 2026-09-29：补齐档下也能编辑竖线（判据只看落点，不读 chkAutoRow）----------
        # ①② 在改动前的代码上是红的（那时 canEditMk() 返回 false，补齐档把一切落点都当加点）；
        # ③ 两边都绿，是防回归的那条——它守的正是旧代码当初禁编辑的理由。
        # 关键：整行补齐这时一直开着（上面设过 $('chkAutoRow').checked=true，没有关回去）。
        # 挑一根左右都空着的竖线：.mk 命中盒有 44px 宽，挨得比 44px 近时后画的盖住先画的，
        # 而 markUnder 还有「不超过到最近邻一半」那条横向限制，选错线会判成「空白」而不是编辑。
        TGT,PGAP=await pg.evaluate("""()=>{const w=boxes[2].clientWidth,mk=M.filter(x=>x.page===2).sort((a,b)=>a.nx-b.nx);
            let best=mk[0],bd=-1;
            for(let i=0;i<mk.length;i++){const l=i?Math.abs(mk[i].nx-mk[i-1].nx)*w:1e9,
                r=i<mk.length-1?Math.abs(mk[i+1].nx-mk[i].nx)*w:1e9,d=Math.min(l,r);
                if(d>bd){bd=d;best=mk[i]}}
            return [best.m,bd]}""")
        print(ok(PGAP>60), f"选中的竖线左右最近邻 {PGAP:.0f}px（>44px 命中盒，点得准）: 小节 {TGT}")

        async def click_mk(m,drag=None):
            """点在某根竖线命中盒的中心（= 它自己的 nx）= 压在竖线上；drag 给了就先拖那么多 px"""
            el=await pg.query_selector(f'.mk[data-m="{m}"]')
            await el.scroll_into_view_if_needed(); await asyncio.sleep(0.25)
            bb=await el.bounding_box()
            mx,my=bb["x"]+bb["width"]/2, bb["y"]+bb["height"]/2
            if drag is None:
                await pg.mouse.click(mx,my)
            else:
                await pg.mouse.move(mx,my); await pg.mouse.down()
                await pg.mouse.move(mx+drag,my,steps=6); await pg.mouse.up()
            await pg.wait_for_timeout(450)

        # ① 点已有竖线 = 编辑它（开面板），不再原样 push 一个重复标记
        await pg.evaluate("$('panel').style.display='none';curM=null")
        n0=await pg.evaluate("M.length")
        await click_mk(TGT)
        n1=await pg.evaluate("M.length")
        pd=await pg.evaluate("$('panel').style.display")
        print(ok(n1==n0 and pd=="block"),
              f"补齐档下点已有竖线 = 编辑它：不重复加点（M {n0}→{n1}）且开面板（display={pd}）")
        await pg.evaluate("$('panel').style.display='none';curM=null")

        # ② 拖中段真的挪得动（pointerdown 那条路也得认编辑，不只是 onclick）
        #    松手会 applySnaps 吸印刷线，所以只断言「确实变了」而不是变成某个具体值
        m0=await pg.evaluate("(m)=>M.find(x=>x.m===m).nx",TGT)
        await click_mk(TGT,drag=90)
        m1=await pg.evaluate("(m)=>M.find(x=>x.m===m).nx",TGT)
        print(ok(abs(m1-m0)>0.01), f"补齐档下鼠标拖中段挪得动：小节 {TGT} nx {m0:.3f} → {m1:.3f}")

        # ③ 点空白处仍然补（重跑整行补齐这条路没被堵死）——旧代码要保的就是这条
        await pg.evaluate("M=[];syncNext();layout();save()")
        await click_row(pg,2,0.06,0.33)               # 行首空白（第一根印刷线在 0.15）
        await pg.wait_for_timeout(700)
        n3=await pg.evaluate("M.length")
        print(ok(n3>0), f"补齐档下点空白处仍然补：M.length={n3}（「{await pg.inner_text('#msg')}」）")

        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
