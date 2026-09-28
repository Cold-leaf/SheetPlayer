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

        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
