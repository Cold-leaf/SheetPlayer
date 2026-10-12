"""Real numbered-score regression: row selection, note false positives, partial fill and zoom."""
import asyncio, functools, http.server, socketserver, threading
from pathlib import Path
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parents[1]
PDF=ROOT.parent/'SheetPlayerTests/XH_雪花的快乐[简][SATB+NA+WO].pdf'
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
        await pg.set_input_files('#fPdf',str(PDF))
        await pg.wait_for_function('()=>pdf&&pageObj[2]')
        result=await pg.evaluate("""async()=>{
          const c=await recognitionCanvas(1);M=[];
          const out=[];
          for(const ny of [.181,.342,.556,.783]){
            const variants=[];
            for(const z of [.5,1,2]){
              zoom=z;applyZoom();const image=await recognitionCanvas(1);
              const sys=autoRowSystem(1,ny,image);
              if(!sys||!sys.numbered||Math.abs(sys.top-ny)>.012)throw Error('行错位 '+ny);
              const lines=detectRowBars(1,sys,.11,image);
              if(lines.length!==6)throw Error('小节线误检/漏检 '+ny+' '+lines);
              const expected=ny===.783?[.233,.366,.520,.680,.820,.957]:null;
              if(expected&&lines.some((x,i)=>Math.abs(x-expected[i])>.004))throw Error('第 28 小节行识别位置错误 '+lines);
              const tail=detectRowBars(1,sys,.52,image);
              if(JSON.stringify(tail)!==JSON.stringify(lines.filter(x=>x>.522)))throw Error('补后半行改变识别');
              variants.push(JSON.stringify({sys,lines}));
            }
            if(new Set(variants).size!==1)throw Error('缩放不一致');
            out.push(ny);
          }
          return out;
        }""")
        print('PASS 雪花第 1 页四行：点击定位、六条边界、后半行补齐、三档缩放',result)
        result=await pg.evaluate("""async()=>{
          M=[];const results=[];
          for(const [ny,expected] of [
            [.10,[.257,.396,.528,.677,.828,.966]],
            [.35,[.235,.383,.530,.672,.817,.964]],
            [.59,[.253,.398,.541,.681,.826,.965]],
            [.84,[.257,.399,.540,.683,.820,.961]]]){
            const variants=[];
            for(const z of [.5,1,2]){
              zoom=z;applyZoom();const c=await recognitionCanvas(2);
              const sys=autoRowSystem(2,ny,c);
              if(!sys?.numbered||sys.staves.length!==4)throw Error('第 2 页声部点击识别错误 '+ny);
              const bars=detectRowBars(2,sys,.12,c);
              if(bars.length!==6||bars.some((x,i)=>Math.abs(x-expected[i])>.004))throw Error('第 2 页边界错误 '+bars);
              variants.push(JSON.stringify({sys,bars}));
            }
            if(new Set(variants).size!==1)throw Error('第 2 页缩放不一致');
            results.push(ny);
          }
          return results;
        }""")
        print('PASS 雪花第 2 页四行：中间声部点击、真实边界位置、三档缩放',result)
        assert not errors,errors
        await browser.close()
asyncio.run(main())
