# 返回键：谱面 → 曲目库 → 离开应用（两级）。有浮层开着时先关浮层。
import asyncio, http.server, socketserver, threading, functools
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
PDF=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8805),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c): return "OK   " if c else "FAIL "
URL="http://127.0.0.1:8805/player.html"

# 按一次返回键。用 evaluate 发 history.back() 而不是 pg.go_back()：
# 走到最底那层时 go_back() 会一直等一次永远不会发生的导航，evaluate 发完就走，自己等一会儿更可控
async def back(pg,ms=500):
    await pg.evaluate("history.back()"); await pg.wait_for_timeout(ms)

async def open_track(pg):
    await pg.set_input_files("#fPdf",PDF)
    await pg.wait_for_function("()=>document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=40000)

async def main():
    errs=[]
    async with async_playwright() as p:
        b=await p.chromium.launch()

        # --- 一、谱面 → 曲目库 → 离开 ---
        pg=await b.new_page(viewport={"width":1440,"height":900})
        pg.on("pageerror",lambda e:errs.append(str(e)))
        await pg.goto(URL)
        await pg.wait_for_function("()=>idb!==null",timeout=15000)
        print(ok(await pg.evaluate("(history.state||{}).v")=="lib"),
              f"开机就在库那一层: state={(await pg.evaluate('(history.state||{}).v'))}")
        await open_track(pg)
        st=await pg.evaluate("()=>({lib:$('lib').style.display,state:(history.state||{}).v})")
        print(ok(st["lib"]=="none" and st["state"]=="score"),
              f"进谱面：库收起、历史栈压到 score 层 (库={st['lib']} state={st['state']})")

        await back(pg)
        st=await pg.evaluate("()=>({lib:$('lib').style.display,state:(history.state||{}).v,pdf:!!pdf,pid:!!pid})")
        print(ok(st["lib"]=="flex" and st["state"]=="lib" and st["pdf"] and st["pid"]),
              f"按返回回曲目库，谱面原样留着 (库={st['lib']} state={st['state']} pdf={st['pdf']})")

        # 库里再按一次：记录走完了，应该**真的离开**这个文档。
        # 标签页里表现为导航走（about:），装成 PWA 时就是关掉应用——这正是要的两级返回
        # 这一下会**当场**离开文档，evaluate 的 Promise 来不及返回就被销毁（报
        # Execution context was destroyed）——那正是预期，吞掉这个异常再核对 URL
        try:
            await pg.evaluate("history.back()")
        except Exception:
            pass
        await pg.wait_for_timeout(900)
        print(ok(pg.url.startswith("about:") or pg.url==""),
              f"库里再按返回就离开应用: 当前 URL = {pg.url}")
        await pg.close()

        # --- 二、浮层开着时：先关浮层，不弹回曲目库，而且 await 不能挂死 ---
        pg2=await b.new_page(viewport={"width":1440,"height":900})
        pg2.on("pageerror",lambda e:errs.append(str(e)))
        await pg2.goto(URL)
        await pg2.wait_for_function("()=>idb!==null",timeout=15000)
        await open_track(pg2)
        # 造一个真实挂起的对话框：await 它的那半边必须收到 null，否则「新建项目」之类会永远卡住
        await pg2.evaluate("()=>{window.__r='pending';askText('返回键测试','').then(v=>window.__r=String(v))}")
        await pg2.wait_for_timeout(250)
        await back(pg2)
        st=await pg2.evaluate("()=>({dlg:$('dlg').style.display,lib:$('lib').style.display,"
                              "r:window.__r,state:(history.state||{}).v})")
        print(ok(st["dlg"]=="none" and st["r"]=="null" and st["lib"]=="none" and st["state"]=="score"),
              f"浮层开着时返回：只关浮层、不弹回库，await 落地成 {st['r']}"
              f" (弹框={st['dlg']} 库={st['lib']} state={st['state']})")
        # 浮层关掉之后，返回键才轮到"回曲目库"
        await back(pg2)
        st=await pg2.evaluate("()=>({lib:$('lib').style.display,state:(history.state||{}).v})")
        print(ok(st["lib"]=="flex" and st["state"]=="lib"),
              f"浮层没了之后，返回键才是回曲目库 (库={st['lib']} state={st['state']})")
        await pg2.close()

        # --- 三、库 ↔ 谱面来回切，历史栈不许越撑越长 ---
        pg4=await b.new_page(viewport={"width":1440,"height":900})
        pg4.on("pageerror",lambda e:errs.append(str(e)))
        await pg4.goto(URL)
        await pg4.wait_for_function("()=>idb!==null",timeout=15000)
        await open_track(pg4)
        n1=await pg4.evaluate("history.length")
        for _ in range(3):
            await pg4.evaluate("$('bLib').onclick()"); await pg4.wait_for_timeout(500)     # 进库（会弹掉 score 层）
            await pg4.evaluate("$('libClose').click()"); await pg4.wait_for_timeout(500)   # 出库（会再压一层）
        n2=await pg4.evaluate("history.length")
        print(ok(n2==n1), f"库/谱面来回切 3 次，历史栈不增长: {n1} → {n2}")
        await pg4.close()

        # --- 四、direct 模式不参与历史（返回键照旧直接退出）---
        pg5=await b.new_page(viewport={"width":1440,"height":900})
        pg5.on("pageerror",lambda e:errs.append(str(e)))
        await pg5.goto(URL+"?direct=1")
        await open_track(pg5)
        st=await pg5.evaluate("()=>({state:(history.state||{}).v,n:history.length})")
        print(ok(st["state"] is None), f"direct 模式不碰历史栈: state={st['state']!r}")
        await pg5.close()

        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
