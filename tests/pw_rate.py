# 排练胶囊里的倍速：点「1×」铺开档位、点一档就生效、和工具栏下拉双向同步。
# 胶囊只在收起工具栏后出现（body.hidebar），所以先切到排练态。
import asyncio, glob, http.server, socketserver, threading, functools, wave, struct, math
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
PDF=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
AUD=glob.glob(ROOT+"/ICT_working/08-Assets/*.mp3")[0]
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8815),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c): return "OK   " if c else "FAIL "

async def main():
    errs=[]
    async with async_playwright() as p:
        b=await p.chromium.launch()
        pg=await b.new_page(viewport={"width":1500,"height":1000})
        pg.on("pageerror",lambda e:errs.append(str(e)))
        await pg.goto("http://127.0.0.1:8815/player.html?direct=1")
        await pg.set_input_files("#fPdf",PDF)
        await pg.wait_for_function("()=>document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=60000)
        await pg.set_input_files("#fAud",AUD)
        # 挂着音频才会有得播；direct 模式不弹模式框
        await pg.wait_for_function("()=>aud.src&&aud.readyState>=1",timeout=90000)
        print(ok(True), "音频就绪")

        # 收起工具栏 → 胶囊出现
        await pg.evaluate("setBarHidden(true)")
        print(ok(await pg.evaluate("getComputedStyle($('reh')).display")=="flex"), "排练胶囊出现")

        # 速度键显示当前倍速，初始 1×
        print(ok(await pg.evaluate("$('rehRate').textContent")=="1×"),
              "胶囊速度键显示当前倍速: "+await pg.evaluate("$('rehRate').textContent"))
        print(ok(await pg.evaluate("getComputedStyle($('rehRate')).display")!='none'), "速度键可见")
        w=await pg.evaluate("$('rehRate').getBoundingClientRect().width")
        h=await pg.evaluate("$('rehRate').getBoundingClientRect().height")
        print(ok(w>=44 and h>=40), f"速度键是够大的触控目标（{round(w)}×{round(h)}）")

        # 点开浮层：档位齐全、当前档高亮、浮层在胶囊上方
        await pg.click("#rehRate")
        await pg.wait_for_function("()=>$('ratePop').style.display==='block'",timeout=5000)
        chips=await pg.evaluate("[...$('rateRow').querySelectorAll('button')].map(b=>b.textContent)")
        opts=await pg.evaluate("[...$('rate').options].map(o=>String(+o.value)+'×')")
        print(ok(chips==opts), f"档位跟工具栏下拉一致：{chips}")
        print(ok(await pg.evaluate("[...$('rateRow').querySelectorAll('button')].filter(b=>b.classList.contains('on')).map(b=>b.textContent).join()")=="1×"),
              "当前档位高亮")
        box=await pg.evaluate("(r=>({pop:r.top}))($('ratePop').getBoundingClientRect())")
        reh=await pg.evaluate("$('reh').getBoundingClientRect().top")
        print(ok(box["pop"]<reh), f"浮层在胶囊上方（{round(box['pop'])} < {round(reh)}），不挡谱面中间")

        # 点 0.7 → 生效、浮层收起、按钮文案跟着变
        await pg.click("#rateRow button[data-r='0.7']")
        await pg.wait_for_timeout(200)
        print(ok(await pg.evaluate("aud.playbackRate")==0.7), "选 0.7 生效: "+str(await pg.evaluate("aud.playbackRate")))
        print(ok(await pg.evaluate("$('ratePop').style.display")=='none'), "选完自动收起（不挡住谱子）")
        print(ok(await pg.evaluate("$('rehRate').textContent")=="0.7×"), "按钮文案更新: "+await pg.evaluate("$('rehRate').textContent"))
        print(ok(await pg.evaluate("$('rate').value")=="0.7"), "工具栏下拉同步到 0.7")

        # 反向同步：改工具栏下拉 → 胶囊按钮跟着变
        #（排练态里工具栏是 display:none，select_option 点不到，直接走它的 onchange 同一条路）
        await pg.evaluate("$('rate').value='1.25';$('rate').onchange()")
        await pg.wait_for_timeout(200)
        print(ok(await pg.evaluate("$('rehRate').textContent")=="1.25×"), "工具栏改速度，胶囊跟着变: "+await pg.evaluate("$('rehRate').textContent"))
        print(ok(await pg.evaluate("aud.playbackRate")==1.25), "下拉选择生效")

        # 键盘微调也同步（- / = / 0）
        await pg.evaluate("document.activeElement.blur()")
        await pg.keyboard.press("0")
        await pg.wait_for_timeout(150)
        print(ok(await pg.evaluate("$('rehRate').textContent")=="1×"), "按 0 归位，胶囊同步")
        await pg.keyboard.press("-")
        await pg.wait_for_timeout(150)
        print(ok(await pg.evaluate("$('rehRate').textContent")=="0.9×"), "按 - 微调，胶囊同步")

        # 再点一次速度键 / 点外面 / Esc 都要能收起
        await pg.click("#rehRate"); await pg.wait_for_timeout(150)
        print(ok(await pg.evaluate("$('ratePop').style.display")=='block'), "再点速度键打开")
        await pg.click("#rehRate"); await pg.wait_for_timeout(150)
        print(ok(await pg.evaluate("$('ratePop').style.display")=='none'), "再点一次收起（开合）")
        await pg.click("#rehRate"); await pg.wait_for_timeout(150)
        await pg.mouse.click(750,300); await pg.wait_for_timeout(150)
        print(ok(await pg.evaluate("$('ratePop').style.display")=='none'), "点外面收起")
        await pg.click("#rehRate"); await pg.wait_for_timeout(150)
        await pg.keyboard.press("Escape"); await pg.wait_for_timeout(150)
        print(ok(await pg.evaluate("$('ratePop').style.display")=='none'), "Esc 收起")
        print(ok(await pg.evaluate("aud.playbackRate")==0.9), "收起浮层不影响已设的速度")

        # 播放中改速度不该打断播放，也不该丢进度
        await pg.evaluate("aud.currentTime=10;aud.play()")
        await pg.wait_for_timeout(600)
        await pg.click("#rehRate"); await pg.wait_for_timeout(150)
        await pg.click("#rateRow button[data-r='0.5']")
        await pg.wait_for_timeout(600)
        print(ok(await pg.evaluate("!aud.paused")), "改速度不打断播放")
        print(ok(await pg.evaluate("aud.currentTime")>=10), "进度没有跳回开头")
        print(ok(await pg.evaluate("aud.playbackRate")==0.5 and await pg.evaluate("$('rehRate').textContent")=="0.5×"),
              "播放中改速度同样生效")

        # 展开工具栏时浮层要收起来，别悬在谱面上
        await pg.click("#rehRate"); await pg.wait_for_timeout(150)
        await pg.evaluate("setBarHidden(false)")
        await pg.wait_for_timeout(150)
        print(ok(await pg.evaluate("$('ratePop').style.display")=='none'), "展开工具栏时浮层自动收起")

        # 窄屏（平板竖屏）下档位换行也不能溢出屏幕
        await pg.set_viewport_size({"width":390,"height":844})
        await pg.evaluate("setBarHidden(true)"); await pg.wait_for_timeout(300)
        await pg.click("#rehRate"); await pg.wait_for_timeout(300)
        r=await pg.evaluate("(b=>({l:b.left,rt:b.right,w:b.width}))($('ratePop').getBoundingClientRect())")
        print(ok(r["l"]>=0 and r["rt"]<=390), f"窄屏浮层不出屏（{round(r['l'])}–{round(r['rt'])}）")
        rc=await pg.evaluate("(b=>({l:b.left,r:b.right,b:b.bottom&&b.bottom}))($('reh').getBoundingClientRect())")
        print(ok(rc["l"]>=-1 and rc["r"]<=391), f"窄屏胶囊不出屏（{round(rc['l'])}–{round(rc['r'])}）")
        await pg.click("#rateRow button[data-r='1']")
        await pg.wait_for_timeout(200)
        print(ok(await pg.evaluate("$('rehRate').textContent")=="1×"), "窄屏下选档同样生效")

        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
