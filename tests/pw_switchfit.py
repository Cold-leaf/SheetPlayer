# 切曲目之后谱面该是什么样：**按新谱子自己的适配值铺，并且水平居中**。
#
# 两条都踩过：
# 1) 「打开的谱面越来越小、都是贴着左边」。zoom 是绝对数，是「上一张纸的尺寸 × 可用区」
#    算出来的：手机上 595×842 的线谱 fit≈0.61、2180×3090 的影印件 fit≈0.17。上一份谱子
#    捏过之后（autofit=false），这份的 zoom 被原样搬到下一份上——影印件上捏到 0.5，
#    切到线谱就是 366→300px 宽、贴在左边（右侧空 90px）的纸；反向是 2000px 宽的巨幅。
#    所以「换谱子＝重新整页适配」，手动缩放的粘性只留给同一份谱子的窗口变化。
# 2) 页比视口窄时（高度决定缩放 / 影印件页宽参差 / 手机上那 24px 余量）谱面贴左：
#    #pages 是 width:max-content 的盒，盒在 wrap 里左对齐、scrollHome 又把 scrollLeft
#    落在 paddingLeft 上＝盒左边贴视口左边。补 min-width:100% 后 .page 的 margin:auto
#    才有余量把页居中。
#
# 断言全部用「相对量」而不是写死像素：fitZoom 是页尺寸与可用区的函数，
# 写死 366/773 这种数会像 1.3 时代那批断言一样，改一次缩放就全红。
import asyncio, http.server, socketserver, threading, functools
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
D=ROOT+"/线谱合集/"
SK="SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"        # 596x842  线谱
MG="MG_牧歌[线][SATB+ST+NA].pdf"                  # 596x842
YQ="YQ_忆秦娥_娄山关[线][SATB+NA+Pn].pdf"          # 2180x3090 影印件
TRACKS=[("斯卡布罗",SK),("牧歌",MG),("忆秦娥",YQ)]
class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*a): pass
H=functools.partial(Quiet,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8844),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c): return "OK   " if c else "FAIL "

# 几何一次量全：页盒、视口、可用区、以及**页在视口里的左右余量**（居中与否看这两个数）
GEO="""()=>{const b=boxes[1].getBoundingClientRect(),w=wrap.getBoundingClientRect();
  return {zoom:+zoom.toFixed(5),fit:+(fitZoom()||0).toFixed(5),autofit:autofit,
    pw:Math.round(b.width),ph:Math.round(b.height),vw:wrap.clientWidth,
    left:Math.round(b.left-w.left),right:Math.round(b.right-w.left),
    aw:wrap.clientWidth-24,ah:wrap.clientHeight-barHpx()-rehHpx()-24};}"""

# 居中判据：页左边到视口左边的距离 == 视口右边到页右边的距离，两边差 ≤2px。
# （#pages 的 padding 左右对等，居中后必然对称；贴左时右边那个数会差出几十上百像素）
def centered(g): return abs(g["left"]-(g["vw"]-g["right"]))<=2

async def main():
    errs=[]
    async with async_playwright() as p:
        b=await p.chromium.launch()
        async def session(w,h,label):
            pg=await b.new_page(viewport={"width":w,"height":h},has_touch=True,device_scale_factor=2)
            pg.on("pageerror",lambda e:errs.append(label+": "+str(e)))
            await pg.goto("http://127.0.0.1:8844/player.html")
            await pg.wait_for_function("()=>idb!==null&&$('lib').style.display==='flex'",timeout=15000)
            async def newproj(nm,f):
                await pg.click("#libNew")
                await pg.wait_for_selector("#dlg",state="visible")
                await pg.fill("#dlgInp",nm); await pg.click("#dlgOk")
                await pg.wait_for_function("()=>$('dlg').style.display==='none'",timeout=8000)
                card=pg.locator(".libCard",has_text=nm).first
                async with pg.expect_file_chooser() as fc:
                    await card.locator("button.open").click()
                await (await fc.value).set_files(D+f)
                await pg.wait_for_function("()=>$('lib').style.display==='none'",timeout=40000)
                await pg.wait_for_function("()=>document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=40000)
                await pg.evaluate("$('bLib').onclick()")
                await pg.wait_for_function("()=>$('lib').style.display==='flex'",timeout=10000)
                await pg.wait_for_timeout(250)
            async def open(nm):
                await pg.click(f".libCard:has-text('{nm}') button.open")
                await pg.wait_for_function("()=>$('lib').style.display==='none'",timeout=40000)
                await pg.wait_for_function("()=>document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=40000)
                await pg.wait_for_timeout(600)          # 让 250ms 的 scheduleFit 防抖跑完
                return await pg.evaluate(GEO)
            print(f"===== {label} {w}x{h} =====")
            for nm,f in TRACKS: await newproj(nm,f)

            # 1) 连开三份：每次都是**这份谱子自己的**适配值 + 居中
            for nm,_ in TRACKS:
                g=await open(nm)
                print(ok(abs(g["zoom"]-g["fit"])<1e-4 and centered(g)),
                      f"[{nm}] 按自己的适配值铺 zoom={g['zoom']}(fit={g['fit']}) 页={g['pw']}x{g['ph']}"
                      f" 左余量={g['left']}px 右余量={g['vw']-g['right']}px")
                await pg.evaluate("$('bLib').onclick()")
                await pg.wait_for_function("()=>$('lib').style.display==='flex'",timeout=10000)
                await pg.wait_for_timeout(200)

            # 2) 在影印件上捏合放大（autofit 交出控制权），再切线谱：
            #    不许把影印件的绝对 zoom 搬过来（那会出现 300px 宽、贴左的纸）
            g=await open("忆秦娥")
            big=await pg.evaluate("fitZoom()*3")
            await pg.evaluate(f"zoomAt({big},wrap.clientWidth/2,wrap.clientHeight/2)")
            await pg.wait_for_timeout(400)
            gz=await pg.evaluate(GEO)
            print(ok(gz["autofit"]==False and gz["zoom"]>gz["fit"]*1.5),
                  f"[忆秦娥] 捏合放大到适配的 3 倍: zoom={gz['zoom']}(fit={gz['fit']}) autofit={gz['autofit']}")
            await pg.evaluate("$('bLib').onclick()")
            await pg.wait_for_function("()=>$('lib').style.display==='flex'",timeout=10000)
            g=await open("斯卡布罗")
            print(ok(abs(g["zoom"]-g["fit"])<1e-4 and g["autofit"] and centered(g)),
                  f"[影印件→线谱] 换谱回到整页适配: zoom={g['zoom']}(fit={g['fit']}) 页={g['pw']}x{g['ph']}"
                  f" 左余量={g['left']}px 右余量={g['vw']-g['right']}px autofit={g['autofit']}"
                  f"（照搬旧 zoom 的话页宽只会是 {round(596*gz['zoom'])}px）")
            await pg.close()
        await session(390,844,"手机竖屏")
        await session(834,1194,"平板竖屏")     # 高度决定缩放：页比视口窄，原来是最明显的贴左
        print("page errors:",errs[:3]) if errs else None
        await b.close()
asyncio.run(main())
