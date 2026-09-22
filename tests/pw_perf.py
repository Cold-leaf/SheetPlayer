# 演奏 / 编辑 两态（body.perf）。
# 要保的是三件事：
#   1. 演奏态工具栏真的只剩一行，且编辑行/状态行是整行 display:none（不是逐个按钮藏）
#   2. 演奏态里点谱面不落点、工具被退回「播放」——锁上就不该还能改标注
#   3. 默认值按设备分（触屏演奏、桌面编辑），且刷新即回默认（不持久化）
# 顺带量一下两态各自的工具栏高度，作为「一行」这个说法有没有兑现的判据。
import asyncio, http.server, socketserver, threading, functools
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
PDF=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8823),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c): return "OK   " if c else "FAIL "

STATE="""()=>{
  const vis=id=>{const e=document.getElementById(id);return !!e&&getComputedStyle(e).display!=='none'};
  return {perf:document.body.classList.contains('perf'),
          hidebar:document.body.classList.contains('hidebar'),
          btn:document.getElementById('bPerf').textContent,
          play:vis('rowPlay'),edit:vis('rowEdit'),state:vis('rowState'),
          barH:barHpx(),
          rows:[...document.querySelectorAll('#bar .row')].filter(r=>getComputedStyle(r).display!=='none').length,
          mode:document.getElementById('mode').value};
}"""

