"""Real numbered-score regression: row selection, note false positives, partial fill and zoom."""
import asyncio, functools, http.server, socketserver, threading
from pathlib import Path
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parents[1]
PDF=ROOT.parent/'SheetPlayerTests/XH_雪花的快乐[线][SATB+NA+Pn].pdf'
class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*args): pass
srv=socketserver.TCPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(ROOT)))
threading.Thread(target=srv.serve_forever,daemon=True).start()
async def main():
    async with async_playwright() as p:
        browser=await p.chromium.launch()
        pg=await browser.new_page()
        errors=[];pg.on('pageerror',lambda e:errors.append(str(e)))
        await pg.goto(f'http://127.0.0.1:{srv.server_address[1]}/player.html')
        await pg.wait_for_function('()=>!!idb')
        await pg.set_input_files('#fPdf',str(PDF))
        await pg.click('#dlgProjNew')
        await pg.wait_for_function('()=>pdf&&pageObj[2]')
        result=await pg.evaluate("""async()=>{
          const n=pdf.numPages,c=await recognitionCanvas(n),st=staves(n,c);
          const rows=[st[0].top,st[6].top],out=[];
          for(let i=0;i<rows.length;i++){
            const variants=[];
            for(const z of [.5,1,2]){
              zoom=z;applyZoom();const image=await recognitionCanvas(n),sys=autoRowSystem(n,rows[i],image);
              const bars=detectRowBars(n,sys,.13,image);
              const expected=i===0?[.3225,.5196,.717,.9129]:[.3068,.4881,.6704,.9035];
              if(bars.length!==4||bars.some((x,k)=>Math.abs(x-expected[k])>.008))throw Error('真实小节线错误 '+i+' '+bars);
              if(bars.some(x=>Math.abs(x-.1505)<.01||Math.abs(x-.218)<.01))throw Error('音符符干误检');
              variants.push(JSON.stringify(bars));
            }
            if(new Set(variants).size!==1)throw Error('缩放不一致');
            out.push(JSON.parse(variants[0]));
          }
          return out;
        }""")
        print('PASS 雪花线谱最后一页两行：音符误检排除、真实边界保留、三档缩放',result)
        assert not errors,errors
        await browser.close()
asyncio.run(main())
