# 换谱要把音频一起接回来。
# 换谱只换 PDF 这个附件，而 resetPdfDerived 会把播放器整个清空（audUrl 撤销、aud.src=''）。
# 原来的 replacePdf 漏了「打开曲目」里那段「把上次在听的音频变体接回来」，于是换完谱：
# audUrl 是空的，但 aud.src 读回来是**文档 URL**（空 src 按 base 解析，非空为真），
# 所有 if(aud.src) 的播放键守卫照常放行 → aud.play() 抛 NotSupportedError，
# 界面上还列着那个音频、没有任何 ⚠ —— 表现就是「按播放没反应」。
# 断言里因此**绝不能用 if(aud.src)** 判有没有音频，只有 audUrl / blob: 前缀能信。
import asyncio, http.server, socketserver, threading, functools, wave, struct, math
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
A=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
B=ROOT+"/线谱合集/BW_不忘初心[线][SATB+NA+Pn].pdf"       # 第二个项目（乙）用
C=ROOT+"/线谱合集/CQ_传奇[线][SATB+NA+Pn][任知超][处理后].pdf"
WAV="/tmp/tone_repl.wav"                                 # 短的生成 WAV：省掉长音频的分析时间
with wave.open(WAV,'w') as w:
    w.setnchannels(1);w.setsampwidth(2);w.setframerate(22050)
    w.writeframes(b''.join(struct.pack('<h',int(12000*math.sin(2*math.pi*440*i/22050))) for i in range(22050*3)))
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8776),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c): return "OK   " if c else "FAIL "

async def attach_wav(pg):
    await pg.set_input_files("#fAud",WAV)
    await pg.wait_for_function("()=>$('dlgMode').style.display==='flex'",timeout=8000)
    await pg.click("#dlgModeOk")
    await pg.wait_for_function("()=>audUrl!==null&&track&&track.lastAudio",timeout=30000)

# 「这一份谱子已经打开完了」：pdfHash/track 都在 pdf 之前赋值，只看它们会在
# openPdf 还没回来时就算通过——然后下一条命令又去开另一份，两个 loadPdfBlob 交错，
# 页数和名字会串成谁也不认识的组合（实测踩过：7 页的乙配着 11 页的哈希）。
# 页面盒子建完（buildPages 的产物）才是真正的完成点
# extra 是"这次操作"的判据，必须挑一个**开跑之前不成立**的：pid===x 在"点开另一个项目"时
# 不成立、pdfHash===x 在"换成另一份谱子"时不成立。光看页面盒子的话，上一份谱子已经建好盒子，
# 条件一开始就是真的，等于没等
async def loaded(pg,extra,arg,t=60000):
    await pg.wait_for_function("(a)=>pdf!==null&&document.querySelectorAll('.page').length===pdf.numPages&&"+extra,
                               arg=arg,timeout=t)

async def swap_via_lib(pg,path,h_old):
    await pg.evaluate("$('bLib').onclick()")
    await pg.wait_for_function("()=>$('lib').style.display==='flex'",timeout=8000)
    # 上一次换谱的「已换谱…」还会在 #msg 上停留几秒，不清掉就会把上一条当成这次的结果
    # （实测踩过：第三条拿到的是一条**上一次**的消息，哈希没变却"通过"了等待）
    await pg.evaluate("$('msg').textContent=''")
    pg.once("dialog",lambda dlg:asyncio.create_task(dlg.accept()))   # 「换谱：… 个小节标记原样保留」
    async with pg.expect_file_chooser() as fc:
        await pg.click(".libCard button.repl")
    await (await fc.value).set_files(path)
    await pg.wait_for_function("(h)=>pdfHash!==h&&$('msg').textContent.includes('已换谱')",
                               arg=h_old,timeout=60000)

# 换谱后的播放器状态。src 单独取出来看：只看 audUrl 不够，要亲眼确认它不再是文档 URL
AUDST="()=>({u:audUrl,s:aud.src,rs:aud.readyState,dur:aud.duration,paused:aud.paused,t:aud.currentTime,"
AUDST+="sel:$('audSel').value,opt:($('audSel').selectedOptions[0]||{}).textContent||''})"

# 换完 blob 是刚挂上去的，元数据要等一拍才到（大文件更明显：真机走查时 3.7MB 的 mp3
# 在那一刻 duration 还是 NaN）。等它自己就绪，别拿"立刻读到的值"当断言——
# 那是竞态，不是这次要测的行为。旧代码上它永远等不到，照样红。
async def wait_meta(pg,t=15000):
    try:
        await pg.wait_for_function("()=>audUrl!==null&&aud.readyState>=1&&aud.duration>0",timeout=t)
        return True
    except Exception: return False

