import asyncio, http.server, socketserver, threading, functools, sys
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
PDF=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*a): pass          # 这些测量脚本要打整块表格，别被访问日志冲掉
H=functools.partial(Quiet,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8820),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c): return "OK   " if c else "FAIL "

# 触屏平板竖/横各种尺寸。竖屏宽度就是 iPad 各型号的 CSS 宽度。
SIZES=[
    ("iPad mini 竖",   744,1133),
    ("iPad 10.2 竖",   810,1080),
    ("iPad Air 竖",    820,1180),
    ("iPad Pro11 竖",  834,1194),
    ("iPad Pro12 竖", 1024,1366),
    ("iPad 横",       1133,744),
    ("iPad Pro12 横", 1366,1024),
]

PROBE="""()=>{
  // .row 是 align-items:center，同一折行上的子项纵向居中 → 中心相同。
  // 用 top 计数会把同行的 44px 按钮和 20px 分隔符算成两行，必须按中心聚类。
  const lines=el=>{
    const kids=[...el.children].filter(c=>{
      const cs=getComputedStyle(c);
      return cs.display!=='none'&&c.getBoundingClientRect().height>0});
    const centers=kids.map(c=>{const r=c.getBoundingClientRect();return (r.top+r.bottom)/2})
                      .sort((a,b)=>a-b);
    let n=0,last=-1e9;
    for(const c of centers){if(c-last>6){n++;last=c}}
    return n;
  };
  const rows=[...document.querySelectorAll('#bar .row')].map((r,i)=>({
    i,
    lines:lines(r),
    oh:r.offsetHeight,
    sw:r.scrollWidth,
    cw:r.clientWidth,
    overflow:Math.max(0,r.scrollWidth-r.clientWidth),
    wrap:getComputedStyle(r).flexWrap,
    ox:getComputedStyle(r).overflowX,
  }));
  // 面板必须真的打开再量：量 display:none 的元素只能拿到计算值，
  // 而 top:auto 这类"被更靠后的基础规则压掉"的问题，只有在真实布局里才看得出来
  const pn=document.querySelector('#panel');
  const pcs=getComputedStyle(pn);
  const pr=pn.getBoundingClientRect();
  return {
    barH:document.querySelector('#bar').offsetHeight,
    barHVar:getComputedStyle(document.documentElement).getPropertyValue('--barH').trim(),
    rows,
    panelOpen:pn.style.display!=='none'&&pcs.display!=='none',
    panel:{top:Math.round(pr.top),bottom:Math.round(pr.bottom),h:Math.round(pr.height),
           left:Math.round(pr.left),right:Math.round(pr.right),
           cssTop:pcs.top,cssBottom:pcs.bottom, maxH:pcs.maxHeight},
    barBottom:document.querySelector('#bar').getBoundingClientRect().bottom,
    vw:innerWidth, vh:innerHeight,
  };
}"""

async def probe(pg):
    return await pg.evaluate(PROBE)

