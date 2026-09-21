# 手机/平板打开就收起工具栏（只留排练胶囊）；曲名是播放列表的入口
import asyncio, http.server, socketserver, threading, functools
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
PDF=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8803),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c): return "OK   " if c else "FAIL "

# 量「谱面有没有被胶囊盖住」：光看页高不够——页高对了、滚动位置不在原点照样会被盖。
# 判据是**页盒的屏幕位置**：底边要落在胶囊顶边之上
GEO="""()=>{const b=boxes[1].getBoundingClientRect(),r=$('reh').getBoundingClientRect();
  return {pw:Math.round(b.width),ph:Math.round(b.height),
          ptop:Math.round(b.top),pbot:Math.round(b.bottom),
          rehTop:Math.round(r.top),rehH:Math.round(innerHeight-r.top),
          hidden:document.body.classList.contains('hidebar'),
          barShown:getComputedStyle($('bar')).display!=='none',
          rehShown:getComputedStyle($('reh')).display!=='none'};}"""

async def open_pdf(b,w,h,touch,errs):
    pg=await b.new_page(viewport={"width":w,"height":h},has_touch=touch,device_scale_factor=2 if touch else 1)
    pg.on("pageerror",lambda e,tag=w:errs.append(f"[{tag}] "+str(e)))
    await pg.goto("http://127.0.0.1:8803/player.html?direct=1")
    await pg.evaluate("localStorage.clear()"); await pg.reload()
    await pg.set_input_files("#fPdf",PDF)
    await pg.wait_for_function("()=>cvs[1]&&document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=40000)
    await pg.wait_for_timeout(600)        # 首次适配 + 可能的补算都落定
    return pg

async def main():
    errs=[]
    async with async_playwright() as p:
        b=await p.chromium.launch()

        # --- 手机：打开就收起，只留胶囊 ---
        pgm=await open_pdf(b,390,844,True,errs)
        g=await pgm.evaluate(GEO)
        print(ok(g["hidden"] and not g["barShown"] and g["rehShown"]),
              f"[390 触摸] 打开即收起工具栏、胶囊顶上来: hidebar={g['hidden']} 工具栏={g['barShown']} 胶囊={g['rehShown']}")
        print(ok(g["pbot"]<=g["rehTop"]),
              f"[390 触摸] 谱面底边让开胶囊: 页底 {g['pbot']}px ≤ 胶囊顶 {g['rehTop']}px（胶囊占 {g['rehH']}px）")
        print(ok(abs(g["pw"]-(390-24))<=3),
              f"[390 触摸] 页宽仍是屏幕宽-24: {g['pw']}px（收起工具栏没把宽度换掉）")

        # 曲名是个按钮：有曲目时光标 + 44px 命中
        btn=await pgm.evaluate("""()=>{track={name:'测试曲目名称很长很长很长很长很长的',audios:[]};syncReh();
            const el=$('rehLbl'),r=el.getBoundingClientRect();
            return {tag:el.tagName,w:Math.round(r.width),h:Math.round(r.height),
                    caret:getComputedStyle($('rehLblCaret')).display,title:el.title,
                    txt:$('rehLblTxt').textContent}}""")
        print(ok(btn["tag"]=="BUTTON" and btn["h"]>=44 and btn["caret"]!="none" and "播放列表" in btn["title"]),
              f"[390 触摸] 曲名是 {btn['tag']}、命中 {btn['w']}×{btn['h']}px、有 ▾、title 提示去播放列表")
        # 长曲名不许把胶囊撑破（省略号要生效）
        narrow=await pgm.evaluate("""()=>{const r=$('rehLbl').getBoundingClientRect();
            return {l:Math.round(r.left),r:Math.round(r.right),vw:innerWidth}}""")
        print(ok(narrow["r"]<=narrow["vw"]+1),
              f"[390 触摸] 长曲名不撑破胶囊: 曲名按钮 [{narrow['l']},{narrow['r']}] ⊆ 视口 0–{narrow['vw']}")

        # 点曲名 → 列表从胶囊**上方**顶出
        await pgm.evaluate("$('rehLbl').click()"); await pgm.wait_for_timeout(400)
        pop=await pgm.evaluate("""()=>{const p=$('plPop'),r=p.getBoundingClientRect(),q=$('reh').getBoundingClientRect();
            return {shown:getComputedStyle(p).display,top:Math.round(r.top),bottom:Math.round(r.bottom),
                    rehTop:Math.round(q.top)}}""")
        print(ok(pop["shown"]=="block" and pop["bottom"]<=pop["rehTop"]+1 and pop["top"]>=0),
              f"[390 触摸] 点曲名，列表从胶囊上方顶出且不出屏: 弹层 [{pop['top']},{pop['bottom']}] ⊆ 0–{pop['rehTop']}（胶囊顶）")
        # 再点一下收起（同一个入口开合）
        await pgm.evaluate("$('rehLbl').click()"); await pgm.wait_for_timeout(300)
        print(ok(await pgm.evaluate("$('plPop').style.display")=="none"), "[390 触摸] 再点一下曲名收起列表")
        # 点外面关掉
        await pgm.evaluate("$('rehLbl').click()"); await pgm.wait_for_timeout(300)
        await pgm.evaluate("wrap.click()"); await pgm.wait_for_timeout(300)
        print(ok(await pgm.evaluate("$('plPop').style.display")=="none"), "[390 触摸] 点谱面关掉列表")
        # 列表开着时点胶囊上的按钮：列表该关，但**这一下要生效**
        # （关列表那个监听在 capture 阶段，不把 #reh 放行就会把点击整个吞掉）
        # 用「展开工具栏」而不是播放键：播放键在没音频时会走 aud.src —— 而 aud.src='' 取到的
        # 其实是**文档 URL**（非空），于是去播 HTML 页面、冒出 "no supported sources"。
        # 那是另一个既有问题，别混进这条测试里
        await pgm.evaluate("$('rehLbl').click();$('rehUp').addEventListener('click',()=>window.__hit=1)")
        await pgm.wait_for_timeout(300)
        await pgm.click("#rehUp"); await pgm.wait_for_timeout(400)
        st=await pgm.evaluate("()=>({hit:window.__hit,pop:$('plPop').style.display,bar:$('bar').offsetHeight>0})")
        print(ok(st["hit"]==1 and st["pop"]=="none" and st["bar"]),
              f"[390 触摸] 列表开着时点胶囊的「展开工具栏」：列表关掉且这一下真的生效（工具栏已展开）")
        await pgm.close()

        # --- 平板竖屏：这一档页高才是约束（胶囊让出的高度真的起作用）---
        pgt=await open_pdf(b,834,1194,True,errs)
        gt=await pgt.evaluate(GEO)
        print(ok(gt["hidden"] and gt["pbot"]<=gt["rehTop"]),
              f"[834×1194 平板竖屏] 收起 + 整页在胶囊之上: 页底 {gt['pbot']}px ≤ 胶囊顶 {gt['rehTop']}px")
        # 收起后可用高比展开时更大（胶囊 1 行 < 工具栏），所以谱面应该更大
        before=(gt["pw"],gt["ph"])
        await pgt.evaluate("setBarHidden(false)"); await pgt.wait_for_timeout(800)
        gs=await pgt.evaluate(GEO)
        print(ok(gt["ph"]>gs["ph"]),
              f"[834×1194] 收起时谱面比展开时大: 页高 {gt['ph']}px（收起）> {gs['ph']}px（展开）")
        await pgt.close()

        # --- 桌面（无触摸）：工具栏该留着 ---
        pgd=await open_pdf(b,1440,900,False,errs)
        gd=await pgd.evaluate(GEO)
        print(ok(not gd["hidden"] and gd["barShown"] and not gd["rehShown"]),
              f"[1440×900 无触摸] 不收起工具栏、胶囊不出现: hidebar={gd['hidden']} 工具栏={gd['barShown']} 胶囊={gd['rehShown']}")
        await pgd.close()

        # --- 列表行真的渲染出来（direct=1 下 idb 是 null，renderPL 直接 return，测不出东西）---
        pgl=await b.new_page(viewport={"width":390,"height":844},has_touch=True,device_scale_factor=2)
        pgl.on("pageerror",lambda e:errs.append("[lib] "+str(e)))
        await pgl.goto("http://127.0.0.1:8803/player.html")
        await pgl.wait_for_function("()=>idb!==null",timeout=15000)
        await pgl.evaluate("""async()=>{await idbPut(idb,'projects',{id:'t1',name:'甲曲',aka:[],pdf:null,
            pdfHistory:[],audios:[],lastAudio:null,createdAt:Date.now(),updatedAt:Date.now()});
          await idbPut(idb,'projects',{id:'t2',name:'乙曲',aka:[],pdf:null,
            pdfHistory:[],audios:[],lastAudio:null,createdAt:Date.now(),updatedAt:Date.now()});
          PL={items:[{pid:'t1',audioHash:null},{pid:'t2',audioHash:null}],loop:true,pauseEach:false};
          track={name:'甲曲',audios:[]};syncReh();drawPL()}""")
        await pgl.evaluate("$('rehLbl').click()"); await pgl.wait_for_timeout(600)
        rows=await pgl.evaluate("document.querySelectorAll('#plPopList .plRow').length")
        names=await pgl.evaluate("[...document.querySelectorAll('#plPopList .nm')].map(x=>x.textContent).join('/')")
        print(ok(rows==2), f"[390 触摸] 曲名开的列表真的渲染出行: {rows} 行（{names}）")
        await pgl.close()

        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
