# 切模式不移动视图 + 频谱条是浮层。
#
# 用户报：「播放」和「打时间」之间来回切时视图大幅移动。实测三处动因，全在「切到打时间」
# 这一步上：
#   1) 模式自己的显隐会改工具栏高度（编辑行按钮增减、状态行从空长出「目标 → 小节 N」），
#      而工具栏高度是自动适配的输入之一 —— 250ms 后 scheduleFit 重适配、位置按比例挪；
#   2) 频谱条那时还占真实布局空间，specShow(true) 把 wrap.clientHeight 挤小一截，上面那次
#      重适配正好读到这个被改小的值，于是 zoom 整档缩小 —— 这才是「大幅移动」的主体；
#   3) setTap 里是 follow(el,true)，强制滚到「第一个没打时间的小节」，可能离你看的地方很远。
# 前两条靠「频谱浮层化 + absorbFitBox 吸收这次盒子变化」消掉，第三条改成不跟随。
#
# 断言刻意只比「同一份几何的前后」，不写死像素：这套测试里有一批绑死旧默认缩放的教训。
import asyncio, http.server, socketserver, threading, functools
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
PDF=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8846),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c): return "OK   " if c else "FAIL "
settle=0.65          # 切模式后要等过那 250ms 的 scheduleFit 防抖，否则量的是"还没动"

# 竖版视口：页子上下铺开，scrollTop 才有纵深。"视图有没有动"看的就是 zoom + 两个滚动量
VIEW="""()=>({zoom:+zoom.toFixed(4),top:Math.round(wrap.scrollTop),left:Math.round(wrap.scrollLeft),
  wrapH:wrap.clientHeight,wrapW:wrap.clientWidth,specPos:getComputedStyle($('specBox')).position,
  stat:$('stat').textContent,tapM:tapM})"""

# 注意：这套断言只引用 barHpx/rehHpx/specOn 这些旧代码里就有的东西，几何全部现量。
# 反向探针（新测试 × 旧代码）才不会一上来就 ReferenceError —— 那样量到的是"函数名不存在"，
# 不是行为差异，探针就白跑了

errs=[]

