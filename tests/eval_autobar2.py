# 自动标小节 —— 精细评估（区分"真误检"和"合法但非小节起点的线"）
# 关键认知：用户标的是【小节起点】；印刷的线是【小节边界】。
#   行首那条起点在谱号/调号之后，没有印刷线 → 只能推导，不能检测
#   系统左边界线、行末终止线 是真线，但不是小节起点 → 应排除而非算误检
import asyncio, json, hashlib, glob, os, http.server, socketserver, threading, functools
from collections import defaultdict
from playwright.async_api import async_playwright

ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
PDFDIR=ROOT+"/SheetPlayerTests"; ANN=ROOT+"/SheetPlayer/annotations.json"
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8781),H); threading.Thread(target=srv.serve_forever,daemon=True).start()

SCAN_JS=open(os.path.join(os.path.dirname(__file__),"_scan.js")).read() if False else r"""
([ny,h,page,darkTh,fillTh])=>{
  const c=cvs[page]; if(!c||!c.width) return {err:'canvas 未渲染'};
  const st=staves(page); if(!st||!st.length) return {err:'没找到谱表(全页 '+(staves(page)||[]).length+')'};
  const W=c.width,H=c.height, y0=ny,y1=ny+h;
  const hit=st.filter(s=>s.bot>y0&&s.top<y1);
  if(!hit.length) return {err:'该行没覆盖谱表(全页'+st.length+'个)',allStaves:st.map(s=>+s.top.toFixed(3))};
  const ys=Math.max(0,Math.round(hit[0].top*H)-1), ye=Math.min(H-1,Math.round(hit[hit.length-1].bot*H)+1);
  let img; try{img=c.getContext('2d',{willReadFrequently:true}).getImageData(0,ys,W,ye-ys+1)}catch(e){return {err:'读像素失败'}}
  const d=img.data,iw=img.width;
  const dark=(ix,y)=>{const iy=y-ys;
    for(let k=Math.max(0,ix-1);k<=Math.min(iw-1,ix+1);k++){const p=(iy*iw+k)*4;
      if(d[p]*.299+d[p+1]*.587+d[p+2]*.114<darkTh)return true} return false};
  const cols=[];
  for(let ix=1;ix<iw-1;ix++){
    let okAll=true;
    for(const s of hit){
      const a=Math.max(ys,Math.round(s.top*H)),bb=Math.min(ye,Math.round(s.bot*H)),hh=bb-a+1;
      if(hh<6){okAll=false;break}
      let n=0; for(let y=a;y<=bb;y++) if(dark(ix,y)) n++;
      if(n/hh<fillTh){okAll=false;break}
    }
    if(okAll)cols.push(ix);
  }
  const runs=[]; for(const x of cols){const r=runs[runs.length-1];
    if(r&&x-r[1]<=3)r[1]=x;else runs.push([x,x])}
  return {lines:runs.map(([a,b])=>(a+b)/2/W), staves:hit.length};
}
"""

def load_truth():
    d=json.load(open(ANN)); local={}
    for p in glob.glob(PDFDIR+"/*.pdf"):
        local[hashlib.sha256(open(p,'rb').read(1<<20)).hexdigest()]=p
    out=[]
    for it in d["items"]:
        pdf=local.get(it["pdfHash"])
        if not pdf: continue
        rows=defaultdict(list)
        for m in it["data"].get("M",[]): rows[(m["page"],round(m["ny"],3))].append(m)
        out.append({"name":os.path.basename(pdf)[:22],"pdf":pdf,
                    "rows":{k:sorted(v,key=lambda x:x["nx"]) for k,v in rows.items()}})
    return out

