# 诊断：把【你标的 nx】和【检测出来的小节线】放在同一页上比，看差在哪。
# eval_autobar3 只报一个「召回 35.3%」——知道不对，不知道是怎么不对。这一个专门回答：
#   · 整体平移？  → 每行残差同号、且不随 x 变
#   · 整体缩放？  → 残差随 x 线性增大，拟合出的 a≠1
#   · 每行都找不到（systemAt 返回 null）？ → ny 就不对，是页码/内容对不上
# 用法：python3 tests/diag_align.py <pdf路径> <标注项名片段> [页码平移=0]
import asyncio, json, sys, http.server, socketserver, threading, functools
from collections import defaultdict
from playwright.async_api import async_playwright

ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
ANN=ROOT+"/SheetPlayer/annotations.json"
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8779),H); threading.Thread(target=srv.serve_forever,daemon=True).start()

RUN=r"""
([page,ny,headNx])=>{
  const sys=systemAt(page,ny);
  if(!sys) return {err:'systemAt null'};
  const lines=detectRowBars(page,sys,headNx);
  if(!lines) return {err:'detectRowBars null'};
  return {sysTop:sys.top,sysBot:sys.bot,nstaff:sys.staves.length,all:lines,used:lines.slice(0,-1)};
}
"""

def load_item(frag):
    d=json.load(open(ANN))
    for it in d["items"]:
        if frag in it["name"]:
            rows=defaultdict(list)
            for m in it["data"].get("M",[]):
                rows[(m["page"],round(m["ny"],3))].append(m)
            return it,{k:sorted(v,key=lambda x:x["nx"]) for k,v in rows.items()}
    raise SystemExit("没找到标注项: "+frag)

async def main():
    pdf, frag = sys.argv[1], sys.argv[2]
    OFF = int(sys.argv[3]) if len(sys.argv)>3 else 0
    it, rows = load_item(frag)
    print(f'标注项「{it["name"]}」 · 标注 {sum(len(v) for v in rows.values())} 条 · 平移到 PDF 页 {OFF:+d}')
    print(f'PDF: {pdf}\n')

    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={"width":1600,"height":1000})
        await pg.goto("http://127.0.0.1:8779/player.html?direct=1")
        await pg.set_input_files("#fPdf",pdf)
        await pg.wait_for_function("()=>pdf&&boxes.length>1",timeout=60000)
        await pg.evaluate("io&&io.disconnect()")
        await pg.wait_for_timeout(1200)
        nopages=await pg.evaluate("()=>boxes.length")
        print(f"这份 PDF 有 {nopages} 页\n")

        pairs=[]; stats=defaultdict(lambda: defaultdict(float))
        for page in sorted({k[0] for k in rows}):
            tp=page+OFF
            if tp<1 or tp>nopages:
                print(f"— 标注第{page}页 → PDF第{tp}页：超出范围，跳过"); continue
            async def draw():
                await pg.evaluate("""async(n)=>{if(!boxes[n])return;
                    while(tasks.has(n)){await tasks.get(n).promise.catch(()=>{})}
                    delete boxes[n].dataset.done; visible.add(n); await renderPage(n);}""",tp)
                await pg.wait_for_function("(n)=>boxes[n]&&boxes[n].dataset.done&&cvs[n]&&cvs[n].width>0",
                                           arg=tp,timeout=60000)
            await draw()
            CW,CH=await pg.evaluate("(n)=>[cvs[n].width,cvs[n].height]",tp)
            print(f"══ 标注第{page}页 → PDF第{tp}页 （画布 {CW}x{CH}）")
            for (pgn,ny),marks in sorted(rows.items()):
                if pgn!=page: continue
                gt=[m["nx"] for m in marks]
                r=await pg.evaluate(RUN,[tp,ny,gt[0]])
                if r is None or r.get("err"):
                    print(f"  ny={ny:.3f}  ✗ {r.get('err') if r else 'null'}   （这行整体没检出）")
                    stats[page]["errrow"]+=1; stats[page]["marks"]+=len(gt)-1; continue
                det=sorted(r["used"]); used=set(); hits=[]; miss=[]
                for g in gt[1:]:
                    best=None;bd=0.008
                    for i,x in enumerate(det):
                        if i in used: continue
                        if abs(x-g)<bd: bd=abs(x-g);best=i
                    if best is None: miss.append(g)
                    else: used.add(best); hits.append((g,det[best]))
                pairs += hits
                dh=r["sysBot"]-r["sysTop"]
                hs=[m["h"] for m in marks]
                res=[f"{(d-g)*1000:+.1f}‰" for g,d in hits]
                print(f"  ny={ny:.3f} 系统[{r['sysTop']:.3f},{r['sysBot']:.3f}] 高{dh:.3f}"
                      f"（标注 h≈{sum(hs)/len(hs):.3f}）谱表×{r['nstaff']} "
                      f"检出{len(det)}条 命中{len(hits)}/{len(gt)-1}")
                print(f"        残差(‰页宽): {' '.join(res) if res else '—'}")
                if miss:
                    print(f"        漏: {' '.join(f'{m:.3f}' for m in miss)}")
                    print(f"        标注全: {' '.join(f'{m:.3f}' for m in gt)}")
                    print(f"        检出全: {' '.join(f'{x:.3f}' for x in sorted(r['all']))}")
                stats[page]["marks"]+=len(gt)-1; stats[page]["hit"]+=len(hits)
            print()
        await b.close()

    print("═"*70)
    tm=th=0
    for page in sorted(stats):
        m=stats[page]["marks"]; h=stats[page]["hit"]
        if m: print(f"  标注第{page}页: {int(h)}/{int(m)} = {h/m*100:.1f}%  整行没检出 {int(stats[page]['errrow'])} 行")
        tm+=m; th+=h
    print(f"  合计: {int(th)}/{int(tm)} = {th/tm*100:.1f}%" if tm else "  没有可比对的行")
    # 线性拟合 nx_det = a*nx_ann + b —— a≈1 且 b≈0 说明只是噪声，a≠1 就是缩放
    if len(pairs)>=4:
        n=len(pairs); sx=sum(g for g,_ in pairs); sy=sum(d for _,d in pairs)
        sxx=sum(g*g for g,_ in pairs); sxy=sum(g*d for g,d in pairs)
        den=n*sxx-sx*sx
        a=(n*sxy-sx*sy)/den if den else float('nan'); b=(sy-a*sx)/n
        my=sy/n; ss=sum((d-my)**2 for _,d in pairs)
        sr=sum((d-(a*g+b))**2 for g,d in pairs)
        r2=1-sr/ss if ss else float('nan')
        res=[d-g for g,d in pairs]
        print(f"\n  残差：均值{sum(res)/n*1000:+.1f}‰  最大{max(res,key=abs)*1000:+.1f}‰  |残差|中位{sorted(abs(x) for x in res)[n//2]*1000:.1f}‰")
        print(f"  拟合 nx_检出 = {a:.4f}·nx_标注 {b:+.4f}   R²={r2:.4f}")
        print(f"  → {'差不多只是噪声/平移' if abs(a-1)<0.002 else f'**缩放**：检出比标注横向缩了 {1-a:+.4f}（{(1-a)*100:+.2f}% 页宽）'}")
asyncio.run(main())
