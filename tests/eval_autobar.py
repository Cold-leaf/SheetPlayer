# 自动标小节 —— 离线评估
# 用真实标注（annotations.json 里 4 首谱子共 312 条竖线）当标准答案，
# 评估「扫描整页找小节线」的检出效果。不改 player.html，检测函数注入运行。
import asyncio, json, hashlib, glob, os, http.server, socketserver, threading, functools
from collections import defaultdict
from playwright.async_api import async_playwright

ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
PDFDIR=ROOT+"/SheetPlayerTests"
ANN=ROOT+"/SheetPlayer/annotations.json"
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8780),H); threading.Thread(target=srv.serve_forever,daemon=True).start()

# 扫描一行：复用 staves() 检测谱表，要求候选列在该行覆盖的【每个谱表】都通到底（跨声部校验）
SCAN_JS = r"""
([ny,h,page,darkTh,fillTh])=>{
  const c=cvs[page]; if(!c||!c.width) return {err:'canvas 未渲染'};
  const st=staves(page); if(!st||!st.length) return {err:'没找到谱表'};
  const W=c.width,H=c.height;
  const y0=ny,y1=ny+h;
  const hit=st.filter(s=>s.bot>y0&&s.top<y1);
  if(!hit.length) return {err:'该行没覆盖到谱表'};
  const ys=Math.max(0,Math.round(hit[0].top*H)-1);
  const ye=Math.min(H-1,Math.round(hit[hit.length-1].bot*H)+1);
  let img;
  try{img=c.getContext('2d',{willReadFrequently:true}).getImageData(0,ys,W,ye-ys+1)}catch(e){return {err:'读像素失败'}}
  const d=img.data,iw=img.width;
  const dark=(ix,y)=>{const iy=y-ys;
    for(let k=Math.max(0,ix-1);k<=Math.min(iw-1,ix+1);k++){
      const p=(iy*iw+k)*4;
      if(d[p]*.299+d[p+1]*.587+d[p+2]*.114<darkTh)return true;
    }
    return false;
  };
  const cols=[];
  for(let ix=1;ix<iw-1;ix++){
    let okAll=true;
    for(const s of hit){
      const a=Math.max(ys,Math.round(s.top*H)),bb=Math.min(ye,Math.round(s.bot*H));
      const hh=bb-a+1; if(hh<6){okAll=false;break}
      let n=0; for(let y=a;y<=bb;y++) if(dark(ix,y)) n++;
      if(n/hh<fillTh){okAll=false;break}
    }
    if(okAll)cols.push(ix);
  }
  // 相邻列并成一条线（线有宽度+抗锯齿；双小节线间隔小也并一起）
  const runs=[];
  for(const x of cols){const r=runs[runs.length-1];
    if(r&&x-r[1]<=3)r[1]=x;else runs.push([x,x])}
  return {lines:runs.map(([a,b])=>(a+b)/2/W), staves:hit.length, W:W};
}
"""

def load_truth():
    d=json.load(open(ANN))
    local={}
    for p in glob.glob(PDFDIR+"/*.pdf"):
        local[hashlib.sha256(open(p,'rb').read(1<<20)).hexdigest()]=p
    out=[]
    for it in d["items"]:
        pdf=local.get(it["pdfHash"])
        if not pdf: continue
        rows=defaultdict(list)
        for m in it["data"].get("M",[]):
            rows[(m["page"],round(m["ny"],3))].append(m)
        out.append({"name":os.path.basename(pdf),"pdf":pdf,
                    "rows":{k:sorted(v,key=lambda x:x["nx"]) for k,v in rows.items()}})
    return out

async def main():
    truth=load_truth()
    TOL=0.006          # 命中容差（页宽比例，约 ±9px @1500px 宽）
    async with async_playwright() as p:
        b=await p.chromium.launch()
        pg=await b.new_page(viewport={"width":1600,"height":1000})
        errs=[]; pg.on("pageerror",lambda e:errs.append(str(e)))
        await pg.goto("http://127.0.0.1:8780/player.html?direct=1")
        grand={"gt":0,"hit":0,"det":0,"fp":0}
        for T in truth:
            await pg.set_input_files("#fPdf",T["pdf"])
            await pg.wait_for_function("()=>pdf&&boxes.length>1",timeout=60000)
            # 关掉懒渲染的 IntersectionObserver：否则页面滚出视口时 canvas 会被释放
            await pg.evaluate("io&&io.disconnect();zoom=1.6;$('zoom').value=1.6;setPageSizes()")
            print(f'\n══ {T["name"]}')
            per={"gt":0,"hit":0,"det":0,"fp":0}
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
                    h=marks[0].get("h",0.05)
                    r=await pg.evaluate(SCAN_JS,[ny,h,page,175,0.93])
                    gt=[m["nx"] for m in marks]
                    if r is None or r.get("err"):
                        print(f'  p{page} ny={ny:.3f}: 真实 {len(gt)} | ✗ {r.get("err") if r else "null"}')
                        per["gt"]+=len(gt); continue
                    det=r["lines"]
                    matched=set(); hits=0; miss=[]
                    for g in gt:
                        best=None;bd=TOL
                        for i,x in enumerate(det):
                            if i in matched: continue
                            if abs(x-g)<bd: bd=abs(x-g);best=i
                        if best is not None: matched.add(best);hits+=1
                        else: miss.append(g)
                    fp=len(det)-len(matched)
                    per["gt"]+=len(gt);per["hit"]+=hits;per["det"]+=len(det);per["fp"]+=fp
                    flag="" if hits==len(gt) and fp<=2 else "  ⚠"
                    ms=(" 漏:"+",".join(f"{x:.3f}" for x in miss[:4])) if miss else ""
                    print(f'  p{page} ny={ny:.3f} 谱表{r["staves"]}: 真实 {len(gt):2} | 检出 {len(det):2} | '
                          f'命中 {hits:2} | 多检 {fp:2}{flag}{ms}')
            for k in grand: grand[k]+=per[k]
            rec=per["hit"]/per["gt"]*100 if per["gt"] else 0
            print(f'  ── 小计: 召回 {per["hit"]}/{per["gt"]} = {rec:.1f}% | 多检 {per["fp"]}')
        print("\n"+"═"*58)
        rec=grand["hit"]/grand["gt"]*100 if grand["gt"] else 0
        prec=grand["hit"]/grand["det"]*100 if grand["det"] else 0
        print(f'总计: 真实 {grand["gt"]} | 检出 {grand["det"]} | 命中 {grand["hit"]}')
        print(f'      召回率 {rec:.1f}%（真实竖线被找到的比例）')
        print(f'      准确率 {prec:.1f}%（检出的里面是真竖线的比例）| 多检 {grand["fp"]}')
        print("page errors:",errs[:3] or "(none)")
        await b.close()
asyncio.run(main())
