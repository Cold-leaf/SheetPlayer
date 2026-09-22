# 把一份 PDF 的每一页排成一张联页小图，用来一眼看清：有没有封面、内容对不对、边框是否一样。
# 用法：python3 tests/diag_sheet.py <pdf> <输出png> [每页宽]
import asyncio, sys, http.server, socketserver, threading, functools
from playwright.async_api import async_playwright

ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8783),H); threading.Thread(target=srv.serve_forever,daemon=True).start()

JS=r"""
async ([pw,labs])=>{
  const draw=async(n)=>{await new Promise(async res=>{
      if(!boxes[n]){res();return}
      while(tasks.has(n)){await tasks.get(n).promise.catch(()=>{})}
      delete boxes[n].dataset.done; visible.add(n); await renderPage(n); res();});
    await new Promise(r=>{const t=setInterval(()=>{if(boxes[n]&&boxes[n].dataset.done&&cvs[n]&&cvs[n].width){clearInterval(t);r()}},50);setTimeout(()=>{clearInterval(t);r()},60000)})};
  const n=boxes.length;
  const out=document.createElement('canvas');
  out.width=pw*n; out.height=Math.round(pw*1.4142)+18;
  const g=out.getContext('2d'); g.fillStyle='#fff'; g.fillRect(0,0,out.width,out.height);
  for(let i=0;i<n;i++){
    await draw(i);
    const c=cvs[i];
    if(c&&c.width){
      const h=pw*c.height/c.width;
      g.drawImage(c,0,0,c.width,c.height,i*pw,18,pw,h);
      g.strokeStyle='#c00'; g.lineWidth=1; g.strokeRect(i*pw+.5,18.5,pw-1,h-1);
    } else { g.fillStyle='#eee'; g.fillRect(i*pw,18,pw,out.height-18); }
    g.fillStyle='#000'; g.font='12px sans-serif'; g.fillText((labs&&labs[i])||('p'+(i+1)),i*pw+4,13);
  }
  return out.toDataURL('image/png');
}
"""

async def main():
    pdf,out = sys.argv[1],sys.argv[2]
    pw = int(sys.argv[3]) if len(sys.argv)>3 else 170
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={"width":1600,"height":1000})
        await pg.goto("http://127.0.0.1:8783/player.html?direct=1")
        await pg.set_input_files("#fPdf",pdf)
        await pg.wait_for_function("()=>pdf&&boxes.length>1",timeout=60000)
        await pg.evaluate("io&&io.disconnect()"); await pg.wait_for_timeout(1500)
        url=await pg.evaluate(JS,[pw,None])
        await b.close()
    import base64; open(out,"wb").write(base64.b64decode(url.split(",",1)[1])); print("已存",out)
asyncio.run(main())
