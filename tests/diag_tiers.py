# 把 detectRowBars 的两档阈值拆开看：严格档(0.9) / 宽松档(0.72) 各找到哪些线，
# 再算「现在的规则」「修掉档位判定」「两档取并集」三种做法各自能召回多少。
# 用带钩子的临时副本 /tmp/sp_dbg（原版是闭包，外面调不到 scan）。
# 用法：python3 tests/diag_tiers.py <pdf> <标注项片段> [页码平移=0]
import asyncio, json, sys, http.server, socketserver, threading, functools
from collections import defaultdict
from playwright.async_api import async_playwright

ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
ANN=ROOT+"/SheetPlayer/annotations.json"
SERVE="/tmp/sp_dbg"
# 原版 player.html 里 scan() 是闭包，外面调不到。这里按需造一份带钩子的临时副本：
#   scan 多收一个显式裁剪边界，并挂出 window.__scanX，别的逻辑一行不改。
def build_probe_copy():
    import os,shutil,subprocess
    src=os.path.dirname(os.path.abspath(__file__))+"/.."
    if os.path.exists(SERVE+"/player.html") and "--rebuild" not in sys.argv: return
    shutil.rmtree(SERVE,ignore_errors=True); os.makedirs(SERVE)
    for f in ("player.html","index.html","sw.js","manifest.json","annotations.json"):
        shutil.copy(os.path.join(src,f),SERVE)
    shutil.copytree(os.path.join(src,"lib"),SERVE+"/lib")
    for f in os.listdir(src):
        if f.startswith("icon-") and f.endswith(".png"): shutil.copy(os.path.join(src,f),SERVE)
    q=open(SERVE+"/player.html").read()
    q=q.replace("  const scan=(fill,tiltOn)=>{\n","  const scan=(fill,tiltOn,CLIP)=>{\n",1)
    q=q.replace("    const lines=runs.map(([a,b])=>(a+b)/2/W).filter(x=>x>rightOfNx+0.002).sort((a,b)=>a-b);",
                "    const clip=(CLIP===undefined?rightOfNx:CLIP);\n"
                "    const lines=runs.map(([a,b])=>(a+b)/2/W).filter(x=>x>clip+0.002).sort((a,b)=>a-b);",1)
    q=q.replace("  const twoTier=tiltOn=>{","  window.__scanX=(fill,clip,tiltOn)=>scan(fill,tiltOn,clip);\n  const twoTier=tiltOn=>{",1)
    open(SERVE+"/player.html","w").write(q)
build_probe_copy()
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=SERVE)
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8790),H); threading.Thread(target=srv.serve_forever,daemon=True).start()

JS=r"""
([page,ny,head])=>{
  const sys=systemAt(page,ny); if(!sys) return {err:'systemAt null'};
  const real=detectRowBars(page,sys,head);   // 顺便把钩子挂出来，并留作对照
  const g=(f,c,t)=>((window.__scanX(f,c,t))||[]);
  const sets={};
  for(const t of [true,false])
    for(const [k,f] of [["s",0.9],["l",0.72]])
      sets[k+(t?"T":"F")]=g(f,head,t);
  return {sysTop:sys.top,sysBot:sys.bot,nstaff:sys.staves.length,real,
          sets,strictAll:g(0.9,-1,false)};
}
"""
TOL=0.008
def dedup(xs,gap=0.025):
    out=[]
    for x in sorted(xs):
        if not out or x-out[-1]>=gap: out.append(x)
    return out
def match(gt,det):
    used=set(); hit=0
    for g in sorted(gt):
        best=None;bd=TOL
        for i,x in enumerate(sorted(det)):
            if i in used: continue
            if abs(x-g)<bd: bd=abs(x-g);best=i
        if best is not None: used.add(best);hit+=1
    return hit
def load(frag):
    d=json.load(open(ANN))
    for it in d["items"]:
        if frag in it["name"]:
            rows=defaultdict(list)
            for m in it["data"].get("M",[]):
                rows[(m["page"],round(m["ny"],3))].append(m)
            return it,{k:sorted(v,key=lambda x:x["nx"]) for k,v in rows.items()}
    raise SystemExit("没找到:"+frag)

