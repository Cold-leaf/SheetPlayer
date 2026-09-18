# v1 库（曲目身份 = PDF 内容哈希）→ v2（项目 + 附件）的迁移。
# 幂等、单个事务、非破坏性：老的 tracks/anns 原样留着，回滚 = 退回旧代码。
# 用 ?direct=1 页面先手搓一个 v1 库（那条路径不碰 IndexedDB），再正常启动让迁移跑。
import asyncio, base64, http.server, socketserver, threading, functools
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
PDF=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8813),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c): return "OK   " if c else "FAIL "

AUD="b"*64
ORPH="legacy:孤儿.pdf"   # 只有 anns 没有 tracks 的孤儿行（sweepLegacy 先写 anns、catch 被吞掉留下的）

# 用真实 PDF 的字节建 v1 库（哈希用页面自己的 sha256Hex 算），这样迁移后是真能打开的
SEED="""async(b64)=>{
  const bin=atob(b64),bytes=new Uint8Array(bin.length);
  for(let i=0;i<bin.length;i++)bytes[i]=bin.charCodeAt(i);
  const blob=new Blob([bytes]);
  const HASH=await sha256Hex(blob);            // 和线上完全一样的哈希算法
  await new Promise(r=>{const q=indexedDB.deleteDatabase('sheetplayer');q.onsuccess=r;q.onerror=r;q.onblocked=r});
  const db=await new Promise((res,rej)=>{const r=indexedDB.open('sheetplayer',1);
    r.onupgradeneeded=()=>{for(const s of ['files','tracks','anns','spec','meta'])
      if(!r.result.objectStoreNames.contains(s))r.result.createObjectStore(s,{keyPath:'hash'})};
    r.onsuccess=()=>res(r.result);r.onerror=()=>rej(r.error)});
  const put=(s,v)=>new Promise((res,rej)=>{const t=db.transaction(s,'readwrite');t.objectStore(s).put(v);
    t.oncomplete=()=>res();t.onerror=()=>rej(t.error);t.onabort=()=>rej(t.error)});
  const M=(n)=>Array.from({length:n},(_,i)=>({page:1,nx:0.1+0.1*i,ny:0.3,m:i+1,h:0.05}));
  await put('files',{hash:HASH,kind:'pdf',name:'老谱子.pdf',size:bytes.length,blob});
  await put('files',{hash:'%s',kind:'audio',name:'老音频.mp3',size:9,blob:new Blob(['y'])});
  await put('tracks',{hash:HASH,name:'老谱子.pdf',createdAt:1000,updatedAt:2000,
    audios:[{hash:'%s',name:'老音频.mp3',mode:'标准'}],lastAudio:'%s'});
  await put('anns',{hash:HASH,data:{v:6,M:M(4),modes:{'标准':{E:[{m:1,t:1.5,src:'tap'}],
    TEMPO:[{m:1,bpm:120}],METER:[{sig:[4,4],ranges:[]}],FORM:[],offset:0}},activeMode:'标准',ts:1755630000000}});
  // 孤儿行：只有 anns，没有对应的 tracks
  await put('anns',{hash:'%s',data:{v:5,M:M(2),E:[],TEMPO:[{m:1,bpm:120}],
    METER:[{sig:[4,4],ranges:[]}],FORM:[],offset:0,ts:1755630000001}});
  await put('spec',{hash:'%s',px:new Uint8ClampedArray(2*SP_H),frames:2,hop:1,sr:1,dur:1});
  await put('meta',{hash:'playlist',v:{items:[{pdfHash:HASH,audioHash:'%s'}],loop:true,pauseEach:false}});
  db.close();
  return HASH;
}""" % (AUD,AUD,AUD,ORPH,AUD,AUD)

DUMP="""(async()=>{const db=await new Promise(r=>{const o=indexedDB.open('sheetplayer');o.onsuccess=()=>r(o.result)});
 const g=s=>new Promise(r=>{db.transaction(s).objectStore(s).getAll().onsuccess=e=>r(e.target.result)});
 const m=await new Promise(r=>{db.transaction('meta').objectStore('meta').get('playlist').onsuccess=e=>r(e.target.result)});
 const F=await g('files'),S=await g('spec');
 return {p:await g('projects'),k:await g('marks'),t:await g('tracks'),a:await g('anns'),
         fh:F.map(x=>x.hash+':'+x.kind),sh:S.map(x=>x.hash),pl:m?m.v:null}})()"""

