"""Clean playback preserves hit targets and restores full strokes in editing."""
import asyncio, functools, http.server, threading
from pathlib import Path
from playwright.async_api import async_playwright
ROOT = Path(__file__).resolve().parents[1]
class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args): pass

def pdf_bytes():
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>',
               b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 400] /Resources << >> >>']
    data = b'%PDF-1.4\n'; offsets = [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(data)); data += f'{i} 0 obj\n'.encode() + obj + b'\nendobj\n'
    start = len(data)
    data += b'xref\n0 4\n0000000000 65535 f \n'
    data += b''.join(f'{o:010d} 00000 n \n'.encode() for o in offsets[1:])
    return data + f'trailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n'.encode()

async def main():
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=str(ROOT)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
      async with async_playwright() as pw:
        browser=await pw.chromium.launch()
        page=await browser.new_page(viewport={'width':1200,'height':900})
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        await page.goto(f'http://127.0.0.1:{server.server_port}/player.html')
        await page.wait_for_function('()=>!!idb')
        await page.set_input_files('#fPdf',{'name':'test.pdf','mimeType':'application/pdf','buffer':pdf_bytes()})
        await page.click('#dlgProjNew')
        await page.wait_for_function('()=>!!pdf')
        await page.evaluate("""()=>{
          M=[{m:1,page:1,nx:.2,ny:.25,h:.2},{m:2,page:1,nx:.6,ny:.25,h:.2}];
          E=[{m:1,t:0},{m:2,t:4}];layout();
          $('mode').value='play';$('chkBeats').checked=true;syncMode();refresh();
        }""")
        await page.wait_for_function("()=>document.querySelector('.mk.cur')")
        assert await page.evaluate("getComputedStyle(document.querySelector('.mk')).width==='44px'")
        assert await page.evaluate("""()=>[...document.querySelectorAll('.mk>b,.beatMark>b')].every(b=>
          Math.abs(b.getBoundingClientRect().height-b.parentElement.getBoundingClientRect().height)<1 &&
          +getComputedStyle(b).opacity>0 && +getComputedStyle(b).opacity<=.4)""")
        assert await page.locator('#chkFullLines').count()==0
        await page.evaluate("()=>{setPerf(false);$('mode').value='mark';syncMode()}")
        assert await page.evaluate("!pagesEl.classList.contains('cleanPlay')")
        await page.evaluate("()=>{$('mode').value='play';syncMode();setPerf(true)}")
        assert await page.evaluate("pagesEl.classList.contains('cleanPlay')")
        for width in [390,820,1200]:
          await page.set_viewport_size({'width':width,'height':900})
          assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        assert not errors,errors
        print('OK clean playback strokes, retained hit areas, full-length translucent lines, edit mode and mobile layout')
        await browser.close()
    finally:server.shutdown()
asyncio.run(main())
