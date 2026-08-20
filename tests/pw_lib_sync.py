import asyncio, json, http.server, socketserver, threading, functools
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8774),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c): return "OK   " if c else "FAIL "

def mk(n):
    return [{"page":1,"nx":0.1+0.1*i,"ny":0.3,"m":i+1,"h":0.05} for i in range(n)]

def payload(ts, nbars, phash="sync1"):
    return {"app":"sheetplayer","v":1,"items":[
        {"name":"测试曲目","pdfHash":phash,"data":{"v":5,"M":mk(nbars),"E":[],
         "TEMPO":[{"m":1,"bpm":120}],"METER":[{"sig":[4,4],"ranges":[]}],
         "FORM":[],"offset":0,"ts":ts}}]}

async def main():
    errs=[]
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={"width":1500,"height":1000})
        pg.on("pageerror",lambda e:errs.append(str(e)))
        state={"status":200,"body":payload(1000,2)}
        async def route_handler(route):
            await route.fulfill(status=state["status"],content_type="application/json",
                                body=json.dumps(state["body"]))
        await pg.route("**raw.githubusercontent.com/**", route_handler)
        await pg.goto("http://127.0.0.1:8774/player.html")
        await pg.wait_for_function("()=>idb!==null&&$('lib').style.display==='flex'",timeout=15000)

        # 首次同步：拉到一个曲目（2 小节）
        await pg.click("#bSync")
        await pg.wait_for_function("()=>document.querySelectorAll('.libCard').length===1",timeout=10000)
        print(ok("已标 2 小节" in await pg.inner_text(".libCard")), "从 GitHub 同步到 1 首（已标 2 小节）")
        print(ok("同步完成：导入 1 首" in await pg.inner_text("#msg")), "同步提示: "+await pg.inner_text("#msg"))

        # 较新数据 → 覆盖
        state["body"]=payload(2000,3)
        await pg.click("#bSync")
        await pg.wait_for_function("()=>document.querySelector('.libCard')?.innerText.includes('已标 3 小节')",timeout=10000)
        print(ok("已标 3 小节" in await pg.inner_text(".libCard")), "时间戳较新 → 覆盖（3 小节）")

        # 较旧数据 → 跳过
        state["body"]=payload(500,1)
        await pg.click("#bSync")
        await pg.wait_for_timeout(800)
        print(ok("已标 3 小节" in await pg.inner_text(".libCard")), "时间戳较旧 → 不覆盖（仍是 3 小节）")
        print(ok("跳过 1 首" in await pg.inner_text("#msg")), "跳过提示: "+await pg.inner_text("#msg"))

        # 404：仓库里还没有文件
        state["status"]=404; state["body"]="404: Not Found"
        await pg.click("#bSync")
        await pg.wait_for_timeout(800)
        print(ok("annotations.json" in await pg.inner_text("#msg")), "404 给出友好提示: "+await pg.inner_text("#msg"))

        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