async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch()
        pg=await b.new_page(viewport={"width":1100,"height":1400})
        pg.on("pageerror",lambda e:errs.append(str(e)))
        await pg.goto("http://127.0.0.1:8846/player.html?direct=1")
        await pg.evaluate("localStorage.clear()"); await pg.reload()
        await pg.set_input_files("#fPdf",PDF)
        await pg.wait_for_function("()=>cvs[1]&&document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=40000)

        # 每页撒 3 个标记铺满整份谱子：有足够纵深，"视图该不该动"才看得出来
        n=await pg.evaluate("""()=>{const n=cvs.length-1;M=[];let m=0;
          for(let p=1;p<=n;p++)for(let i=0;i<3;i++)M.push({page:p,nx:.15+i*.3,ny:.15+(i%2)*.3,m:++m});
          syncNext();layout();return n}""")
        await asyncio.sleep(0.3)

        # --- 1. 切模式视图不动（核心回归条）---
        # 停在谱子中段（不是原点：从原点出发"位置没变"没有说服力）
        await pg.evaluate("()=>{wrap.scrollTop=Math.round(wrap.scrollHeight*0.45)}")
        await asyncio.sleep(0.2)
        a=await pg.evaluate(VIEW)
        await pg.select_option("#mode","time"); await asyncio.sleep(settle)
        t=await pg.evaluate(VIEW)
        await pg.select_option("#mode","play"); await asyncio.sleep(settle)
        pl=await pg.evaluate(VIEW)
        await pg.select_option("#mode","time"); await asyncio.sleep(settle)
        t2=await pg.evaluate(VIEW)
        print(ok(a["zoom"]==t["zoom"] and a["top"]==t["top"] and a["left"]==t["left"]),
              f"进「打时间」视图不动: zoom {a['zoom']}→{t['zoom']}, "
              f"scrollTop {a['top']}→{t['top']}, scrollLeft {a['left']}→{t['left']}")
        print(ok(a["zoom"]==t2["zoom"] and a["top"]==t2["top"] and a["left"]==t2["left"]),
              f"time→play→time 来回切仍不动: zoom {t2['zoom']}, scrollTop {t2['top']}, scrollLeft {t2['left']}"
              f"（中途回 play 时是 {pl['zoom']}/{pl['top']}/{pl['left']}）")

        # --- 2. 频谱条是浮层 ---
        print(ok(t["specPos"]=="fixed"), f"#specBox 是 position:fixed（实际 {t['specPos']}）")
        # 它是浮层，所以开合它不改 #wrap 的高度。旧代码上这里会从 1400 掉到 ~1257 ——
        # 那正是"重适配读到被改小的 wrap.clientHeight、于是谱子缩一圈"的入口
        print(ok(a["wrapH"]==t["wrapH"] and a["wrapW"]==t["wrapW"]),
              f"自动展开频谱不改 #wrap 的尺寸: {a['wrapW']}×{a['wrapH']} → {t['wrapW']}×{t['wrapH']}")

        # 浮层不参与适配 => 手动开合它也不改缩放。这正是"适应屏幕之后关掉频谱、
        # 谱面底部空一块"的根因：旧代码里关掉它时 #wrap 变高，可那次适配读到的仍是旧值
        await pg.click("#specClose"); await asyncio.sleep(settle)
        c=await pg.evaluate(VIEW)
        await pg.click("#bSpec"); await asyncio.sleep(settle)
        d=await pg.evaluate(VIEW)
        print(ok(c["zoom"]==t["zoom"] and d["zoom"]==t["zoom"] and c["wrapH"]==t["wrapH"]),
              f"手动收起/展开频谱都不改缩放与 #wrap: zoom {t['zoom']}→{c['zoom']}→{d['zoom']}, "
              f"wrap 高 {t['wrapH']}→{c['wrapH']}→{d['wrapH']}")

        # --- 3. 跟随把目标停在「工具栏下沿 → 频谱上沿」这一截里（浮层化的配套改动）---
        # 这条是**配套守卫**，不是新旧的分水岭：旧代码里它靠 #wrap 被频谱挤小而隐式成立
        # （可见带的高度碰巧对得上）。浮层化之后 #wrap 不再被挤，就得由 follow 自己把浮层减掉
        # —— 漏了的话它以为可见带一直到视口底，落点整体往下掉 0.15*频谱高 ≈ 21px。
        # 拿最后一个小节（一定在屏幕外）强制跟随，量它落点对不对得上实际可见带的 15%
        await pg.evaluate("()=>{wrap.scrollTop=0}")
        await asyncio.sleep(0.2)
        r=await pg.evaluate("""()=>{const m=M[M.length-1].m;setTap(m,true);
          return new Promise(res=>setTimeout(()=>{
            const wr=wrap.getBoundingClientRect();
            const vt=wr.top+barHpx();                  // 可见带上沿：工具栏下沿
            let vb=innerHeight-rehHpx();               // 下沿：先到视口底 - 排练胶囊
            if(specOn())vb=Math.min(vb,$('specBox').getBoundingClientRect().top);
            const g={vt:Math.round(vt),vh:Math.round(vb-vt),
                     specTop:Math.round($('specBox').getBoundingClientRect().top)};
            const b=byM.get(m)[0].getBoundingClientRect();
            res({m,top:Math.round(b.top),want:Math.round(g.vt+g.vh*0.15),
                 specTop:g.specTop,vt:g.vt,vh:g.vh});
          },1100))}""")
        print(ok(abs(r["top"]-r["want"])<=3 and r["top"]<r["specTop"]),
              f"跟随落在可见带的 15% 处: 小节{r['m']} 顶边 {r['top']} ≈ 期望 {r['want']}"
              f"（带 {r['vt']}→{r['vt']+r['vh']}，高 {r['vh']}；频谱上沿 {r['specTop']}）")

        # --- 4. 不再强制跟随，但目标不丢 ---
        # 让「第一个还没打时间的小节」落在谱子后段（一定在屏幕外），再清掉 tapM、滚回原点。
        # 旧代码会 follow(el,true) 把你直接拽到那个小节；新代码留在原地，目标写在状态行里
        await pg.select_option("#mode","play"); await asyncio.sleep(settle)
        await pg.evaluate("""()=>{wrap.scrollTop=0;tapM=null;
          E=M.slice(0,Math.floor(M.length*0.6)).map((mk,i)=>({m:mk.m,t:i,src:'tap'}));
          refresh()}""")
        await asyncio.sleep(settle)     # 状态行由有内容变空，等这波布局/适配定下来再取基准
        before=await pg.evaluate(VIEW)
        await pg.select_option("#mode","time"); await asyncio.sleep(settle)
        after=await pg.evaluate(VIEW)
        print(ok(before["top"]==after["top"]),
              f"切到打时间不再强制跟随: scrollTop {before['top']}→{after['top']}")
        print(ok(after["tapM"] is not None and "目标 → 小节" in after["stat"]),
              f"但目标仍在状态行里: tapM={after['tapM']} stat=\"{after['stat']}\"")

        # --- 5. absorbFitBox 只吸收"切模式"那一条路，别把真该重适配的也吞掉 ---
        # 演奏态整行收起编辑行+状态行（setPerf 也会调 syncMode），这是刻意的"给谱面腾地方"；
        # 要是把 absorbFitBox 挪进 syncMode()，这一条就会静默失效 —— 谱子该变大却纹丝不动
        # 先走一趟演奏态再回来：切模式是吸收掉的（这正是上面在测的），所以此刻的 zoom 还停在
        # 上一个模式的工具栏高度上；这一趟会真的重适配一次，把 zoom 落到当前工具栏的稳态，
        # 之后两次切换才有干净的基准可比
        await pg.select_option("#mode","play"); await asyncio.sleep(settle)
        await pg.click("#bPerf"); await asyncio.sleep(settle)
        await pg.click("#bPerf"); await asyncio.sleep(settle)
        z0=await pg.evaluate("zoom")
        await pg.click("#bPerf"); await asyncio.sleep(settle)
        z1=await pg.evaluate("zoom")
        await pg.click("#bPerf"); await asyncio.sleep(settle)
        print(ok(z1>z0), f"切演奏态（编辑行/状态行收起）仍然重适配: zoom {round(z0,3)} → {round(z1,3)}")
        # 收起工具栏同理：工具栏没了、底部胶囊浮出来，谱面该按新的可用高重算
        z3=await pg.evaluate("zoom")
        await pg.click("#bBar"); await asyncio.sleep(settle)
        z2=await pg.evaluate("zoom")
        await pg.click("#barShow"); await asyncio.sleep(settle)
        print(ok(z2!=z3), f"收起工具栏仍然重适配: zoom {round(z3,3)} → {round(z2,3)}")

        if errs: print("page errors:",errs)
        await b.close()

asyncio.run(main())
