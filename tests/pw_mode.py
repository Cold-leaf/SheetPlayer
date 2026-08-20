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
        pg.on("dialog",lambda d:asyncio.create_task(d.accept()))
        await pg.goto("http://127.0.0.1:8794/player.html")
        await pg.wait_for_function("()=>idb!==null&&$('lib').style.display==='flex'",timeout=15000)
        await pg.set_input_files("#fPdf",PDF)
        await pg.wait_for_function("()=>document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=30000)

        # 标 2 小节 + 标准模式打 1 个时间点
        await pg.evaluate("""()=>{M=[{page:1,nx:.2,ny:.3,m:1,h:.08},{page:1,nx:.35,ny:.3,m:2,h:.08}];
          E=[{m:1,t:0.5,src:'tap'}];syncNext();layout()}""")
        print(ok(await pg.evaluate("Object.keys(MODES).join(',')")=="标准",), "默认一个「标准」模式")
        print(ok(await pg.evaluate("E.length")==1), "标准模式时间点=1")

        # 新建「现场」模式
        await pg.click("#bMenu")
        await pg.fill("#newMode","现场"); await pg.dispatch_event("#newMode","change")
        await pg.click("#bNewMode"); await pg.wait_for_timeout(300)
        print(ok(await pg.evaluate("activeMode")=="现场"), "新建后切到现场")
        print(ok(await pg.evaluate("E.length")==0), "现场时间点空")
        print(ok(await pg.evaluate("M.length")==2), "小节位置共享")

        # 加音频 1 → 默认挂当前模式（现场）
        await pg.set_input_files("#fAud",AUD)
        await pg.wait_for_function("()=>track.audios.length===1",timeout=10000)
        print(ok(await pg.evaluate("track.audios[0].mode")=="现场"), f"音频1挂到现场: {await pg.evaluate('track.audios[0].mode')}")
        h1=await pg.evaluate("track.lastAudio")

        # 切回标准，加音频 2（弹窗输入「标准」）→ 应挂标准
        await pg.evaluate("switchMode('标准')")
        pg.once("dialog",lambda d:asyncio.create_task(d.accept("标准")))
        await pg.set_input_files("#fAud",WAV)
        await pg.wait_for_function("()=>track.audios.length===2",timeout=10000)
        print(ok(await pg.evaluate("track.audios[1].mode")=="标准"), f"音频2挂到标准: {await pg.evaluate('track.audios[1].mode')}")
        h2=await pg.evaluate("track.lastAudio")

        # 切到音频1（现场）→ 应自动切到现场模式，时间点变空
        await pg.evaluate("switchMode('标准')")   # 先回标准（E=1）
        await pg.select_option("#audSel",h1)
        await pg.wait_for_function("()=>activeMode==='现场'",timeout=10000)
        print(ok(await pg.evaluate("E.length")==0), f"切到音频1自动切现场: E={await pg.evaluate('E.length')}")

        # 切回音频2（标准）→ 时间点恢复
        await pg.select_option("#audSel",h2)
        await pg.wait_for_function("()=>activeMode==='标准'",timeout=10000)
        print(ok(await pg.evaluate("E.length")==1), f"切回音频2自动切标准: E={await pg.evaluate('E.length')}")

        # 音频下拉显示模式
        txt=await pg.evaluate("[...$('audSel').options].map(o=>o.text).join('|')")
        print(ok("现场" in txt and "标准" in txt), f"音频下拉带模式名: {txt}")

        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
