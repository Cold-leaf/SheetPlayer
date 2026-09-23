# 库里每份谱子的**每页尺寸**。fitZoom 对 w 和 h 各取一次 max（保证哪一页都装得下），
# 混排（封面/折页/横页）时两个 max 会来自不同的页 → 拟合出一个不存在的"幽灵页"，
# 于是"最宽的那页"之外的所有页都比可用区小一圈（QL 差 5.7%、YR 差 5.6%）：
# 尺寸小一点、盒里居中——想查「这份谱子为什么没铺满」时先看这里。
import asyncio, base64, glob, http.server, socketserver, threading, functools, os
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
FILES=sorted(glob.glob(ROOT+"/线谱合集/*.pdf"))
class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*a): pass
H=functools.partial(Quiet,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8839),H); threading.Thread(target=srv.serve_forever,daemon=True).start()

PROBE="""async ([b64])=>{
  const bin=atob(b64),u8=new Uint8Array(bin.length);
  for(let i=0;i<bin.length;i++)u8[i]=bin.charCodeAt(i);
  const doc=await pdfjsLib.getDocument({data:u8}).promise;
  const out=[];
  for(let n=1;n<=doc.numPages;n++){
    const v=(await doc.getPage(n)).getViewport({scale:1});
    out.push([Math.round(v.width),Math.round(v.height)]);
  }
  return out;}"""

async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page()
        await pg.goto("http://127.0.0.1:8839/player.html")
        await pg.wait_for_function("()=>typeof pdfjsLib!=='undefined'",timeout=20000)
        bad=[]
        for f in FILES:
            b64=base64.b64encode(open(f,'rb').read()).decode()
            try: sizes=await pg.evaluate(PROBE,[b64])
            except Exception as e:
                print("ERR",os.path.basename(f),e); continue
            ws=sorted({s[0] for s in sizes}); hs=sorted({s[1] for s in sizes})
            wmax=max(s[0] for s in sizes); hmax=max(s[1] for s in sizes)
            # 幽灵页：两个 max 不同页 → 存在某页在自己的宽或高上不是最大
            ghost=any(s[0]!=wmax and s[1]!=hmax for s in sizes) or len(ws)>1 or len(hs)>1
            tag="⚠混排" if (len(ws)>1 or len(hs)>1) else ("·拼max" if ghost else "")
            print(f"{os.path.basename(f)[:46]:48s} 页数={len(sizes):3d} 宽{sorted(set(s[0] for s in sizes))} 高{sorted(set(s[1] for s in sizes))} {tag}")
            if tag: bad.append(os.path.basename(f))
        print("\n混排/拼max 的文件:",bad)
        await b.close()
asyncio.run(main())
