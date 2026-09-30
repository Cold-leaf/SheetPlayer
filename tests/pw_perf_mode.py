# 演奏态下能切音频模式（T1 → T2）。2026-09-30 用户在手机上报：演奏态找不到切模式的地方。
# 原因是 #modeSel 放在编辑行（演奏态整行收掉），而演奏行的 #audSel 只列当前模式的音频——
# 两条路都断了。现在 #lblMode 挪进演奏行；演奏态只给切，不列会写数据的「＋ 新建模式…」。
import asyncio, glob, http.server, socketserver, threading, functools
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
PDF=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
import wave, struct, math
MP3=glob.glob(ROOT+"/ICT_working/08-Assets/*.mp3")[0]
WAV="/tmp/pw_perf_mode_T2.wav"                   # 第二份音频要内容不同，否则按哈希去重只剩一个
with wave.open(WAV,'wb') as w:
    w.setnchannels(1);w.setsampwidth(2);w.setframerate(8000)
    w.writeframes(b''.join(struct.pack('<h',int(8000*math.sin(i*0.2))) for i in range(8000*3)))
class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*a): pass
H=functools.partial(Q,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8841),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c): return "OK   " if c else "FAIL "
VIS="(s=>{const e=document.querySelector(s);return !!e&&e.getClientRects().length>0})"

async def add_audio(pg,path,n):
    await pg.set_input_files("#fAud",path)
    await pg.wait_for_function("()=>$('dlgMode').style.display==='flex'",timeout=8000)
    await pg.click("#dlgModeOk")
    await pg.wait_for_function("(n)=>track.audios.length===n",arg=n,timeout=20000)

async def main():
    errs=[]
    async with async_playwright() as p:
        b=await p.chromium.launch()
        # 手机：触屏开机默认就是演奏态
        pg=await b.new_page(viewport={"width":412,"height":900},has_touch=True,is_mobile=True,device_scale_factor=2)
        pg.on("pageerror",lambda e:errs.append(str(e)))
        await pg.goto("http://127.0.0.1:8841/player.html")
        await pg.wait_for_function("()=>idb!==null",timeout=15000)
        await pg.evaluate("setPerf(false)")                      # 先解锁，把两个模式和音频备好
        await pg.set_input_files("#fPdf",PDF)
        await pg.wait_for_function("()=>document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=60000)
        await pg.evaluate("newMode('T1',true);switchMode('T1')")
        await add_audio(pg,MP3,1)
        await pg.evaluate("newMode('T2',true);switchMode('T2')")
        await add_audio(pg,WAV,2)
        await pg.evaluate("switchMode('T1')"); await pg.wait_for_timeout(300)

        print(ok(await pg.evaluate("[...$('modeSel').options].some(o=>o.value==='__new__')")),
              "编辑态：模式下拉里有「＋ 新建模式…」")

        await pg.evaluate("setPerf(true);setBarHidden(false)"); await pg.wait_for_timeout(300)
        print(ok(await pg.evaluate("document.body.classList.contains('perf')")), "进入演奏态")
        print(ok(await pg.evaluate("$('lblMode').closest('#rowPlay')!==null")), "模式下拉在演奏行里")
        print(ok(await pg.evaluate(VIS,"#lblMode")), "演奏态下模式下拉可见")
        print(ok(not await pg.evaluate("[...$('modeSel').options].some(o=>o.value==='__new__')")),
              "演奏态：不列「＋ 新建模式…」（它写数据）")
        # 真实地切：滑到它、选 T2
        await pg.evaluate("$('lblMode').scrollIntoView({inline:'center'})")
        await pg.select_option("#modeSel","T2"); await pg.wait_for_timeout(800)
        print(ok(await pg.evaluate("activeMode")=='T2'), f"演奏态下切到 T2: activeMode={await pg.evaluate('activeMode')}")
        h2=await pg.evaluate("track.audios.find(a=>a.mode==='T2').hash")
        print(ok(await pg.evaluate("track.lastAudio")==h2), "音频跟着换成 T2 的那个")

        await pg.evaluate("setPerf(false)"); await pg.wait_for_timeout(200)
        print(ok(await pg.evaluate("[...$('modeSel').options].some(o=>o.value==='__new__')")),
              "切回编辑态：「＋ 新建模式…」回来了")

        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
