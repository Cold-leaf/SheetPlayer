# ownCloud 面板的「最新更新时间」列（PROPFIND 的 getlastmodified）。
#
# 三节各自盯着一个会静默出错的地方：
#   1. 解析：字段没读 → 这一列永远空着，不报错、不崩，看着像"服务器没给"。
#      所以这节桩的是 fetch（喂一段真的 PROPFIND XML），**不是**桩 davList——
#      把 davList 换掉的话，被测的正好是被替换掉的那一层，怎么错都是绿的
#      （pw_davfilter 桩 davList 是对的：它测的是过滤，不是解析）
#   2. 分档：今天/昨天/同年/跨年，以及服务器不给这个字段时不能竖一排「Invalid Date」
#   3. 版式：多一列不能把曲名挤碎；窄屏两列放不下时留时间、藏大小
import asyncio, http.server, socketserver, threading, functools
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*a): pass
H=functools.partial(Quiet,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8847),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c): return "OK   " if c else "FAIL "
def this_year(): return __import__("datetime").date.today().year

# 造一段真实形态的 multistatus（ownCloud/sabre-dav 的 allprop 输出）。
# 时间由页面里的 JS 按本地时区生成再 toUTCString()——服务器给的就是 RFC1123 的 GMT，
# 这样期望值不依赖跑测试的机器在哪个时区。
BUILD_XML = """async()=>{
  const H='/owncloud/remote.php/webdav';
  const now=new Date();
  const at=(dy,h,mi)=>new Date(now.getFullYear(),now.getMonth(),now.getDate()+dy,h,mi,0);
  const times={
    today:at(0,8,12),                      // 今天
    yest :at(-1,21,5),                     // 昨天
    old  :new Date(now.getFullYear()-1,5,15,7,0,0),   // 去年（跨年档）
  };
  const resp=(name,extra)=>{
    const href=H+'/'+encodeURIComponent(name);
    return '<d:response><d:href>'+href+'</d:href><d:propstat><d:prop>'+extra+
      '</d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>';
  };
  const lm=t=>'<d:getlastmodified>'+t.toUTCString()+'</d:getlastmodified>';
  const sz=n=>'<d:getcontentlength>'+n+'</d:getcontentlength>';
  const coll='<d:resourcetype><d:collection/></d:resourcetype>';
  const xml='<?xml version="1.0"?><d:multistatus xmlns:d="DAV:" xmlns:s="http://sabredav.org/ns">'+
    resp('',coll)+                                                   // 目录自身，必须被跳过
    resp('乐谱',coll+lm(times.yest))+
    resp('ZG_战歌 线[TTBB].pdf',sz(123456)+lm(times.today))+
    resp('战歌_T1.mp3',sz(2345678)+lm(times.old))+
    resp('无时间戳.pdf',sz(999))                                     // 服务器没给这个字段
    +'</d:multistatus>';
  window.fetch=async()=>({ok:true,status:207,text:async()=>xml});
  const items=await davList('');
  return {items,want:{today:times.today.getTime(),yest:times.yest.getTime(),old:times.old.getTime()}};
}"""

