# ownCloud 面板只列 PDF 和音频：共享盘上堆着 .sib / .mscz / .mp4 / .pptx 这些用不上的东西，
# 全铺出来会把真正要找的谱子淹掉。这里用桩替换 davList()，不联网、不碰真服务器。
#
# 四条断言各自盯着一个易错点：
#   1. 该显示的显示、该隐藏的隐藏（目录必须留着，不然没法往下走）
#   2. 「隐藏了几个」要说出来——不说用户会以为文件没了，而不是被过滤了
#   3. 点某一行的 onclick 绑的是【过滤后】的那一项。下标错位是这类过滤最经典的 bug：
#      列表看着对，点下去下错文件
#   4. 全是杂文件 / 空目录，两种空态得分开说
import asyncio, http.server, socketserver, threading, functools
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*a): pass
H=functools.partial(Quiet,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8801),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c): return "OK   " if c else "FAIL "

def f(name,size=1000): return {"name":name,"path":name,"dir":False,"size":size}
# 真实形态：一首曲子的目录里混着乐谱(.pdf/.sib)、midi 音频(.mp3)、视频和文档
MIXED=[
  {"name":"乐谱","path":"乐谱","dir":True,"size":0},
  f("ZG_战歌[线][TTBB].pdf",123456),
  f("战歌_T1.mp3",2345678),
  f("战歌.wma",3456789),
  f("战歌.mscz",999), f("战歌.sib",888),
  f("曲目介绍.pptx",777), f("排练.mp4",666), f("曲目介绍.txt",55),
]
JUNK=[f("战歌.mscz",999),f("排练.mp4",666)]

async def render(pg,files):
    await pg.evaluate("""(files)=>{
      DAV={base:'https://example.test/owncloud',kind:'webdav',user:'u',pass:'p'};
      window.davList=async()=>files;            // 覆盖全局函数声明，请求不出网
      return davRender();
    }""",files)
    await pg.wait_for_timeout(300)
    names=await pg.evaluate("[...document.querySelectorAll('#davList .dRow .nm')].map(e=>e.textContent)")
    note =await pg.evaluate("(document.querySelector('#davList .dEmpty')||{}).textContent||''")
    return names,note

