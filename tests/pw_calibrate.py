"""Independent tempo calibration UI regression without external assets."""
import asyncio, functools, http.server, threading
from pathlib import Path
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parents[1]
class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*args): pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(ROOT)))
threading.Thread(target=server.serve_forever,daemon=True).start()
async def main():
    async with async_playwright() as p:
        browser=await p.chromium.launch()
        page=await browser.new_page(viewport={'width':1100,'height':800})
        errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        await page.goto(f'http://127.0.0.1:{server.server_port}/player.html?direct=1')
        assert await page.evaluate('TEMPO[0].bpm===null&&defaultModeData().TEMPO[0].bpm===null')
        await page.evaluate("""()=>{
          M=Array.from({length:14},(_,i)=>({m:i+1,page:1,nx:.2,ny:.2}));
          TEMPO=[{m:1,bpm:65.508},{m:10,bpm:65.508}];
          METER=[{sig:[4,4],ranges:[]}];FORM=[];
          E=[{m:1,t:0,src:'tap'},{m:10,t:36,src:'tap'},{m:14,t:48,src:'tap'}];
          openGen();
        }""")
        await page.click('#gCal')
        assert await page.evaluate('TEMPO.map(t=>t.bpm)')==[60,80]
        text=await page.locator('#gCalInfo').inner_text()
        assert '小节 1–9：♩=60' in text and '小节 10 起：♩=80' in text,text
        assert await page.locator('#gTempo input[data-f="bpm"]').evaluate_all('(els)=>els.map(e=>+e.value)')==[60,80]
        assert await page.evaluate("genTimeline(null,false).E.filter(e=>[5,12].includes(e.m)).map(e=>e.t)")==[16,42]
        print('OK   calibration button updates separate tempo rows and generated timeline')
        await page.evaluate("""()=>{
          TEMPO=[{m:1,bpm:120},{m:10,bpm:90}];
          E=[{m:1,t:0,src:'tap'},{m:5,t:16,src:'tap'},{m:14,t:50,src:'tap'}];drawSig();
        }""")
        await page.click('#gCal')
        assert await page.evaluate('TEMPO.map(t=>t.bpm)')==[60,90]
        text=await page.locator('#gCalInfo').inner_text()
        assert '实测点不足，未修改' in text and '跨变速间隔未使用' in text,text
        print('OK   partial calibration explains unsupported segments and skipped cross-boundary intervals')
        await page.fill('#gForm','10-1')
        await page.click('#gCal')
        assert await page.evaluate('TEMPO.map(t=>t.bpm)')==[60,90]
        assert '反了' in await page.locator('#gFormInfo').inner_text()
        await page.evaluate("""()=>{
          TEMPO=[{m:1,bpm:null},{m:10,bpm:null}];FORM=[];
          E=[{m:1,t:0,src:'tap'},{m:10,t:36,src:'tap'},{m:14,t:48,src:'tap'}];openGen();
        }""")
        assert await page.locator('#gTempo input[data-f="bpm"]').evaluate_all('(els)=>els.every(e=>e.value==="")')
        assert await page.locator('#gRun').is_disabled()
        assert '未填写' in await page.locator('#gPrev').inner_text()
        await page.click('#gCal')
        assert await page.evaluate('TEMPO.map(t=>t.bpm)')==[60,80]
        assert await page.locator('#gRun').is_enabled()
        await page.locator('#gTempo input[data-f="bpm"]').nth(1).fill('')
        await page.locator('#gTempo input[data-f="bpm"]').nth(1).dispatch_event('change')
        assert await page.evaluate('TEMPO[1].bpm===null')
        assert await page.locator('#gRun').is_disabled()
        await page.evaluate("E=[{m:1,t:0,src:'tap'},{m:5,t:16,src:'tap'},{m:14,t:50,src:'tap'}]")
        await page.click('#gCal')
        assert await page.evaluate('TEMPO.map(t=>t.bpm)')==[60,None]
        assert await page.locator('#gRun').is_disabled()
        await page.click('#gAddT')
        assert await page.locator('#gTempo input[data-f="bpm"]').last.input_value()==''
        assert await page.evaluate('JSON.parse(JSON.stringify(TEMPO))[2].bpm===null')
        print('OK   blank BPM defaults, independent inference, clearing, missing evidence and new blank segments')
        assert not errors,errors
        print('OK   invalid playback order blocks calibration; no page errors')
        await browser.close()
try: asyncio.run(main())
finally: server.shutdown()
