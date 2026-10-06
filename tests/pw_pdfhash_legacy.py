# 探针：老记录（升级前只有「前 1MB」这一个键）在换了指纹口径之后还认不认得回来。
# 换指纹最怕的不是漏认，是**多认**：同一份文件被当成新的一份，于是 pdfHistory 凭空多一条、
# 同一个几十 MB 的 blob 存两遍、跨设备同步的身份也跟着漂。所以这一条必须绿：
#   ① 同一份文件 → 沿用老键 O，pdfHistory 不长、库里还是一份 blob
#   ② 改了后面那一版 → 走新键 N，换谱真的换（老键 O 进历史）
import asyncio, http.server, socketserver, threading, functools, os, hashlib, base64, shutil
from playwright.async_api import async_playwright
ROOT = "/home/xiaoyuanzhu/my-life-db/data/assets"
SRC = ROOT + "/线谱合集/QL_七律长征[线][SATB+T+Pn][彦克,吕远].pdf"     # 2.58 MB
NAME = os.path.basename(SRC)
NEW = "/tmp/probe_legacy/" + NAME
os.makedirs("/tmp/probe_legacy", exist_ok=True)
raw = open(SRC, "rb").read()
open(NEW, "wb").write(raw + "\n% 2026-10-06 加完笔记重新导出（增量保存的形态）\n%%EOF\n".encode())
O = hashlib.sha256(raw[:1 << 20]).hexdigest()          # 升级前的键：前 1MB

H = functools.partial(http.server.SimpleHTTPRequestHandler, directory=ROOT + "/SheetPlayer")
socketserver.TCPServer.allow_reuse_address = True
srv = socketserver.TCPServer(("127.0.0.1", 8780), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()

def ok(c): return "OK   " if c else "FAIL "

DB = """(async()=>{const db=await new Promise(r=>{const o=indexedDB.open('sheetplayer');o.onsuccess=()=>r(o.result)});
 const g=(s)=>new Promise(r=>{db.transaction(s).objectStore(s).getAll().onsuccess=e=>r(e.target.result)});
 const F=await g('files'),P=await g('projects'),M=await g('marks');
 return {f:F.map(x=>({hash:x.hash,size:x.size,kind:x.kind})),p:P,m:M.map(x=>({id:x.id,m:(x.data&&x.data.M||[]).length}))}})()"""

# 把新库"退回"成老代码建出来的样子：键换成前 1MB 的那个哈希
REKEY = """async(O)=>{
  const db=idb;
  const all=await new Promise(r=>{const q=db.transaction('files').objectStore('files').getAll();q.onsuccess=()=>r(q.result)});
  const pdfs=all.filter(x=>x.kind==='pdf');
  for(const x of pdfs){
    await idbPut(db,'files',{...x,hash:O});
    await idbDel(db,'files',x.hash);
  }
  const ps=await new Promise(r=>{const q=db.transaction('projects').objectStore('projects').getAll();q.onsuccess=()=>r(q.result)});
  for(const p of ps){ if(p.pdf){ p.pdf={...p.pdf,hash:O}; await idbPut(db,'projects',p); } }
  return pdfs.length;
}"""

async def main():
    errs = []
    dialogs = []
    async with async_playwright() as p:
        b = await p.chromium.launch(); pg = await b.new_page(viewport={"width": 1500, "height": 1000})
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("dialog", lambda d: (dialogs.append(d.message), asyncio.create_task(d.accept())))
        await pg.goto("http://127.0.0.1:8780/player.html")
        await pg.wait_for_function("()=>idb!==null&&$('lib').style.display==='flex'", timeout=15000)

        # 用当前代码导入一次，再把键改写成老口径 → 这就是"升级前建好的库"
        await pg.set_input_files("#fPdf", SRC)
        await pg.wait_for_function("()=>document.querySelector('.page[data-page=\"1\"]')?.dataset.done", timeout=60000)
        pid0 = await pg.evaluate("pid")
        marked = await pg.evaluate("""async()=>{M=[{page:1,nx:.3,ny:.4,m:1,h:.09},
          {page:1,nx:.5,ny:.4,m:2,h:.09}];save();return M.length}""")
        await asyncio.sleep(1.2)          # save() 是防抖的，落库前不能改键/刷新
        n = await pg.evaluate(REKEY, O)
        print(ok(n == 1), f"改成老口径：{n} 份 PDF 的键换成前 1MB 哈希")
        d = await pg.evaluate(DB)
        print(ok(d["p"][0]["pdf"]["hash"] == O), "项目记录也指向老键")
        await pg.reload()
        await pg.wait_for_function("()=>idb!==null&&$('lib').style.display==='flex'", timeout=15000)

        # ① 同一份文件再导一次：必须沿用老键 O，pdfHistory 不长、blob 不翻倍
        async def openLib():
            if await pg.evaluate("$('lib').style.display!=='flex'"):
                await pg.evaluate("$('bLib').onclick()")
            await pg.wait_for_selector(".libCard button.repl")
        dialogs.clear()
        await openLib()
        async with pg.expect_file_chooser() as fc:
            await pg.click(".libCard button.repl")
        await (await fc.value).set_files(SRC)
        await pg.wait_for_function("(h)=>pdfHash===h", arg=O, timeout=60000)
        await asyncio.sleep(0.8)
        d = await pg.evaluate(DB)
        print(ok(await pg.evaluate("pid") == pid0), "还是同一个项目")
        print(ok(await pg.evaluate("pdfHash") == O), "身份键沿用老键 O（没漂移）")
        print(ok(len(d["f"]) == 1), f"库里还是一份 blob：{len(d['f'])}")
        print(ok(len(d["p"][0]["pdfHistory"]) == 0), f"pdfHistory 没多出条目：{len(d['p'][0]['pdfHistory'])}")
        print(ok(d["p"][0]["pdf"]["hash"] == O), "项目记录仍指向老键")
        print(ok(d["m"][0]["m"] == marked), f"标注原样：{d['m'][0]['m']} 个小节")

        # ② 改了后面那版：新键，真换谱，老键进历史
        dialogs.clear()
        await openLib()
        async with pg.expect_file_chooser() as fc:
            await pg.click(".libCard button.repl")
        await (await fc.value).set_files(NEW)
        await pg.wait_for_function("(h)=>pdfHash!==h", arg=O, timeout=60000)
        await asyncio.sleep(0.8)
        h2 = await pg.evaluate("pdfHash")
        d = await pg.evaluate(DB)
        print(ok("已换谱" in (await pg.inner_text("#msg"))), "换谱提示：" + (await pg.inner_text("#msg")))
        print(ok(len(dialogs) > 0), f"弹了确认框（{len(dialogs)} 个）")
        print(ok(len(d["f"]) == 2), f"改成两份 blob：{len(d['f'])}")
        print(ok([x["hash"] for x in d["p"][0]["pdfHistory"]] == [O]), "老键 O 进了 pdfHistory")
        print(ok(d["p"][0]["pdf"]["hash"] == h2), "项目记录换成新键")
        print(ok(d["m"][0]["m"] == marked), f"标注原样：{d['m'][0]['m']} 个小节")

        print("\npage errors:", errs or "(none)")
        await b.close()

asyncio.run(main())