async def main():
    errs=[]
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={"width":1500,"height":1000})
        pg.on("pageerror",lambda e:errs.append(str(e)))
        await pg.goto("http://127.0.0.1:8776/player.html")
        await pg.wait_for_function("()=>idb!==null&&$('lib').style.display==='flex'",timeout=15000)

        # --- 铺场景：项目挂谱子 A、标 3 个小节、加一个音频变体、再放一个时间点 ---
        await pg.set_input_files("#fPdf",A)
        await pg.wait_for_function("()=>document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=60000)
        pid0=await pg.evaluate("pid"); hA=await pg.evaluate("pdfHash")
        jiaName=await pg.evaluate("track.name")          # 甲的项目名，第 ④ 条要用
        await pg.select_option("#mode","mark")
        bb=await (await pg.query_selector('.page[data-page="1"]')).bounding_box()
        for fx in (0.3,0.45,0.6):
            await pg.mouse.click(bb["x"]+bb["width"]*fx,bb["y"]+bb["height"]*0.4)
        await asyncio.sleep(0.9)
        print(ok(await pg.evaluate("M.length")==3), "项目里标好 3 个小节")
        await attach_wav(pg)
        audH=await pg.evaluate("track.lastAudio")
        await pg.evaluate("E=[{m:1,t:12.5}];save()")
        await asyncio.sleep(0.6)
        st=await pg.evaluate(AUDST)
        print(ok(bool(st["u"]) and st["s"].startswith("blob:") and st["dur"]>0),
              f"换谱前：音频已就位（时长 {st['dur']:.2f}s）")

        # --- ① 换谱：音频必须跟着回来，播放键要真的能出声（用户报的那一条）---
        await swap_via_lib(pg,C,hA)
        hC=await pg.evaluate("pdfHash")
        print(ok(hC not in (hA,"")), "确实换了谱子")
        print(ok(await pg.evaluate("M.length")==3), "换谱后 3 个小节还在")
        meta=await wait_meta(pg)
        st=await pg.evaluate(AUDST)
        print(ok(bool(st["u"]) and st["s"].startswith("blob:")),
              "换谱后音频接回来了（audUrl 非空、src 是 blob）: "+str(st["s"])[:32])
        print(ok(meta), f"音频元数据就绪：readyState={st['rs']} duration={st['dur']:.2f}s")
        print(ok(st["sel"]==audH and "不在本机" not in st["opt"]),
              "下拉里选中的还是那个音频、且没标「不在本机」: "+st["opt"])
        m=await pg.inner_text("#msg")
        print(ok("已换谱" in m and "不在这台设备上" not in m), "提示只有换谱结果，没有音频缺失: "+m)
        await pg.click("#bPlay")                                  # 可信手势，不触发自动播放拦截
        try:
            await pg.wait_for_function("()=>!aud.paused&&aud.currentTime>0",timeout=8000)
            playing=True
        except Exception: playing=False
        st=await pg.evaluate(AUDST)
        print(ok(playing and st["t"]>0), f"点一下播放键，真的开始放了：paused={st['paused']} t={st['t']:.3f}s")
        await pg.evaluate("aud.pause()")

        # --- ② 按历史谱子换回去，音频同样要接回来 ---
        await pg.evaluate("$('bLib').onclick()")
        await pg.wait_for_function("()=>$('lib').style.display==='flex'",timeout=8000)
        pg.once("dialog",lambda dlg:asyncio.create_task(dlg.accept()))   # 「用它换回《…》现在的谱子？」
        await pg.set_input_files("#fPdf",A)
        await loaded(pg,"pdfHash===a",hA)
        await pg.wait_for_function("()=>M.length===3",timeout=60000)
        print(ok(await pg.evaluate("pid")==pid0), "换回历史谱子：还是同一个项目")
        print(ok(await pg.evaluate("M.length")==3), "换回历史谱子：标注照旧")
        meta=await wait_meta(pg)
        st=await pg.evaluate(AUDST)
        print(ok(meta and st["s"].startswith("blob:")),
              f"换回历史谱子：音频也接回来了（时长 {st['dur']:.2f}s）")
        print(ok(await pg.evaluate("track.pdfHistory.length")==2),
              "pdfHistory 2 条（换走的那份也在）: "+str(await pg.evaluate("track.pdfHistory.length")))

        # --- ③ 音频文件不在本机：换谱照常完成，提示把两件事拼在一起 ---
        await pg.evaluate("(h)=>idbDel(idb,'files',h)",audH)
        await swap_via_lib(pg,C,hA)
        m=await pg.inner_text("#msg")
        print(ok("已换谱" in m and "不在这台设备上" in m and m.index("已换谱")<m.index("不在这台设备上")),
              "提示先讲换谱结果、再追加音频缺失: "+m)
        st=await pg.evaluate(AUDST)
        print(ok(not st["u"]), "文件确实不在本机：播放器没有源（audUrl 为空）")
        print(ok(st["s"].startswith("http")), "（aud.src 这时候是文档 URL，不能拿它当'有音频'的判据）")
        print(ok(await pg.evaluate("M.length")==3), "音频缺失不影响标注：3 个小节还在")

        # --- ④ 换别人的谱子、在确认框上点「取消」：一个字节的状态都不许动 ---
        # 看着甲、去点乙那行的「换谱」再取消。旧代码在 confirm **之前**就把 pid/track/标注
        # 换成乙的了，取消只是 return —— 屏幕上是甲、内存里是乙：之后在甲上添的一笔，
        # save() 的 key 已经是乙，会写进乙的标注里
        await pg.set_input_files("#fPdf",B)              # 另起一个项目「乙」
        await loaded(pg,"pid!==a",pid0)
        yiPid=await pg.evaluate("pid")
        print(ok(yiPid!=pid0), "第二份谱子另起了一个项目（乙）")
        await pg.evaluate("$('bLib').onclick()")
        await pg.wait_for_function("()=>$('lib').style.display==='flex'",timeout=8000)
        await pg.click('.libCard button.open[data-h="'+pid0+'"]')      # 回到甲
        await loaded(pg,"pid===a",pid0)
        await pg.wait_for_function("()=>document.querySelectorAll('.mk').length===3",timeout=60000)
        nPage=await pg.evaluate("pdf.numPages")
        await pg.evaluate("$('bLib').onclick()")
        await pg.wait_for_function("()=>$('lib').style.display==='flex'",timeout=8000)
        seen={}
        def on_dlg(d):
            seen["m"]=d.message
            asyncio.create_task(d.dismiss())             # 取消
        pg.once("dialog",on_dlg)
        async with pg.expect_file_chooser() as fc:
            await pg.click('.libCard button.repl[data-h="'+yiPid+'"]')
        await (await fc.value).set_files(A)              # 跟乙现在的谱子不同 → 会弹确认框
        for _ in range(60):
            if seen.get("m"): break
            await asyncio.sleep(0.1)
        print(ok("换谱" in (seen.get("m") or "")), "确认框确实弹出来了: "+str(seen.get("m")))
        await asyncio.sleep(0.5)
        st=await pg.evaluate("()=>({pid,track:track&&track.name,m:M.length,"
                             "mk:document.querySelectorAll('.mk').length,pages:pdf.numPages})")
        print(ok(st["pid"]==pid0 and st["track"]==jiaName), "取消后 pid/曲目还是甲的: "+str(st["track"]))
        print(ok(st["m"]==3 and st["mk"]==3 and st["pages"]==nPage),
              f"取消后内存和屏幕都还是甲的：M={st['m']} .mk={st['mk']} {st['pages']} 页")
        # 真的危害在这儿：取消之后添的一笔必须落进甲。旧代码里它会写进乙的标注
        # （取消 = 没换，所以还停在曲目库里；先回到谱面再添这一笔）
        await pg.evaluate("showLib(false)")
        await pg.evaluate("()=>{const s=$('mode');if(s.value!=='mark'){s.value='mark';s.onchange()}}")
        bb=await (await pg.query_selector('.page[data-page="1"]')).bounding_box()
        await pg.mouse.click(bb["x"]+bb["width"]*0.8,bb["y"]+bb["height"]*0.4)
        await asyncio.sleep(1.2)
        got=await pg.evaluate("""async(ids)=>{const o={};
            for(const[k,id]of Object.entries(ids)){const r=await idbGet(idb,'marks',id);o[k]=r?r.data.M.length:0}
            return o}""",{"jia":pid0,"yi":yiPid})
        print(ok(got["jia"]==4 and got["yi"]==0),
              "取消之后添的一笔落进甲（4 个），乙一个都没多: "+str(got))

        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
