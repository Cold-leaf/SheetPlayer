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
        assert await page.evaluate("""()=>{
          const cv=document.createElement('canvas');cv.width=3;cv.height=1;
          const d=new Uint8ClampedArray(12);
          [40,180,250].forEach((v,i)=>{d.set(SP_LUT.slice(v*3,v*3+3),i*4);d[i*4+3]=255});
          cv.getContext('2d').putImageData(new ImageData(d,3,1),0,0);
          const filtered=brightSpec(cv,65),out=filtered.getContext('2d').getImageData(0,0,3,1).data;
          return out[0]===SP_LUT[0]&&out[1]===SP_LUT[1]&&
            out.slice(4).every((v,i)=>v===d[i+4])&&brightSpec(cv,65)===filtered&&
            brightSpec(cv,0)===cv&&cv.getContext('2d').getImageData(0,0,3,1).data.every((v,i)=>v===d[i]);
        }""")
        before=await page.evaluate('Array.from(SPEC.onsets)')
        for level in ['0','65','95']:
            await page.locator('#specBrightLevel').fill(level)
            await page.evaluate('drawSpec()')
            assert await page.locator('#specBrightValue').inner_text()==level+'%'
        await page.uncheck('#specBright')
        assert await page.evaluate('Array.from(SPEC.onsets)')==before
        await page.set_viewport_size({'width':390,'height':800})
        assert await page.locator('#specClose').evaluate('(el)=>el.getBoundingClientRect().right<=innerWidth')
        print('OK   bright filter hides dark colors, preserves bright colors and source; controls leave onsets unchanged')
        for value,low,high in [('soprano',60,84),('alto',53,77),('tenor',48,72),('bass',40,64)]:
            await page.select_option('#specRange',value)
            result=await page.evaluate("""([low,high])=>{
              const r=specFrequencyRange(),H=$('specCv').clientHeight;
              const y=n=>(specFrequencyRow(440*2**((n-69)/12))-r.top)/(r.bottom-r.top)*H;
              drawSpec();
              return r.top>=0&&r.bottom<=SP_H&&y(high)>0&&y(high)<H*.05&&y(low)>H*.95&&y(low)<H;
            }""",[low,high])
            assert result
        await page.select_option('#specRange','all')
        assert await page.evaluate('specFrequencyRange().top===0&&specFrequencyRange().bottom===SP_H')
        await page.uncheck('#specNotes');await page.check('#specNotes')
        assert await page.evaluate('Array.from(SPEC.onsets)')==before
        await page.screenshot(path='/tmp/sheetplayer-note-axis.png')
        print('OK   SATB ranges map note frequencies correctly; full range restored; onsets unchanged')
        assert not await page.locator('#specKeyLabel').is_visible()
        await page.select_option('#specNoteMode','solfege')
        assert await page.locator('#specKeyLabel').is_visible()
        await page.select_option('#specKey','2')
        assert await page.evaluate("""()=>{
          drawSpec();
          return specNoteLabel(62,'solfege',2).text==='1'&&
            specNoteLabel(64,'solfege',2).text==='2'&&
            specNoteLabel(61,'solfege',2).text==='7̣'&&
            specNoteLabel(63,'solfege',2).altered&&
            specNoteLabel(69,'solfege',0).text==='6'&&
            specNoteLabel(60,'note',2).text==='C4';
        }""")
        await page.select_option('#specNoteMode','note')
        assert not await page.locator('#specKeyLabel').is_visible()
        assert await page.evaluate('Array.from(SPEC.onsets)')==before
        print('OK   movable-do key selection, chromatic notes, octave boundaries and note mode')
        assert not errors,errors
        print('OK   removed experimental views; original default; restored detector and cache round trip')
        await browser.close()
try: asyncio.run(main())
finally: server.shutdown()
