# 自动标小节 —— 端到端评估（走真正上线的那条路）
# eval_autobar / eval_autobar2 注入的是脚本自带的扫描函数，只能测到 staves()；
# 这一个直接调 systemAt() + detectRowBars()，测的是「整行补齐」点下去实际发生的事。
# 口径同 eval_autobar2：行首起点在谱号/调号之后、没有印刷线，只能推导，单列不算漏。
import asyncio, json, hashlib, glob, os, http.server, socketserver, threading, functools
from collections import defaultdict
from playwright.async_api import async_playwright

ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
PDFDIR=ROOT+"/SheetPlayerTests"; ANN=ROOT+"/SheetPlayer/annotations.json"
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8778),H); threading.Thread(target=srv.serve_forever,daemon=True).start()

RUN=r"""
([page,ny,headNx])=>{
  const sys=systemAt(page,ny);
  if(!sys) return {err:'systemAt 返回 null（离所有谱表都太远）'};
  const lines=detectRowBars(page,sys,headNx);
  if(!lines) return {err:'detectRowBars 返回 null'};
  // 上线时的真实行为：去掉最右那条（行末终止线），剩下的才会变成小节
  return {staves:sys.staves.length, all:lines, used:lines.slice(0,-1)};
}
"""

def load_truth():
    d=json.load(open(ANN)); local={}
    for p in glob.glob(PDFDIR+"/*.pdf"):
        local[hashlib.sha256(open(p,'rb').read(1<<20)).hexdigest()]=p
    out=[]
    for it in d["items"]:
        pdf=local.get(it.get("pdf") or it.get("pdfHash"))   # 导出格式 v2 起字段从 pdfHash 改名成 pdf
        if not pdf: continue
        rows=defaultdict(list)
        for m in it["data"].get("M",[]): rows[(m["page"],round(m["ny"],3))].append(m)
        out.append({"name":os.path.basename(pdf)[:22],"pdf":pdf,
                    "rows":{k:sorted(v,key=lambda x:x["nx"]) for k,v in rows.items()}})
    return out

async def main():
    TOL=0.008
    G=defaultdict(int); PER=defaultdict(lambda: defaultdict(int)); FAIL=[]
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={"width":1600,"height":1000})
        await pg.goto("http://127.0.0.1:8778/player.html?direct=1")
        for T in load_truth():
            await pg.set_input_files("#fPdf",T["pdf"])
            await pg.wait_for_function("()=>pdf&&boxes.length>1",timeout=60000)
            await pg.evaluate("io&&io.disconnect();zoom=1.6;$('zoom').value=1.6;setPageSizes()")
            bypage=defaultdict(list)
            for (page,ny),marks in T["rows"].items(): bypage[page].append((ny,marks))
            for page in sorted(bypage):
                await pg.evaluate("""async(n)=>{if(!boxes[n])return;
                    while(tasks.has(n)){await tasks.get(n).promise.catch(()=>{})}
                    delete boxes[n].dataset.done; visible.add(n); await renderPage(n);}""",page)
                await pg.wait_for_function("(n)=>boxes[n]&&boxes[n].dataset.done&&cvs[n]&&cvs[n].width>0",
                                           arg=page,timeout=60000)
                for ny,marks in sorted(bypage[page]):
                    gt=[m["nx"] for m in marks]
                    head,rest=gt[0],gt[1:]
                    r=await pg.evaluate(RUN,[page,ny,head])
                    if r is None or r.get("err"):
                        FAIL.append((T["name"],page,ny,len(rest),(r or {}).get("err")))
                        PER[T["name"]]["fail"]+=len(rest); G["fail"]+=len(rest); continue
                    det=sorted(r["used"]); used=set(); hit=0
                    for g in rest:
                        best=None;bd=TOL
                        for i,x in enumerate(det):
                            if i in used: continue
                            if abs(x-g)<bd: bd=abs(x-g);best=i
                        if best is not None: used.add(best);hit+=1
                    extra=len(det)-hit
                    for k,v in [("rest",len(rest)),("hit",hit),("extra",extra),("rows",1),
                                ("empty",1 if not det else 0)]:
                        PER[T["name"]][k]+=v; G[k]+=v
        await b.close()
    print("═"*74)
    print(f'{"谱子":24} {"内部小节线":>12} {"召回":>7} {"多补的":>7} {"一条没补的行":>12}')
    print("─"*74)
    for n,d in PER.items():
        tot=d["rest"]+d["fail"]
        rec=d["hit"]/tot*100 if tot else 0
        print(f'{n:24} {str(d["hit"])+"/"+str(tot):>12} {rec:6.1f}% {d["extra"]:7} {str(d["empty"])+"/"+str(d["rows"]):>12}')
    print("─"*74)
    tot=G["rest"]+G["fail"]
    rec=G["hit"]/tot*100 if tot else 0
    print(f'{"总计":24} {str(G["hit"])+"/"+str(tot):>12} {rec:6.1f}% {G["extra"]:7} {str(G["empty"])+"/"+str(G["rows"]):>12}')
    print(f'\n整行失败（systemAt/detectRowBars 没结果）涉及真实竖线: {G["fail"]} 条')
    for n,pgn,ny,c,err in FAIL[:10]: print(f'  {n:22} p{pgn} ny={ny:.3f} ({c}条) — {err}')
asyncio.run(main())
