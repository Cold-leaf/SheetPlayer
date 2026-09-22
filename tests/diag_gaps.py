# 只数【谱表与谱表之间那几条空档】的暗度：真小节线在那里也是黑的，音符/符杠/歌词不是。
# 用这个当"印刷小节线在哪"的客观尺子。
# 用法：python3 tests/diag_gaps.py <pdf> <页> <ny> ["标注nx"] [阈值]
import asyncio, sys, http.server, socketserver, threading, functools
from playwright.async_api import async_playwright

ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8785),H); threading.Thread(target=srv.serve_forever,daemon=True).start()

JS=r"""
([page,ny,thr,xs])=>{
  const c=cvs[page], W=c.width, Hh=c.height;
  const sys=systemAt(page,ny); if(!sys) return {err:'systemAt null'};
  const st=sys.staves;
  // 谱表之间的空档（取中间那一截，避开谱线本身和贴着谱表的符头）
  const bands=[];
  for(let i=0;i<st.length-1;i++){
    const a=st[i].bot, b=st[i+1].top;
    if(b-a<0.004) continue;
    bands.push([a+(b-a)*0.30, a+(b-a)*0.70]);
  }
  if(!bands.length) return {err:'没有谱表间空档'};
  const d=c.getContext('2d',{willReadFrequently:true}).getImageData(0,0,W,Hh).data;
  const darkAt=(x,y)=>{for(let k=Math.max(0,x-1);k<=Math.min(W-1,x+1);k++){
      const p=(y*W+k)*4; if(d[p]*.299+d[p+1]*.587+d[p+2]*.114<175)return true} return false};
  const score=new Array(W).fill(0);
  for(let x=0;x<W;x++){
    let hit=0,tot=0;
    for(const [a,b] of bands){
      const y0=Math.round(a*Hh), y1=Math.round(b*Hh);
      let s=0,n=0;
      for(let y=y0;y<=y1;y++){n++;if(darkAt(x,y))s++}
      if(n&&s/n>=0.85) hit++;          // 这一条空档里，该列基本是黑的
      tot++;
    }
    score[x]=tot?hit/tot:0;
  }
  const runs=[]; let cur=null;
  for(let x=0;x<W;x++){
    if(score[x]>=thr){ if(!cur)cur={a:x,b:x}; else cur.b=x }
    else if(cur){runs.push(cur);cur=null}
  }
  if(cur)runs.push(cur);
  const lines=runs.filter(r=>(r.b-r.a)<=Math.max(4,W*0.012)&&(r.a+r.b)/2>W*0.02)
                  .map(r=>((r.a+r.b)/2)/W);
  // 每个指定位置上的"空档暗度"：真小节线应该接近 1
  const probe=xs=>xs.map(x=>{
    const xi=Math.round(x*W); let hit=0;
    for(const [a,b] of bands){
      const y0=Math.round(a*Hh), y1=Math.round(b*Hh);
      let s=0,n=0;
      for(let y=y0;y<=y1;y++){n++;if(darkAt(xi,y))s++}
      if(n&&s/n>=0.5) hit++;
    }
    return [x, hit/bands.length];
  });
  const det=detectRowBars(page,sys,0.05)||[];
  const uniq=[...new Set([...xs,...det].map(x=>Math.round(x*1000)/1000))].sort((a,b)=>a-b);
  return {sysTop:sys.top,sysBot:sys.bot,nst:st.length,ngap:bands.length,lines,W,H:Hh,
          det,probe:probe(uniq)};
}
"""
async def main():
    pdf,page,ny = sys.argv[1],int(sys.argv[2]),float(sys.argv[3])
    ann=[float(x) for x in sys.argv[4].split(",")] if len(sys.argv)>4 and sys.argv[4] else []
    thr=float(sys.argv[5]) if len(sys.argv)>5 else 0.6
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={"width":1600,"height":1000})
        await pg.goto("http://127.0.0.1:8785/player.html?direct=1")
        await pg.set_input_files("#fPdf",pdf)
        await pg.wait_for_function("()=>pdf&&boxes.length>1",timeout=60000)
        await pg.evaluate("io&&io.disconnect()"); await pg.wait_for_timeout(1200)
        await pg.evaluate("""async(n)=>{while(tasks.has(n)){await tasks.get(n).promise.catch(()=>{})}
            delete boxes[n].dataset.done; visible.add(n); await renderPage(n);}""",page)
        await pg.wait_for_function("(n)=>boxes[n]&&boxes[n].dataset.done&&cvs[n]&&cvs[n].width>0",arg=page,timeout=60000)
        r=await pg.evaluate(JS,[page,ny,thr,ann])
        await b.close()
    if "err" in r: print("ERR",r["err"]); return
    f=lambda xs:" ".join(f"{x:.3f}" for x in xs)
    print(f'系统[{r["sysTop"]:.3f},{r["sysBot"]:.3f}] 谱表×{r["nst"]} 空档×{r["ngap"]} 画布{r["W"]} 阈值{thr}')
    print(f'  空档验出的印刷线 [{len(r["lines"])}]: {f(r["lines"])}')
    if ann: print(f'  标注            [{len(ann)}]: {f(ann)}')
    print(f'  检测 detectRowBars [{len(r["det"])}]: {f(sorted(r["det"]))}')
    print(f'  各位置的空档暗度（1.0=整条空档都黑=真小节线）：')
    for x,v in r["probe"]:
        tag="标注" if any(abs(x-a)<0.008 for a in ann) else "    "
        dtag="检测" if any(abs(x-d)<0.008 for d in r["det"]) else "    "
        print(f'     {x:.3f}  {v:.2f}   {tag} {dtag}')
    TOL=0.008; near=lambda a,bs:any(abs(a-b)<TOL for b in bs)
    if ann:
        print(f'  标注对不上空档线的: {f([a for a in ann if not near(a,r["lines"])]) or "—"}')
        print(f'  标注对不上的、却出现在检测里的: {f([a for a in ann if not near(a,r["lines"]) and near(a,r["det"])]) or "—"}')
        print(f'  空档线里检测也没检出的: {f([x for x in r["lines"] if not near(x,r["det"])]) or "—"}')
        print(f'  检测有、空档线没有的 : {f([x for x in sorted(r["det"]) if not near(x,r["lines"])]) or "—"}')
asyncio.run(main())