async def main():
    errs=[]
    async with async_playwright() as p:
        b=await p.chromium.launch()
        pg=await b.new_page(viewport={"width":1280,"height":900})
        pg.on("pageerror",lambda e:errs.append(str(e)))
        await pg.goto("http://127.0.0.1:8847/player.html")
        await pg.wait_for_timeout(1200)

        # ================= 1. 从 PROPFIND 里解析出来 =================
        await pg.evaluate("()=>{DAV={base:'https://example.test/owncloud',kind:'webdav',user:'u',pass:'p'}}")
        r=await pg.evaluate(BUILD_XML)
        it={x["name"]:x for x in r["items"]}
        want=r["want"]
        print(ok(len(r["items"])==4),"目录自身被跳过，只剩 4 条: "+str(list(it)))
        print(ok(it.get("ZG_战歌 线[TTBB].pdf",{}).get("mtime")==want["today"]),
              "getlastmodified 解成了毫秒时间戳（今天那条）: "+repr(it.get("ZG_战歌 线[TTBB].pdf")))
        print(ok(it.get("战歌_T1.mp3",{}).get("mtime")==want["old"]), "跨年那条也解对了")
        print(ok(it.get("乐谱",{}).get("mtime")==want["yest"] and it["乐谱"]["dir"]),
              "目录也带时间（渲染时再决定不显示）")
        print(ok(it.get("无时间戳.pdf",{}).get("mtime")==0),
              "服务器没给该字段 → mtime 落成 0（不是 NaN）: "+repr(it.get("无时间戳.pdf")))
        print(ok(it.get("ZG_战歌 线[TTBB].pdf",{}).get("size")==123456),
              "顺带确认 getcontentlength 没被这次改动带坏: "+str(it.get("ZG_战歌 线[TTBB].pdf",{}).get("size")))

        # ================= 2. davWhen 分档 =================
        w=await pg.evaluate("""()=>{
          const now=new Date();
          const T=(dy,h,mi)=>new Date(now.getFullYear(),now.getMonth(),now.getDate()+dy,h,mi,0).getTime();
          // 6/15 那条的期望值写死成「06-15 08:12」；今天真要是 6/15 或 6/16 就成了今天/昨天，
          // 那两天跳过这一条，而不是把断言写成跟着实现走（那样等于没测）
          const sy=new Date(now.getFullYear(),5,15,8,12,0).getTime();
          const t0=new Date(now.getFullYear(),now.getMonth(),now.getDate(),0,0,0).getTime();
          return {
            today:davWhen(T(0,9,7)),
            yest :davWhen(T(-1,21,5)),
            sy   :davWhen(sy),
            syEdge:(sy>=t0-86400000&&sy<t0+86400000),
            ly   :davWhen(new Date(now.getFullYear()-1,5,15,7,0,0).getTime()),
            zero :davWhen(0),
            nan  :davWhen(NaN),
            full :davWhen(T(-1,21,5)).full,
          };
        }""")
        print(ok(w["today"]["short"]=="今天 09:07"),"当天 → 「今天 09:07」: "+repr(w["today"]["short"]))
        print(ok(w["yest"]["short"]=="昨天 21:05"),"前一天 → 「昨天 21:05」: "+repr(w["yest"]["short"]))
        print(ok(w["full"]),                     "title 里有完整时间: "+repr(w["full"]))
        if w["syEdge"]: print("SKIP 同年档（今天正好是 6/15 或 6/16）")
        else: print(ok(w["sy"]["short"]=="06-15 08:12"),
                    "同年 → 「06-15 08:12」不带年份: "+repr(w["sy"]["short"]))
        print(ok(w["ly"]["short"]==str(this_year()-1)+"-06-15"),
              "跨年 → 带年份、不带时分: "+repr(w["ly"]["short"]))
        print(ok(w["zero"]=={"short":"","full":""} and w["nan"]=={"short":"","full":""}),
              "缺失/非法时间 → 空串，不是 Invalid Date: "+repr(w["zero"])+repr(w["nan"]))

        # ================= 3. 渲染成行 =================
        await pg.evaluate("""()=>{
          const now=new Date();
          const at=(dy,h,mi)=>new Date(now.getFullYear(),now.getMonth(),now.getDate()+dy,h,mi,0).getTime();
          window.__mt={today:at(0,9,7),yest:at(-1,21,5)};
          // 面板得真的打开：display:none 时所有行的 getBoundingClientRect 都是 0，
          // 下面那几条量宽度的断言会「全部通过」而什么都没量到
          $('davPop').style.display='flex';
          window.davList=async()=>[
            {name:'乐谱',path:'乐谱',dir:true,size:0,mtime:window.__mt.yest},
            {name:'ZG_中美建交三十年纪念音乐会[线][TTBB+NA+Pn].pdf',path:'a.pdf',dir:false,size:123456,mtime:window.__mt.today},
            {name:'战歌_T1.mp3',path:'b.mp3',dir:false,size:2345678,mtime:0},
          ];
          return davRender();
        }""")
        await pg.wait_for_timeout(300)
        rows=await pg.evaluate("""()=>[...document.querySelectorAll('#davList .dRow')].map(e=>({
          name:e.querySelector('.nm').textContent,
          dt:(e.querySelector('.dt')||{textContent:null}).textContent,
          dtTitle:(e.querySelector('.dt')||{title:''}).title,
          sz:e.querySelector('.sz').textContent,
          nmW:Math.round(e.querySelector('.nm').getBoundingClientRect().width),
          rowW:Math.round(e.getBoundingClientRect().width)}))""")
        print(ok(rows[1]["dt"]=="今天 09:07"),"行上显示的当天时间: "+repr(rows[1]["dt"]))
        print(ok(bool(rows[1]["dtTitle"]) and str(this_year()) in rows[1]["dtTitle"]),
              "悬停 title 是完整时间（带年份）: "+repr(rows[1]["dtTitle"]))
        print(ok(rows[2]["dt"]=="" ),"没有时间戳的文件：这列留空: "+repr(rows[2]["dt"]))
        print(ok(rows[0]["dt"]=="" ),"目录：不显示时间（父目录 mtime 随子文件变，是噪音）: "+repr(rows[0]["dt"]))
        print(ok("Invalid" not in "".join(r["dt"] or "" for r in rows) and "NaN" not in "".join(r["dt"] or "" for r in rows)),
              "整列没有 Invalid Date / NaN")
        print(ok(rows[2]["sz"]=="2.2 MB"),"大小列照旧: "+repr(rows[2]["sz"]))

        # ================= 4. 版式：宽屏两列都在、窄屏留时间藏大小 =================
        wide=await pg.evaluate("""()=>{
          const r=document.querySelectorAll('#davList .dRow')[1],box=$('davList');
          return {sz:getComputedStyle(r.querySelector('.sz')).display,
                  dt:getComputedStyle(r.querySelector('.dt')).display,
                  over:box.scrollWidth-box.clientWidth,
                  nmW:Math.round(r.querySelector('.nm').getBoundingClientRect().width)}}""")
        print(ok(wide["sz"]!="none" and wide["dt"]!="none"),
              "宽屏（1280）：时间和大小都在: "+str(wide))
        print(ok(wide["over"]<=1 and wide["nmW"]>=300),
              "宽屏下没被多出来的一列挤出横向滚动，曲名仍有位置: "+str(wide))

        await pg.set_viewport_size({"width":390,"height":844})
        await pg.wait_for_timeout(200)
        nar=await pg.evaluate("""()=>{
          const r=document.querySelectorAll('#davList .dRow')[1],box=$('davList');
          return {sz:getComputedStyle(r.querySelector('.sz')).display,
                  dt:getComputedStyle(r.querySelector('.dt')).display,
                  over:box.scrollWidth-box.clientWidth,
                  nmW:Math.round(r.querySelector('.nm').getBoundingClientRect().width),
                  dtTxt:r.querySelector('.dt').textContent,
                  rowH:Math.round(r.querySelector('.nm').getBoundingClientRect().height)}}""")
        print(ok(nar["sz"]=="none" and nar["dt"]!="none"),
              "窄屏（390）：藏大小、留时间: "+str(nar))
        print(ok(nar["over"]<=1),"窄屏下这一行不产生横向滚动: scrollWidth-clientWidth="+str(nar["over"]))
        print(ok(nar["nmW"]>=100),"窄屏下单行曲名仍有 ≥100px（三列都留会碎成每行两三个字）: "+str(nar["nmW"]))
        print(ok(nar["dtTxt"]=="今天 09:07"),"窄屏下时间照常显示: "+repr(nar["dtTxt"]))

        print("\npage errors:",errs or "(none)")
        await b.close()

asyncio.run(main())
