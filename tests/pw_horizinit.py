import asyncio, http.server, socketserver, threading, functools
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
PDF=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8777),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c): return "OK   " if c else "FAIL "

# 量当前方向：状态（chkHoriz + horiz 类）、前两页的相对位置，以及方向按钮
# —— 它该**只在菜单里**一处，文案显示当前方向。量之前菜单是开着的（见 probe），
# 否则 display:none 的元素 getBoundingClientRect 全是 0。
GEO="""()=>{
  const ps=[...document.querySelectorAll('.page')].map(p=>p.getBoundingClientRect());
  const b=document.getElementById('bHoriz'), r=b.getBoundingClientRect();
  return {on:$('chkHoriz').checked, cls:pagesEl.classList.contains('horiz'),
          txt:b.textContent, shown:getComputedStyle(b).display!=='none',
          inMenu:!!b.closest('#menu'), inBar:!!b.closest('#bar'),
          l:Math.round(r.left), r:Math.round(r.right), vw:innerWidth,
          w:Math.round(r.width), h:Math.round(r.height),
          dx:ps.length>1?Math.round(ps[1].left-ps[0].left):0,
          dy:ps.length>1?Math.round(ps[1].top-ps[0].top):0};
}"""

# 监听必须在 goto 之前挂上：boot() 里那几下时序不对的话，错误就发生在加载期，事后挂就漏了
async def probe(b,w,h,touch,errs):
    pg=await b.new_page(viewport={"width":w,"height":h},has_touch=touch)
    pg.on("pageerror",lambda e:errs.append(str(e)))
    await pg.goto("http://127.0.0.1:8777/player.html?direct=1")
    await pg.evaluate("localStorage.clear()"); await pg.reload()
    # 手机/平板现在打开就收起工具栏（player.html 里 pointer:coarse 那段）。
    # 这里有一条断言量的是工具栏里「☰ 菜单」的位置——不展开的话 #bar 是 display:none，
    # 它的 rect 恒为 [0,0]，那条会**假绿**（0 当然落在视口里）
    await pg.evaluate("setBarHidden(false)")
    # 同一个「假绿」陷阱还多了一层：触屏开机同时进演奏态，编辑行整行 display:none，
    # 而下面那条「曲目库在场时 ☰ 菜单仍完整可见」量的正是编辑行里的 #bLib——
    # 不解锁的话它在隐藏行里，rect 恒为 [0,0]，又是 0 落在视口里
    await pg.evaluate("setPerf(false)")
    await pg.set_input_files("#fPdf",PDF)
    await pg.wait_for_function("()=>document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=40000)
    # 直接写 display 而不是点 #bMenu——菜单按钮事件绑在别处，这里只要它开着
    await pg.evaluate("$('menu').style.display='block'"); await asyncio.sleep(0.2)
    return pg

async def main():
    errs=[]
    async with async_playwright() as p:
        b=await p.chromium.launch()

        # --- 初始方向 = 窗口宽 >700 且 宽≥高。两档各站一次，700 跟版式那条 (max-width:700px) 同一个数 ---
        # 必须带上高度：单看宽度的话 iPad 竖屏（744–1024）跟桌面同一档，
        # "竖着拿"那一档就是靠第二个条件分出来的（见 player.html 里那段注释）
        for w,h,exp in [(700,800,False),(701,700,True),(1440,900,True),
                        (390,844,False),(834,1194,False),(1194,834,True)]:
            pg=await b.new_page(viewport={"width":w,"height":h})
            pg.on("pageerror",lambda e:errs.append(str(e)))
            await pg.goto("http://127.0.0.1:8777/player.html?direct=1")
            v=await pg.evaluate("()=>({on:$('chkHoriz').checked,cls:pagesEl.classList.contains('horiz')})")
            print(ok(v["on"]==exp and v["cls"]==exp),
                  f"[{w}×{h}] 初始就是{'横向铺开' if exp else '纵向堆叠'}（chkHoriz={v['on']}，horiz 类={v['cls']}）")
            await pg.close()

        # --- 手机竖屏 390（触摸）：窄了就该一页一行 ---
        pgm=await probe(b,390,844,True,errs)
        g=await pgm.evaluate(GEO)
        print(ok(not g["on"] and not g["cls"]),
              f"[390] 初始纵向堆叠: chkHoriz={g['on']}，有 horiz 类={g['cls']}")
        print(ok(abs(g["dx"])<2 and g["dy"]>0),
              f"[390] 第2页在第1页正下方 (x差 {abs(g['dx'])}px, y下移 {g['dy']}px)")
        # 方向按钮只该有一处，且在菜单里：工具栏第 1 行 390px 下只剩 2px 余量，塞不下第二个入口
        print(ok(g["inMenu"] and not g["inBar"]),
              f"[390] 方向按钮只在菜单里一处（inMenu={g['inMenu']}，inBar={g['inBar']}）")
        print(ok(g["shown"] and g["l"]>=0 and g["r"]<=g["vw"]+1),
              f"[390] 按钮在菜单里点得到、横向不出屏: [{g['l']},{g['r']}] ⊆ 0–{g['vw']}")
        print(ok(g["w"]>=44 and g["h"]>=44),
              f"[390 触摸] 按钮命中区 {g['w']}×{g['h']}px ≥44（手机上真点得准）")
        # 光"看得见"不够——手机上点一下得真的切得动（这正是"手机上改不了方向"那个窟窿）
        await pgm.click("#bHoriz"); await asyncio.sleep(0.3)
        g2=await pgm.evaluate(GEO)
        print(ok(g2["on"] and g2["cls"] and g2["txt"]=="横向铺开" and g2["dx"]>0),
              f"[390] 点菜单里的按钮切到横向、文案变 «{g2['txt']}»（第2页右移 {g2['dx']}px）")
        # 「☰ 菜单」是手机上通往一切设置的入口，方向按钮又住在里面——它被挤掉就什么都改不了。
        # 它和「演奏/编辑」锁包在 #sysBox 里，而 sysBox 在 .rowScroll **外面**：
        # 行内容（390px 下 ~800px）在 rowScroll 里横滑，sysBox 占着行尾的真实布局位置，
        # 不需要 sticky（sticky 会盖住滑过的控件偷点击，被 pw_touch_targets 抓到过）。
        # 要断的是「内容确实溢出得滑」和「不管滑不滑，bMenu 都在视口里」
        mb=await pgm.evaluate("""()=>{const scr=$('rowPlay').querySelector('.rowScroll');
            const rc=()=>{const m=$('bMenu').getBoundingClientRect();
                          return {l:Math.round(m.left),r:Math.round(m.right)}};
            scr.scrollLeft=0; const at0=rc();
            scr.scrollLeft=9999; const atEnd=rc();
            return {at0,atEnd,vw:innerWidth,sw:scr.scrollWidth,cw:scr.clientWidth}}""")
        print(ok(mb["sw"]>mb["cw"]),
              f"[390] 前提：演奏行内容 {mb['sw']}px 确实超出可视 {mb['cw']}px（横滑容器）")
        print(ok(mb["at0"]["l"]>=0 and mb["at0"]["r"]<=mb["vw"]+1),
              f"[390] 不滚动时「☰ 菜单」完整可见: [{mb['at0']['l']},{mb['at0']['r']}] ⊆ 0–{mb['vw']}")
        print(ok(mb["atEnd"]["l"]>=0 and mb["atEnd"]["r"]<=mb["vw"]+1),
              f"[390] 内容滚到最右它仍钉在行尾: [{mb['atEnd']['l']},{mb['atEnd']['r']}] ⊆ 0–{mb['vw']}")
        await pgm.close()

        # --- 平板竖屏 834（触摸）：宽过 700 但比自己高 → 纵向堆叠，且整页装得下 ---
        # 这一档是新增的：以前只看宽度，834 跟桌面同一档、竖着也左右铺开。
        # 光看 chkHoriz 不够——真正要保的是"竖着拿时一页一行，且不用横滑也能看全整页"
        pgt=await probe(b,834,1194,True,errs)
        g=await pgt.evaluate(GEO)
        print(ok(not g["on"] and abs(g["dx"])<2 and g["dy"]>0),
              f"[834×1194 平板竖屏] 纵向堆叠: 第2页在第1页正下方 (x差 {abs(g['dx'])}px, y下移 {g['dy']}px)")
        fit=await pgt.evaluate("""()=>{const b=boxes[1].getBoundingClientRect();
            return {w:Math.round(b.width),h:Math.round(b.height),
                    vw:wrap.clientWidth,vh:wrap.clientHeight,bh:barHpx()}}""")
        print(ok(fit["w"]<=fit["vw"]-24+1 and fit["h"]<=fit["vh"]-fit["bh"]-24+1),
              f"[834×1194 平板竖屏] 进谱面整页装进视口: 页 {fit['w']}×{fit['h']}px ⊆ 可用 "
              f"{fit['vw']-24}×{fit['vh']-fit['bh']-24}px（工具栏 {fit['bh']}px 已扣除）")
        await pgt.close()

        # --- 桌面宽窗：默认横向铺开，按钮在菜单里显示当前方向、点一下翻过去 ---
        pgd=await probe(b,1440,900,False,errs)
        g=await pgd.evaluate(GEO)
        print(ok(g["on"] and g["cls"] and g["dx"]>0 and abs(g["dy"])<2),
              f"[1440] 初始横向铺开: 第2页在右侧 (x移 {g['dx']}px, y差 {abs(g['dy'])}px)")
        print(ok(g["shown"] and g["inMenu"] and not g["inBar"] and g["txt"]=="横向铺开"),
              f"[1440] 菜单里的方向按钮显示当前方向 «{g['txt']}»，工具栏上没有")
        await pgd.click("#bHoriz"); await asyncio.sleep(0.3)
        g2=await pgd.evaluate(GEO)
        print(ok(not g2["on"] and not g2["cls"] and g2["txt"]=="纵向堆叠" and abs(g2["dx"])<2 and g2["dy"]>0),
              f"点一下翻到纵向、文案变 «{g2['txt']}»（第2页下移 {g2['dy']}px）")
        await pgd.click("#bHoriz"); await asyncio.sleep(0.3)
        g3=await pgd.evaluate(GEO)
        print(ok(g3["on"] and g3["cls"] and g3["txt"]=="横向铺开" and g3["dx"]>0),
              f"再点一下翻回横向、文案变 «{g3['txt']}»（第2页右移 {g3['dx']}px）")
        # 按钮只是 hidden #chkHoriz 的壳：程序化改状态，文案也得跟着走（bFitW 那条路靠它）
        await pgd.evaluate("$('chkHoriz').checked=false;$('chkHoriz').onchange()"); await asyncio.sleep(0.2)
        print(ok(await pgd.evaluate("$('bHoriz').textContent")=="纵向堆叠"),
              "直接改 chkHoriz 状态，按钮文案同步（壳不自己存状态）")
        await pgd.close()

        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
