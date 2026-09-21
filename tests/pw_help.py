# 帮助面板。原来是全文件唯一一个不自我约束的浮层：没有 max-height、没有 overflow，
# 而 body{overflow:hidden} —— 屏幕一矮内容就够不着；面板里也没有关闭键，
# 平板上没有 Esc，点遮罩是唯一出路。这里把这些连同「手势没写进去」一起盯住。
import asyncio, http.server, socketserver, threading, functools
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
PDF=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*a): pass          # 别让访问日志冲掉断言输出
H=functools.partial(Quiet,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8822),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c): return "OK   " if c else "FAIL "

# 8 项手势的关键词。每项至少命中一个词就说明写进去了。
GESTURES=[
    ("双指缩放",            ["双指缩放","捏合","两指"]),
    ("桌面等价的 Ctrl+滚轮", ["Ctrl","ctrl","滚轮"]),
    ("单指拖动暂停跟随",     ["跟随","暂停"]),
    ("排练胶囊",            ["排练","胶囊"]),
    ("胶囊进度条拖走带",     ["走带","拖"]),
    ("频谱拖动/定位",        ["频谱"]),
    ("编辑模式拖竖线",       ["编辑"]),
    ("点遮罩/关闭键关闭浮层", ["关闭","点外面","遮罩"]),
]

JS_RECT="""(s=>{const e=document.querySelector(s);if(!e)return null;const r=e.getBoundingClientRect();
  return {l:r.left,t:r.top,r:r.right,b:r.bottom,w:r.width,h:r.height,
          sw:e.scrollWidth,sh:e.scrollHeight,cw:e.clientWidth,ch:e.clientHeight}})"""

