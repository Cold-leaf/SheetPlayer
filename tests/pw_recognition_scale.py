"""Fixed recognition resolution and manually anchored numbered-score rows."""
import asyncio, functools, http.server, socketserver, threading
from pathlib import Path
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parents[1]
PDF=ROOT.parent/'线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf'
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
        result=await pg.evaluate('''async()=>{
          const results=[];
          for(const z of [.5,1,2]){
            zoom=z;applyZoom();
            const c=await recognitionCanvas(2),st=staves(2,c);
            if(!st.length)throw Error('真实五线谱未识别');
            const sys=systemAt(2,(st[0].top+st[0].bot)/2,c);
            results.push({w:c.width,h:c.height,sys,bars:detectRowBars(2,sys,0,c)});
          }
          if(results.some(x=>JSON.stringify(x)!==JSON.stringify(results[0])))throw Error('缩放改变识别');
          if(results[0].bars.length<2)throw Error('真实谱页未检测到小节线');
          const c=document.createElement('canvas');c.width=1000;c.height=1400;
          const ctx=c.getContext('2d');ctx.fillStyle='white';ctx.fillRect(0,0,1000,1400);
          ctx.fillStyle='black';ctx.font='28px serif';
          for(const y of [720,780,840,900])for(let x=220;x<900;x+=70)ctx.fillText('6',x,y);
          for(const x of [200,450,700,930])ctx.fillRect(x,700,3,230);
          M=[{m:1,page:1,nx:.2,ny:.5,h:230/1400}];
          const sys=autoRowSystem(1,.505,c);
          if(sys.top!==.5||!sys.continuous)throw Error('简谱行范围未沿用');
          const bars=detectRowBars(1,sys,.21,c);
          if(bars.length!==3||bars.some((x,i)=>Math.abs(x-[.451,.701,.931][i])>.003))throw Error('数字误检或小节线漏检 '+bars);
          M=[];
          if(autoRowSystem(1,.505,c)!==null)throw Error('简谱数字误认作五线谱');
          return {stable:results[0],numberedBars:bars};
        }''')
        print('PASS 固定分辨率在三档缩放下识别完全一致；真实谱页检出',len(result['stable']['bars']),'条线')
        print('PASS 简谱沿用人工行范围；数字不误检；无行范围时不猜测五线谱')
        assert not errors,errors
        await browser.close()
asyncio.run(main())