async def main():
    pdf,frag = sys.argv[1],sys.argv[2]
    OFF=int(sys.argv[3]) if len(sys.argv)>3 else 0
    it,rows=load(frag)
    res=defaultdict(lambda: defaultdict(int))     # 策略 -> 计数
    DONE=[0]
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={"width":1600,"height":1000})
        await pg.goto("http://127.0.0.1:8790/player.html?direct=1")
        await pg.set_input_files("#fPdf",pdf)
        await pg.wait_for_function("()=>pdf&&boxes.length>1",timeout=60000)
        await pg.evaluate("io&&io.disconnect()"); await pg.wait_for_timeout(1500)
        for page in sorted({k[0] for k in rows}):
            tp=page+OFF
            if tp<1: continue
            has=await pg.evaluate("(n)=>!!(boxes[n]&&cvs[n])",tp)
            if not has: print(f"  （第{tp}页取不到画布，跳过）"); continue
            await pg.evaluate("""async(n)=>{if(!boxes[n])return;
                while(tasks.has(n)){await tasks.get(n).promise.catch(()=>{})}
                delete boxes[n].dataset.done; visible.add(n); await renderPage(n);}""",tp)
            await pg.wait_for_function("(n)=>boxes[n]&&boxes[n].dataset.done&&cvs[n]&&cvs[n].width>0",arg=tp,timeout=60000)
            for (pgn,ny),marks in sorted(rows.items()):
                if pgn!=page: continue
                gt=[m["nx"] for m in marks]
                r=await pg.evaluate(JS,[tp,ny,gt[0]])
                if r is None or r.get("err"): continue
                rest=gt[1:]
                if not rest: continue
                # 先用四种组合复刻 detectRowBars，和真函数比对（对不上说明复刻错了）
                def emulate(rr,head_ok=True):
                    cand=[]
                    for t,T in (("T",True),("F",False)):
                        st=sorted(rr["sets"]["s"+t]); lo=sorted(rr["sets"]["l"+t])
                        o=st
                        if len(o)<4 and len(lo)>len(o): o=lo
                        cand.append(o)
                    return max(cand,key=len)
                cur=emulate(r)
                a,b2=sorted(cur),sorted(r["real"])
                ok = len(a)==len(b2) and all(abs(x-y)<1e-9 for x,y in zip(a,b2))
                if not DONE[0]:
                    DONE[0]=1
                    f=lambda xs:" ".join(f"{x:.4f}" for x in sorted(xs))
                    print(f'  【对照】真函数head={gt[0]:.3f}: {f(r["real"])}')
                    print(f'         复刻:          {f(cur)}')
                    for k in ("sT","sF","lT","lF"): print(f'          {k}: {f(r["sets"][k])}')
                res["(自检)复刻=真函数" if ok else "**(自检)复刻对不上**"]["tot"]+=1
                res["(自检)复刻=真函数" if ok else "**(自检)复刻对不上**"]["hit"]+=1 if ok else 0
                # 各策略
                sT,sF=sorted(r["sets"]["sT"]),sorted(r["sets"]["sF"])
                lT,lF=sorted(r["sets"]["lT"]),sorted(r["sets"]["lF"])
                SALL=sorted(set(sT)|set(sF))
                uni=dedup(SALL+list(set(lT)|set(lF)))
                fixed=[]
                for st,lo in ((sT,lT),(sF,lF)):
                    o=st
                    if len(r["strictAll"])<4 and len(lo)>len(o): o=lo
                    fixed.append(o)
                fixed=dedup([x for c in fixed for x in c]) if False else max(fixed,key=len)
                for name,det in [("现在的规则(复刻)",cur),("修掉档位判定",fixed),
                                 ("两档取并集",uni),("只用严格档",SALL),("只用宽松档",dedup(lT+lF))]:
                    res[name]["hit"]+=match(rest,det); res[name]["tot"]+=len(rest)
                # 行起点（应用的正常用法：点行首）
                r2=await pg.evaluate(JS,[tp,ny,0.02])
                if r2 and not r2.get("err"):
                    cur2=emulate(r2); u2=dedup(list(set(r2["sets"]["sT"])|set(r2["sets"]["sF"]))+list(set(r2["sets"]["lT"])|set(r2["sets"]["lF"])))
                    res["行首·现在的规则"]["hit"]+=match(rest,cur2); res["行首·现在的规则"]["tot"]+=len(rest)
                    res["行首·两档并集"]["hit"]+=match(rest,u2); res["行首·两档并集"]["tot"]+=len(rest)
        await b.close()
    print(f'标注项「{it["name"]}」 · 平移{OFF:+d} · {pdf.split("/")[-1]}')
    print(f'{"策略":22} {"召回":>12} {"命中率":>8}')
    print("─"*46)
    for name,d in res.items():
        if not d["tot"]: continue
        print(f'{name:22} {str(d["hit"])+"/"+str(d["tot"]):>12} {d["hit"]/d["tot"]*100:7.1f}%')
asyncio.run(main())
