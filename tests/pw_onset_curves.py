"""Self-contained onset analysis, cache and responsive UI regression."""
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
        result=await page.evaluate('''async()=>{
          const sr=SP_SR,m=new Float32Array(sr*2),times=[0,.5,.58,.66,1.98];
          for(const t of times)for(let k=0;k<sr*.03&&Math.round(t*sr)+k<m.length;k++)
            m[Math.round(t*sr)+k]+=.8*Math.exp(-k/(sr*.004))*Math.sin(2*Math.PI*1500*k/sr);
          await buildSpec(m,2,specSeq);
          const timesOk=times.every(t=>[...SPEC.onsets].some(x=>Math.abs(x-t)<.015));
          cacheSpec('onset-test');
          return {timesOk,count:SPEC.onsets.length};
        }''')
        assert result=={'timesOk':True,'count':5},result
        print('OK   production build detects rapid and boundary attacks')
        await page.wait_for_function("async()=>!!(await idbGet(idb,'spec','onset-test'))")
        assert await page.evaluate('''async()=>{
          const rec=await idbGet(idb,'spec','onset-test');
          const before=Array.from(SPEC.curves[0]);restoreSpec(rec);
          return rec.version===3&&SPEC.curves[0].every((v,i)=>v===before[i])&&SPEC.curveStep>0;
        }''')
        print('OK   IndexedDB cache restores continuous curves')
        for width in [1100,760,390]:
            await page.set_viewport_size({'width':width,'height':800})
            for band in ['0','1','2','3']:
                await page.select_option('#onsetBand',band)
                await page.evaluate('drawSpec()')
            assert await page.locator('#specClose').evaluate('(el)=>el.getBoundingClientRect().right<=innerWidth')
        await page.uncheck('#chkCurve');await page.evaluate('drawSpec()')
        await page.check('#chkCurve');await page.evaluate('drawSpec()')
        await page.screenshot(path='/tmp/sheetplayer-onset-curves.png')
        assert not errors,errors
        print('OK   band switching, curve toggle and responsive controls; no page errors')
        await browser.close()
try: asyncio.run(main())
finally: server.shutdown()
