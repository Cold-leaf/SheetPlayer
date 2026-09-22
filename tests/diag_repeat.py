# 同一页、同一行，反复问 detectRowBars 同一件事 —— 看它给不给一样的答案。
# 这是"同一份文件两次测出不同召回"的根子所在。
# 用法：python3 tests/diag_repeat.py <pdf> <页> <ny>
import asyncio, sys, http.server, socketserver, threading, functools
from playwright.async_api import async_playwright

ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8786),H); threading.Thread(target=srv.serve_forever,daemon=True).start()

JS=r"""
([page,ny,heads])=>{
  const sys=systemAt(page,ny);
  const c=cvs[page];
  const out=[];
  for(const h of heads){
    const r=detectRowBars(page,sys,h);
    out.push({head:h,staves:sys.staves.length,cw:c.width,ch:c.height,
              lines:(r||[]).map(x=>+x.toFixed(4))});
  }
  return out;
}
"""
async def main():
    pdf,page,ny = sys.argv[1],int(sys.argv[2]),float(sys.argv[3])
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={"width":1600,"height":1000})
        await pg.goto("http://127.0.0.1:8786/player.html?direct=1")
        await pg.set_input_files("#fPdf",pdf)
        await pg.wait_for_function("()=>pdf&&boxes.length>1",timeout=60000)
        await pg.evaluate("io&&io.disconnect()"); await pg.wait_for_timeout(1200)
        await pg.evaluate("""async(n)=>{while(tasks.has(n)){await tasks.get(n).promise.catch(()=>{})}
            delete boxes[n].dataset.done; visible.add(n); await renderPage(n);}""",page)
        await pg.wait_for_function("(n)=>boxes[n]&&boxes[n].dataset.done&&cvs[n]&&cvs[n].width>0",arg=page,timeout=60000)
        # 同一个 head 连问三次，再换 head 问，再换回来
        r=await pg.evaluate(JS,[page,ny,[0.05,0.15,0.25,0.35,0.45,0.50,0.55,0.62,0.05]])
        await b.close()
    for i,x in enumerate(r):
        print(f'[{i}] head={x["head"]} 画布{x["cw"]}x{x["ch"]} 谱表×{x["staves"]} → {x["lines"]}')
    base=r[0]["lines"]
    print("\n随 head 右移，检出集合怎么变（* = 不是首行的子集，说明换了档）:")
    for x in r:
        sub = all(any(abs(y-b)<0.002 for b in base) for y in x["lines"])
        print(f'  head={x["head"]:.3f}  {len(x["lines"])}条 {"子集" if sub else "*不嵌套*"}')
asyncio.run(main())
