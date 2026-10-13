"""Switch actual library songs and verify media rate, UI and elapsed audio time."""
import asyncio, functools, http.server, pathlib, tempfile, threading, wave
from playwright.async_api import async_playwright
ROOT=pathlib.Path(__file__).resolve().parents[1]
PDF=ROOT.parent/'线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf'
class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*args): pass
srv=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(ROOT)))
threading.Thread(target=srv.serve_forever,daemon=True).start()
async def main():
  with tempfile.TemporaryDirectory() as tmp:
    async with async_playwright() as pw:
      browser=await pw.chromium.launch(args=['--autoplay-policy=no-user-gesture-required'])
      pg=await browser.new_page(viewport={'width':1440,'height':950})
      errors=[];pg.on('pageerror',lambda e:errors.append(str(e)))
      await pg.goto(f'http://127.0.0.1:{srv.server_port}/player.html')
      await pg.wait_for_function('()=>idb!==null')
      ids=[]
      for i in range(2):
        pdf=pathlib.Path(tmp)/f'score{i}.pdf';pdf.write_bytes(PDF.read_bytes()+f'\n% rate fixture {i}\n'.encode())
        wav=pathlib.Path(tmp)/f'tone{i}.wav'
        with wave.open(str(wav),'wb') as f:
          f.setnchannels(1);f.setsampwidth(2);f.setframerate(8000);f.writeframes(b'\0\0'*8000*(20+i))
        await pg.set_input_files('#fPdf',str(pdf))
        await pg.wait_for_function("()=>pdf && $('lib').style.display==='none'")
        await pg.set_input_files('#fAud',str(wav))
        await pg.wait_for_selector('#dlgMode',state='visible');await pg.click('#dlgModeOk')
        await pg.wait_for_function('(d)=>aud.readyState>=2 && aud.duration===d',arg=20+i)
        await pg.wait_for_function("()=>document.querySelector('.page[data-page=\"1\"]')?.dataset.done")
        ids.append(await pg.evaluate('pid'))
      assert ids[0]!=ids[1]
      async def check_rate(rate):
        assert await pg.evaluate('(r)=>aud.playbackRate===r && aud.defaultPlaybackRate===r && +$("rate").value===r && +$("rehRate").value===r',rate)
      for rate in [.5,.1,4]:
        await pg.select_option('#rate',str(rate))
        await check_rate(rate)
        target=ids[0] if await pg.evaluate('pid')==ids[1] else ids[1]
        await pg.click('#bLib')
        await pg.wait_for_function("()=>$('lib').style.display==='flex'")
        await pg.wait_for_selector('.libCard')
        await pg.locator('.libCard').filter(has_text='score'+str(ids.index(target))).locator('button.open').click()
        await pg.wait_for_function('(id)=>pid===id && aud.readyState>=2',arg=target)
        await check_rate(rate)
        await pg.evaluate('aud.currentTime=1;aud.play()')
        await pg.wait_for_timeout(150)
        before=await pg.evaluate('({t:aud.currentTime,wall:performance.now()})')
        await pg.wait_for_timeout(700)
        after=await pg.evaluate('({t:aud.currentTime,wall:performance.now()})')
        measured=(after['t']-before['t'])/((after['wall']-before['wall'])/1000)
        assert abs(measured-rate)<max(.08,rate*.2),(rate,measured)
        await pg.evaluate('aud.pause()')
        print(f'OK    Library song switch preserves {rate}x; measured playback {measured:.2f}x')
      await pg.evaluate('setBarHidden(true)')
      await pg.select_option('#rehRate','2.5');await check_rate(2.5)
      await pg.evaluate('aud.load()');await pg.wait_for_function('()=>aud.readyState>=2');await check_rate(2.5)
      assert not errors,errors
      print('OK    Compact control, media reload and both rate displays stay synchronized')
      await browser.close()
try: asyncio.run(main())
finally: srv.shutdown()
