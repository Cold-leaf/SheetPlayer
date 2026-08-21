# 两个模式两个音频，其中「现场」的音频文件损坏：进曲目默认现场 0:00 放不了，
# 切到「标准」模式应该自动加载标准的音频、能播放。
import asyncio, glob, http.server, socketserver, threading, functools, wave, struct, math
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
PDF=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
AUD=glob.glob(ROOT+"/ICT_working/08-Assets/*.mp3")[0]          # 标准（正常）
BAD="/tmp/bad_现场.mp3"
open(BAD,'wb').write(b'not-audio'*2000)                          # 现场（损坏）
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8808),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c): return "OK   " if c else "FAIL "

async def main():
    errs=[]
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={"width":1500,"height":1000})
        pg.on("pageerror",lambda e:errs.append(str(e)))
        await pg.goto("http://127.0.0.1:8808/player.html")
        await pg.wait_for_function("()=>idb!==null",timeout=15000)
        await pg.set_input_files("#fPdf",PDF)
        await pg.wait_for_function("()=>document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=60000)

        # 建「现场」模式，挂损坏音频
        await pg.evaluate("newMode('现场',true);switchMode('现场')")
        await pg.set_input_files("#fAud",BAD)
        await pg.wait_for_function("()=>$('dlg').style.display==='flex'",timeout=8000)
        await pg.click("#dlgOk")
        await pg.wait_for_function("()=>track.audios.length===1",timeout=20000)

        # 切回标准，挂正常音频
        await pg.evaluate("switchMode('标准')")
        await pg.set_input_files("#fAud",AUD)
        await pg.wait_for_function("()=>$('dlg').style.display==='flex'",timeout=8000)
        await pg.click("#dlgOk")
        await pg.wait_for_function("()=>track.audios.length===2",timeout=20000)
        # 让 lastAudio 指向损坏的「现场」，模拟"进去默认现场"
        await pg.evaluate("""async()=>{const a=track.audios.find(x=>x.mode==='现场');
          track.lastAudio=a.hash;track.updatedAt=Date.now();await idbPut(idb,'tracks',track)}""")
        await asyncio.sleep(0.8)

        # 重新打开曲目（模拟"进去默认现场"）
        await pg.evaluate("showLib(true)")
        await pg.wait_for_timeout(400)
        await pg.click(".libCard button.open")
        await pg.wait_for_function("()=>document.querySelectorAll('.mk').length>=0",timeout=30000)
        await pg.wait_for_timeout(1000)
        print(ok(await pg.evaluate("activeMode")=='现场'), f"默认现场模式: {await pg.evaluate('activeMode')}")
        print(ok(await pg.evaluate("aud.readyState")==0 or await pg.evaluate("isNaN(aud.duration)||aud.duration===0")),
              f"现场音频损坏放不了（readyState={await pg.evaluate('aud.readyState')}, duration={await pg.evaluate('aud.duration')}）")

        # 切到「标准」→ 应自动加载标准音频、能播
        await pg.select_option("#modeSel","标准")
        await pg.wait_for_function("()=>aud.readyState>=1&&aud.duration>0",timeout=30000)
        print(ok(await pg.evaluate("aud.duration")>0), f"切到标准后能播: duration={await pg.evaluate('aud.duration')}")
        print(ok(await pg.evaluate("activeMode")=='标准'), "模式已是标准")

        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
