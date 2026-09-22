import asyncio, http.server, socketserver, threading, functools
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
PDF=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8755),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c): return "OK   " if c else "FAIL "

async def main():
    errs=[]
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={"width":1500,"height":1000})
        pg.on("pageerror",lambda e:errs.append(str(e)))
        await pg.goto("http://127.0.0.1:8755/player.html?direct=1")
        await pg.evaluate("localStorage.clear()"); await pg.reload()
        await pg.set_input_files("#fPdf",PDF)
        await pg.wait_for_function("()=>cvs[1]&&document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=40000)

        # 找一条真实小节线 + 它所在谱表
        truth=await pg.evaluate("""()=>{const s=staves(1),c=cvs[1],W=c.width,Hh=c.height;
          const d=c.getContext('2d',{willReadFrequently:true}).getImageData(0,0,W,Hh).data;
          const lum=(x,y)=>{const p=(y*W+x)*4;return d[p]*.299+d[p+1]*.587+d[p+2]*.114};
          const s0=s[2],a=Math.round(s0.top*Hh),bb=Math.round(s0.bot*Hh),hh=bb-a+1,out=[];
          for(let x=2;x<W-2;x++){let n=0;for(let y=a;y<=bb;y++){let dk=false;
            for(let k=x-1;k<=x+1;k++)if(lum(k,y)<175){dk=true;break} if(dk)n++}
            if(n/hh>=0.95&&(!out.length||x-out[out.length-1]>5))out.push(x)}
          return {tx:out[Math.floor(out.length/2)],W,ny:s0.top,h:s0.bot-s0.top}}""")
        sc=await pg.evaluate("boxes[1].clientWidth/cvs[1].width")
        tx=truth["tx"]

        # 先放一个没吸准的标记（故意偏 8px）
        await pg.evaluate("$('chkAlignY').checked=true;$('chkSnapX').checked=true;$('barWin').value=12")
        await pg.evaluate(f"""M=[{{page:1,nx:{(tx+8)/truth['W']},ny:{truth['ny']},m:1,h:{truth['h']}}}];
                              lastH={truth['h']};E=[];syncNext();layout()""")
        nx0=await pg.evaluate("M[0].nx*"+str(truth["W"]))
        print(ok(abs(nx0-(tx+8))<1), f"初始：故意偏 8px，未吸（直接塞数据不走吸附）: {nx0}")

        # 编辑模式，抓中段，拖一下再松手。
        # 拖动方向是**朝着**真值挪（−4px），不是背着它挪。原来写的是 (+6,+3)，落点停在
        # 真值 +14px 处——barWin 是 12px，那已经在吸附窗口之外了，当年能过纯属印刷小节线
        # 的抗锯齿尾巴多够到 2px（实测把「偏 N px」扫一遍：基线在 +14 还能吸、+16 就不行，
        # 新版卡在 +12）。也就是说那条断言测的不是吸附，是一个 1px 的巧合——换台机器、
        # 换个缩放就会翻。挪到窗口内才是在测「松手会吸」这件事本身。
        # 纵向仍要给够 +4：dragMove 的起手死区是 hypot<3px，只动横向容易卡在死区里。
        await pg.select_option("#mode","mark")
        el=await pg.query_selector('.mk[data-m="1"]'); r=await el.bounding_box()
        mx=r["x"]+r["width"]/2; my=r["y"]+r["height"]/2
        await pg.mouse.move(mx,my); await pg.mouse.down()
        await pg.mouse.move(mx-4,my+4,steps=5); await pg.mouse.up(); await asyncio.sleep(0.3)
        got=await pg.evaluate("Math.round(M[0].nx*cvs[1].width)")
        print(ok(abs(got-tx)<=3), f"拖动松手后吸附: 存成 {got} (真值 {tx}±3)")
        print(ok("小节 1" in await pg.inner_text("#msg")), f'提示: "{await pg.inner_text("#msg")}"')

        # 改长度（拖下端）不该触发吸附
        await pg.evaluate("undo();syncNext();layout()")
        el=await pg.query_selector('.mk[data-m="1"]'); r=await el.bounding_box()
        nx0=await pg.evaluate("M[0].nx"); h0=await pg.evaluate("M[0].h")
        await pg.mouse.move(r["x"]+r["width"]/2, r["y"]+r["height"]-1); await pg.mouse.down()
        await pg.mouse.move(r["x"]+r["width"]/2, r["y"]+r["height"]+50,steps=5); await pg.mouse.up()
        await asyncio.sleep(0.3)
        nx1=await pg.evaluate("M[0].nx"); h1=await pg.evaluate("M[0].h")
        print(ok(abs(nx1-nx0)<1e-9 and abs(h1-h0)>0.01),
              f"拖下端改长度：nx 不变({nx0}->{nx1})，高度变了({h0:.3f}->{h1:.3f})，没被吸附弹走")

        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
