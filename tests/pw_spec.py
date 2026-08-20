import asyncio, glob, http.server, socketserver, threading, functools
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
PDF=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
AUD=glob.glob(ROOT+"/ICT_working/08-Assets/*.mp3")[0]
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8742),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c): return "OK   " if c else "FAIL "

async def main():
    errs=[]
    async with async_playwright() as p:
        b=await p.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"])
        pg=await b.new_page(viewport={"width":1500,"height":1000})
        pg.on("pageerror",lambda e:errs.append(str(e)))
        await pg.goto("http://127.0.0.1:8742/player.html?direct=1")
        await pg.evaluate("localStorage.clear()"); await pg.reload()

        # 无音频时的占位
        await pg.click("#bSpec"); await asyncio.sleep(0.3)
        print(ok(await pg.is_visible("#specBox")), "频谱条可展开")
        print(ok(await pg.evaluate("SPEC===null")), "没音频时 SPEC 为空（画占位文字）")

        await pg.set_input_files("#fPdf",PDF)
        await pg.wait_for_function("()=>document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=30000)
        await pg.set_input_files("#fAud",AUD)
        t0=await pg.evaluate("performance.now()")
        await pg.wait_for_function("()=>SPEC!==null",timeout=60000)
        t1=await pg.evaluate("performance.now()")
        s=await pg.evaluate("({frames:SPEC.frames,hop:SPEC.hop,dur:+SPEC.dur.toFixed(1),w:SPEC.cv.width,h:SPEC.cv.height})")
        print(ok(s["frames"]>1000), f"分析完成 {round(t1-t0)}ms: {s}")
        sm=await pg.inner_text("#specMsg")
        print(ok("检出" in sm and "起音" in sm), f'分析完毕后提示改为起音数: "{sm}"')

        # 画布确实画出了东西（不是纯黑）
        stats=await pg.evaluate("""()=>{const c=$('specCv'),x=c.getContext('2d');
          const d=x.getImageData(0,0,c.width,c.height).data;
          let sum=0,n=0,mx=0; for(let i=0;i<d.length;i+=4*97){const v=(d[i]+d[i+1]+d[i+2])/3;sum+=v;n++;if(v>mx)mx=v}
          return {avg:+(sum/n).toFixed(1),max:mx,w:c.width,h:c.height}}""")
        print(ok(stats["max"]>60 and stats["avg"]>5), f"画布有内容: {stats}")

        # 竖线：造几个时间点
        await pg.evaluate("""()=>{M=Array.from({length:20},(_,i)=>({page:1,nx:.1+(i%6)*.15,ny:.2+Math.floor(i/6)*.1,m:i+1}));
          E=[{m:1,t:1.0,src:'tap'},{m:2,t:3.0,src:'gen'},{m:3,t:5.0,src:'gen'}];
          syncNext();layout();aud.currentTime=3;specDirty=true}""")
        await asyncio.sleep(0.4)
        # 抓取黄色(实测)和蓝色(生成)像素
        px=await pg.evaluate("""()=>{const c=$('specCv'),x=c.getContext('2d');
          const d=x.getImageData(0,0,c.width,c.height).data;
          let yellow=0,blue=0,red=0;
          for(let i=0;i<d.length;i+=4){const r=d[i],g=d[i+1],b=d[i+2];
            if(r>200&&g>170&&g<230&&b<110)yellow++;
            if(b>210&&r<130&&g>140&&g<200)blue++;
            if(r>220&&g<95&&b<95)red++;}
          return {yellow,blue,red}}""")
        print(ok(px["yellow"]>50 and px["blue"]>50 and px["red"]>50),
              f"竖线渲染: 实测(黄)={px['yellow']}px 生成(蓝)={px['blue']}px 播放头(红)={px['red']}px")

        # 点击空白定位
        cv=await pg.query_selector("#specCv"); r=await cv.bounding_box()
        await pg.evaluate("aud.pause();aud.currentTime=10")
        await asyncio.sleep(0.2)
        before=await pg.evaluate("aud.currentTime")
        await pg.mouse.click(r["x"]+r["width"]*0.25, r["y"]+r["height"]*0.5)
        after=await pg.evaluate("aud.currentTime")
        pps=await pg.evaluate("specPPS"); w=await pg.evaluate("specW()")
        want=before-(w/2)/pps+(w*0.25)/pps
        print(ok(abs(after-want)<0.15), f"点击定位: {before:.2f}s -> {after:.2f}s (期望 {want:.2f}s)")

        # 拖竖线改时间
        await pg.evaluate("aud.currentTime=3;E=[{m:2,t:3.0,src:'gen'}];refresh();specDirty=true")
        await asyncio.sleep(0.3)
        x0=r["x"]+r["width"]/2
        await pg.mouse.move(x0, r["y"]+r["height"]/2); await pg.mouse.down()
        await pg.mouse.move(x0+80, r["y"]+r["height"]/2, steps=6); await pg.mouse.up()
        await asyncio.sleep(0.3)
        e=await pg.evaluate("E[0]")
        print(ok(e["src"]=="tap" and abs(e["t"]-(3.0+80/pps))<0.05),
              f"拖竖线: t=3.00 -> {e['t']:.3f} (期望 {3.0+80/pps:.3f}), src={e['src']}")
        await pg.evaluate("undo()"); await asyncio.sleep(0.2)
        print(ok(abs(await pg.evaluate("E[0].t")-3.0)<1e-6), f"拖动可撤销: t={await pg.evaluate('E[0].t')}")

        # 点一下不动，不该留下垃圾快照
        h0=await pg.evaluate("hist.length")
        await pg.mouse.click(x0, r["y"]+r["height"]/2)
        h1=await pg.evaluate("hist.length")
        print(ok(h1==h0), f"点竖线不拖动不产生快照: hist {h0} -> {h1}")

        # 缩放
        await pg.select_option("#specZoom","420"); await asyncio.sleep(0.3)
        print(ok(await pg.evaluate("specPPS")==420), f"横向缩放 -> {await pg.evaluate('specPPS')} px/s")

        # 切到打时间模式自动展开
        await pg.click("#specClose"); await asyncio.sleep(0.2)
        print(ok(not await pg.is_visible("#specBox")), "收起")
        await pg.select_option("#mode","time"); await asyncio.sleep(0.3)
        print(ok(await pg.is_visible("#specBox")), "切到「打时间」自动展开")

        # 换音频要重新分析（必须用不同文件：同一路径浏览器不触发 change）
        # specSeq 是取消令牌，每次换音频会递增（可能不止 +1：先作废旧分析再开新分析），只断言递增
        await pg.evaluate("window.__old=SPEC")
        s0=await pg.evaluate("specSeq")
        await pg.set_input_files("#fAud","/tmp/other.mp3")
        await pg.wait_for_function("()=>SPEC!==null&&SPEC!==window.__old",timeout=60000)
        s1=await pg.evaluate("specSeq")
        print(ok(s1>s0), f"换音频后重新分析 specSeq={s0}->{s1}")
        # 清空 value 后，同一路径也能再次触发
        await pg.evaluate("window.__old=SPEC")
        s0=await pg.evaluate("specSeq")
        await pg.set_input_files("#fAud","/tmp/other.mp3")
        await pg.wait_for_function("()=>specSeq>"+str(s0),timeout=10000)
        print(ok(True), "重选同名文件也能重新分析（value 已清空）")
        await pg.wait_for_function("()=>SPEC!==null",timeout=60000)

        # 谱面仍然可用（布局没被挤坏）
        pages=await pg.evaluate("document.querySelectorAll('.page').length")
        wrapH=await pg.evaluate("wrap.clientHeight")
        print(ok(pages>0 and wrapH>200), f"谱面区仍在: {pages} 页, wrap 高 {wrapH}px")

        await pg.evaluate("aud.currentTime=8;specDirty=true"); await asyncio.sleep(0.5)
        await pg.screenshot(path="/tmp/spec.png")
        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