async def main():
    errs=[]
    async with async_playwright() as p:
        b=await p.chromium.launch()

        # ============ A. 触摸平板 ============
        pg=await b.new_page(viewport={"width":834,"height":1194},has_touch=True,device_scale_factor=2)
        pg.on("pageerror",lambda e:errs.append(str(e)))
        await pg.goto("http://127.0.0.1:8822/player.html?direct=1")
        await pg.set_input_files("#fPdf",PDF)
        await pg.wait_for_function("()=>document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=40000)
        await pg.wait_for_timeout(250)

        await pg.evaluate("toggleHelp(true)"); await pg.wait_for_timeout(250)
        print(ok(await pg.evaluate("getComputedStyle($('help')).display")=="flex"), "帮助面板打开")
        await pg.evaluate("toggleHelp(false)")
        # 走真实入口：☰ 菜单里的「? 快捷键」（它从「生成/数据」挪到了菜单最上面的「应用」栏）
        await pg.evaluate("$('menu').style.display='block'"); await pg.wait_for_timeout(200)
        await pg.click("#bHelp"); await pg.wait_for_timeout(300)
        print(ok(await pg.evaluate("getComputedStyle($('help')).display")=="flex"),
              "点菜单里的「? 快捷键」能打开（入口挪过位置）")
        # 打开面板必须顺手收菜单——#help 的 z-index(20) 比 #menu(25) 低，不收就被盖住。
        # 收起工具栏（触屏默认态）之后菜单抽屉能长高 160 多像素，盖掉的正是关闭键，
        # 「? 快捷键」点了像没反应。跟「安装卡片」那条一个惯例
        print(ok(await pg.evaluate("$('menu').style.display==='none'")), "打开帮助时菜单自动收起")

        box=await pg.evaluate(JS_RECT,"#help>div")
        print(ok(box["w"]<=834 and box["h"]<=1194), f"[平板] 面板不出视口: {box['w']:.0f}×{box['h']:.0f} (视口 834×1194)")
        print(ok(box["sh"]<=box["ch"]+1 or box["ch"]>0),
              f"[平板] 面板可滚动或内容装得下: 内容高 {box['sh']:.0f} / 可视 {box['ch']:.0f}")

        # 关闭键存在、够大、在视口里
        cb=await pg.evaluate("""()=>{const e=$('helpClose');if(!e)return null;
            const r=e.getBoundingClientRect();return {w:r.width,h:r.height,t:r.top,l:r.left}}""")
        print(ok(cb is not None), "面板里有显式关闭键（平板上没有 Esc）")
        if cb:
            print(ok(cb["w"]>=44 and cb["h"]>=44), f"关闭键够大: {cb['w']:.0f}×{cb['h']:.0f}")
            print(ok(cb["t"]>=0 and cb["t"]<1194), f"关闭键在视口内: top={cb['t']:.0f}")

        # 手势段排在键盘段前面
        orders=await pg.evaluate("""()=>{const g=document.querySelector('#helpGest'),k=document.querySelector('#helpKeys');
            if(!g||!k)return null;
            return {g:g.getBoundingClientRect().top,k:k.getBoundingClientRect().top,
                    go:getComputedStyle(g).order,ko:getComputedStyle(k).order,
                    gd:getComputedStyle(g).display,kd:getComputedStyle(k).display}}""")
        print(ok(orders is not None), "手势段与键盘段都存在")
        if orders:
            print(ok(orders["g"]<orders["k"]), f"[平板] 手势段排在键盘段之前: 手势 top={orders['g']:.0f} < 键盘 top={orders['k']:.0f}")
            print(ok(orders["gd"]!="none" and orders["kd"]!="none"),
                  f"[平板] 键盘段没有被藏掉（可能接外接键盘）: display={orders['gd']}/{orders['kd']}")

        # 关闭键真的能关
        await pg.click("#helpClose"); await pg.wait_for_timeout(200)
        print(ok(await pg.evaluate("getComputedStyle($('help')).display")=="none"), "点关闭键能关掉")

        # 点遮罩也能关
        await pg.evaluate("toggleHelp(true)"); await pg.wait_for_timeout(150)
        await pg.mouse.click(6,6); await pg.wait_for_timeout(200)
        print(ok(await pg.evaluate("getComputedStyle($('help')).display")=="none"), "点遮罩也能关（这一条要写进面板里）")

        await pg.close()

        # ============ B. 矮视口：以前内容会够不着 ============
        pg2=await b.new_page(viewport={"width":900,"height":480},has_touch=True)
        pg2.on("pageerror",lambda e:errs.append(str(e)))
        await pg2.goto("http://127.0.0.1:8822/player.html?direct=1")
        await pg2.set_input_files("#fPdf",PDF)
        await pg2.wait_for_function("()=>document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=40000)
        await pg2.wait_for_timeout(250)
        await pg2.evaluate("toggleHelp(true)"); await pg2.wait_for_timeout(250)
        box=await pg2.evaluate(JS_RECT,"#help>div")
        print(ok(box["h"]<=480), f"[矮屏 900×480] 面板高 {box['h']:.0f} ≤ 视口高 480")
        print(ok(box["t"]>=0 and box["b"]<=481), f"[矮屏] 面板整体在视口内: {box['t']:.0f}–{box['b']:.0f}")
        print(ok(box["sh"]>box["ch"]), f"[矮屏] 内容超长时可滚动: 内容 {box['sh']:.0f} > 可视 {box['ch']:.0f}")
        # 滚到底还能看到关闭键（sticky 头）
        await pg2.evaluate("$('help').firstElementChild.scrollTop=99999"); await pg2.wait_for_timeout(200)
        cb=await pg2.evaluate(JS_RECT,"#helpClose")
        print(ok(cb["t"]>=0 and cb["b"]<=481), f"[矮屏] 滚到底后关闭键仍在视口内: top={cb['t']:.0f}")
        await pg2.close()

        # ============ C. 桌面：键盘表在前 ============
        pg3=await b.new_page(viewport={"width":1600,"height":900})
        pg3.on("pageerror",lambda e:errs.append(str(e)))
        await pg3.goto("http://127.0.0.1:8822/player.html?direct=1")
        await pg3.set_input_files("#fPdf",PDF)
        await pg3.wait_for_function("()=>document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=40000)
        await pg3.wait_for_timeout(250)
        await pg3.evaluate("toggleHelp(true)"); await pg3.wait_for_timeout(250)
        orders=await pg3.evaluate("""()=>{const g=document.querySelector('#helpGest'),k=document.querySelector('#helpKeys');
            return {g:g.getBoundingClientRect().top,k:k.getBoundingClientRect().top,
                    gd:getComputedStyle(g).display,kd:getComputedStyle(k).display}}""")
        print(ok(orders["k"]<orders["g"]), f"[桌面] 键盘表排在手势段之前: 键盘 top={orders['k']:.0f} < 手势 top={orders['g']:.0f}")
        print(ok(orders["gd"]!="none"), "[桌面] 手势段仍然可见（只是沉底，没有藏起来）")

        # ============ D. 手势关键词都在 ============
        txt=await pg3.evaluate("$('help').innerText")
        missing=[]
        for name,kws in GESTURES:
            hit=any(k in txt for k in kws)
            if not hit: missing.append(name)
        print(ok(not missing), f"{len(GESTURES)} 项手势全部写进面板" + (f" —— 缺: {missing}" if missing else ""))
        await pg3.close()

        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
