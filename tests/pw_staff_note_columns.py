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
        await pg.wait_for_function('()=>pdf&&pageObj[pdf.numPages]')
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
        await pg.set_input_files('#fPdf',str(ROOT.parent/'SheetPlayerTests/AY_爱永在[线][SATB+NA+Pn].pdf'))
        await pg.click('#dlgProjNew')
        await pg.wait_for_function('()=>pdfName.startsWith("AY_")&&pageObj[8]')
        await pg.evaluate("""async()=>{
          const expected=[.215,.299,.383,.461,.539,.621,.695,.763,.827,.902];
          for(const z of [.5,1,2]){
            M=[];zoom=z;applyZoom();const c=await recognitionCanvas(8),sys=autoRowSystem(8,.575,c);
            const bars=detectRowBars(8,sys,.15,c);
            if(bars.length!==10||bars.some((x,i)=>Math.abs(x-expected[i])>.004))throw Error('标号17页第二行漏检/误检 '+bars);
            const tail=detectRowBars(8,sys,.42,c);
            if(JSON.stringify(tail)!==JSON.stringify(bars.filter(x=>x>.422)))throw Error('局部识别不一致');
            $('mode').value='mark';syncMode();$('chkAutoRow').checked=true;nextM=98;layout();
            const el=document.querySelector('.page[data-page="8"]'),r=el.getBoundingClientRect();
            await pagesEl.onclick({target:el,clientX:r.left+r.width*.095,clientY:r.top+r.height*.575});
            if(M.length!==10||M.some((m,i)=>m.m!==98+i))throw Error('98至107小节实际补齐失败');
          }
        }""")
        print('PASS 爱永在标号17页第二行：98至107小节完整补齐，三档缩放与局部识别一致')
        await pg.evaluate("""async()=>{
          for(const [ny,start,expected] of [[.13,126,[.327,.536,.726,.913]],[.60,130,[.344,.540,.751,.918]]]){
            const variants=[];
            for(const z of [.5,1,2]){
              M=[];zoom=z;applyZoom();const c=await recognitionCanvas(11),sys=autoRowSystem(11,ny,c);
              const bars=detectRowBars(11,sys,.15,c);
              if(sys?.staves.length!==6||bars.length!==4||bars.some((x,i)=>Math.abs(x-expected[i])>.005))throw Error('标号20页倾斜识别错误 '+ny+' '+JSON.stringify({sys,bars}));
              variants.push(JSON.stringify(bars));
              nextM=start;layout();const el=document.querySelector('.page[data-page="11"]'),r=el.getBoundingClientRect();
              await pagesEl.onclick({target:el,clientX:r.left+r.width*.11,clientY:r.top+r.height*ny});
              if(M.length!==4||M.some((m,i)=>m.m!==start+i))throw Error('标号20页实际补齐错误 '+JSON.stringify(M));
            }
            if(new Set(variants).size!==1)throw Error('倾斜页识别随缩放改变');
          }
        }""")
        print('PASS 爱永在标号20页两行：六谱表完整识别，126至133小节、三档缩放实际补齐')
        edges=[]
        for z in [.5,1,2]:
            await pg.evaluate("""z=>{
              zoom=z;applyZoom();recognitionPages.clear();rowEdgeCache.clear();
              M=[{page:9,nx:.726,ny:.144,h:.32,m:115}];E=[{m:115,t:0}];layout();
              $('chkProg').checked=true;rowRightEdge(M[0]);
            }""",z)
            await pg.wait_for_function('()=>recognitionPages.has(9)&&rowEdgePending.size===0')
            edge=await pg.evaluate("""()=>{
              const i=OCC.findIndex(o=>o.m===115);updateProg(.5,i,OCC[i]);
              return (parseFloat(bandEl.style.left)+parseFloat(bandEl.style.width))/100;
            }""")
            assert abs(edge-.909)<.008,edge
            edges.append(edge)
        assert max(edges)-min(edges)<.0001,edges
        print('PASS 标号18页第一行末小节：无识别缓存时自动加载固定精度画布，三档缩放橙色范围一致',edges)
        await pg.evaluate("""async()=>{
          const results=[];
          for(const z of [.5,1,2]){
            zoom=z;applyZoom();await recognitionCanvas(8);
            const sys=autoRowSystem(8,.575,recognitionPages.get(8));
            const mk={page:8,nx:.216,ny:sys.top,h:sys.bot-sys.top,m:98};
            M=[mk];$('chkSnapX').checked=true;$('chkAlignY').checked=false;
            await applySnaps(mk);
            if(Math.abs(mk.nx-.215)>.004)throw Error('固定精度吸附未命中 '+mk.nx);
            results.push(mk.nx);
          }
          if(Math.max(...results)-Math.min(...results)>.001)throw Error('吸附位置随缩放改变 '+results);
          recognitionPages.clear();
          const mk=M[0],old=mk.nx;
          const pending=applySnaps(mk);M=[];await pending;
          if(mk.nx!==old)throw Error('异步吸附修改已删除标记');
        }""")
        print('PASS 手动/拖动共用吸附：三档缩放命中同一边界，异步期间删除标记不被修改')
        assert not errors,errors
        await browser.close()
asyncio.run(main())
