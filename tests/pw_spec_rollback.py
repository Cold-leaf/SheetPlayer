"""Regression for removing experimental views and restoring onset analysis."""
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
        await page.select_option('#mode','time')
        await page.evaluate('async()=>{idb=(await initStore()).db}')
        assert await page.locator('#chkCurve').count()==0
        assert await page.locator('#onsetBand').count()==0
        assert await page.locator('#specView').input_value()=='original'
        assert await page.locator('#specView option').count()==2
        await page.evaluate("""async()=>{
          const m=new Float32Array(SP_SR*2);
          for(let k=0;k<300;k++)m[5500+k]=.8*Math.exp(-k/44)*Math.sin(2*Math.PI*1500*k/SP_SR);
          await buildSpec(m,2,specSeq);cacheSpec('rollback-test');
        }""")
        await page.wait_for_function("async()=>!!(await idbGet(idb,'spec','rollback-test'))")
        assert await page.evaluate("""async()=>{
          const rec=await idbGet(idb,'spec','rollback-test');
          const expected=Array.from(SPEC.onsets);restoreSpec(rec);
          return rec.version===6&&!('curves' in SPEC)&&!('pitchCv' in SPEC)&&
            expected.length===1&&SPEC.onsets.every((v,i)=>v===expected[i])&&SPEC.changeCv.width===SPEC.frames;
        }""")
        for view in ['original','change']:
            await page.select_option('#specView',view)
            await page.evaluate('drawSpec()')
        assert not errors,errors
        print('OK   removed experimental views; original default; restored detector and cache round trip')
        await browser.close()
try: asyncio.run(main())
finally: server.shutdown()
