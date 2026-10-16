"""Slow PDF rendering must preserve the preview and catch up with later zooms."""
import asyncio, functools, http.server, socketserver, threading
from pathlib import Path
from playwright.async_api import async_playwright
ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT.parent / '线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf'
class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args): pass
srv = socketserver.TCPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=str(ROOT)))
threading.Thread(target=srv.serve_forever, daemon=True).start()

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        pg = await browser.new_page()
        errors = []
        pg.on('pageerror', lambda e: errors.append(str(e)))
        await pg.goto(f'http://127.0.0.1:{srv.server_address[1]}/player.html?direct=1')
        await pg.set_input_files('#fPdf', str(PDF))
        await pg.wait_for_function('()=>cvs[1]&&boxes[1].dataset.done&&!tasks.size')
        await pg.evaluate('zoom*=1.2;applyZoom()')
        await pg.wait_for_function("()=>visible.size>0&&[...visible].every(n=>cvs[n]&&boxes[n].dataset.done===zoom+'@'+DPR)&&!tasks.size")
        await pg.evaluate('''async()=>{
          const check=(x,m)=>{if(!x)throw Error(m)};
          io.disconnect();visible.clear();visible.add(1);
          const page=pageObj[1],original=page.render;
          const pending=[];
          page.render=({canvasContext:ctx})=>{
            let resolve,reject;
            const promise=new Promise((a,b)=>{resolve=a;reject=b});
            const t={promise,cancel(){this.cancelled=true}};
            pending.push({t,finish(){ctx.fillStyle='black';ctx.fillRect(0,0,20,20);resolve()},reject});
            return t;
          };
          const tick=async()=>{await Promise.resolve();await Promise.resolve()};
          const old=cvs[1],pixels=old.toDataURL();
          zoom*=1.1;applyZoom();
          check(cvs[1]===old&&old.isConnected&&old.toDataURL()===pixels,'缩放清空了旧画面');
          zoom*=1.2;applyZoom();zoom*=1.1;applyZoom();
          check(pending.length===1,'同一页并发渲染');
          pending[0].finish();await tick();
          check(pending.length===2,'没有补画最新缩放');
          check(cvs[1]===old&&old.toDataURL()===pixels,'过期比例替换了旧画面');
          pending[1].finish();await tick();
          check(cvs[1]!==old&&cvs[1].isConnected,'未替换完成画面');
          check(boxes[1].dataset.done===zoom+'@'+DPR&&!tasks.has(1),'最新比例未完成');
          check(cvs[1].getContext('2d').getImageData(1,1,1,1).data[3]===255,'发布了空白画布');
          zoom*=1.1;applyZoom();
          const cancelled=pending[2];
          visible.delete(1);freePage(1);visible.add(1);renderPage(1);
          check(cancelled.t.cancelled,'离开页面没有取消任务');
          cancelled.reject({name:'RenderingCancelledException'});await tick();
          check(tasks.get(1)===pending[3].t,'旧任务删除了新任务');
          pending[3].finish();await tick();
          check(cvs[1]?.isConnected&&boxes[1].dataset.done===zoom+'@'+DPR,'重新进入页面未恢复');
          zoom*=1.1;applyZoom();
          const obsolete=pending[4];
          resetPdfDerived();obsolete.finish();await tick();
          check(!cvs[1]&&!tasks.size,'换谱后旧画面回写');
          page.render=original;
        }''')
        assert not errors, errors
        print('OK   慢速重绘保留旧画面；连续缩放自动追上；取消竞态与换谱隔离通过')
        await browser.close()
try:
    asyncio.run(main())
finally:
    srv.shutdown();srv.server_close()