async def open_score(pg,url):
    await pg.goto(url)
    await pg.evaluate("localStorage.clear()")
    await pg.set_input_files("#fPdf",PDF)
    await pg.wait_for_function("()=>document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=40000)
    await pg.wait_for_timeout(300)

async def main():
    errs=[]
    async with async_playwright() as p:
        b=await p.chromium.launch()

        # ================= 桌面 =================
        pg=await b.new_page(viewport={"width":1600,"height":900})
        pg.on("pageerror",lambda e:errs.append("桌面: "+str(e)))
        await open_score(pg,"http://127.0.0.1:8823/player.html?direct=1")

        d=await pg.evaluate(STATE)
        print(ok(not d["perf"] and d["play"] and d["edit"] and d["state"]),
              f"[桌面] 默认是编辑态，三段都在: {d['perf']} / {d['rows']} 行")
        print(ok(d["btn"]=="编辑"), f"[桌面] 按钮文案显示当前状态: 「{d['btn']}」")
        editH=d["barH"]

        # --- 切演奏态：只剩一行 ---
        await pg.click("#bPerf"); await pg.wait_for_timeout(300)
        s=await pg.evaluate(STATE)
        print(ok(s["perf"] and s["play"] and not s["edit"] and not s["state"]),
              f"[桌面] 演奏态只剩演奏行，编辑行/状态行整行收掉: 可见 {s['rows']} 行")
        print(ok(s["btn"]=="演奏"), f"[桌面] 文案跟着变: 「{s['btn']}」")
        print(ok(s["barH"]<editH), f"[桌面] 工具栏变矮: 编辑态 {editH}px → 演奏态 {s['barH']}px")
        print(ok(s["mode"]=="play"), f"[桌面] 锁上顺手退回播放工具: mode={s['mode']}")

        # --- 演奏态里点谱面不落点 ---
        await pg.evaluate("M=[];E=[];refresh()")
        bb=await (await pg.query_selector('.page[data-page="1"]')).bounding_box()
        await pg.mouse.click(bb["x"]+bb["width"]*.35, bb["y"]+bb["height"]*.3)
        await pg.wait_for_timeout(250)
        print(ok(await pg.evaluate("M.length")==0),
              f"[桌面] 演奏态点谱面不落点: 标记数 {await pg.evaluate('M.length')}")

        # 撤销按钮已经被整行收掉了，但 Backspace 还够得到——那是同一个锁上的窟窿
        await pg.evaluate("E=[{m:1,t:1,src:'tap'}];refresh()")
        await pg.keyboard.press("Backspace"); await pg.wait_for_timeout(250)
        print(ok(await pg.evaluate("E.length")==1),
              f"[桌面] 演奏态 Backspace 不撤销: 时间点还剩 {await pg.evaluate('E.length')} 个")

        # --- 演奏态里菜单的编辑分区收起，但应用/统计/视图还在 ---
        await pg.click("#bMenu"); await pg.wait_for_timeout(250)
        # 可见性判据用 getClientRects().length，不能用 getComputedStyle().display：
        # 编辑分区是靠给**外层 .editOnly 包一层** display:none 收起来的，子孙自己的
        # computed display 仍然是 inline-block——拿 computed 判会把它们全判成「可见」，
        # 这条断言就假红了（第一版就是这么写的，报 bClr=True）
        men=await pg.evaluate("""()=>{
          const vis=e=>!!e&&e.getClientRects().length>0;
          return {kept:[...document.querySelectorAll('#menu .msec')]
                    .filter(m=>vis(m)&&!m.closest('.editOnly')).map(m=>m.textContent.trim()),
                  bClr:vis($('bClr')), bExp:vis($('bExp')), chkAlignY:vis($('chkAlignY')),
                  bHelp:vis($('bHelp')), chkNum:vis($('chkNum')), bHoriz:vis($('bHoriz'))}}""")
        print(ok(not men["bClr"] and not men["bExp"] and not men["chkAlignY"]),
              f"[桌面] 演奏态里编辑分区收起: 清空时间点={men['bClr']} 导出={men['bExp']} 竖线吸附={men['chkAlignY']}")
        print(ok(men["bHelp"] and men["chkNum"] and men["bHoriz"]),
              f"[桌面] 「应用 / 视图」这些非编辑分区照常: 帮助={men['bHelp']} 显示编号={men['chkNum']} 方向={men['bHoriz']}")
        print(ok("应用" in men["kept"] and "统计" in men["kept"] and "视图" in men["kept"]),
              f"[桌面] 演奏态保留的菜单分区: {men['kept']}")
        await pg.click("#bMenu"); await pg.wait_for_timeout(200)

        # --- 切回编辑态 ---
        await pg.click("#bPerf"); await pg.wait_for_timeout(300)
        e2=await pg.evaluate(STATE)
        print(ok(not e2["perf"] and e2["edit"] and e2["state"]),
              f"[桌面] 再点一下回到编辑态: {e2['perf']} / 可见 {e2['rows']} 行")

        # --- 不持久化：刷新回默认（桌面 = 编辑态）---
        # reload 之后不重设 #fPdf，所以就别等谱面渲染了——setPerf 是文件末尾同步跑的那几行，
        # 在 boot() 之前，页面一加载完状态就已经定下来了（等谱面只会等成超时）
        await pg.click("#bPerf"); await pg.wait_for_timeout(200)
        await pg.reload(); await pg.wait_for_timeout(1500)
        r=await pg.evaluate(STATE)
        print(ok(not r["perf"]), f"[桌面] 刷新回默认、不记忆上一态: perf={r['perf']}")

        # --- 循环弹层 ---
        await pg.click("#bLoopMore"); await pg.wait_for_timeout(200)
        lp=await pg.evaluate("""()=>{const e=$('loopPop');const g=e.getBoundingClientRect();
            const bar=$('bar').getBoundingClientRect();
            return {vis:getComputedStyle(e).display!=='none',gap:Math.round(g.top-bar.bottom),
                    right:Math.round(g.right),vw:innerWidth,
                    bA:!!e.querySelector('#bA'),txt:!!e.querySelector('#loopTxt')}}""")
        print(ok(lp["vis"] and lp["bA"] and lp["txt"]),
              f"[桌面] 「循环 ▾」打开弹层，起点/区间文字都在里面: {lp}")
        print(ok(lp["gap"]>=0 and lp["right"]<=lp["vw"]+1),
              f"[桌面] 弹层钉在工具栏下方、不出屏: 间距 {lp['gap']}px, 右 {lp['right']} ≤ {lp['vw']}")
        await pg.mouse.click(800,760); await pg.wait_for_timeout(250)
        print(ok(await pg.evaluate("getComputedStyle($('loopPop')).display==='none'")),
              "[桌面] 点弹层外面能关掉")
        # 待命后弹层自己收起，否则会挡住要点的那个小节
        await pg.click("#bLoopMore"); await pg.wait_for_timeout(200)
        await pg.click("#bA"); await pg.wait_for_timeout(250)
        print(ok(await pg.evaluate("getComputedStyle($('loopPop')).display==='none'")
                 and await pg.evaluate("arm")=="a"),
              "[桌面] 按起点待命后弹层自动收起（下一击落在谱面上）")
        await pg.evaluate("arm=null;updLoop()")
        await pg.close()

        # ================= 触屏 =================
        pg2=await b.new_page(viewport={"width":834,"height":1194},has_touch=True,device_scale_factor=2)
        pg2.on("pageerror",lambda e:errs.append("触屏: "+str(e)))
        await open_score(pg2,"http://127.0.0.1:8823/player.html?direct=1")
        t=await pg2.evaluate(STATE)
        print(ok(t["perf"] and t["hidebar"]),
              f"[触屏] 打开默认就是演奏态 + 收起了工具栏: perf={t['perf']} hidebar={t['hidebar']}")
        await pg2.evaluate("setBarHidden(false)"); await pg2.wait_for_timeout(300)
        t2=await pg2.evaluate(STATE)
        print(ok(t2["perf"] and t2["rows"]==1),
              f"[触屏] 展开工具栏后仍然只有一行: 可见 {t2['rows']} 行，高 {t2['barH']}px")
        await pg2.click("#bPerf"); await pg2.wait_for_timeout(300)
        t3=await pg2.evaluate(STATE)
        print(ok(not t3["perf"] and t3["edit"] and t3["state"]),
              f"[触屏] 点「演奏」能解锁回编辑态: 可见 {t3['rows']} 行")
        await pg2.reload(); await pg2.wait_for_timeout(1500)   # 同上：不等谱面，状态在 boot 前就定了
        t4=await pg2.evaluate(STATE)
        print(ok(t4["perf"]), f"[触屏] 刷新回默认（触屏 = 演奏态）: perf={t4['perf']}")
        await pg2.close()

        await b.close()
    print("\npage errors:", errs or "(none)")
asyncio.run(main())
