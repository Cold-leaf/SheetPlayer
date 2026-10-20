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
        await pg.wait_for_function('()=>!!idb')
        await pg.set_input_files('#fPdf',str(PDF))
        await pg.click('#dlgProjNew')
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
        await pg.set_input_files('#fPdf',str(ROOT.parent/'SheetPlayerTests/AY_爱永在[简][SATB+NA+WO].pdf'))
        await pg.click('#dlgProjNew')
        await pg.wait_for_function('()=>pdfName.startsWith("AY_") && pageObj[1]')
        await pg.evaluate("""async()=>{
          M=[];
          const expectedRows=[
            [.265,[.268,.395,.534,.638,.765,.894]],
            [.478,[.296,.425,.569,.712,.898]],
            [.737,[.265,.412,.588,.740,.899]]];
          for(const [ny,expected] of expectedRows){
            const variants=[];
            for(const z of [.5,1,2]){
              zoom=z;applyZoom();const c=await recognitionCanvas(1);
              const sys=autoRowSystem(1,ny,c);
              if(!sys?.numbered||sys.staves.length!==4)throw Error('爱永在行定位错误 '+ny);
              const bars=detectRowBars(1,sys,.15,c);
              if(bars.length!==expected.length||bars.some((x,i)=>Math.abs(x-expected[i])>.004))throw Error('爱永在边界错误 '+ny+' '+bars);
              const tail=detectRowBars(1,sys,.54,c);
              if(JSON.stringify(tail)!==JSON.stringify(bars.filter(x=>x>.542)))throw Error('爱永在后半行不一致');
              variants.push(JSON.stringify({sys,bars}));
            }
            if(new Set(variants).size!==1)throw Error('爱永在缩放不一致');
          }
          $('mode').value='mark';syncMode();$('chkAutoRow').checked=true;
          const el=document.querySelector('.page'),r=el.getBoundingClientRect();
          await pagesEl.onclick({target:el,clientX:r.left+r.width*.15,clientY:r.top+r.height*.265});
          if(M.length!==6||M.some(m=>Math.abs(m.ny-.265)>.005))throw Error('实际点击未补齐第一行 '+JSON.stringify(M));
          for(const [ny,start,count] of [[.265,.12,6],[.478,.093,5],[.737,.093,5]]){
            const variants=[];
            for(const z of [.5,1,2])for(const dx of [-.004,.004]){
              M=[];syncNext();zoom=z;applyZoom();layout();
              const r=el.getBoundingClientRect();
              await pagesEl.onclick({target:el,clientX:r.left+r.width*(start+dx),clientY:r.top+r.height*ny});
              if(M.length!==count)throw Error('粗细行首重复计数 '+ny+' '+dx+' '+JSON.stringify(M));
              variants.push(JSON.stringify(M.map(m=>({nx:m.nx,m:m.m}))));
            }
            if(new Set(variants).size!==1)throw Error('粗细行首或缩放改变小节位置 '+ny+' '+variants);
          }

        }""")
        print('PASS 爱永在第一页三行：短小节线、页眉干扰、三档缩放、后半行补齐；第一行实际点击生成六个小节')
        await pg.evaluate("""async()=>{
          M=[];
          const rows=[
            [.145,[.214,.304,.393,.501,.591,.697,.787,.893]],
            [.446,[.231,.346,.428,.527,.641,.723,.794,.892]],
            [.746,[.205,.314,.393,.503,.582,.691,.783,.891]]];
          for(const [ny,expected] of rows){
            const variants=[];
            for(const z of [.5,1,2]){
              zoom=z;applyZoom();const c=await recognitionCanvas(5),sys=autoRowSystem(5,ny,c);
              if(!sys?.numbered||sys.staves.length!==4)throw Error('第5页行定位错误 '+ny);
              const bars=detectRowBars(5,sys,.12,c);
              if(bars.length!==8||bars.some((x,i)=>Math.abs(x-expected[i])>.004))throw Error('第5页数字误检或真线漏检 '+ny+' '+bars);
              const tail=detectRowBars(5,sys,.54,c);
              if(JSON.stringify(tail)!==JSON.stringify(bars.filter(x=>x>.542)))throw Error('第5页局部补齐不一致');
              variants.push(JSON.stringify(bars));
            }
            if(new Set(variants).size!==1)throw Error('第5页缩放不一致');
          }
          M=[];nextM=62;layout();
          const el=document.querySelector('.page[data-page="5"]'),r=el.getBoundingClientRect();
          await pagesEl.onclick({target:el,clientX:r.left+r.width*.085,clientY:r.top+r.height*.446});
          if(M.length!==8||M.some((m,i)=>m.m!==62+i))throw Error('第5页第2行实际补齐编号错误 '+JSON.stringify(M));
          if(Math.abs(M[5].nx-.641)>.004)throw Error('第67小节未落到真实边界');
        }""")
        print('PASS 爱永在第5页三行：真实边界、数字与重音误检排除、三档缩放；第2行实际补齐62至69小节')
        await pg.evaluate("""async()=>{
          const expected=[.200,.286,.359,.431,.650,.894];
          for(const z of [.5,1,2]){
            zoom=z;applyZoom();M=[];
            const c=await recognitionCanvas(7);
            for(const ny of [.418,.48,.53,.585]){
              const sys=autoRowSystem(7,ny,c),bars=detectRowBars(7,sys,.12,c);
              if(!sys?.numbered||sys.staves.length!==4||bars.length!==6||bars.some((x,i)=>Math.abs(x-expected[i])>.004))throw Error('第7页第2行识别错误 '+ny+' '+bars);
            }
            M=[];nextM=110;layout();
            const el=document.querySelector('.page[data-page="7"]'),r=el.getBoundingClientRect();
            await pagesEl.onclick({target:el,clientX:r.left+r.width*.086,clientY:r.top+r.height*.418});
            if(M.length!==6||M.some((m,i)=>m.m!==110+i)||Math.abs(M[5].nx-.650)>.004)throw Error('第115小节位置错误 '+JSON.stringify(M));
          }
        }""")
        print('PASS 爱永在第7页第2行：四声部点击、三档缩放、110至115小节，第115小节落在真实边界')
        assert not errors,errors
        await browser.close()
asyncio.run(main())
