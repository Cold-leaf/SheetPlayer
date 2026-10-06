# 换谱：改了「前 1MB 之后」的那一版 PDF，必须真的换上去。
# sha256Hex 只哈希前 1MB（身份键），所以：
#   - 增量保存（前面字节原样保留、改动追加在后面）→ 前缀哈希一模一样
#   - 同样大小的原地修改（改动在第 1MB 之后）→ 前缀哈希一模一样
# 两条路都会让 attachPdf/replacePdf 认为「这就是同一份」，于是既不换 blob、也不动项目记录，
# 屏幕上还是老的那份。用户看到的就是「换谱了，没变」。
import asyncio, http.server, socketserver, threading, functools, shutil, hashlib, os
from playwright.async_api import async_playwright
ROOT = "/home/xiaoyuanzhu/my-life-db/data/assets"
SRC = ROOT + "/线谱合集/QL_七律长征[线][SATB+T+Pn][彦克,吕远].pdf"     # 2.58 MB > 1 MiB
CTRL = ROOT + "/线谱合集/BW_不忘初心[线][SATB+NA+Pn].pdf"             # 完全不同的另一份（<1MB）
NAME = os.path.basename(SRC)
NEW = "/tmp/probe_new/" + NAME                                        # 同名、前 1MB 不变
CTRL_NAME = "/tmp/probe_new/" + os.path.basename(CTRL)

os.makedirs("/tmp/probe_new", exist_ok=True)
raw = open(SRC, "rb").read()
# 增量保存的最小模型：原字节一个不动，改动追加在末尾
open(NEW, "wb").write(raw + b"\n% 2026-10-06 edited after page 1\n1 0 obj\n<<>>\nendobj\n%%EOF\n")
shutil.copy(CTRL, CTRL_NAME)

def h(b): return hashlib.sha256(b).hexdigest()
def prefix(b): return hashlib.sha256(b[:1 << 20]).hexdigest()

H = functools.partial(http.server.SimpleHTTPRequestHandler, directory=ROOT + "/SheetPlayer")
socketserver.TCPServer.allow_reuse_address = True
srv = socketserver.TCPServer(("127.0.0.1", 8779), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()

def ok(c): return "OK   " if c else "FAIL "

DB = """(async()=>{const db=await new Promise(r=>{const o=indexedDB.open('sheetplayer');o.onsuccess=()=>r(o.result)});
 const g=(s)=>new Promise(r=>{db.transaction(s).objectStore(s).getAll().onsuccess=e=>r(e.target.result)});
 const P=await g('projects'),M=await g('marks'),F=await g('files');
 return {p:P,m:M,f:F.filter(x=>x.kind==='pdf').map(x=>({hash:x.hash,size:x.size,name:x.name}))}})()"""

async def main():
    errs = []
    dialogs = []
    async with async_playwright() as p:
        b = await p.chromium.launch(); pg = await b.new_page(viewport={"width": 1500, "height": 1000})
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("dialog", lambda d: (dialogs.append(d.message), asyncio.create_task(d.accept())))
        await pg.goto("http://127.0.0.1:8779/player.html")
        await pg.wait_for_function("()=>idb!==null&&$('lib').style.display==='flex'", timeout=15000)

        # ① 两份文件确实是不同的内容，但应用看得见的那 1MB 完全一样
        print(ok(h(raw) != h(open(NEW, "rb").read())), "两份文件内容确实不同（全文件 sha256）")
        print(ok(prefix(raw) == prefix(open(NEW, "rb").read())), "前 1MB 的 sha256 完全相同 → 应用算出来是同一个哈希")

        # ② 新文件仍是一份合法 PDF（pdf.js 打得开、页数一样）
        import base64
        n = await pg.evaluate("""async(b64)=>{
            const b=Uint8Array.from(atob(b64),c=>c.charCodeAt(0));
            const d=await pdfjsLib.getDocument({data:b}).promise; return d.numPages}""",
            base64.b64encode(open(NEW, "rb").read()).decode())
        print(ok(n > 0), f"改过的那份 pdf.js 打得开，{n} 页")

        # ③ 导入原谱并标 3 个小节
        await pg.set_input_files("#fPdf", SRC)
        await pg.wait_for_function("()=>document.querySelector('.page[data-page=\"1\"]')?.dataset.done", timeout=60000)
        pid0 = await pg.evaluate("pid"); h1 = await pg.evaluate("pdfHash")
        await pg.select_option("#mode", "mark")
        bb = await (await pg.query_selector('.page[data-page="1"]')).bounding_box()
        for fx in (0.3, 0.45, 0.6):
            await pg.mouse.click(bb["x"] + bb["width"] * fx, bb["y"] + bb["height"] * 0.4)
        await asyncio.sleep(0.9)
        print(ok(await pg.evaluate("M.length") == 3), "原谱标好 3 个小节")

        # ④ 点「换谱」换成改过的那一版（同名、只改了 1MB 之后）
        async def openLib():
            if await pg.evaluate("$('lib').style.display!=='flex'"):
                await pg.evaluate("$('bLib').onclick()")
            await pg.wait_for_selector(".libCard button.repl")
        dialogs.clear()
        await openLib()
        async with pg.expect_file_chooser() as fc:
            await pg.click(".libCard button.repl")
        await (await fc.value).set_files(NEW)
        await asyncio.sleep(2.5)
        h2 = await pg.evaluate("pdfHash")
        print(ok(h2 != h1), "换谱后应用认的哈希变了？（没变＝它以为还是同一份）")
        print(ok("已换谱" in (await pg.inner_text("#msg"))), "有「已换谱」的提示：" + (await pg.inner_text("#msg")))
        print(ok(len(dialogs) > 0), f"弹过确认框（{len(dialogs)} 个）")

        d = await pg.evaluate(DB)
        stor = [f for f in d["f"] if f["hash"] == h1]
        print(ok(stor and stor[0]["size"] == len(raw)),
              "库里 h1 那条存着的还是老文件（大小 %s vs 新文件 %s）" %
              (stor[0]["size"] if stor else "?", len(open(NEW, "rb").read())))
        print(ok(len(d["f"]) == 2), f"库里有几份 PDF：{len(d['f'])}（期望 2＝老的一份 + 新的一份）")
        print(ok(d["p"][0]["pdf"]["hash"] != h1), "项目记录指向的是新哈希")
        print(ok(await pg.evaluate("M.length") == 3), "标注没动（3 个小节）")

        # ⑤ 对照组：换成一份完全不同的谱子（前 1MB 也不同）→ 这条路是好的
        print("--- 对照组：换成完全不同的谱子 ---")
        dialogs.clear()
        await openLib()
        async with pg.expect_file_chooser() as fc:
            await pg.click(".libCard button.repl")
        await (await fc.value).set_files(CTRL_NAME)
        await pg.wait_for_function("(h)=>pdfHash!==h", arg=h1, timeout=60000)
        await asyncio.sleep(0.5)
        print(ok(await pg.evaluate("pdfHash") not in (h1, prefix(raw))), "对照组：哈希确实变了")
        print(ok("已换谱" in (await pg.inner_text("#msg"))), "对照组提示：" + (await pg.inner_text("#msg")))

        print("\npage errors:", errs or "(none)")
        await b.close()

asyncio.run(main())
