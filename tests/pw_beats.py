"""Beat layer: production UI, independent timing, repeat visits, persistence and undo."""
import asyncio, base64, functools, http.server, io, pathlib, threading, wave
from playwright.async_api import async_playwright
ROOT = pathlib.Path(__file__).resolve().parents[1]
PDF = ROOT.parent / '线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf'
class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args): pass
srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=str(ROOT)))
threading.Thread(target=srv.serve_forever, daemon=True).start()

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=['--autoplay-policy=no-user-gesture-required'])
        page = await browser.new_page(viewport={'width':1400,'height':1000})
        errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        await page.goto(f'http://127.0.0.1:{srv.server_port}/player.html?direct=1')
        await page.set_input_files('#fPdf',str(PDF))
        await page.wait_for_function('()=>boxes[1] && pdf!==null')
        await page.evaluate("""()=>{
          setPerf(false);M=[1,2,3].map((m,i)=>({m,page:1,nx:.15+i*.3,ny:.2,h:.12}));
          E=[{m:1,t:0,src:'tap'},{m:2,t:3,src:'tap'},{m:1,t:6,src:'tap'},
             {m:2,t:9,src:'tap'},{m:3,t:12,src:'gen'}];
          METER=[{sig:[3,4],ranges:[]}];BEATS={};hist=[];layout();
          $('mode').value='play';syncMode();
        }""")
        audio=io.BytesIO()
        with wave.open(audio,'wb') as f:
            f.setnchannels(1);f.setsampwidth(2);f.setframerate(8000);f.writeframes(b'\0\0'*8000*20)
        await page.evaluate('(src)=>{aud.src=src;aud.load()}', 'data:audio/wav;base64,'+base64.b64encode(audio.getvalue()).decode())
        await page.wait_for_function('()=>aud.readyState>=2')
        await page.check('#chkBeats')
        assert await page.locator('.beatMark').count()==6
        assert await page.evaluate('beatPoints(M[0],0).map(p=>p.t)')==[1,2]
        assert await page.evaluate('beatPoints(M[0],1).map(p=>p.t)')==[7,8]
        print('OK    3/4 creates two internal lines; repeat visits have independent times')
        first=page.locator('.beatMark[data-m="1"][data-beat="1"]')
        third=page.locator('.beatMark[data-m="1"][data-beat="2"]')
        await first.click()
        assert abs(await page.evaluate('aud.currentTime')-1)<.02
        assert await page.evaluate('aud.paused') and await page.locator('#beatPanel').is_hidden()
        await first.click()
        assert abs(await page.evaluate('aud.currentTime')-7)<.02
        await third.click()
        assert abs(await page.evaluate('aud.currentTime')-8)<.02
        await page.click('#bBeatEdit')
        assert await page.input_value('#beatNumber')=='2'
        assert await page.input_value('#beatVisit')=='1'
        await page.select_option('#beatNumber','1')
        assert await page.input_value('#beatTime')=='7.000'
        await page.click('#beatClose')
        await page.evaluate('lastSeek=null;aud.currentTime=0;aud.play()')
        await third.click()
        assert not await page.evaluate('aud.paused')
        assert 2<=await page.evaluate('aud.currentTime')<2.5
        await page.evaluate('aud.pause();aud.currentTime=0;lastSeek=null')
        await page.locator('.mk[data-m="1"]').dblclick()
        assert abs(await page.evaluate('aud.currentTime')-6)<.02
        assert await page.locator('#beatPanel').is_hidden()
        await first.click()
        assert abs(await page.evaluate('aud.currentTime')-7)<.02
        await page.locator('.mk[data-m="1"]').click()
        assert abs(await page.evaluate('aud.currentTime')-6)<.02
        await page.evaluate('aud.currentTime=0;lastSeek=null')
        print('OK    Beat clicks seek without editing, cycle visits, preserve playback, and select the editor target')
        await page.evaluate('openBeatPanel(M[0],1,0)')
        await page.fill('#beatTime','1.2');await page.locator('#beatTime').dispatch_event('change')
        assert await page.evaluate('beatPoints(M[0],0)[0].manual')
        assert await page.evaluate('beatPoints(M[0],1)[0].t')==7
        assert await page.evaluate('E.length')==5
        assert await page.evaluate('''()=>{updateProg(1.2,0,OCC[0]);
          const expected=(M[0].nx+(beatRight(M[0])-M[0].nx)/3)*100;
          return Math.abs(parseFloat(sweepEl.style.left)-expected)<.001}''')
        await page.fill('#beatTime','2.5');await page.locator('#beatTime').dispatch_event('change')
        assert await page.evaluate('beatPoints(M[0],0)[0].t')==1.2
        assert '前后拍' in await page.inner_text('#msg')
        print('OK    Manual edit affects only selected visit; out-of-order times are rejected')
        await page.evaluate('undo()')
        assert await page.evaluate('beatPoints(M[0],0)[0].t')==1, await page.evaluate('({BEATS,hist})')
        await page.evaluate("SPEC={onsets:Float32Array.from([1.05]),onsetStr:Float32Array.from([1])};openBeatPanel(M[0],1,0)")
        await page.click('#beatSnap')
        assert await page.evaluate("beatPoints(M[0],0)[0].adjusted && !beatPoints(M[0],0)[0].manual")
        assert await page.evaluate("E.filter(e=>e.src!=='gen').length")==4
        await page.evaluate('E[1].t=3.6;refresh()')
        assert await page.evaluate('beatPoints(M[0],0)[0].t')==1.2
        await page.evaluate('E[1].t=3;refresh();openBeatPanel(M[0],1,0)')
        await page.click('#beatClose')
        await page.evaluate('SPEC=null')
        el=page.locator('.beatMark[data-m="1"][data-beat="1"]')
        box=await el.bounding_box(); x=box['x']+box['width']/2;y=box['y']+box['height']/2
        before=await page.evaluate('beatPoints(M[0],0)[0].t')
        await page.mouse.move(x,y);await page.mouse.down();await page.mouse.move(x+25,y,steps=5);await page.mouse.up()
        assert await page.evaluate('beatRatio(M[0],1)')>1/3
        assert await page.evaluate('beatPoints(M[0],0)[0].t')==before
        assert await page.evaluate('pureM()[0].beatPositions')
        assert abs(await page.evaluate('aud.currentTime'))<.02
        shown=await page.evaluate('(()=>{updateProg(1.05,0,OCC[0]);return sweepEl.style.left})()')
        await page.uncheck('#chkBeats')
        assert await page.evaluate('(()=>{updateProg(1.05,0,OCC[0]);return sweepEl.style.left})()')==shown
        await page.check('#chkBeats')
        print('OK    Automatic snap remains inferred; dragging edits only score position')
        await page.evaluate("aud.currentTime=1;specShow(true);$('chkSnap').checked=false;drawSpec()")
        assert await page.evaluate('''()=>{
          const ctx=$('specCv').getContext('2d'),labels=[],original=ctx.fillText;
          ctx.fillText=function(text,...args){labels.push(String(text));return original.call(this,text,...args)};
          try{drawSpec()}finally{ctx.fillText=original}
          return labels.includes('1.2')&&labels.includes('1.3');
        }''')
        await page.screenshot(path='/tmp/sheetplayer-beat-spectrum.png')
        async def drag_spec(target, delta):
            rect=await page.locator('#specCv').bounding_box()
            x=await page.evaluate('(t)=>(t-specT0())*specPPS',target)
            await page.mouse.move(rect['x']+x,rect['y']+40)
            await page.mouse.down()
            await page.mouse.move(rect['x']+x+delta,rect['y']+40,steps=5)
            await page.mouse.up()
        event_data=await page.evaluate('JSON.stringify(E)')
        old_pos=await page.evaluate('beatRatio(M[0],1)')
        old_hist=await page.evaluate('hist.length')
        await drag_spec(before,32)
        assert abs(await page.evaluate('beatPoints(M[0],0)[0].t')-(before+.2))<.005
        assert await page.evaluate('beatPoints(M[0],0)[0].manual')
        assert await page.evaluate('beatPoints(M[0],1)[0].t')==7
        assert await page.evaluate('beatRatio(M[0],1)')==old_pos
        assert await page.evaluate('JSON.stringify(E)')==event_data
        assert await page.evaluate('hist.length')==old_hist+1
        await page.evaluate('undo()')
        assert await page.evaluate('beatPoints(M[0],0)[0].t')==before
        await drag_spec(before,300)
        assert 1.99<await page.evaluate('beatPoints(M[0],0)[0].t')<2
        await page.evaluate('undo()')
        await page.evaluate("SPEC={onsets:Float32Array.from([1.3]),onsetStr:Float32Array.from([1])};$('chkSnap').checked=true")
        await drag_spec(before,32)
        assert abs(await page.evaluate('beatPoints(M[0],0)[0].t')-1.3)<.001
        await page.evaluate('undo();SPEC=null')
        # Cancel a live drag without adding history or saving a partial edit.
        rect=await page.locator('#specCv').bounding_box()
        x=await page.evaluate('(t)=>(t-specT0())*specPPS',before)
        await page.mouse.move(rect['x']+x,rect['y']+40);await page.mouse.down()
        await page.mouse.move(rect['x']+x+25,rect['y']+40)
        await page.locator('#specCv').dispatch_event('pointercancel')
        await page.mouse.up()
        assert await page.evaluate('beatPoints(M[0],0)[0].t')==before
        await page.evaluate('setPerf(true)')
        await page.uncheck('#chkBeats');assert await page.locator('.beatMark').count()==0
        await page.check('#chkBeats');assert await page.locator('.beatMark').count()>0
        await page.evaluate('aud.currentTime=1')
        await drag_spec(before,32)
        assert await page.evaluate('beatPoints(M[0],0)[0].t')==before
        await page.evaluate('setPerf(false);aud.currentTime=0;specShow(false)')
        print('OK    Spectrum beat drag edits only this visit; bounds, snapping, undo, cancel and performance toggle/lock work')
        await page.evaluate('window.savedBeatData=annotationData();BEATS={};M=[];applySave(savedBeatData);layout()')
        assert await page.evaluate('beatRatio(M[0],1)')>1/3
        assert await page.evaluate('beatPoints(M[0],0)[0].t')==before
        await page.evaluate("newMode('另一版',true);switchMode('另一版')")
        assert await page.evaluate('Object.keys(BEATS).length')==0
        await page.evaluate("switchMode('标准')")
        assert await page.evaluate('beatPoints(M[0],0)[0].t')==before
        # Persist a manual edit and move its measure boundary past it: retain and flag it.
        await page.evaluate('openBeatPanel(M[0],1,0)')
        await page.fill('#beatTime','1.2');await page.locator('#beatTime').dispatch_event('change')
        await page.evaluate('E[0].t=1.5;refresh()')
        assert await page.evaluate('beatPoints(M[0],0)[0].t')==1.2
        assert await page.evaluate('beatPoints(M[0],0)[0].conflict')
        print('OK    Save/restore and audio mode isolation; changed boundaries flag manual conflicts')
        await page.evaluate("E[0].t=0;METER=[{sig:[4,4],ranges:[]}];refresh()")
        assert await page.locator('.beatMark[data-m="1"]').count()==3
        await page.evaluate("METER=[{sig:[6,8],ranges:[]}];refresh();openBeatPanel(M[0],1,0)")
        assert await page.locator('.beatMark[data-m="1"]').count()==1
        await page.fill('#beatCountInput','6');await page.locator('#beatCountInput').dispatch_event('change')
        assert await page.locator('.beatMark[data-m="1"]').count()==5
        await page.fill('#beatCountInput','1');await page.locator('#beatCountInput').dispatch_event('change')
        assert await page.locator('.beatMark[data-m="1"]').count()==0
        await page.evaluate('undo()')
        assert await page.locator('.beatMark[data-m="1"]').count()==5
        await page.evaluate('openBeatPanel(M[0],1,0)')
        await page.screenshot(path='/tmp/sheetplayer-beats-desktop.png')
        assert await page.evaluate('beatPoints(M[2],0).every(p=>p.estimated)')
        assert await page.evaluate('''()=>{const w=beatWindow(M[2],0),i=OCC.length-1;
          updateProg(w.end+.1,i,OCC[i]);
          return Math.abs(parseFloat(sweepEl.style.left)-beatRight(M[2])*100)<.001}''')
        await page.evaluate('M[1].ny=.6;refresh()')
        assert await page.evaluate('Array.from(document.querySelectorAll(\'.beatMark[data-m="1"]\')).every(e=>parseFloat(e.style.top)===20)')
        print('OK    4/4, compound-meter subdivisions, pickup override, undo, final estimate and row end')
        await page.uncheck('#chkBeats');assert await page.locator('.beatMark').count()==0
        await page.check('#chkBeats');assert await page.locator('.beatMark').count()>0
        await page.evaluate('setPerf(true);aud.currentTime=0;lastSeek=null')
        await page.locator('.beatMark[data-m="1"]').first.click()
        assert abs(await page.evaluate('aud.currentTime')-.5)<.02
        assert await page.locator('#beatPanel').is_hidden()
        await page.evaluate("setPerf(false);$('mode').value='time';syncMode()")
        assert await page.locator('.beatMark').count()>0
        await page.set_viewport_size({'width':390,'height':844})
        await page.evaluate("$('mode').value='play';syncMode();setPerf(true)")
        await page.uncheck('#chkBeats');assert await page.locator('.beatMark').count()==0
        await page.check('#chkBeats');assert await page.locator('.beatMark').count()>0
        await page.evaluate('setPerf(false)')
        await page.evaluate("$('mode').value='play';syncMode();openBeatPanel(M[0],1,0)")
        rect=await page.locator('#beatPanel').bounding_box()
        assert rect['x']>=0 and rect['x']+rect['width']<=390
        await page.screenshot(path='/tmp/sheetplayer-beats-mobile.png')
        assert not errors,errors
        print('OK    Hide/show preserves data; performance lock prevents edits; no browser errors')
        await page.keyboard.press('Escape')
        assert await page.locator('#beatPanel').is_hidden()
        expected=await page.evaluate('JSON.stringify({M:pureM(),BEATS})')
        await page.evaluate('async()=>{save();await flushSave()}')
        await page.reload()
        await page.set_input_files('#fPdf',str(PDF))
        await page.wait_for_function('()=>M.length===3 && pdf!==null')
        assert await page.evaluate('JSON.stringify({M:pureM(),BEATS})')==expected
        assert not errors,errors
        print('OK    Escape closes editor; beat positions and times survive browser reload')
        await browser.close()
try: asyncio.run(main())
finally: srv.shutdown()
