import asyncio, http.server, socketserver, threading, functools
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
PDF=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8754),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c): return "OK   " if c else "FAIL "

async def main():
    errs=[]
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={"width":1500,"height":1000})
        pg.on("pageerror",lambda e:errs.append(str(e)))
        await pg.goto("http://127.0.0.1:8754/player.html?direct=1")
        await pg.evaluate("localStorage.clear()"); await pg.reload()
        await pg.set_input_files("#fPdf",PDF)
        await pg.wait_for_function("()=>cvs[1]&&document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=40000)

        st=await pg.evaluate("staves(1).map(s=>({t:+s.top.toFixed(4),b:+s.bot.toFixed(4)}))")
        print(ok(len(st)>=8), f"谱表检测: {len(st)} 个，前两个 {st[:2]}")
        print(ok(await pg.evaluate("staves(1)===staves(1)")), "结果被缓存（同一对象）")

        # --- ① 对齐同行 ---
        await pg.evaluate("$('chkSnapX').checked=false;$('chkAlignY').checked=true")
        await pg.evaluate("M=[{page:1,nx:.30,ny:.28,m:1,h:.06}];lastH=.06;syncNext();layout()")
        await pg.evaluate("""()=>{const mk={page:1,nx:.50,ny:.295,m:2,h:.09};M.push(mk);
            window.__hit=applySnaps(mk);syncNext();layout()}""")
        r=await pg.evaluate("({ny:M[1].ny,h:M[1].h,nx:+M[1].nx.toFixed(3),hit:window.__hit})")
        print(ok(abs(r["ny"]-.28)<1e-9 and abs(r["h"]-.06)<1e-9 and abs(r["nx"]-.50)<1e-9),
              f"对齐同行: ny .295->{r['ny']}, h .09->{r['h']}, nx 不动={r['nx']} ({r['hit']})")
        # 纵向差太远（不同系统）不对齐
        await pg.evaluate("""()=>{const mk={page:1,nx:.5,ny:.60,m:3,h:.09};M.push(mk);
            window.__hit2=applySnaps(mk)}""")
        print(ok(abs(await pg.evaluate("M[2].ny")-.60)<1e-9), f"隔了一个系统不对齐: ny={await pg.evaluate('M[2].ny')}")
        await pg.evaluate("$('chkAlignY').checked=false")
        await pg.evaluate("""()=>{const mk={page:1,nx:.5,ny:.295,m:4,h:.09};M.push(mk);applySnaps(mk)}""")
        print(ok(abs(await pg.evaluate("M[3].ny")-.295)<1e-9), "关掉开关就不对齐")

        # --- ② 吸小节线 ---
        await pg.evaluate("$('chkAlignY').checked=false;$('chkSnapX').checked=true;$('barWin').value=12")
        # 取一个真实小节线位置
        truth=await pg.evaluate("""()=>{const s=staves(1),c=cvs[1],W=c.width,Hh=c.height;
          const d=c.getContext('2d',{willReadFrequently:true}).getImageData(0,0,W,Hh).data;
          const lum=(x,y)=>{const p=(y*W+x)*4;return d[p]*.299+d[p+1]*.587+d[p+2]*.114};
          const s0=s[2],a=Math.round(s0.top*Hh),bb=Math.round(s0.bot*Hh),hh=bb-a+1,out=[];
          for(let x=2;x<W-2;x++){let n=0;for(let y=a;y<=bb;y++){let dk=false;
            for(let k=x-1;k<=x+1;k++)if(lum(k,y)<175){dk=true;break} if(dk)n++}
            if(n/hh>=0.95&&(!out.length||x-out[out.length-1]>5))out.push(x)}
          return {xs:out,W,ny:s0.top,h:s0.bot-s0.top}}""")
        tx=truth["xs"][len(truth["xs"])//2]
        for off in (-7,-3,5,8):
            got=await pg.evaluate("""([nx,ny,h])=>{const mk={page:1,nx,ny,h};
              const r=snapBarX(mk,12);return r==null?null:Math.round(r*cvs[1].width)}""",
              [(tx+off)/truth["W"],truth["ny"],truth["h"]])
            print(ok(got is not None and abs(got-tx)<=3), f"  放偏 {off:+d}px -> 吸到 {got} (真值 {tx}±3，同一条线的宽度内)")
        far=await pg.evaluate("""([nx,ny,h])=>{const mk={page:1,nx,ny,h};
          const r=snapBarX(mk,12);return r==null?null:Math.round(r*cvs[1].width)}""",
          [(tx+60)/truth["W"],truth["ny"],truth["h"]])
        print(ok(far is None or abs(far-(tx+60))<=12), f"  放偏 60px（窗口外）-> {far}，不会拉回原来那条")
        # 画布没渲染时不吸
        none=await pg.evaluate("""()=>{const mk={page:99,nx:.5,ny:.3,h:.06};return snapBarX(mk,12)}""")
        print(ok(none is None), "页面没渲染 -> 不吸（返回 null）")

        # --- ③ 行末高亮带按同行中位间距收边 ---
        await pg.evaluate("""()=>{M=[{page:1,nx:.15,ny:.30,m:1,h:.06},{page:1,nx:.35,ny:.30,m:2,h:.06},
             {page:1,nx:.55,ny:.30,m:3,h:.06},{page:1,nx:.15,ny:.50,m:4,h:.06}];
          E=[{m:1,t:0},{m:2,t:2},{m:3,t:4},{m:4,t:6}];syncNext();layout();aud.pause()}""")
        await pg.evaluate("aud.currentTime=4.5"); await asyncio.sleep(0.25)
        r=await pg.evaluate("""()=>{const b=document.getElementById('band'),W=b.parentElement.clientWidth;
          return {L:+(b.offsetLeft/W).toFixed(3),R:+((b.offsetLeft+b.offsetWidth)/W).toFixed(3)}}""")
        print(ok(abs(r["R"]-.935)<.01), f"行末小节: 带子 {r['L']}→{r['R']} (精确检测行末终止线 .935，不再拿中位间距猜成 .75)")
        print(ok(abs(await pg.evaluate("lineSpan(M[2])")-.20)<1e-6), f"中位间距 = {await pg.evaluate('lineSpan(M[2])')}")

        # --- 实际点击标小节时生效 ---
        await pg.evaluate("M=[];E=[];syncNext();layout();$('chkAlignY').checked=true;$('chkSnapX').checked=true")
        await pg.select_option("#mode","mark")
        bb=await (await pg.query_selector('.page[data-page="1"]')).bounding_box()
        ny=truth["ny"]; h=truth["h"]
        await pg.evaluate(f"lastH={h}")
        sc=await pg.evaluate("boxes[1].clientWidth/cvs[1].width")
        await pg.mouse.click(bb["x"]+(tx+6)*sc, bb["y"]+bb["height"]*(ny+h/2))
        got=await pg.evaluate("Math.round(M[0].nx*cvs[1].width)")
        print(ok(abs(got-tx)<=3), f"点击标小节自动吸附: 点在 {tx+6} -> 存成 {got} (真值 {tx}±3)")
        print(ok("吸到小节线" in await pg.inner_text("#msg")), f'提示: "{await pg.inner_text("#msg")}"')

        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
