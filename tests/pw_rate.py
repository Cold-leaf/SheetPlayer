# 排练胶囊里的倍速：一个涂成胶囊样子的原生 select（平板上点开就是系统选择器），
# 和工具栏那个 #rate 下拉双向同步。胶囊只在收起工具栏后出现（body.hidebar）。
import asyncio, glob, http.server, socketserver, threading, functools
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
        await pg.wait_for_function("()=>aud.src&&aud.readyState>=1",timeout=90000)
        print(ok(True), "音频就绪")

        # 收起工具栏 → 胶囊出现
        await pg.evaluate("setBarHidden(true)")
        print(ok(await pg.evaluate("getComputedStyle($('reh')).display")=="flex"), "排练胶囊出现")

        # 是原生 select（不是自制浮层），档位跟工具栏下拉一致
        print(ok(await pg.evaluate("$('rehRate').tagName")=="SELECT"), "速度控件是原生 select")
        print(ok(await pg.evaluate("$('rehRate').options.length")>=9), f"档位数 {await pg.evaluate('$(\"rehRate\").options.length')}")
        caps=await pg.evaluate("[...$('rehRate').options].map(o=>o.textContent)")
        tops=await pg.evaluate("[...$('rate').options].map(o=>String(+o.value)+'×')")
        print(ok(caps==tops), f"档位跟工具栏下拉一致：{caps}")
        print(ok(await pg.evaluate("$('rehRate').value")=="1"), "初始显示当前倍速 1×")
        print(ok(await pg.evaluate("$('rehRate').selectedOptions[0].textContent")=="1×"),
              "选中项的文案: "+await pg.evaluate("$('rehRate').selectedOptions[0].textContent"))

        # 可点、够大
        bb=await pg.evaluate("(r=>({w:r.width,h:r.height}))($('rehRate').getBoundingClientRect())")
        print(ok(bb["w"]>=44 and bb["h"]>=40), f"是够大的触控目标（{round(bb['w'])}×{round(bb['h'])}）")

        # 切宽窄不一的档位，控件宽度不变（胶囊不会跟着抖）
        w1=await pg.evaluate("$('rehRate').getBoundingClientRect().width")
        await pg.select_option("#rehRate","1.25")
        await pg.wait_for_timeout(150)
        w2=await pg.evaluate("$('rehRate').getBoundingClientRect().width")
        print(ok(abs(w1-w2)<0.5), f"切档时宽度不变（{round(w1)} → {round(w2)}，不会抖）")
        print(ok(await pg.evaluate("aud.playbackRate")==1.25), "胶囊里选的档位生效")

        # 选完不挡住谱面：没有自制浮层残留，胶囊高度也没变
        print(ok(await pg.evaluate("!document.getElementById('ratePop')")), "没有自制浮层挡在谱面上")

        # 反向同步：改工具栏下拉 → 胶囊跟着变
        #（排练态里工具栏是 display:none，select_option 点不到，直接走它的 onchange 同一条路）
        await pg.evaluate("$('rate').value='0.7';$('rate').onchange()")
        await pg.wait_for_timeout(150)
        print(ok(await pg.evaluate("$('rehRate').value")=="0.7"), "工具栏改速度，胶囊跟着变: "+await pg.evaluate("$('rehRate').value"))
        print(ok(await pg.evaluate("aud.playbackRate")==0.7), "下拉选择生效")

        # 键盘微调也同步（- / = / 0）
        await pg.evaluate("document.activeElement.blur()")
        await pg.keyboard.press("0"); await pg.wait_for_timeout(150)
        print(ok(await pg.evaluate("$('rehRate').value")=="1"), "按 0 归位，胶囊同步")
        await pg.keyboard.press("-"); await pg.wait_for_timeout(150)
        print(ok(await pg.evaluate("$('rehRate').value")=="0.9"), "按 - 微调，胶囊同步")

        # 播放中改速度不该打断播放，也不该丢进度
        await pg.evaluate("aud.currentTime=10;aud.play()")
        await pg.wait_for_timeout(600)
        await pg.select_option("#rehRate","0.5")
        await pg.wait_for_timeout(600)
        print(ok(await pg.evaluate("!aud.paused")), "改速度不打断播放")
        print(ok(await pg.evaluate("aud.currentTime")>=10), "进度没有跳回开头")
        print(ok(await pg.evaluate("aud.playbackRate")==0.5 and await pg.evaluate("$('rehRate').value")=="0.5"),
              "播放中改速度同样生效")

        # 浏览器原生速度菜单设出非档位值（1.05）时不能把下拉清空
        await pg.evaluate("aud.playbackRate=1.05")
        await pg.wait_for_timeout(150)
        print(ok(await pg.evaluate("$('rehRate').value")=="0.5"),
              "非档位值（1.05）不会让胶囊下拉变空白，保持原选中项")

        # 窄屏（平板竖屏）不出屏
        await pg.set_viewport_size({"width":390,"height":844})
        await pg.wait_for_timeout(400)
        r=await pg.evaluate("(b=>({l:b.left,r:b.right}))($('reh').getBoundingClientRect())")
        print(ok(r["l"]>=-1 and r["r"]<=391), f"窄屏胶囊不出屏（{round(r['l'])}–{round(r['r'])}）")
        rr=await pg.evaluate("(b=>({l:b.left,r:b.right}))($('rehRate').getBoundingClientRect())")
        print(ok(rr["l"]>=0 and rr["r"]<=390), f"窄屏速度控件不出屏（{round(rr['l'])}–{round(rr['r'])}）")
        await pg.select_option("#rehRate","1")
        await pg.wait_for_timeout(200)
        print(ok(await pg.evaluate("aud.playbackRate")==1), "窄屏下选档同样生效")

        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
