# 把一页的【整页纵向/横向墨迹剖面】导出来存成 json —— 用来和另一份 PDF 的同一页做互相关，
# 客观回答「笔记软件导出到底有没有改变版式（缩放/平移）」。
# 不看应用自己的检测，纯像素。
# 用法：python3 tests/diag_profile.py <pdf> <页> <输出json> [亮度阈值]
import asyncio, sys, json, http.server, socketserver, threading, functools
from playwright.async_api import async_playwright

ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8784),H); threading.Thread(target=srv.serve_forever,daemon=True).start()

JS=r"""
([page,thr])=>{
  const c=cvs[page], W=c.width, Hh=c.height;
  const d=c.getContext('2d',{willReadFrequently:true}).getImageData(0,0,W,Hh).data;
  const col=new Array(W).fill(0), row=new Array(Hh).fill(0);
  let n=0;
  for(let y=0;y<Hh;y++){
    for(let x=0;x<W;x++){
      const p=(y*W+x)*4;
      if(d[p]*.299+d[p+1]*.587+d[p+2]*.114<thr){col[x]++;row[y]++;n++}
    }
  }
  // 归一到「该列/该行有几成是墨」
  for(let x=0;x<W;x++)col[x]/=Hh;
  for(let y=0;y<Hh;y++)row[y]/=W;
  return {W,H:Hh,inkFrac:n/(W*Hh),col,row};
}
"""
async def main():
    pdf,page,out = sys.argv[1],int(sys.argv[2]),sys.argv[3]
    thr=int(sys.argv[4]) if len(sys.argv)>4 else 175
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={"width":1600,"height":1000})
        await pg.goto("http://127.0.0.1:8784/player.html?direct=1")
        await pg.set_input_files("#fPdf",pdf)
        await pg.wait_for_function("()=>pdf&&boxes.length>1",timeout=60000)
        await pg.evaluate("io&&io.disconnect()"); await pg.wait_for_timeout(1500)
        await pg.evaluate("""async(n)=>{while(tasks.has(n)){await tasks.get(n).promise.catch(()=>{})}
            delete boxes[n].dataset.done; visible.add(n); await renderPage(n);}""",page)
        await pg.wait_for_function("(n)=>boxes[n]&&boxes[n].dataset.done&&cvs[n]&&cvs[n].width>0",arg=page,timeout=60000)
        r=await pg.evaluate(JS,[page,thr])
        await b.close()
    json.dump(r,open(out,"w"))
    print(f'已存 {out}: 画布 {r["W"]}x{r["H"]} 墨占比 {r["inkFrac"]*100:.1f}%')
asyncio.run(main())
