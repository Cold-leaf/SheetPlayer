# 曲目库「一眼找到」四件事：曲名拆分显示 / 搜索 / 排序（标注也算「最近」）/ 网格列数。
#
# 排序那条是这个文件的重点：#libList 原来按 updatedAt 倒序，而 updatedAt 只在库结构变更时写
# （导入谱子/换谱/改名/加音频），标注走 marks 表根本不碰它——刚标完两小时的曲子不会冒头。
# 所以这里造一个"updatedAt 最旧、但刚被标注过"的项目，断言它排到最前。
import asyncio, http.server, socketserver, threading, functools
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
PDF=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*a): pass
H=functools.partial(Quiet,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8891),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c): return "OK   " if c else "FAIL "

SONG="SH_松花江上[线][SATB+T+Pn]标注"      # 库里的项目名（带上前缀和两个方括号标记）
SL="四海"                                   # 不合命名约定：没有前缀、没有方括号
CQ="CQ_传奇[线][SATB+Pn]标注"
# 卡片上只显示曲名，所以按卡片定位时用的是这个（不是项目名）
T_SONG,T_SL,T_CQ="松花江上","四海","传奇"

async def main():
    errs=[]
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={"width":1500,"height":1000})
        pg.on("pageerror",lambda e:errs.append(str(e)))
        await pg.goto("http://127.0.0.1:8891/player.html")
        await pg.wait_for_function("()=>idb!==null",timeout=10000)
        await pg.wait_for_function("()=>$('lib').style.display==='flex'",timeout=10000)

        async def newProject(nm):
            await pg.click("#libNew")
            await pg.wait_for_selector("#dlg",state="visible")
            await pg.fill("#dlgInp",nm); await pg.click("#dlgOk")
            await pg.wait_for_function("()=>$('dlg').style.display==='none'",timeout=8000)
            await pg.wait_for_timeout(150)          # 拉开相邻项目的时间戳，排序断言才有意义

        async def enterScore():
            # 先等 loadPdfBlob 走到 showLib(false)，再等第一页渲染完。
            # 只等 data-done 不行：那是"这一页渲染过了"的记号，上一首曲子就已经是 true，
            # 会立刻返回——等于没等，后面 backToLib 就跟还没读完的那次导入抢上了
            await pg.wait_for_function("()=>$('lib').style.display==='none'",timeout=40000)
            await pg.wait_for_function("()=>document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=40000)

        async def importPdf(title):
            card=pg.locator(".libCard",has_text=title).first
            async with pg.expect_file_chooser() as fc:
                await card.locator("button.open").click()
            await (await fc.value).set_files(PDF)
            await enterScore()

        async def open(title,expect):
            await pg.click(f".libCard:has-text('{title}') button.open")
            await enterScore()
            await pg.wait_for_function(f"()=>document.querySelectorAll('.mk').length==={expect}",timeout=20000)

        async def backToLib(n):
            await pg.evaluate("$('bLib').onclick()")
            await pg.wait_for_function("()=>$('lib').style.display==='flex'",timeout=10000)
            await pg.wait_for_function(f"()=>document.querySelectorAll('.libCard').length==={n}",timeout=10000)
            await pg.wait_for_timeout(200)

        async def mark(n,expect):
            await pg.select_option("#mode","mark")
            bb=await (await pg.query_selector('.page[data-page="1"]')).bounding_box()
            for i in range(n):
                await pg.mouse.click(bb["x"]+bb["width"]*(0.3+0.15*i),bb["y"]+bb["height"]*0.4)
            await pg.wait_for_function(f"()=>document.querySelectorAll('.mk').length==={expect}",timeout=15000)
            await asyncio.sleep(1.0)                # > save() 的 400ms 防抖，让 marks.ts 真的落库

        async def titles():
            return await pg.evaluate("()=>[...document.querySelectorAll('.libCard .nm .t')].map(e=>e.textContent)")
        async def ncards():
            return await pg.evaluate("document.querySelectorAll('.libCard').length")
        async def search(q):
            await pg.fill("#libQ",q)
            await pg.wait_for_timeout(300)          # > 120ms 防抖
        async def cols():
            return await pg.evaluate("""()=>getComputedStyle($('libList')).gridTemplateColumns
                                          .split(' ').filter(Boolean).length""")

        # --- 0. 建 3 个项目。顺序很讲究：A 先拿谱子（updatedAt 最旧），B、C 依次更晚 ---
        await newProject(SONG); await importPdf(T_SONG); await backToLib(1)
        await newProject(SL);   await importPdf(T_SL);   await backToLib(2)
        await newProject(CQ);   await importPdf(T_CQ);   await backToLib(3)
        print(ok(await ncards()==3), f"库里 {await ncards()} 张卡片")

        # --- 1. 曲名拆开显示：曲名在 .nm .t 里、方括号标记收进 .nm .tags 一行小字 ---
        info=await pg.evaluate("""()=>[...document.querySelectorAll('.libCard')].map(c=>({
            t:c.querySelector('.nm .t')?.textContent||'',
            tags:c.querySelector('.nm .tags')?.textContent||'',
            title:c.querySelector('.nm')?.getAttribute('title')||'',
            meta:c.querySelector('.meta')?.textContent||''}))""")
        by={x["t"]:x for x in info}
        print(ok("松花江上" in by), f"曲名剥掉了 SH_ 前缀和方括号: {sorted(by)}")
        s=by.get("松花江上",{})
        print(ok("线" in s.get("tags","") and "SATB+T+Pn" in s.get("tags","")),
              f"方括号标记降成一行小字: 「{s.get('tags','')}」")
        print(ok(s.get("title")==SONG), f".nm 的 title 仍是原名（完整名字没丢）: {s.get('title','')}")
        print(ok("四海" in by and by["四海"]["tags"]==""),
              "不合命名约定的「四海」整串当曲名、没有硬凑出标记")
        print(ok("已标 0 小节" in by.get("四海",{}).get("meta","")),
              f"元信息文案没改（其它探针靠它）: 「{by.get('四海',{}).get('meta','')}」")
        print(ok("\n" not in by.get("四海",{}).get("meta","")), "元信息压成一行")

        # --- 2. 卡片纵向三段：名字 / 元信息 / 操作 ---
        bands=await pg.evaluate("""()=>{const c=document.querySelector('.libCard');
            const g=s=>{const e=c.querySelector(s);return e?Math.round(e.getBoundingClientRect().top):null};
            const btns=[...c.querySelectorAll('.acts button')].map(b=>Math.round(b.getBoundingClientRect().top));
            return {nm:g('.nm'),meta:g('.meta'),acts:g('.acts'),
                    n:btns.length,rows:new Set(btns).size}}""")
        print(ok(bands["nm"] is not None and bands["nm"]<bands["meta"]<bands["acts"]),
              f"名字 → 元信息 → 操作 自上而下（{bands['nm']} < {bands['meta']} < {bands['acts']}）")
        # 一行放得下是设计意图（卡片高度才不失控），所以连行数一起断言
        print(ok(bands["n"]==5 and bands["rows"]==1),
              f"5 个按钮一个没少、且排在一行（{bands['n']} 个，占 {bands['rows']} 行）")

        # --- 3. 排序：标注过的排到最前（updatedAt 最旧也算最近动过）---
        t0=await titles()
        print(ok(t0==["传奇","四海","松花江上"]),
              f"初始按 updatedAt 倒序（最后建的在最前）: {t0}")
        await open(T_SONG,0)
        await mark(1,1)
        await backToLib(3)
        t1=await titles()
        print(ok(t1[0]=="松花江上"),
              f"刚标注过的《松花江上》冒到最前（它的 updatedAt 反而最旧）: {t1}")
        eff=await pg.evaluate("""async()=>{const ps=await idbAll(idb,'projects');
            const a=ps.find(p=>p.name.startsWith('SH_')),b=ps.find(p=>p.name==='四海');
            const m=await idbGet(idb,'marks',a.id);
            return {aUp:a.updatedAt,bUp:b.updatedAt,ts:m&&m.data.ts}}""")
        print(ok(eff["aUp"]<eff["bUp"]<eff["ts"]),
              f"证据：A.updatedAt {eff['aUp']} < B.updatedAt {eff['bUp']} < A.marks.ts {eff['ts']}")

        # 曲名排序：断言「整列按中文排序序」+ 第一个是拼音最靠前的那个，不写死 ICU 的排法
        await pg.click("#libTools button:has-text('曲名')")
        await pg.wait_for_timeout(300)
        sortedOk=await pg.evaluate("""()=>{const g=[...document.querySelectorAll('.libCard .nm .t')].map(e=>e.textContent);
            return g.every((x,i)=>i===0||g[i-1].localeCompare(x,'zh')<=0)}""")
        t2=await titles()
        print(ok(sortedOk and t2[0]=="传奇"), f"切「曲名」整列按中文序排: {t2}")
        await pg.click("#libTools button:has-text('最近')")
        await pg.wait_for_timeout(300)
        print(ok((await titles())[0]=="松花江上"), f"切回「最近」还原: {await titles()}")

        # --- 4. 当前曲目高亮 ---
        cur=await pg.evaluate("[...document.querySelectorAll('.libCard.cur .nm .t')].map(e=>e.textContent)")
        print(ok(cur==["松花江上"]), f"当前曲目那张卡带 .cur: {cur}")

        # --- 5. 搜索：曲名 / 别名 / 藏在方括号里的标记都要能搜到 ---
        await search("松花"); print(ok(await titles()==["松花江上"]), f"搜「松花」→ {await titles()}")
        await search("SATB"); print(ok(sorted(await titles())==sorted(["松花江上","传奇"])),
                                   f"搜「SATB」（藏在方括号里）→ {await titles()}")
        await search("四海"); print(ok(await titles()==["四海"]), f"搜「四海」→ {await titles()}")
        await search("不存在的曲子")
        empty=await pg.inner_text("#libList")
        print(ok(await ncards()==0 and "没有匹配" in empty), f"搜不到时的提示: 「{empty.strip()}」")
        await search("")
        print(ok(await ncards()==3), f"清空搜索后 {await ncards()} 张卡片全回来")

        # --- 6. 网格列数随宽度变。300px 的下限是照着「5 个按钮排一行」定的（桌面 288px、
        #        触屏 44px 下 298px），所以顺带钉住每列不窄于 300、手机上一列也不横向溢出 ---
        w=await pg.evaluate("()=>Math.round(document.querySelector('.libCard').getBoundingClientRect().width)")
        print(ok(await cols()==3 and w>=300), f"1500px：{await cols()} 列，卡片 {w}px 宽")
        await pg.set_viewport_size({"width":834,"height":1194}); await pg.wait_for_timeout(300)
        w=await pg.evaluate("()=>Math.round(document.querySelector('.libCard').getBoundingClientRect().width)")
        print(ok(await cols()==2 and w>=300), f"iPad 竖屏 834px：{await cols()} 列，卡片 {w}px 宽")
        await pg.set_viewport_size({"width":390,"height":844}); await pg.wait_for_timeout(300)
        over=await pg.evaluate("""()=>{const l=$('libList').getBoundingClientRect();
            return [...document.querySelectorAll('.libCard')].some(c=>c.getBoundingClientRect().right>l.right+1)}""")
        print(ok(await cols()==1 and not over), f"iPhone 竖屏 390px：{await cols()} 列、不横向溢出")

        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
