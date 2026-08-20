import asyncio, glob, http.server, socketserver, threading, functools
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
PDF=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
AUD=glob.glob(ROOT+"/ICT_working/08-Assets/*.mp3")[0]
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8736),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c): return "OK   " if c else "FAIL "

async def main():
    errs=[]
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={"width":1600,"height":980})
        pg.on("pageerror",lambda e:errs.append(str(e)))
        await pg.goto("http://127.0.0.1:8736/player.html")
        await pg.evaluate("localStorage.clear()"); await pg.reload()
        await pg.set_input_files("#fPdf",PDF); await pg.set_input_files("#fAud",AUD)
        await pg.wait_for_function("()=>document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=30000)

        # 只标位置，不卡任何时间
        await pg.evaluate("""()=>{ M=Array.from({length:24},(_,i)=>
             ({page:1,nx:.10+(i%6)*.15,ny:.20+Math.floor(i/6)*.09,m:i+1}));
             E=[];syncNext();layout(); }""")
        print(ok(await pg.evaluate("document.querySelectorAll('.mk.noT').length")==24),
              "生成前：24 个灰点（无时间）")

        # --- 打开面板，3/4 ♩=120，锚点 小节1 = 0.42s ---
        await pg.evaluate("$('bGen').click()"); await asyncio.sleep(0.2)
        await pg.fill('#gMeter input.sig',"3/4"); await pg.dispatch_event('#gMeter input.sig',"change")
        await pg.fill('#gTempo input[data-f="bpm"]',"120"); await pg.dispatch_event('#gTempo input[data-f="bpm"]',"change")
        print(ok("1.500s" in await pg.inner_text("#gMeter")), "面板算出每小节时长:", (await pg.inner_text("#gMeter")).split("每小节")[-1].strip())
        await pg.fill("#gAncT","0.42"); await pg.dispatch_event("#gAncT","change")
        prev=await pg.inner_text("#gPrev")
        print(ok("24" in prev and "0:00" in prev), "预览:", prev.replace("\n"," | "))

        await pg.click("#gRun"); await asyncio.sleep(0.4)
        n=await pg.evaluate("E.length")
        t=await pg.evaluate("[1,5,24].map(m=>+E.find(e=>e.m===m).t.toFixed(3))")
        print(ok(n==24 and t==[0.42,6.42,34.92]), f"生成 {n} 个点, 小节1/5/24 = {t} (期望 [0.42, 6.42, 34.92])")
        st=await pg.evaluate("[document.querySelectorAll('.mk.calc').length,document.querySelectorAll('.mk.noT').length]")
        print(ok(st==[24,0]), f"三态显示: 推算点 {st[0]} 个, 无时间 {st[1]} 个")
        print(ok(await pg.evaluate("$('mode').value")=="play"), "自动切到播放模式")

        # --- 手动改一个点 -> 升级为实测 -> 重新生成时当锚点保留 ---
        await pg.evaluate("aud.currentTime=13.0; addTime(12,stamp()); refresh()")
        e12=await pg.evaluate("E.filter(e=>e.m===12)")
        print(ok(len(e12)==1 and e12[0]["src"]=="tap" and abs(e12[0]["t"]-13.0)<0.01),
              f"手改小节12（生成值 16.92，差 3.9s）-> 替换而非新增: {e12}")
        await pg.evaluate("$('bGen').click()"); await asyncio.sleep(0.2)
        print(ok(await pg.inner_text("#gTapN")=="1"), "面板识别到 1 个实测锚点")
        await pg.click("#gRun"); await asyncio.sleep(0.4)
        keep=await pg.evaluate("E.find(e=>e.m===12)")
        print(ok(keep["src"]=="tap" and abs(keep["t"]-13.0)<0.01), f"重新生成后手改点保留: {keep}")
        print(ok(await pg.evaluate("E.filter(e=>e.m===12).length")==1), "锚点小节没有重复生成")
        print(ok(await pg.evaluate("document.querySelectorAll('.mk:not(.calc):not(.noT)').length")==1),
              "谱面上恰好 1 个实测蓝点")

        # --- 反复：播放顺序 ---
        await pg.evaluate("E=[];refresh()")
        await pg.evaluate("$('bGen').click()"); await asyncio.sleep(0.2)
        await pg.fill("#gForm","1-8, 3-8, 9-12"); await pg.dispatch_event("#gForm","input"); await asyncio.sleep(0.2)
        print(ok("3 段" in await pg.inner_text("#gFormInfo")), "顺序解析:", await pg.inner_text("#gFormInfo"))
        await pg.fill("#gAncT","0"); await pg.dispatch_event("#gAncT","change")
        await pg.click("#gRun"); await asyncio.sleep(0.4)
        chips=await pg.eval_on_selector_all(".chip","e=>e.map(x=>x.textContent)")
        print(ok(len(chips)==3), "段落条按声明切段:", chips)
        t3=await pg.evaluate("E.filter(e=>e.m===3).map(e=>+e.t.toFixed(2)).sort((a,b)=>a-b)")
        print(ok(t3==[3,12]), f"小节3 两遍的时间: {t3} (期望 [3, 12])")
        # 段落上下文选遍仍然有效
        await pg.evaluate("aud.pause();aud.currentTime=14")
        el=await pg.query_selector('.mk[data-m="5"]'); r=await el.bounding_box()
        await pg.mouse.click(r["x"]+r["width"]/2,r["y"]+r["height"]/2)
        print(ok(round(await pg.evaluate("aud.currentTime"),2)==15.0),
              f"②段内点小节5 -> {round(await pg.evaluate('aud.currentTime'),2)}s (期望 15.0)")

        # --- 反推 BPM ---
        await pg.evaluate("E=[{m:1,t:0,src:'tap'},{m:24,t:36.8,src:'tap'}];FORM=[];refresh()")
        await pg.evaluate("$('bGen').click()"); await asyncio.sleep(0.2)
        await pg.fill("#gForm",""); await pg.dispatch_event("#gForm","input")
        await pg.click("#gCal"); await asyncio.sleep(0.3)
        bpm=await pg.evaluate("TEMPO[0].bpm")
        print(ok(abs(bpm-120*34.5/36.8)<0.01), f"反推 BPM = {bpm} (期望 {round(120*34.5/36.8,3)})")
        print("   面板提示:", await pg.inner_text("#gCalInfo"))

        # --- 错误处理 ---
        await pg.fill("#gForm","1-8, 8-3"); await pg.dispatch_event("#gForm","input"); await asyncio.sleep(0.2)
        e1=await pg.inner_text("#gFormInfo"); c1=await pg.get_attribute("#gFormInfo","class")
        print(ok("反了" in e1 and c1=="gerr"), f'非法顺序报错: "{e1}"')
        await pg.fill("#gForm","1-8, 99-120"); await pg.dispatch_event("#gForm","input"); await asyncio.sleep(0.2)
        pv=await pg.inner_text("#gPrev")
        print(ok("还没标位置" in pv), f'未标位置告警: "{pv.splitlines()[-1][:60]}"')

        # --- 存档/导出带上 SIG+FORM ---
        await pg.fill("#gForm","1-8, 3-8"); await pg.dispatch_event("#gForm","input")
        await pg.click("#gRun"); await asyncio.sleep(0.9)
        await pg.evaluate("window.__b=null;URL.createObjectURL=b=>{window.__b=b;return 'blob:x'}")
        await pg.evaluate("$('bExp').onclick()")
        import json; j=json.loads(await pg.evaluate("window.__b.text()"))
        print(ok("METER" in j and "FORM" in j and j["FORM"]==[{"from":1,"to":8},{"from":3,"to":8}]),
              f"导出含结构: TEMPO={j.get('TEMPO')} METER={j.get('METER')} FORM={j.get('FORM')}")
        await pg.reload(); await pg.set_input_files("#fPdf",PDF)
        await pg.wait_for_function("()=>document.querySelectorAll('.mk').length>0",timeout=30000)
        rs=await pg.evaluate("[METER,FORM,E.length]")
        print(ok(rs[1]==[{"from":1,"to":8},{"from":3,"to":8}]), f"刷新后恢复结构: METER={rs[0]} FORM={rs[1]} E={rs[2]}")

        await pg.evaluate("aud.currentTime=5"); await asyncio.sleep(0.3)
        await pg.evaluate("wrap.scrollTop=0")
        await pg.screenshot(path="/tmp/player_gen.png",clip={"x":0,"y":0,"width":1600,"height":620})
        await pg.evaluate("$('bGen').click()"); await asyncio.sleep(0.3)
        await pg.screenshot(path="/tmp/player_dialog.png")
        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
