# 同步过来的曲目：标注/音频名都在，但音频【文件】不在本机。
# 以前静默跳过，界面显示着音频名却 0:00 放不了；现在要明确提示 + 下拉标注。
import asyncio, glob, http.server, socketserver, threading, functools, wave, struct, math
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
PDF=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
WAV="/tmp/am_a.wav"
with wave.open(WAV,'w') as w:
    w.setnchannels(1);w.setsampwidth(2);w.setframerate(22050)
    w.writeframes(b''.join(struct.pack('<h',int(9000*math.sin(2*math.pi*440*i/22050))) for i in range(22050*2)))
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8804),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c): return "OK   " if c else "FAIL "

async def main():
    errs=[]
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={"width":1500,"height":1000})
        pg.on("pageerror",lambda e:errs.append(str(e)))
        await pg.goto("http://127.0.0.1:8804/player.html")
        await pg.wait_for_function("()=>idb!==null",timeout=15000)
        await pg.set_input_files("#fPdf",PDF)
        await pg.wait_for_function("()=>document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=60000)
        await pg.set_input_files("#fAud",WAV)
        await pg.wait_for_function("()=>$('dlg').style.display==='flex'",timeout=8000)
        await pg.click("#dlgOk")
        await pg.wait_for_function("()=>track&&track.audios.length===1",timeout=20000)
        await pg.evaluate("M=[{page:1,nx:.2,ny:.3,m:1,h:.08}];E=[{m:1,t:0.5,src:'tap'}];syncNext();layout();save()")
        await asyncio.sleep(0.8)
        h=await pg.evaluate("track.lastAudio")

        # 模拟"同步过来"：曲目记录里音频名还在，但把音频文件从 files 删掉
        await pg.evaluate("""async(h)=>{await idbDel(idb,'files',h)}""",h)
        await pg.reload()
        await pg.wait_for_function("()=>idb!==null&&$('lib').style.display==='flex'",timeout=15000)
        await pg.wait_for_timeout(400)
        await pg.click(".libCard button.open")
        await pg.wait_for_function("()=>document.querySelectorAll('.mk').length===1",timeout=30000)
        await pg.wait_for_timeout(600)

        print(ok(await pg.evaluate("M.length")==1 and await pg.evaluate("E.length")==1), "标注仍然完整（1 标记 / 1 时间点）")
        m=await pg.inner_text("#msg")
        print(ok("不在这台设备上" in m), f"明确提示音频不在本机: {m[:52]}…")
        opts=await pg.evaluate("[...$('audSel').options].map(o=>o.text)")
        print(ok(any("不在本机" in o for o in opts)), f"音频下拉标注: {opts}")

        # 选中那个不在本机的音频 → 给提示而不是静默无反应
        await pg.evaluate("$('msg').textContent=''")
        await pg.select_option("#audSel",h)
        await pg.wait_for_timeout(400)
        m2=await pg.inner_text("#msg")
        print(ok("不在这台设备上" in m2), f"选中缺失音频有提示: {m2[:52]}…")

        # 在本机重新选一次同一个文件 → 恢复可播放
        await pg.set_input_files("#fAud",WAV)
        await pg.wait_for_function("()=>$('dlg').style.display==='flex'",timeout=8000)
        await pg.click("#dlgOk")
        await pg.wait_for_function("()=>!!audUrl",timeout=20000)
        await pg.wait_for_timeout(500)
        opts2=await pg.evaluate("[...$('audSel').options].map(o=>o.text)")
        print(ok(not any("不在本机" in o for o in opts2)), f"本机补上文件后标注消失: {opts2}")
        print(ok(await pg.evaluate("M.length")==1 and await pg.evaluate("E.length")==1), "补音频后标注不受影响")

        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
