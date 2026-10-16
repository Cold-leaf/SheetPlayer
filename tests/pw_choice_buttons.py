import asyncio,functools,http.server,threading
from pathlib import Path
from playwright.async_api import async_playwright
class Quiet(http.server.SimpleHTTPRequestHandler):
 def log_message(self,*a):pass
srv=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(Path(__file__).resolve().parents[1])))
threading.Thread(target=srv.serve_forever,daemon=True).start()
async def main():
 async with async_playwright() as p:
  b=await p.chromium.launch();pg=await b.new_page(viewport={'width':390,'height':844});errors=[];pg.on('pageerror',lambda e:errors.append(str(e)))
  await pg.goto(f'http://127.0.0.1:{srv.server_port}/player.html');await pg.wait_for_function('idb!==null')
  await pg.evaluate('''()=>{showLib(false);document.body.classList.remove('hidebar');pdfName='雪花的快乐.pdf';MODES={'标准':defaultModeData(),['音乐会超长名字'.repeat(25)]:defaultModeData()};syncModeSel();syncAudSel();}''')
  await pg.click('#pickMode');await pg.locator('#choiceItems button').nth(1).click()
  assert await pg.evaluate("activeMode.startsWith('音乐会')")
  await pg.click('#pickMode');assert await pg.locator('#choiceItems button[aria-pressed=true]').count()==1
  assert await pg.evaluate("$('choiceDialog').firstElementChild.scrollWidth<innerWidth")
  await pg.keyboard.press('Escape');assert not await pg.locator('#choiceDialog').is_visible()
  await pg.click('#pickAudio')
  async with pg.expect_file_chooser(): await pg.get_by_role('button',name='＋ 添加音频…',exact=True).click()
  await pg.click('#pickTrack');await pg.get_by_role('button',name='＋ 从 ownCloud 导入谱子…',exact=True).wait_for(state='visible')
  await pg.click('#choiceClose')
  for w in [320,390,700,1440]:
   await pg.set_viewport_size({'width':w,'height':900})
   assert await pg.evaluate("['pickTrack','pickAudio','pickMode'].every(id=>$(id).getBoundingClientRect().width<=160&&$(id).getBoundingClientRect().height>=44)")
  await pg.screenshot(path='/tmp/sheetplayer-choices.png')
  assert not errors,errors
  print('PASS mode selection/checkmark, long names, Escape, file chooser, import entries, four viewport widths')
  await b.close()
try:asyncio.run(main())
finally:srv.shutdown()
