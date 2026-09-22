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
  const st=staves(page);
  const sys=systemAt(page,ny);
  if(!sys) return {err:'systemAt 返回 null（离所有谱表都太远）',nst:(st||[]).length};
  const lines=detectRowBars(page,sys,headNx);
  if(!lines) return {err:'detectRowBars 返回 null',nst:(st||[]).length};
  // 上线时的真实行为：去掉最右那条（行末终止线），剩下的才会变成小节
  return {staves:sys.staves.length, all:lines, used:lines.slice(0,-1),nst:(st||[]).length};
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
    G=defaultdict(int); PER=defaultdict(lambda: defaultdict(int)); FAIL=[]; UNDRAWN=[]
    async with async_playwright() as p:
        # **每份谱子开一个独立的浏览器会话。** 一个会话里连跑多份，画布会累积状态：
        # staves() 拿到的不是刚渲染的这套而是别的（谱表数还不是 0，所以「空白画布」那类
        # 校验抓不到），systemAt 随之为真值里的行返回 null。实测同一份 CQ_传奇，
        # 单独跑 57/61 = 93.4%、和其它 8 份连跑 30/61 = 49.2%，差别全在这里。
        # 开一次浏览器几秒钟，换一份可信的数字，值。
        for T in load_truth():
            b=await p.chromium.launch(); pg=await b.new_page(viewport={"width":1600,"height":1000})
            await pg.goto("http://127.0.0.1:8778/player.html?direct=1")
            await pg.set_input_files("#fPdf",T["pdf"])
            await pg.wait_for_function("()=>pdf&&boxes.length>1",timeout=60000)
            await pg.evaluate("io&&io.disconnect();zoom=1.6;$('zoom').value=1.6;setPageSizes()")
            bypage=defaultdict(list)
            for (page,ny),marks in T["rows"].items(): bypage[page].append((ny,marks))
            for page in sorted(bypage):
                async def draw():
                    await pg.evaluate("""async(n)=>{if(!boxes[n])return;
                        while(tasks.has(n)){await tasks.get(n).promise.catch(()=>{})}
                        delete boxes[n].dataset.done; visible.add(n); await renderPage(n);}""",page)
                    await pg.wait_for_function("(n)=>boxes[n]&&boxes[n].dataset.done&&cvs[n]&&cvs[n].width>0",
                                               arg=page,timeout=60000)
                # 这一页正常画完时该有几个谱表。**画布脏了（渲染没真正画完就被读走）时 staves()
                # 会给出不一样的一套**，systemAt/detectRowBars 跟着算错 —— 表现是同一页上「组」
                # 大小在 6/5/4 之间跳，或者整行检不出。用这个数当可信度尺子。
                # 基线必须是【正数】才认：画布全白时 staves() 返回 0，要是拿 0 当基线，
                # 「0 == 0」会被判成一致，整页的「没画出来」就冒充成「检测失败」了。
                base_nst=0
                for _ in range(3):
                    await draw()
                    base_nst=await pg.evaluate("(n)=>(staves(n)||[]).length",page)
                    if base_nst: break
                if not base_nst:                     # 三次都画不出来：是测量环境的问题，不是检测的问题
                    for ny,marks in sorted(bypage[page]):
                        UNDRAWN.append((T["name"],page,ny,len(marks)-1))
                    PER[T["name"]]["undrawn"]+=sum(len(m)-1 for _,m in bypage[page]); G["undrawn"]+=sum(len(m)-1 for _,m in bypage[page])
                    continue
                for ny,marks in sorted(bypage[page]):
                    gt=[m["nx"] for m in marks]
                    head,rest=gt[0],gt[1:]
                    r=await pg.evaluate(RUN,[page,ny,head])
                    if r is None or r.get("err") or r.get("nst")!=base_nst or not r.get("used"):
                        await draw()
                        r2=await pg.evaluate(RUN,[page,ny,head])
                        if r2 and not r2.get("err") and r2.get("nst")==base_nst:
                            r=r2
                        elif r is None or r.get("err"):
                            r=r2
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
    print(f'{"谱子":24} {"内部小节线":>12} {"召回":>7} {"多补的":>7} {"一条没补的行":>12} {"没量到":>7}')
    print("─"*82)
    for n,d in PER.items():
        tot=d["rest"]+d["fail"]
        rec=d["hit"]/tot*100 if tot else 0
        print(f'{n:24} {str(d["hit"])+"/"+str(tot):>12} {rec:6.1f}% {d["extra"]:7} {str(d["empty"])+"/"+str(d["rows"]):>12} {d["undrawn"]:7}')
    print("─"*82)
    tot=G["rest"]+G["fail"]
    rec=G["hit"]/tot*100 if tot else 0
    print(f'{"总计":24} {str(G["hit"])+"/"+str(tot):>12} {rec:6.1f}% {G["extra"]:7} {str(G["empty"])+"/"+str(G["rows"]):>12} {G["undrawn"]:7}')
    print(f'\n整行失败（systemAt/detectRowBars 没结果）涉及真实竖线: {G["fail"]} 条')
    print(f'整页没画出来、根本没量到的真实竖线: {G["undrawn"]} 条（这是测量环境的问题，不是检测的锅）')
    for n,pgn,ny,c in UNDRAWN[:8]: print(f'  {n:22} p{pgn} ny={ny:.3f} — 页面渲染不出来（{c}条）')
    for n,pgn,ny,c,err in FAIL[:10]: print(f'  {n:22} p{pgn} ny={ny:.3f} ({c}条) — {err}')
asyncio.run(main())
