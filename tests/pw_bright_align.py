"""Generation preview/apply/undo and audio evidence with self-contained fixtures."""
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
        page=await browser.new_page(viewport={'width':1100,'height':900})
        errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        await page.goto(f'http://127.0.0.1:{server.server_port}/player.html?direct=1')
        # Production analysis: strong harmonic notes over quiet repeated accompaniment.
        evidence=await page.evaluate("""async()=>{
          const sr=SP_SR,mono=new Float32Array(sr*19),truth=[];
          for(let i=0;i<33;i++){
            const t=1+i*.5+.06;truth.push(t);
            for(let k=0;k<sr*.2;k++){
              const u=k/sr;mono[Math.round(t*sr)+k]+=.8*Math.exp(-u/.07)*Math.sin(2*Math.PI*(i%2?660:440)*u);
            }
          }
          for(let t=1.25;t<18;t+=.5)for(let k=0;k<sr*.12;k++){
            const u=k/sr;mono[Math.round(t*sr)+k]+=.06*Math.exp(-u/.04)*Math.sin(2*Math.PI*180*u);
          }
          await buildSpec(mono,19,specSeq);
          const candidates=await brightCandidates(SPEC,{threshold:90,range:'all'},()=>false);
          window.fixtureCandidates=candidates;
          return {count:candidates.length,near:candidates.filter(c=>truth.some(t=>Math.abs(t-c.t)<.025)).length};
        }""")
        assert evidence['count']>=20 and evidence['near']==evidence['count'],evidence
        print('OK   real FFT analysis selects bright target attacks over quiet accompaniment',evidence)
        await page.evaluate("""()=>{
          M=Array.from({length:9},(_,i)=>({m:i+1,page:1,nx:.1,ny:.1}));
          TEMPO=[{m:1,bpm:120}];METER=[{sig:[4,4],ranges:[]}];FORM=[];
          E=[{m:1,t:1,src:'tap'},{m:9,t:17,src:'tap'}];BEATS={'2:0:4/4:4:1':{t:3.7,src:'gen',start:3,end:5}};
          openGen();window.beforeAlign=JSON.stringify({E,BEATS});
        }""")
        assert not await page.locator('#gBrightEnabled').is_checked()
        await page.check('#gBrightEnabled')
        assert await page.locator('#gRun').is_disabled()
        await page.click('#gBrightPreview')
        await page.wait_for_function('brightPlan!==null&&!brightBusy')
        assert await page.evaluate('JSON.stringify({E,BEATS})===beforeAlign')
        proposed=await page.evaluate('brightPlan.result.E.filter(e=>e.src==="gen").map(e=>({m:e.m,t:e.t}))')
        assert len(proposed)==7 and all(.025<e['t']-(1+(e['m']-1)*2)<.09 for e in proposed),proposed
        assert '将校准 7' in await page.locator('#gBrightInfo').inner_text()
        print('OK   preview reports coherent regional correction without changing saved timing')
        await page.fill('#gBrightWindow','100')
        assert await page.locator('#gRun').is_disabled()
        await page.click('#gBrightPreview')
        await page.wait_for_function('brightPlan!==null&&!brightBusy')
        await page.click('#gRun')
        assert await page.evaluate('E.filter(e=>e.src!=="gen").map(e=>e.t)')==[1,17]
        assert await page.evaluate('E.filter(e=>e.src==="gen").length')==7
        await page.evaluate("$('bUndo').click()")
        # Undo may normalize segment metadata; original anchors and beat map are preserved.
        assert await page.evaluate('E.map(e=>[e.m,e.t])')==[[1,1],[9,17]]
        assert await page.evaluate("BEATS['2:0:4/4:4:1'].t")==3.7
        print('OK   settings invalidate preview; apply preserves anchors and undo restores original timing')
        # Mode/audio changes after preview must never apply old results.
        await page.evaluate('openGen()')
        await page.click('#gBrightPreview')
        await page.wait_for_function('brightPlan!==null&&!brightBusy')
        assert await page.evaluate("""()=>{
          const old=activeMode;activeMode='test-other';let blocked=false;
          try{generationForApply()}catch(e){blocked=true}activeMode=old;
          const sp=SPEC;SPEC={...sp};let audioBlocked=false;
          try{generationForApply()}catch(e){audioBlocked=true}SPEC=sp;
          return blocked&&audioBlocked;
        }""")
        await page.set_viewport_size({'width':390,'height':850})
        await page.locator('#gBrightPreview').scroll_into_view_if_needed()
        await page.screenshot(path='/tmp/sheetplayer-bright-generation.png')
        assert await page.locator('#gen>div').evaluate('(el)=>el.getBoundingClientRect().right<=innerWidth+1')
        assert not errors,errors
        print('OK   stale audio/mode previews rejected and mobile controls fit; no page errors')
        await browser.close()
try: asyncio.run(main())
finally: server.shutdown()
