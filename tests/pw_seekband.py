# 暂停时点某小节 → 进度带应立刻框住【那一小节】，不该先框上一小节、播放后才跳。
# 根因：浏览器把 aud.currentTime 量化到微秒，跳到 3.9166666666666665 读回 3.916666，
# 严格 <= 判断会认成"还没进这一小节"。occIndex 加 1ms 容差解决。
import asyncio, glob, http.server, socketserver, threading, functools
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
PDF=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
AUD=glob.glob(ROOT+"/ICT_working/08-Assets/*.mp3")[0]
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8799),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c): return "OK   " if c else "FAIL "

async def main():
    errs=[]
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={"width":1400,"height":900})
        pg.on("pageerror",lambda e:errs.append(str(e)))
        await pg.goto("http://127.0.0.1:8799/player.html?direct=1")
        await pg.set_input_files("#fPdf",PDF)
        await pg.wait_for_function("()=>document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=30000)
        await pg.set_input_files("#fAud",AUD)
        await pg.wait_for_function("()=>aud.readyState>=2",timeout=60000)

        # 用「自动生成」那种不规则时间（除不尽的小数），这是量化误差真正会出现的场景
        await pg.evaluate("""()=>{M=[{page:1,nx:.2,ny:.3,m:1,h:.08},{page:1,nx:.5,ny:.3,m:2,h:.08},
            {page:1,nx:.8,ny:.3,m:3,h:.08}];
          E=[{m:1,t:0.4166666666666667,src:'gen'},{m:2,t:3.9166666666666665,src:'gen'},
             {m:3,t:7.416666666666667,src:'gen'}];
          syncNext();layout();aud.pause()}""")

        async def click_bar(m):
            await pg.evaluate("""async(m)=>{
              aud.pause();aud.currentTime=0;lastSeek=null;
              await new Promise(r=>setTimeout(r,200));
              const d=(byM.get(m)||[])[0],rect=d.getBoundingClientRect();
              d.dispatchEvent(new MouseEvent('click',{bubbles:true,
                clientX:rect.left+rect.width/2,clientY:rect.top+rect.height/2}));
            }""",m)
            await pg.wait_for_timeout(350)
            return await pg.evaluate("""()=>{const b=document.getElementById('band'),W=b.parentElement.clientWidth;
              const i=occIndex(aud.currentTime);
              return {t:aud.currentTime,occM:i<0?null:OCC[i].m,
                      L:+(b.offsetLeft/W).toFixed(3),R:+((b.offsetLeft+b.offsetWidth)/W).toFixed(3)}}""")

        r=await click_bar(2)
        print(ok(r["occM"]==2), f"暂停点小节2 → 当前小节={r['occM']}（期望 2，不是 1）")
        print(ok(abs(r["L"]-.5)<.01 and abs(r["R"]-.8)<.01),
              f"  进度带直接框 2–3: {r['L']}→{r['R']}（期望 .5→.8，不是 .2→.5）")

        r=await click_bar(3)
        print(ok(r["occM"]==3), f"暂停点小节3 → 当前小节={r['occM']}（期望 3）")
        print(ok(abs(r["L"]-.8)<.01), f"  进度带从小节3 起: {r['L']}→{r['R']}")

        # 播放后不应再"跳一下"：小节号保持 2
        await click_bar(2)
        await pg.evaluate("aud.play()")
        await pg.wait_for_timeout(250)
        m2=await pg.evaluate("()=>{const i=occIndex(aud.currentTime);return i<0?null:OCC[i].m}")
        await pg.evaluate("aud.pause()")
        print(ok(m2==2), f"开始播放后仍是小节 {m2}（不再跳到 3）")

        # 容差只有 1ms：明显早于小节起点时仍算上一小节
        early=await pg.evaluate("""async()=>{aud.pause();
          aud.currentTime=E.find(e=>e.m===2).t-0.05;
          await new Promise(r=>setTimeout(r,250));
          const i=occIndex(aud.currentTime);return i<0?null:OCC[i].m}""")
        print(ok(early==1), f"早 50ms 仍算小节 {early}（容差没有过头）")

        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