async def main():
    errs=[]
    print("=== 触屏版式基线测量（has_touch=True，原生 44px 目标规则生效）===")
    print("目的：量出工具栏在平板各尺寸下折成几行、占多少高，作为「问题 2 动不动版式」的判据\n")
    async with async_playwright() as p:
        b=await p.chromium.launch()
        worst=0; seen=[]
        for name,w,h in SIZES:
            pg=await b.new_page(viewport={"width":w,"height":h},has_touch=True,device_scale_factor=2)
            pg.on("pageerror",lambda e:errs.append(str(e)))
            await pg.goto("http://127.0.0.1:8820/player.html?direct=1")
            await pg.evaluate("localStorage.clear()")
            # 手机/平板现在打开就收起工具栏（player.html 里 pointer:coarse 那段）。
            # 这个文件量的是工具栏的换行版式与屏高占比，必须在展开态量
            await pg.evaluate("setBarHidden(false)")
            await pg.set_input_files("#fPdf",PDF)
            await pg.wait_for_function("()=>document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=40000)
            await pg.wait_for_timeout(250)
            print(f"--- {name}  {w}×{h} ---")
            for scen,label in [(2,"2 段"),(4,"4 段"),(8,"8 段")]:
                # 用真的 RUNS 切分规则造段落条：小节号往回跳 = 新的一遍
                await pg.evaluate("""(nRuns)=>{
                  M=[];E=[];
                  for(let r=0;r<nRuns;r++)for(let m=1;m<=4;m++){
                    if(r===0)M.push({page:1,nx:.1+.11*m,ny:.3,m,h:.06});
                    E.push({m,t:(r*4+m)*2,src:'tap'});
                  }
                  M.push({page:1,nx:.1+.11*5,ny:.3,m:5,h:.06});
                  syncNext();layout();
                }""",scen)
                await pg.wait_for_timeout(300)
                # 打开标记面板，量它真实的锚定方式（底部抽屉 vs 右上角浮层）
                await pg.select_option("#mode","edit"); await pg.wait_for_timeout(150)
                await pg.evaluate("openPanel(1)"); await pg.wait_for_timeout(250)
                st=await pg.evaluate("()=>({runs:RUNS.length,chips:document.querySelectorAll('#chips .chip').length,"
                                     "cw:$('chipWrap').style.display})")
                d=await probe(pg)
                totalLines=sum(r["lines"] for r in d["rows"])
                worst=max(worst,d["barH"]); seen.append((name,scen,d["barH"]))
                print(f"    · {label}（{st['runs']} 段 / {st['chips']} 个 chip，段落条 display={st['cw'] or 'flex'}）")
                print(f"        工具栏高 {d['barH']}px (--barH={d['barHVar']})  视口高 {d['vh']}px  → 占 {d['barH']/d['vh']*100:.0f}%"
                      f"   折行合计 {totalLines} 行（桌面 3 行）")
                for r in d["rows"]:
                    print(f"          .row[{r['i']}] {r['lines']} 行 / 高 {r['oh']}px  wrap={r['wrap']:<8} ox={r['ox']:<7} "
                          f"内容 {r['sw']} / 可视 {r['cw']}  横向溢出 {r['overflow']}px")
                pa=d["panel"]
                # 别看 computed top 是不是 'auto'——元素一旦参与布局，top:auto 会被解析成实际用的 px 值。
                # 看真实几何：底边贴视口下沿、且左右都留 8px（整幅宽）才算抽屉
                drawer=(abs(pa["bottom"]-(d["vh"]-8))<=1 and pa["left"]==8
                        and abs(pa["right"]-(d["vw"]-8))<=1)
                print(f"        #panel 打开后 {pa['left']}–{pa['right']} × 高 {pa['h']}px，"
                      f"纵向 {pa['top']}–{pa['bottom']}（视口 {d['vh']}）")
                print(f"          {'底部抽屉 ✓ 底边贴视口下沿 8px' if drawer else '右上角浮层（top 锚定）'}"
                      f" · 不压工具栏: {pa['top']} ≥ {round(d['barBottom'])} → {pa['top']>=d['barBottom']-1}"
                      f" · 不出屏: {pa['bottom']} ≤ {d['vh']} → {pa['bottom']<=d['vh']}")
                await pg.evaluate("$('panel').style.display='none'")
            await pg.close()
        print(f"\n工具栏最高 {worst}px")
        print("="*64)
        # 改动的核心断言：工具栏高度不再随段落数增长。
        # 改前 2→8 段，iPad mini 从 242px 一路涨到 458px；改后横滑，恒定不变。
        byCount={}
        for name,scen,bh in seen: byCount.setdefault(name,{})[scen]=bh
        spread=sorted(((max(bs.values())-min(bs.values()),name,bs) for name,bs in byCount.items()),
                      reverse=True)
        for gap,name,bs in spread[:4]:
            print(f"  {name:18} 各段落数下的工具栏高 {dict(sorted(bs.items()))}  差 {gap}px")
        if spread:
            gap,name,_=spread[0]
            print(ok(gap<=8), f"工具栏高度不随段落数增长（最大差 {gap}px / {name} ≤ 8px）")

        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
