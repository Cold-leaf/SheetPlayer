# 把某一行裁出来存成 PNG，并叠上【标注的 nx（红）】和【检测到的 nx（绿）】——直接看谁对。
# 用法：python3 tests/diag_rowimg.py <pdf> <页> <ny> "0.20,0.298,0.396" [输出名]
import asyncio, sys, http.server, socketserver, threading, functools
from playwright.async_api import async_playwright

ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8781),H); threading.Thread(target=srv.serve_forever,daemon=True).start()

JS=r"""
async ([page,ny,ann,out,x0,x1,SC])=>{
  const c=cvs[page]; const sys=systemAt(page,ny);
  if(!sys) return 'systemAt null';
  const lines=detectRowBars(page,sys,ann[0]);
  const H=c.height,W=c.width;
  x0=x0||0; x1=x1||1; SC=SC||2;
  const y0=Math.max(0,Math.round(sys.top*H)-4), y1=Math.min(H,Math.round(sys.bot*H)+4);
  const srcX=Math.round(x0*W), srcW=Math.max(1,Math.round((x1-x0)*W));
  const cv=document.createElement('canvas'); cv.width=srcW*SC; cv.height=(y1-y0)*SC;
  const g=cv.getContext('2d'); g.imageSmoothingEnabled=false;
  g.drawImage(c,srcX,y0,srcW,y1-y0,0,0,srcW*SC,(y1-y0)*SC);
  g.lineWidth=2;
  for(const x of (lines||[])){if(x<x0||x>x1)continue;g.strokeStyle='rgba(0,200,0,.9)';g.beginPath();g.moveTo((x-x0)*W*SC,0);g.lineTo((x-x0)*W*SC,cv.height);g.stroke()}
  for(const x of ann){if(x<x0||x>x1)continue;g.strokeStyle='rgba(255,0,0,.9)';g.beginPath();g.moveTo((x-x0)*W*SC,0);g.lineTo((x-x0)*W*SC,cv.height);g.stroke()}
  return cv.toDataURL('image/png');
}
"""

async def main():
    pdf,page,ny,ann = sys.argv[1],int(sys.argv[2]),float(sys.argv[3]),[float(x) for x in sys.argv[4].split(",")]
    out=sys.argv[5] if len(sys.argv)>5 else "/tmp/row.png"
    x0=float(sys.argv[6]) if len(sys.argv)>6 else 0
    x1=float(sys.argv[7]) if len(sys.argv)>7 else 1
    SC=int(sys.argv[8]) if len(sys.argv)>8 else 2
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={"width":1600,"height":1000})
        await pg.goto("http://127.0.0.1:8781/player.html?direct=1")
        await pg.set_input_files("#fPdf",pdf)
        await pg.wait_for_function("()=>pdf&&boxes.length>1",timeout=60000)
        await pg.evaluate("io&&io.disconnect()"); await pg.wait_for_timeout(1200)
        await pg.evaluate("""async(n)=>{while(tasks.has(n)){await tasks.get(n).promise.catch(()=>{})}
            delete boxes[n].dataset.done; visible.add(n); await renderPage(n);}""",page)
        await pg.wait_for_function("(n)=>boxes[n]&&boxes[n].dataset.done&&cvs[n]&&cvs[n].width>0",arg=page,timeout=60000)
        url=await pg.evaluate(JS,[page,ny,ann,out,x0,x1,SC])
        print("结果:", url[:60] if isinstance(url,str) else url)
        if isinstance(url,str) and url.startswith("data:image/png"):
            import base64; open(out,"wb").write(base64.b64decode(url.split(",",1)[1])); print("已存",out)
        await b.close()
asyncio.run(main())