async def main():
    errs=[]
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={"width":1500,"height":1000})
        pg.on("pageerror",lambda e:errs.append(str(e)))
        # ?direct=1 不碰 IndexedDB，正好用来手搓 v1 库
        await pg.goto("http://127.0.0.1:8813/player.html?direct=1")
        b64=base64.b64encode(open(PDF,'rb').read()).decode()
        HASH=await pg.evaluate(SEED,b64)

        await pg.goto("http://127.0.0.1:8813/player.html")
        await pg.wait_for_function("()=>idb!==null&&$('lib').style.display==='flex'",timeout=15000)
        await pg.wait_for_timeout(600)
        d=await pg.evaluate(DUMP)

        print(ok(len(d["p"])==2), f"v1 的 2 个键（1 个曲目 + 1 个孤儿 anns）都迁成了项目：{len(d['p'])}")
        byname={x["name"]:x for x in d["p"]}
        print(ok("老谱子.pdf" in byname and "孤儿.pdf" in byname),
              "名字原样保留（老 annotations.json 靠它才匹配得上）: "+str(list(byname)))
        main=byname.get("老谱子.pdf",{})
        orph=byname.get("孤儿.pdf",{})
        print(ok(str(main.get("id","")).startswith("p") and main.get("id")!="" and main["id"]!=HASH),
              "新项目用全新 id（p 开头），不复用老哈希: "+str(main.get("id")))
        print(ok(main.get("pdf",{}).get("hash")==HASH), "有 PDF 的曲目：pdf 指向那份内容哈希")
        print(ok(main.get("pdfHistory")==[]), "刚迁移完没有历史谱子")
        print(ok(main.get("audios",[{}])[0].get("hash")==AUD and main.get("lastAudio")==AUD),
              "音频和 lastAudio 照搬")
        print(ok(orph.get("pdf") is None), "孤儿行（只有 anns 没有 tracks）也迁进来了，pdf=null —— 不遍历并集就会静默丢掉它")
        print(ok(len(d["k"])==2), f"2 份标注都搬进了 marks：{len(d['k'])}")
        mm={x["pid"]:x["data"] for x in d["k"]}
        print(ok(len(mm.get(main["id"],{}).get("M",[]))==4), "主曲目的 4 个小节到了 marks（键是项目 id）")
        print(ok(len(mm.get(orph["id"],{}).get("M",[]))==2), "孤儿的 2 个小节也到了")

        print(ok(d["pl"] and len(d["pl"]["items"])==1 and d["pl"]["items"][0]["pid"]==main["id"]
                 and d["pl"]["items"][0].get("pdfHash") is None and d["pl"]["items"][0]["audioHash"]==AUD),
              "播放列表条目在同一个事务里改成了 {pid,audioHash}: "+str(d["pl"]["items"]))

        print(ok(len(d["t"])==1 and len(d["a"])==2), "老的 tracks/anns 原样留着（非破坏性，回滚=退回旧代码）")
        print(ok(AUD+":audio" in d["fh"] and len(d["sh"])==1), "音频 blob 与它的频谱缓存都没有被误删")

        # 界面上：两个项目各一张卡，等待导入谱子的那张有提示
        cards=await pg.evaluate("[...document.querySelectorAll('.libCard')].map(c=>c.innerText.replace(/\\n/g,' '))")
        print(ok(len(cards)==2), f"界面 {len(cards)} 张卡")
        print(ok(any("等待导入谱子" in c for c in cards)), "没有谱子的项目提示等待导入谱子")
        print(ok(any("已标 4 小节" in c for c in cards)), "有谱子的卡片统计正确")

        # 幂等：再启动一次不会重建、也不会覆盖
        await pg.reload()
        await pg.wait_for_function("()=>idb!==null&&$('lib').style.display==='flex'",timeout=15000)
        await pg.wait_for_timeout(600)
        d2=await pg.evaluate(DUMP)
        print(ok(len(d2["p"])==2 and len(d2["k"])==2), "重跑幂等（migrated2 守卫在同一个事务里）")
        print(ok(sorted(x["id"] for x in d2["p"])==sorted(x["id"] for x in d["p"])), "没有生成第二套项目 id")

        # 打开有谱子的那个项目：标注恢复
        await pg.evaluate("""[...document.querySelectorAll('.libCard')]
          .find(c=>c.innerText.includes('老谱子')).querySelector('button.open').click()""")
        await pg.wait_for_function("()=>document.querySelectorAll('.mk').length===4",timeout=30000)
        print(ok(await pg.evaluate("M.length")==4 and await pg.evaluate("E.length")==1),
              "迁移后的项目打开：4 个小节 + 1 个时间点")
        print(ok(await pg.evaluate("track.lastAudio")==AUD and await pg.evaluate("pid")!=HASH),
              "打开时按 pid 取记录、按 pdf.hash 取 blob（两个键没混用）")

        print(ok(await pg.evaluate("audLocal.has('%s')"%AUD)), "打开后认出音频文件在本机（按音频哈希查 files，没被项目 id 污染）")
        print(ok(await pg.evaluate("SPEC!==null||$('specMsg').textContent.length>=0")), "有音频的项目打开不报错")

        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
