import asyncio, glob, http.server, socketserver, threading, functools, wave, struct, math
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
PDF=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
AUD=glob.glob(ROOT+"/ICT_working/08-Assets/*.mp3")[0]   # 3.7MB / 67s，起音 125 个
WAV="/tmp/tone_b.wav"                                    # 第二个音频变体：3 秒正弦波
with wave.open(WAV,'w') as w:
    w.setnchannels(1);w.setsampwidth(2);w.setframerate(22050)
    w.writeframes(b''.join(struct.pack('<h',int(12000*math.sin(2*math.pi*440*i/22050))) for i in range(22050*3)))
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8771),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c): return "OK   " if c else "FAIL "

async def main():
    errs=[]
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={"width":1500,"height":1000})
        pg.on("pageerror",lambda e:errs.append(str(e)))
        await pg.goto("http://127.0.0.1:8771/player.html")
        await pg.wait_for_function("()=>idb!==null&&$('lib').style.display==='flex'",timeout=10000)
        await pg.set_input_files("#fPdf",PDF)
        await pg.wait_for_function("()=>document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=30000)
        await pg.select_option("#mode","mark")
        bb=await (await pg.query_selector('.page[data-page="1"]')).bounding_box()
        for fx in (0.3,0.45,0.6):
            await pg.mouse.click(bb["x"]+bb["width"]*fx,bb["y"]+bb["height"]*0.4)

        # 音频 1 → 完整分析（选完文件会弹「挂到哪个模式」的应用内输入框，直接确定挂当前模式）
        await pg.set_input_files("#fAud",AUD)
        await pg.wait_for_function("()=>$('dlg').style.display==='flex'",timeout=5000)
        await pg.click("#dlgOk")
        await pg.wait_for_function("()=>SPEC!==null||$('specMsg').textContent.includes('失败')",timeout=90000)
        await pg.wait_for_function("()=>track.audios.length===1",timeout=10000)
        print(ok(await pg.evaluate("track.audios[0].name")==AUD.split('/')[-1]), "音频变体挂进曲目（记录文件名）")
        h1=await pg.evaluate("track.lastAudio")

        # 音频 2 → 变体数 2，标注不动
        await pg.set_input_files("#fAud",WAV)
        await pg.wait_for_function("()=>$('dlg').style.display==='flex'",timeout=5000)
        await pg.click("#dlgOk")
        await pg.wait_for_function("()=>SPEC!==null&&SPEC.dur<4",timeout=90000)
        await pg.wait_for_function("()=>track.audios.length===2",timeout=10000)
        print(ok(await pg.evaluate("M.length")==3), "切音频变体：小节标注全部保留")
        print(ok(await pg.evaluate("[...$('audSel').options].length")==3 and
                 "＋ 添加音频" in (await pg.evaluate("[...$('audSel').options].at(-1).text"))), "音频变体下拉齐全")

        # 切回音频 1：会话内缓存命中，不重新分析
        await pg.select_option("#audSel",h1)
        await pg.wait_for_function("()=>SPEC!==null&&SPEC.dur>60",timeout=10000)
        m=await pg.evaluate("$('specMsg').textContent")
        print(ok("缓存" in m and "分析中" not in m), "切回音频 1 命中缓存: "+m)
        print(ok(await pg.evaluate("M.length")==3), "再次切换标注依然保留")

        # 刷新后打开曲目：lastAudio 自动带上，频谱从 IndexedDB 缓存恢复
        await pg.reload()
        await pg.wait_for_function("()=>idb!==null&&$('lib').style.display==='flex'",timeout=10000)
        await pg.wait_for_timeout(400)
        await pg.click(".libCard button.open")
        await pg.wait_for_function("()=>document.querySelectorAll('.mk').length===3",timeout=30000)
        await pg.wait_for_function("()=>SPEC!==null",timeout=15000)
        print(ok(await pg.evaluate("SPEC&&SPEC.dur>60")), "打开曲目自动带上上次的音频变体")
        print(ok((await pg.evaluate("$('specMsg').textContent")).find("缓存")>=0), "频谱跨会话从 IndexedDB 恢复，无重算",
              "msg: "+await pg.evaluate("$('specMsg').textContent"))

        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