async def main():
    errs=[]
    async with async_playwright() as p:
        b=await p.chromium.launch()
        pg=await b.new_page()
        pg.on("pageerror",lambda e:errs.append(str(e)))
        await pg.goto("http://127.0.0.1:8801/player.html")
        await pg.wait_for_timeout(1200)

        names,note=await render(pg,MIXED)
        print(ok(names==["乐谱","ZG_战歌[线][TTBB].pdf","战歌_T1.mp3","战歌.wma"]),
              "只列目录 + PDF + 音频，其余不出现: "+str(names))
        print(ok("已隐藏 5 个" in note),"末尾说明隐藏了几个: "+repr(note))

        # 下标错位最容易出在这：onclick 绑的必须是过滤后那一项
        got=await pg.evaluate("""()=>{
          const seen=[];
          window.__realDL=davDownload;                 // 留着，下面「下载之后弹窗」那节要用真的
          window.davDownload=(it)=>seen.push(it.name);
          document.querySelectorAll('#davList .dRow')[1].onclick();
          document.querySelectorAll('#davList .dRow')[3].onclick();
          return seen;
        }""")
        print(ok(got==["ZG_战歌[线][TTBB].pdf","战歌.wma"]),
              "点第 2/4 行下的是过滤后的第 2/4 项: "+str(got))

        names,note=await render(pg,JUNK)
        print(ok(names==[] and "没有 PDF 或音频" in note),
              "整目录都是杂文件时给明确说法: "+repr(note))

        names,note=await render(pg,[])
        print(ok(names==[] and "是空的" in note),"空目录仍旧说空: "+repr(note))

        # ================= 下载之后弹窗选项目 =================
        # 以前点一下文件名就直接落库、挂到哪儿全凭自动认领；一首歌有几个版本
        #（[线][TTBB+NA+Pn] / [简][TB+NA+WO]）时名字整串对不上，每导一份就新建一个项目。
        # 这一节只验「问对了没有、挂对没有」：下载和两个导入函数都换成桩，不联网、不解析 PDF。
        await pg.evaluate("""async()=>{
          // 内容由路径决定 → 同一个路径的哈希可预期，能精确造出「① 哈希命中」那一档
          const body=p=>new TextEncoder().encode('body:'+p);
          window.davGet=p=>Promise.resolve(new File([body(p)],p.split('/').pop()));
          const hashOf=p=>sha256Hex(new File([body(p)],'x'));
          const now=Date.now();
          const mk=(id,name,pdfHash,pdfName)=>idbPut(idb,'projects',{id,name,aka:[],
            pdf:pdfHash?{hash:pdfHash,name:pdfName}:null,pdfHistory:[],audios:[],lastAudio:null,
            createdAt:now,updatedAt:now});
          // 库里只有「[线]」这一版（用户的真实形态）；「天路」还没谱子；「老版」正用着 /dl/equal.pdf
          await mk('pLine','ZG_中国人民志愿军战歌[线][TTBB+NA+Pn]','a'.repeat(64),'a.pdf');
          await mk('pSong','十送红军','b'.repeat(64),'b.pdf');
          await mk('pWait','ZT_天路[线]',null,null);
          await mk('pEqual','ZG_中国人民志愿军战歌（老版）',await hashOf('/dl/equal.pdf'),'equal.pdf');
          window.__calls=[];
          window.attachPdf=(f,pid,forceNew)=>{window.__calls.push(['pdf',pid,forceNew])};
          window.importAudioFile=(f,pid)=>{window.__calls.push(['aud',pid])};
        }""")

        async def dl(name,path=None):
            await pg.evaluate("""a=>{window.__calls=[];window.__realDL({name:a.n,path:a.p,dir:false,size:10})}""",
                              {"n":name,"p":path or ('/dl/'+name)})
            await pg.wait_for_selector("#dlgProj",state="visible",timeout=5000)

        async def dlg():
            return await pg.evaluate("""()=>({
              msg:$('dlgProjMsg').textContent,
              rows:[...document.querySelectorAll('#dlgProj .pjRow')].map(e=>({
                name:e.querySelector('.pjName').textContent,
                sub:(e.querySelector('.pjSub')||{textContent:''}).textContent,
                on:e.classList.contains('on')})),
              newShown:$('dlgProjNew').style.display!=='none',
              davShown:getComputedStyle($('davPop')).display})""")

        async def calls():
            await pg.wait_for_timeout(200)
            return await pg.evaluate("window.__calls")

        # --- 1. 名字整串对不上（用户的核心场景）：按相似度把同曲的另一版排最前并预选 ---
        await dl("ZG_中国人民志愿军战歌[简][TB+NA+WO].pdf")
        d=await dlg()
        print(ok(d["msg"].startswith("这份谱子要挂到哪个项目")),"弹窗问的是「挂到哪个项目」: "+repr(d["msg"]))
        print(ok(d["rows"][0]["name"]=="ZG_中国人民志愿军战歌[线][TTBB+NA+Pn]" and d["rows"][0]["on"]),
              "同曲的另一版排最前且已预选: "+str(d["rows"][:2]))
        print(ok(d["rows"][0]["sub"]==""),"没命中三步时不乱标命中理由: "+repr(d["rows"][0]["sub"]))
        await pg.click("#dlgProjOk")
        print(ok(await calls()==[["pdf","pLine",None]]),
              "默认一路「确定」就挂到最像的那个项目: "+str(await calls()))

        # --- 2. ① 内容哈希命中 → 那个项目置顶并写明理由（这时名字可能毫无关系）---
        await dl("equal.pdf")
        d=await dlg()
        print(ok(d["rows"][0]["name"]=="ZG_中国人民志愿军战歌（老版）" and d["rows"][0]["on"]
                 and "就是这份谱子在用的" in d["rows"][0]["sub"]),
              "哈希命中排在第一位并写明「就是这份谱子在用的」: "+str(d["rows"][0]))
        await pg.click("#dlgProjOk")
        print(ok(await calls()==[["pdf","pEqual",None]]),"选中的项目 id 原样传给 attachPdf: "+str(await calls()))

        # --- 3.「＋ 新建项目」要带 forceNew：不然用户说要新建、却可能被自动认领挂回已有项目 ---
        await dl("ZG_中国人民志愿军战歌[简][TB+NA+WO].pdf")
        await pg.click("#dlgProjNew")
        print(ok(await calls()==[["pdf",None,True]]),
              "「＋ 新建项目」→ attachPdf(f,null,true)，跳过自动认领: "+str(await calls()))

        # --- 4. 取消：不落库、不导入，而且人还留在 ownCloud 面板里接着挑文件 ---
        await pg.evaluate("$('davPop').style.display='flex'")
        await dl("ZG_中国人民志愿军战歌[简][TB+NA+WO].pdf")
        await pg.click("#dlgProjCancel")
        print(ok(await calls()==[]),"取消就一个字节都不导入: "+str(await calls()))
        print(ok((await dlg())["davShown"]=="flex"),"取消后 ownCloud 面板还开着（能接着挑下一个）")

        # --- 5. 返回键关弹窗必须走取消路径：直接 display:none 会把 await 它的那半边挂死，
        #        表现就是 davBusy 永远停在 true、面板再也点不动 ---
        await dl("ZG_中国人民志愿军战歌[简][TB+NA+WO].pdf")
        await pg.evaluate("closeTopLayer()")
        await pg.wait_for_timeout(250)
        st=await pg.evaluate("()=>({open:getComputedStyle($('dlgProj')).display,busy:davBusy})")
        print(ok(st["open"]=="none" and st["busy"]==False and await calls()==[]),
              "返回键关闭 = 取消（弹窗收掉、davBusy 放掉、不导入）: "+str(st))
        await dl("ZG_中国人民志愿军战歌[简][TB+NA+WO].pdf")   # 还下得动 → 上一轮没挂死
        await pg.click("#dlgProjCancel")

        # --- 6. 音频：不提供「＋ 新建项目」，但**不藏**没谱子的项目——
        #        藏掉用户自己建的东西，他会以为项目没了，而不是"这个暂时用不了" ---
        await dl("战歌_T1.mp3")
        d=await dlg()
        print(ok(not d["newShown"]),"音频不给「＋ 新建项目」（没有谱子的项目打不开，建了也没法用）")
        print(ok("战歌_T1" in d["msg"]),"音频弹窗写明是哪个文件: "+repr(d["msg"]))
        names=[r["name"] for r in d["rows"]]
        print(ok(sorted(names)==sorted(["ZG_中国人民志愿军战歌[线][TTBB+NA+Pn]",
                                        "ZG_中国人民志愿军战歌（老版）","十送红军","ZT_天路[线]"])),
              "项目一个不少（含还没谱子的）: "+str(names))
        sub={r["name"]:r["sub"] for r in d["rows"]}
        print(ok(sub.get("ZT_天路[线]")=="等待导入谱子"),
              "没谱子的那行写明「等待导入谱子」: "+repr(sub.get("ZT_天路[线]")))
        await pg.click("#dlgProjCancel")

        # --- 7. 搜索框：过滤 + 空结果时「确定」点不了，且提交的一定是看得见的那个 ---
        await dl("战歌_T1.mp3")
        d=await dlg()
        print(ok(d["rows"][0]["on"]),"没有预选时高亮第一行，列表不会「谁都没选」")
        await pg.fill("#dlgProjQ","完全无关的曲子")
        await pg.wait_for_timeout(150)
        d=await dlg()
        print(ok([r["name"] for r in d["rows"]]==[]),"搜索过滤掉不匹配的项目: "+str(d["rows"]))
        print(ok(await pg.evaluate("$('dlgProjOk').disabled")),"空结果时「确定」是禁用的")
        # 刚才高亮的是「[线]」那一项，搜「老版」把它滤掉了 → 高亮必须跟着挪到唯一剩下那行。
        # 不挪的话「确定」就会提交一个列表里根本没显示的项目
        await pg.fill("#dlgProjQ","老版")
        await pg.wait_for_timeout(150)
        d=await dlg()
        print(ok([r["name"] for r in d["rows"]]==["ZG_中国人民志愿军战歌（老版）"] and d["rows"][0]["on"]),
              "原来的选中项被滤掉后，高亮改到看得见的第一行: "+str(d["rows"]))
        await pg.click("#dlgProjOk")
        print(ok(await calls()==[["aud","pEqual"]]),
              "音频挂到选中的项目上（不是当前打开的曲目——这里根本没打开曲目）: "+str(await calls()))

        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
