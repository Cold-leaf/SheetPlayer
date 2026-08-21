import asyncio, glob, http.server, socketserver, threading, functools, wave, struct, math
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
PDF=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
AUD=glob.glob(ROOT+"/ICT_working/08-Assets/*.mp3")[0]
WAV="/tmp/tone_b.wav"
with wave.open(WAV,'w') as w:
    w.setnchannels(1);w.setsampwidth(2);w.setframerate(22050)
    w.writeframes(b''.join(struct.pack('<h',int(12000*math.sin(2*math.pi*440*i/22050))) for i in range(22050*3)))
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8794),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c): return "OK   " if c else "FAIL "

async def main():
    errs=[]
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={"width":1500,"height":1000})
        pg.on("pageerror",lambda e:errs.append(str(e)))
        await pg.goto("http://127.0.0.1:8794/player.html")
        await pg.wait_for_function("()=>idb!==null&&$('lib').style.display==='flex'",timeout=15000)
        await pg.set_input_files("#fPdf",PDF)
        await pg.wait_for_function("()=>document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=30000)

        # 标 2 小节 + 标准模式打 1 个时间点
        await pg.evaluate("""()=>{M=[{page:1,nx:.2,ny:.3,m:1,h:.08},{page:1,nx:.35,ny:.3,m:2,h:.08}];
          E=[{m:1,t:0.5,src:'tap'}];syncNext();layout()}""")
        print(ok(await pg.evaluate("Object.keys(MODES).join(',')")=="标准",), "默认一个「标准」模式")
        print(ok(await pg.evaluate("E.length")==1), "标准模式时间点=1")

        # 直接点新建（文本框空）→ 弹应用内输入框，填「现场」
        await pg.click("#bMenu")
        await pg.click("#bNewMode")
        await pg.wait_for_function("()=>$('dlg').style.display==='flex'",timeout=5000)
        print(ok(await pg.evaluate("$('dlgMsg').textContent")=="新建模式的名字？"), "空名点新建弹出输入框")
        await pg.fill("#dlgInp","现场"); await pg.click("#dlgOk"); await pg.wait_for_timeout(300)
        print(ok(await pg.evaluate("activeMode")=="现场"), "新建后切到现场")
        print(ok(await pg.evaluate("E.length")==0), "现场时间点空")
        print(ok(await pg.evaluate("M.length")==2), "小节位置共享")

        # 加音频 1 → 选文件后弹输入框（默认当前模式「现场」），直接确定
        await pg.set_input_files("#fAud",AUD)
        await pg.wait_for_function("()=>$('dlg').style.display==='flex'",timeout=5000)
        await pg.click("#dlgOk")
        await pg.wait_for_function("()=>track.audios.length===1",timeout=10000)
        print(ok(await pg.evaluate("track.audios[0].mode")=="现场"), f"音频1挂到现场: {await pg.evaluate('track.audios[0].mode')}")
        h1=await pg.evaluate("track.lastAudio")

        # 切回标准，加音频 2（输入框默认「标准」→ 确定）
        await pg.evaluate("switchMode('标准')")
        await pg.set_input_files("#fAud",WAV)
        await pg.wait_for_function("()=>$('dlg').style.display==='flex'",timeout=5000)
        await pg.click("#dlgOk")
        await pg.wait_for_function("()=>track.audios.length===2",timeout=10000)
        print(ok(await pg.evaluate("track.audios[1].mode")=="标准"), f"音频2挂到标准: {await pg.evaluate('track.audios[1].mode')}")
        h2=await pg.evaluate("track.lastAudio")

        # 音频下拉按模式过滤：标准模式只显示音频2
        await pg.wait_for_function("()=>[...$('audSel').options].some(o=>o.text.includes('tone_b'))",timeout=10000)
        txt=await pg.evaluate("[...$('audSel').options].map(o=>o.text)")
        print(ok("tone_b" in "|".join(txt) and "晨曦酒庄" not in "|".join(txt)), f"标准模式只显示自己音频: {txt}")

        # 切模式到现场：audSel 只显示现场音频，时间点切到现场（空）
        await pg.evaluate("switchMode('现场')")
        await pg.wait_for_timeout(200)
        txt=await pg.evaluate("[...$('audSel').options].map(o=>o.text)")
        print(ok("晨曦酒庄" in "|".join(txt) and "tone_b" not in "|".join(txt)), f"现场模式只显示自己音频: {txt}")
        print(ok(await pg.evaluate("E.length")==0), f"切到现场时间点空: E={await pg.evaluate('E.length')}")
        # 选现场音频 → 仍停留在现场，时间点不变
        await pg.select_option("#audSel",h1)
        await pg.wait_for_timeout(200)
        print(ok(await pg.evaluate("activeMode")=='现场' and await pg.evaluate("E.length")==0), "选现场音频停留在现场模式")

        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
