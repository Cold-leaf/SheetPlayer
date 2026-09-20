import asyncio, http.server, socketserver, threading, functools
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
PDF=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8777),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c): return "OK   " if c else "FAIL "

# 量当前方向：状态（chkHoriz + horiz 类）、前两页的相对位置、工具栏按钮的文字与显隐
GEO="""()=>{
  const ps=[...document.querySelectorAll('.page')].map(p=>p.getBoundingClientRect());
  const b=document.getElementById('bHoriz');
  return {on:$('chkHoriz').checked, cls:pagesEl.classList.contains('horiz'),
          exists:!!b,
          txt:b?b.textContent:'', shown:b?getComputedStyle(b).display!=='none':false,
          w:b?Math.round(b.getBoundingClientRect().width):0,
          h:b?Math.round(b.getBoundingClientRect().height):0,
          dx:ps.length>1?Math.round(ps[1].left-ps[0].left):0,
          dy:ps.length>1?Math.round(ps[1].top-ps[0].top):0};
}"""

# 监听必须在 goto 之前挂上：boot() 里那几下时序不对的话，错误就发生在加载期，事后挂就漏了
async def probe(b,w,h,touch,errs):
    pg=await b.new_page(viewport={"width":w,"height":h},has_touch=touch)
    pg.on("pageerror",lambda e:errs.append(str(e)))
    await pg.goto("http://127.0.0.1:8777/player.html?direct=1")
    await pg.evaluate("localStorage.clear()"); await pg.reload()
    await pg.set_input_files("#fPdf",PDF)
    await pg.wait_for_function("()=>document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=40000)
    return pg

async def main():
    errs=[]
    async with async_playwright() as p:
        b=await p.chromium.launch()

        # --- 阈值两侧各站一次：初始方向只看当前窗口宽，跟版式那条 (max-width:700px) 同一个数 ---
        for w,exp in [(700,False),(701,True),(1440,True),(390,False)]:
            pg=await b.new_page(viewport={"width":w,"height":800})
            pg.on("pageerror",lambda e:errs.append(str(e)))
            await pg.goto("http://127.0.0.1:8777/player.html?direct=1")
            v=await pg.evaluate("()=>({on:$('chkHoriz').checked,cls:pagesEl.classList.contains('horiz')})")
            print(ok(v["on"]==exp and v["cls"]==exp),
                  f"[{w}px] 初始就是{'横向铺开' if exp else '纵向堆叠'}（chkHoriz={v['on']}，horiz 类={v['cls']}）")
            await pg.close()

        # --- 手机竖屏 390（触摸）：窄了就该一页一行 ---
        pgm=await probe(b,390,844,True,errs)
        g=await pgm.evaluate(GEO)
        print(ok(not g["on"] and not g["cls"]),
              f"[390] 初始纵向堆叠: chkHoriz={g['on']}，有 horiz 类={g['cls']}")
        print(ok(abs(g["dx"])<2 and g["dy"]>0),
              f"[390] 第2页在第1页正下方 (x差 {abs(g['dx'])}px, y下移 {g['dy']}px)")
        # 这次取舍的护栏：为了给「☰ 菜单」腾地方才把方向按钮藏掉，菜单就绝不能反被挤掉。
        # direct=1 那条路 boot() 会把「曲目库」藏掉，量出来的余量是假的——这里补回来，
        # 复现真实路径下第 1 行的内容，否则这条护栏在按钮可见时也能过
        await pgm.evaluate("$('bLib').style.display=''"); await asyncio.sleep(0.2)
        print(ok(g["exists"] and not g["shown"]),
              f"[390] 方向按钮在 DOM 里（可被脚本/测试驱动）但不显示: exists={g['exists']} shown={g['shown']}")
        mb=await pgm.evaluate("""()=>{const m=$('bMenu').getBoundingClientRect();
            return {l:Math.round(m.left),r:Math.round(m.right),vw:innerWidth,
                    lib:getComputedStyle($('bLib')).display!=='none'}}""")
        print(ok(mb["lib"] and mb["l"]>=0 and mb["r"]<=mb["vw"]+1),
              f"[390] 「曲目库」在场时「☰ 菜单」仍完整可见: [{mb['l']},{mb['r']}] ⊆ 视口 0–{mb['vw']}"
              f"（工具栏右侧给固定定位的「▲」留了 44px，量的是真实余量）")
        await pgm.close()

        # --- 桌面/横屏宽窗：默认横向铺开，方向按钮在工具栏上 ---
        pgd=await probe(b,1440,900,False,errs)
        g=await pgd.evaluate(GEO)
        print(ok(g["on"] and g["cls"] and g["dx"]>0 and abs(g["dy"])<2),
              f"[1440] 初始横向铺开: 第2页在右侧 (x移 {g['dx']}px, y差 {abs(g['dy'])}px)")
        print(ok(g["exists"] and g["shown"] and g["txt"]=="横向"),
              f"[1440] 工具栏方向按钮可见、文案显示当前方向 «{g['txt']}»")
        # 点它 = 翻过去，文案跟着变（按钮只是 chkHoriz 的壳）
        await pgd.click("#bHoriz"); await asyncio.sleep(0.3)
        g2=await pgd.evaluate(GEO)
        print(ok(not g2["on"] and not g2["cls"] and g2["txt"]=="纵向" and abs(g2["dx"])<2 and g2["dy"]>0),
              f"点一下翻到纵向、文案变 «{g2['txt']}»（第2页下移 {g2['dy']}px）")
        await pgd.click("#bHoriz"); await asyncio.sleep(0.3)
        g3=await pgd.evaluate(GEO)
        print(ok(g3["on"] and g3["cls"] and g3["txt"]=="横向" and g3["dx"]>0),
              f"再点一下翻回横向、文案变 «{g3['txt']}»（第2页右移 {g3['dx']}px）")
        # 菜单里那个勾选框跟按钮是同一个状态：按钮翻完，勾选框跟着走
        await pgd.evaluate("$('menu').style.display='block'"); await asyncio.sleep(0.2)
        chk=await pgd.evaluate("$('chkHoriz').checked")
        lbl=(await pgd.evaluate("document.querySelector('label:has(#chkHoriz)').innerText")).strip()
        print(ok(chk and "纵向" in lbl), f"菜单勾选框与按钮同一状态（勾着={chk}），文案能读出纵向: «{lbl}»")
        await pgd.evaluate("$('menu').style.display='none'")
        await pgd.close()

        # --- 触摸宽屏（iPad 744 起）：按钮不藏，且够 44px 手指点 ---
        pgt=await probe(b,834,1194,True,errs)
        g=await pgt.evaluate(GEO)
        print(ok(g["shown"] and g["w"]>=44 and g["h"]>=44),
              f"[834 触摸] 方向按钮可见且 {g['w']}×{g['h']}px ≥44（窄屏才藏，iPad 放得下）")
        await pgt.close()

        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
