"""Returning through library/playlist preserves the current playback session."""
import asyncio, functools, http.server, socketserver, threading, tempfile, wave
from pathlib import Path
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parents[1]
PDF=ROOT.parent/'线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf'
class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*args): pass
srv=socketserver.TCPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(ROOT)))
threading.Thread(target=srv.serve_forever,daemon=True).start()
URL=f'http://127.0.0.1:{srv.server_address[1]}/player.html'
def check(value,label):
    assert value,label
    print('OK   '+label,flush=True)
async def library(pg):
    await pg.click('#bLib')
    await pg.wait_for_selector('.libCard')
async def main():
  with tempfile.TemporaryDirectory() as tmp:
    files=[]
    for duration in [30,45]:
      path=Path(tmp)/f'tone{duration}.wav'
      with wave.open(str(path),'wb') as f:
        f.setnchannels(1);f.setsampwidth(2);f.setframerate(8000);f.writeframes(b'\0\0'*8000*duration)
      files.append(path)
    async with async_playwright() as pw:
      browser=await pw.chromium.launch()
      pg=await browser.new_page(viewport={'width':1440,'height':900})
      errors=[];pg.on('pageerror',lambda e:errors.append(str(e)))
      await pg.goto(URL);await pg.wait_for_function('()=>idb!==null')
      await pg.set_input_files('#fPdf',str(PDF))
      await pg.wait_for_function("()=>pdf && $('lib').style.display==='none'")
      for f in files:
        await pg.set_input_files('#fAud',str(f));await pg.wait_for_selector('#dlgMode',state='visible');await pg.click('#dlgModeOk')
        await pg.wait_for_function('(n)=>track.audios.length===n',arg=files.index(f)+1)
      await pg.wait_for_function('()=>aud.duration===45')
      await pg.evaluate("()=>{aud.pause();aud.currentTime=8;setRate(1.25);window.score=pdf;window.source=aud.src;window.loads=0;aud.addEventListener('loadstart',()=>window.loads++);window.audio=loadedAudioHash;window.project=pid;window.zoomBefore=zoom;}")
      await library(pg);await pg.click('.libCard .open')
      check(await pg.evaluate('pdf===window.score && aud.src===window.source && loads===0'),'项目打开复用谱面和音频，不重新加载')
      check(await pg.evaluate('aud.paused && Math.abs(aud.currentTime-8)<.1 && aud.playbackRate===1.25 && zoom===zoomBefore'),'暂停返回保留进度、暂停状态、倍速和缩放')
      await pg.click('#bPlay');await pg.wait_for_timeout(250)
      await library(pg);await pg.click('.libCard .open')
      check(await pg.evaluate('!aud.paused && aud.currentTime>=8 && loads===0'),'播放中从曲目库返回不中断、不归零')
      await pg.evaluate('aud.pause();aud.currentTime=11')
      await library(pg);await pg.click('.libCard .pladd');await pg.wait_for_selector('#plList [data-play]')
      await pg.click('#plList [data-play="0"]')
      await pg.wait_for_function('()=>!aud.paused')
      check(await pg.evaluate('aud.currentTime>=11 && aud.src===window.source && pdf===window.score && loads===0'),'播放列表播放当前曲目从暂停位置继续')
      await library(pg);await pg.locator('#plList .plRow .nm').click()
      check(await pg.evaluate('!aud.paused && aud.currentTime>=11 && loads===0'),'点击播放列表整行也保留当前播放')
      await library(pg);await pg.click('#plStart')
      check(await pg.evaluate('aud.currentTime>=11 && loads===0'),'开始播放列表时当前首曲继续播放')
      await pg.click('#plNow');await pg.click('#plPopList [data-play="0"]')
      check(await pg.evaluate('aud.currentTime>=11 && loads===0'),'浮动播放列表的播放按钮同样续播')
      # Selecting a different audio variant is a new playback request.
      await library(pg)
      first=await pg.evaluate('track.audios[0].hash')
      await pg.select_option('#plList select',first)
      await pg.click('#plList [data-play="0"]')
      await pg.wait_for_function('(h)=>loadedAudioHash===h && !aud.paused',arg=first)
      check(await pg.evaluate('aud.currentTime<3 && aud.src!==window.source'),'同一曲目换音频版本从头开始，不沿用旧音频进度')
      # Natural single-item loop must restart, not reuse the ended session.
      await pg.evaluate('aud.currentTime=aud.duration-.2')
      await pg.wait_for_function('()=>!aud.paused && aud.currentTime<3',timeout=10000)
      check(await pg.evaluate('plOn && plIdx===0'),'单曲播放列表自然结束仍能从头循环')
      # Next/previous navigation is distinct from returning from the library.
      await pg.evaluate('aud.currentTime=9')
      await pg.click('#plNext');await pg.wait_for_function('()=>aud.currentTime<3 && !aud.paused')
      check(await pg.evaluate('aud.currentTime<3'),'单曲列表点下一首仍从头开始')
      # A different project can share both blobs; project identity must still differ.
      second=await pg.evaluate("async()=>{const p=structuredClone(track);p.id=newId();p.name='另一首曲目';await idbPut(idb,'projects',p);return p.id}")
      await pg.evaluate('aud.pause();aud.currentTime=7')
      await library(pg);await pg.locator('.libCard',has_text='另一首曲目').locator('.open').click()
      await pg.wait_for_function('(id)=>pid===id && aud.duration===30',arg=second)
      check(await pg.evaluate('aud.currentTime<1 && pdf!==window.score'),'不同项目即使共用文件也重新加载')
      check(not errors,'无浏览器运行错误: '+str(errors))
      await browser.close()
  srv.shutdown()
asyncio.run(main())