async def main():
    TOL=0.008
    G=defaultdict(int); PER=defaultdict(lambda: defaultdict(int)); FAILPAGES=[]
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={"width":1600,"height":1000})
        await pg.goto("http://127.0.0.1:8781/player.html?direct=1")
        for T in load_truth():
            await pg.set_input_files("#fPdf",T["pdf"])
            await pg.wait_for_function("()=>pdf&&boxes.length>1",timeout=60000)
            await pg.evaluate("io&&io.disconnect();zoom=1.6;$('zoom').value=1.6;setPageSizes()")
            bypage=defaultdict(list)
            for (page,ny),marks in T["rows"].items(): bypage[page].append((ny,marks))
            for page in sorted(bypage):
                # 等真正画完：renderPage 遇到进行中的任务会直接 return，
                # 只等 canvas.width>0 会扫到空白画布（首屏页最容易踩）
                await pg.evaluate("""async(n)=>{if(!boxes[n])return;
                    while(tasks.has(n)){await tasks.get(n).promise.catch(()=>{})}
                    delete boxes[n].dataset.done; visible.add(n); await renderPage(n);}""",page)
                await pg.wait_for_function("(n)=>boxes[n]&&boxes[n].dataset.done&&cvs[n]&&cvs[n].width>0",
                                           arg=page,timeout=60000)
                for ny,marks in sorted(bypage[page]):
                    gt=[m["nx"] for m in marks]
                    r=await pg.evaluate(SCAN_JS,[ny,marks[0].get("h",.05),page,175,.93])
                    if r is None or r.get("err"):
                        FAILPAGES.append((T["name"],page,ny,len(gt),(r or {}).get("err")))
                        PER[T["name"]]["fail_gt"]+=len(gt); G["fail_gt"]+=len(gt); continue
                    det=sorted(r["lines"])
                    # 行首起点（第一个 truth）单列：它在调号后，没有印刷线，只能推导
                    head, rest = gt[0], gt[1:]
                    used=set(); hit=0
                    for g in rest:
                        best=None;bd=TOL
                        for i,x in enumerate(det):
                            if i in used: continue
                            if abs(x-g)<bd: bd=abs(x-g);best=i
                        if best is not None: used.add(best);hit+=1
                    # 未匹配的检出线：分成 行首左侧(系统边界) / 行尾右侧(终止线) / 中间(真误检)
                    lo,hi=min(gt),max(gt)
                    edge=inner=0
                    for i,x in enumerate(det):
                        if i in used: continue
                        if x<head-TOL or x>hi+TOL: edge+=1
                        else: inner+=1
                    head_ok=any(abs(x-head)<TOL for x in det)
                    for k,v in [("rest",len(rest)),("hit",hit),("edge",edge),("inner",inner),
                                ("rows",1),("head_ok",1 if head_ok else 0)]:
                        PER[T["name"]][k]+=v; G[k]+=v
        await b.close()
    print("═"*66)
    print(f'{"谱子":24} {"内部小节线":>12} {"召回":>7} {"真误检":>7} {"边界线":>7}')
    print("─"*66)
    for n,d in PER.items():
        rec=d["hit"]/d["rest"]*100 if d["rest"] else 0
        print(f'{n:24} {str(d["hit"])+"/"+str(d["rest"]):>12} {rec:6.1f}% {d["inner"]:7} {d["edge"]:7}')
    print("─"*66)
    rec=G["hit"]/G["rest"]*100 if G["rest"] else 0
    print(f'{"总计":24} {str(G["hit"])+"/"+str(G["rest"]):>12} {rec:6.1f}% {G["inner"]:7} {G["edge"]:7}')
    print(f'\n行首起点（谱号后，无印刷线）: {G["rows"]} 行中只有 {G["head_ok"]} 行恰好检到 → 必须靠推导')
    print(f'检测失败的行涉及真实竖线: {G["fail_gt"]} 条')
    if FAILPAGES:
        print("\n检测失败明细:")
        for n,pgn,ny,c,err in FAILPAGES[:14]: print(f'  {n:22} p{pgn} ny={ny:.3f} ({c}条) — {err}')
asyncio.run(main())
