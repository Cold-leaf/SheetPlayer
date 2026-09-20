# 触控目标：粗指针设备上每个可点控件的命中区都要 ≥44×44，且相邻命中区不许交叠。
#
# 两个容易搞错的点，这里各有一条断言盯着：
#   1. 尺寸查询用 (pointer:coarse),(any-pointer:coarse) —— 二合一笔记本插着鼠标时
#      pointer 是 fine，但手指点下去还是需要大目标。
#   2. 版式查询只能用 (pointer:coarse) —— 否则触屏笔记本会被当成手机排版。
# Playwright 的 has_touch 会把 pointer 和 any-pointer 一起置成 coarse，模拟不出
# 「主指针 fine + 有触屏」那种组合，所以第 1 条额外用样式表结构断言兜底。
import asyncio, http.server, socketserver, threading, functools
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
PDF=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*a): pass
H=functools.partial(Quiet,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8821),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c): return "OK   " if c else "FAIL "

MIN=44
# 每个面板：(名字, 面板根选择器, 根内的可点控件)
PANELS=[
  ("工具栏",   "#bar",     "button,label,select,input[type=checkbox]"),
  ("菜单",     "#menu",    "button,.mbtn,input,select,label"),
  ("播放列表", "#plPop",   "#plPopHd button,#plPopHd label,.plRow button,.plRow select"),
  ("曲目库",   "#lib",     "#libHd button,#libHd label.libBtn,.libCard button,#plHd button,.plRow button,.plRow select"),
  ("生成面板", "#gen",     "button,input,select,label"),
  ("频谱头",   "#specHdr", "button,input,select,label"),
  ("ownCloud", "#davPop",  "#davHd button,#davCfgBox button,#davCfgBox input,#davCfgBox select"),
  ("标记面板", "#panel",   "button,input"),
  ("对话框",   "#dlg",     "button,input"),
  ("模式对话框","#dlgMode","button,input,select"),
  ("安装卡片", "#instPop", "button"),
]

JS = r"""
// 命中区：含 ::before/::after 绝对定位撑出来的那部分（B 层控件视觉盒不到 44，全靠它）
// 绝对定位元素的 getComputedStyle().height 返回的是已用值(px)而不是 auto，
// 所以不能按 height==='auto' 判断，得优先用 top/bottom、left/right 直接算。
window.__hit=el=>{
  const r=el.getBoundingClientRect();
  let l=r.left,t=r.top,rr=r.right,b=r.bottom;
  for(const pe of ['::before','::after']){
    const cs=getComputedStyle(el,pe);
    if(cs.content==='none'||cs.display==='none'||cs.position!=='absolute')continue;
    const n=v=>{const x=parseFloat(v);return isNaN(x)?null:x};
    const bw=n(cs.borderTopWidth)||0,bh=n(cs.borderBottomWidth)||0;
    const lw=n(cs.borderLeftWidth)||0,rw=n(cs.borderRightWidth)||0;
    const top=n(cs.top),bottom=n(cs.bottom),left=n(cs.left),right=n(cs.right);
    let t2,b2;
    if(top!==null&&bottom!==null){t2=r.top+bw+top;b2=r.bottom-bh-bottom}
    else{const h=n(cs.height);if(h===null)continue;t2=r.top+bw+(top||0);b2=t2+h}
    let l2,r2;
    if(left!==null&&right!==null){l2=r.left+lw+left;r2=r.right-rw-right}
    else{const w=n(cs.width);if(w===null)continue;l2=r.left+lw+(left||0);r2=l2+w}
    l=Math.min(l,l2);t=Math.min(t,t2);rr=Math.max(rr,r2);b=Math.max(b,b2);
  }
  return {l,t,r:rr,b};
};
// 勾选框/单选框的命中区其实是外层 <label>（标签内点哪儿都切换），按 label 量才算数
window.__target=el=>{
  if(el.tagName==='INPUT'&&/^(checkbox|radio)$/.test(el.type)){
    const lb=el.closest('label');
    if(lb)return {el:lb,via:el.id||el.type};
  }
  return {el,via:''};
};
window.__scan=root=>{
  const out=[];
  document.querySelectorAll(root).forEach(raw=>{
    const cs0=getComputedStyle(raw);
    if(cs0.display==='none'||cs0.visibility==='hidden')return;
    const {el,via}=window.__target(raw);
    if(el!==raw&&getComputedStyle(el).display==='none')return;
    const r=el.getBoundingClientRect();
    if(r.width<1&&r.height<1)return;
    const h=window.__hit(el);
    out.push({tag:raw.tagName.toLowerCase(),id:raw.id||'',
      cls:raw.className&&raw.className.baseVal===undefined?String(raw.className):'',
      txt:(raw.textContent||'').trim().slice(0,14),via,
      w:Math.round(h.r-h.l),h:Math.round(h.b-h.t),
      l:h.l,t:h.t,rr:h.r,b:h.b});
  });
  return out;
};
// 相邻命中区不能交叠：交叠会让 DOM 靠后的那个偷走点击。
// 祖先/后代不算（label 套 select、label 套 checkbox），同一个 label 收进来的也不算
window.__overlaps=root=>{
  const raw=[...document.querySelectorAll(root)].filter(el=>{
    const cs=getComputedStyle(el);
    return cs.display!=='none'&&cs.visibility!=='hidden'&&el.getBoundingClientRect().width>0});
  const bad=[];
  for(let i=0;i<raw.length;i++)for(let j=i+1;j<raw.length;j++){
    const A=raw[i],B=raw[j];
    if(A.contains(B)||B.contains(A))continue;
    const a=window.__target(A).el,b=window.__target(B).el;
    if(a===b||a.contains(b)||b.contains(a))continue;
    const x=window.__hit(a),y=window.__hit(b);
    const ox=Math.min(x.r,y.r)-Math.max(x.l,y.l), oy=Math.min(x.b,y.b)-Math.max(x.t,y.t);
    if(ox>1&&oy>1)bad.push({a:A.tagName+(A.id?'#'+A.id:'.'+String(A.className).split(' ')[0]),
                            b:B.tagName+(B.id?'#'+B.id:'.'+String(B.className).split(' ')[0]),
                            ow:Math.round(ox),oh:Math.round(oy)});
  }
  return bad;
};
// 样式表结构：把每条规则连同它所在的 @media 条件一起取出来
window.__rules=()=>{
  const out=[];
  const walk=(rs,cond)=>{for(const r of rs){
    if(r.selectorText!==undefined&&r.selectorText)out.push({cond:cond||'',sel:r.selectorText,body:r.cssText||''});
    else if(r.cssRules)walk(r.cssRules, r.conditionText||cond);
  }};
  for(const sh of document.styleSheets){try{walk(sh.cssRules,'')}catch(e){}}
  return out;
};
"""

def line(it):
    name=it['tag']+('#'+it['id'] if it['id'] else ('.'+it['cls'].split(' ')[0] if it['cls'] else ''))
    via=f"（经 {it['via']} 的 label）" if it['via'] else ''
    return f"    FAIL {name} 「{it['txt']}」 命中 {it['w']}×{it['h']}{via}"

async def main():
    errs=[]
    async with async_playwright() as p:
        b=await p.chromium.launch()
        pg=await b.new_page(viewport={"width":834,"height":1194},has_touch=True,device_scale_factor=2)
        pg.on("pageerror",lambda e:errs.append(str(e)))
        await pg.goto("http://127.0.0.1:8821/player.html?direct=1")
        await pg.evaluate("localStorage.clear()")
        await pg.set_input_files("#fPdf",PDF)
        await pg.wait_for_function("()=>document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=40000)
        await pg.wait_for_timeout(300)
        await pg.evaluate(JS)

        # --- 0. 前提 ---
        mq=await pg.evaluate("""()=>({coarse:matchMedia('(pointer:coarse)').matches,
                                      any:matchMedia('(any-pointer:coarse)').matches})""")
        print(ok(mq["coarse"] and mq["any"]), f"该视口下 pointer/any-pointer 都是 coarse: {mq}")

        # --- 1. 样式表结构：尺寸规则带 any-pointer，版式规则不许带 ---
        rules=await pg.evaluate("()=>window.__rules()")
        # Chromium 把条件规范化成 "(any-pointer: coarse)"，比对前先把空格去掉
        norm=lambda c:c.replace(" ","")
        sizeCond=sorted({r["cond"] for r in rules
                         if norm("min-height:44px") in norm(r["body"])})
        print(ok(any(norm("any-pointer:coarse") in norm(c) for c in sizeCond)),
              f"尺寸规则带 any-pointer:coarse: {sizeCond}")
        rowRules=[r for r in rules if ".row" in r["sel"] and "nowrap" in r["body"]]
        badRow=[r["cond"] for r in rowRules if "any-pointer" in norm(r["cond"])]
        print(ok(bool(rowRules) and not badRow),
              f"版式(.row 横滑)只用 pointer、不带 any-pointer: {[r['cond'] for r in rowRules]}")
        helpGest=[r for r in rules if "#helpGest" in r["sel"] and "order" in r["body"]]
        print(ok(len(helpGest)>=2 and any("any-pointer" in norm(r["cond"]) for r in helpGest)),
              f"帮助面板的段落排序也算上触屏笔记本: {[r['cond'] for r in helpGest]}")

        async def scan(label,root,sub,page=None):
            px=page or pg
            sel=",".join(f"{root} {s.strip()}" for s in sub.split(","))
            items=await px.evaluate("s=>window.__scan(s)",sel)
            bad=await px.evaluate("s=>window.__overlaps(s)",sel)
            small=[i for i in items if i["w"]<MIN or i["h"]<MIN]
            print(ok(not small and not bad),
                  f"[{label}] {len(items)} 个控件全部 ≥{MIN}×{MIN}、无交叠"
                  + (f" —— 不达标 {len(small)} 个、交叠 {len(bad)} 处" if (small or bad) else ""))
            for it in small: print(line(it))
            for x in bad: print(f"    FAIL 命中区交叠: {x['a']} ↔ {x['b']} 重叠 {x['ow']}×{x['oh']}px")

        # --- 2. 工具栏 ---
        await scan("工具栏",PANELS[0][1],PANELS[0][2])
        # 段落条：真的切出 RUNS（小节号往回跳 = 新的一遍）
        await pg.evaluate("""()=>{M=[];E=[];
          for(let r=0;r<4;r++)for(let m=1;m<=4;m++){
            if(r===0)M.push({page:1,nx:.1+.11*m,ny:.3,m,h:.06});
            E.push({m,t:(r*4+m)*2,src:'tap'});}
          M.push({page:1,nx:.7,ny:.3,m:5,h:.06});syncNext();layout()}""")
        await pg.wait_for_timeout(400)
        n=await pg.evaluate("document.querySelectorAll('#chips .chip').length")
        print(ok(n>0), f"段落条切出 {n} 个 chip")
        await scan("段落 chips","#chips",".chip")

        # --- 3. 各浮层 ---
        await pg.evaluate("$('bMenu').onclick()"); await pg.wait_for_timeout(250)
        await scan("菜单",PANELS[1][1],PANELS[1][2])

        # 做成按钮样子的 <label>（导入JSON / 导入全部标注）必须跟相邻 <button> 齐平：
        # <button> 把内容纵向居中、<label> 不会，min-height 一撑到 44 基线就差 9px
        al=await pg.evaluate("""()=>{
          const pair=(a,b)=>{const x=document.querySelector(a).getBoundingClientRect(),
                                 y=document.querySelector(b).getBoundingClientRect();
            return {dt:Math.round(y.top-x.top),dh:Math.round(y.height-x.height),
                    disp:getComputedStyle(document.querySelector(b)).display}};
          return {exp:pair('#bExp','#menu .mbtn'), lib:pair('#libAdd','#libHd label.libBtn')};
        }""")
        # 容差 1px：button 和 label 是两套不同的盒模型，静态时实测完全重合，
        # 但布局刚变化时会读到 1px 的亚像素抖动。原来偏 9px，量级差在这里
        print(ok(abs(al["exp"]["dt"])<=1 and al["exp"]["dh"]==0),
              f"「导出JSON」与「导入JSON」齐平: top 差 {al['exp']['dt']}px / 高 差 {al['exp']['dh']}px"
              f"（label display={al['exp']['disp']}）")
        print(ok(abs(al["lib"]["dt"])<=1 and al["lib"]["dh"]==0),
              f"曲目库「导入全部标注」与相邻按钮齐平: top 差 {al['lib']['dt']}px / 高 差 {al['lib']['dh']}px")

        # 帮助 / 安装入口要在菜单一打开就在可视区里：手机上菜单内容远高于可视高度，
        # 塞在最后一栏等于要滚半屏才看得到
        rc=await pg.evaluate("""()=>{const m=$('menu'),mr=m.getBoundingClientRect(),
            r=$('bInstall').getBoundingClientRect();
          return {inView:r.top>=mr.top-1&&r.bottom<=mr.bottom+1,
                  top:Math.round(r.top),mb:Math.round(mr.bottom),
                  scrolls:m.scrollHeight>m.clientHeight+1}}""")
        print(ok(rc["inView"]),
              f"「安装到主屏幕」菜单一打开就可见: y={rc['top']} ≤ 菜单下沿 {rc['mb']}"
              + ("（菜单本身仍要滚动）" if rc["scrolls"] else ""))

        await pg.evaluate("$('menu').style.display='none';openGen()"); await pg.wait_for_timeout(350)
        # 锚点 chip 只在实测点 ≤12 个时逐个列出来；造 4 个 src='tap' 的点让 B 层规则真的被量到
        await pg.evaluate("""()=>{E=[{m:1,t:0,src:'tap'},{m:2,t:4,src:'tap'},
            {m:3,t:8,src:'tap'},{m:4,t:12,src:'tap'}];drawAnchors()}""")
        await pg.wait_for_timeout(250)
        await scan("生成面板",PANELS[4][1],PANELS[4][2])
        anc=await pg.evaluate("document.querySelectorAll('#gAncList .anc button').length")
        print(ok(anc>0), f"锚点 chip 渲染出 {anc} 个 × 按钮（B 层规则针对的就是它）")
        got=await pg.evaluate("""()=>{const b=document.querySelector('#gAncList .anc button');
            const h=window.__hit(b),r=b.getBoundingClientRect();
            const anc=b.closest('.anc').getBoundingClientRect();
            return {w:Math.round(h.r-h.l),h:Math.round(h.b-h.t),
                    vw:Math.round(r.width),vh:Math.round(r.height),
                    an:Math.round(anc.height)}}""")
        print(ok(got["w"]>=MIN and got["h"]>=MIN and abs(got["w"]-got["vw"])<=2),
              f"锚点 × ：命中 {got['w']}×{got['h']}px 没有靠 ::after 外扩（视觉 {got['vw']}×{got['vh']}，"
              f"胶囊整体 {got['an']}px 高）")
        await scan("生成面板·锚点 ×","#gAncList",".anc button")
        await pg.evaluate("$('gen').style.display='none'")

        await pg.evaluate("specShow(true)"); await pg.wait_for_timeout(400)
        await scan("频谱头",PANELS[5][1],PANELS[5][2])
        await pg.evaluate("specShow(false)")

        await pg.select_option("#mode","edit"); await pg.wait_for_timeout(200)
        await pg.evaluate("openPanel(1)"); await pg.wait_for_timeout(300)
        await scan("标记面板",PANELS[7][1],PANELS[7][2])
        await pg.evaluate("$('panel').style.display='none'")

        await pg.evaluate("$('plPop').style.display='block'"); await pg.wait_for_timeout(300)
        await scan("播放列表",PANELS[2][1],PANELS[2][2])
        await pg.evaluate("$('plPop').style.display='none'")

        await pg.evaluate("$('menu').style.display='block';$('bNewMode').onclick()")
        await pg.wait_for_timeout(350)
        await scan("对话框",PANELS[8][1],PANELS[8][2])
        await pg.evaluate("$('dlgCancel').onclick()"); await pg.wait_for_timeout(250)

        await pg.evaluate("$('instPop').style.display='flex'"); await pg.wait_for_timeout(250)
        await scan("安装卡片",PANELS[10][1],PANELS[10][2])
        await pg.evaluate("$('instPop').style.display='none'")
        # 菜单里点得开、卡片按浏览器分列、装过就不显示入口。
        # 直接写 display 而不是点 #bMenu —— 那是个开关，菜单开着时点它反而会关掉
        await pg.evaluate("$('menu').style.display='block'"); await pg.wait_for_timeout(200)
        print(ok(await pg.evaluate("$('bInstall').style.display!=='none'")),
              f"浏览器里显示「安装到主屏幕」入口（isStandalone={await pg.evaluate('isStandalone()')}）")
        await pg.click("#bInstall"); await pg.wait_for_timeout(250)
        itxt=await pg.evaluate("$('instPop').innerText")
        print(ok(await pg.evaluate("getComputedStyle($('instPop')).display")=="flex"), "点菜单入口能打开安装卡片")
        print(ok(await pg.evaluate("$('menu').style.display==='none'")), "打开卡片时菜单自动收起")
        print(ok("添加到主屏幕" in itxt and "重新添加" in itxt),
              "卡片按浏览器分列步骤，且提醒「改过图标要重新添加」")
        print(ok(await pg.evaluate("$('instGo').style.display==='none'")),
              "没有 beforeinstallprompt 时不显示「立即安装」")
        await pg.click("#instClose"); await pg.wait_for_timeout(200)
        print(ok(await pg.evaluate("getComputedStyle($('instPop')).display")=="none"), "关闭键能关安装卡片")
        await pg.evaluate("$('instPop').style.display='flex'"); await pg.wait_for_timeout(150)
        await pg.mouse.click(6,6); await pg.wait_for_timeout(200)
        print(ok(await pg.evaluate("getComputedStyle($('instPop')).display")=="none"), "点遮罩也能关安装卡片")

        # --- 4. 收起工具栏：▼ 和排练胶囊（这两个只在 hidebar 之后才在视口里） ---
        await pg.evaluate("setBarHidden(true)"); await pg.wait_for_timeout(350)
        await scan("展开工具栏 ▼","#barShow","")
        await scan("排练胶囊","#reh","button,select")
        tr=await pg.evaluate("""()=>{const t=document.querySelector('#reh .prog .track');
            const h=window.__hit(t),r=t.getBoundingClientRect();
            return {w:Math.round(h.r-h.l),h:Math.round(h.b-h.t),
                    vw:Math.round(r.width),vh:Math.round(r.height)}}""")
        print(ok(tr["h"]>=MIN and tr["vh"]<=10 and abs(tr["w"]-tr["vw"])<=2),
              f"进度条轨道：视觉 {tr['vw']}×{tr['vh']}px，命中 {tr['w']}×{tr['h']}px（≥44 高、视觉仍细）")
        await pg.evaluate("setBarHidden(false)"); await pg.wait_for_timeout(250)

        # --- 5. 曲目库 / ownCloud：走真实入口（?direct=1 会跳过整个库层，
        #        而 iPad 上的主用路径恰恰全在这里：同步、打开曲目、挂音频） ---
        await pg.close()                      # 库和 direct 模式互斥，单开一页
        pgl=await b.new_page(viewport={"width":834,"height":1194},has_touch=True,device_scale_factor=2)
        pgl.on("pageerror",lambda e:errs.append(str(e)))
        await pgl.goto("http://127.0.0.1:8821/player.html")
        await pgl.wait_for_function("()=>idb!==null",timeout=20000)
        await pgl.wait_for_function("()=>$('lib').style.display==='flex'",timeout=20000)
        await pgl.wait_for_timeout(400)
        await pgl.evaluate(JS)
        await scan("曲目库（空）",PANELS[3][1],PANELS[3][2],pgl)
        # 走真实用户路径：点「＋ 导入谱子」→ 选 PDF → 回库看卡片
        async with pgl.expect_file_chooser() as fc:
            await pgl.click("#libAdd")
        await (await fc.value).set_files(PDF)
        await pgl.wait_for_function("()=>document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=40000)
        await pgl.wait_for_timeout(600)
        await pgl.evaluate("$('bLib').onclick()"); await pgl.wait_for_timeout(800)
        cards=await pgl.evaluate("document.querySelectorAll('.libCard').length")
        print(ok(cards>0), f"曲目库里有 {cards} 张卡片（.libCard button 才有得量）")
        await scan("曲目库（有卡片）",PANELS[3][1],PANELS[3][2],pgl)
        # ownCloud 面板：库头部的 ☁ 进得去
        await pgl.evaluate("$('libDav').onclick()"); await pgl.wait_for_timeout(800)
        dv=await pgl.evaluate("getComputedStyle($('davPop')).display")
        print(ok(dv=="flex"), f"ownCloud 面板打开: display={dv}")
        await pgl.evaluate("$('davCfg').onclick()"); await pgl.wait_for_timeout(300)
        await scan("ownCloud",PANELS[6][1],PANELS[6][2],pgl)
        await pgl.close()

        # --- 6. 已经装成 PWA 时不再显示安装入口 ---
        # Chromium 的 CDP 能模拟 prefers-color-scheme，但模拟不了 display-mode，
        # 所以在页面脚本跑之前把 matchMedia 里跟 display-mode 有关的查询接管掉——
        # 这正是 iOS PWA 里系统会给出的答案，测的是 app 拿到这个答案之后的反应
        pgs=await b.new_page(viewport={"width":834,"height":1194},has_touch=True)
        pgs.on("pageerror",lambda e:errs.append(str(e)))
        # 注意这里是语句体，不是 ()=>{...}——add_init_script 是当脚本求值的，
        # 写成箭头函数表达式只会造个函数然后丢掉，什么也不做
        await pgs.add_init_script("""
          var raw = window.matchMedia.bind(window);
          window.matchMedia = function(q){
            return String(q).indexOf('display-mode')>=0
              ? {matches:true, media:String(q), onchange:null,
                 addEventListener:function(){}, removeEventListener:function(){},
                 addListener:function(){}, removeListener:function(){}}
              : raw(q);
          };
        """)
        await pgs.goto("http://127.0.0.1:8821/player.html?direct=1")
        await pgs.set_input_files("#fPdf",PDF)
        await pgs.wait_for_function("()=>document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=40000)
        await pgs.wait_for_timeout(300)
        st=await pgs.evaluate("""()=>({sa:isStandalone(),
            vis:getComputedStyle($('bInstall')).display!=='none',
            now:getComputedStyle($('instNow')).display!=='none',
            build:$('buildTag').textContent})""")
        print(ok(st["sa"]), f"浏览器报告 standalone 时 isStandalone()={st['sa']}")
        # 入口不藏：判"装没装"不可靠（有些 App 内置浏览器的 WebView 会报 standalone），
        # 藏错了用户就彻底找不到入口。改成常显 + 卡片里写一句状态
        print(ok(st["vis"]), "已装成 App 时入口仍然可见（不再自动隐藏）")
        print(ok(st["now"]==st["sa"]), f"卡片里的「已装过」提示跟着状态走: 显示={st['now']}")
        print(ok("构建" in st["build"]), f"菜单里有构建号可对版本: «{st['build']}»")
        # 点构建号 = 清缓存强制重载。手机上"更新不到新版本"时唯一的自救手段，
        # 所以它必须真的能点、真的绕过 HTTP 缓存（带一个没见过的 query）
        await pgs.evaluate("$('menu').style.display='block'"); await pgs.wait_for_timeout(200)
        await pgs.click("#buildTag")
        await pgs.wait_for_timeout(2500)
        after=pgs.url
        print(ok("_=" in after), f"点构建号能强制重载并绕过缓存: ...{after[-26:]}")
        print(ok(await pgs.evaluate("!!document.getElementById('buildTag')")),
              "重载后页面正常（构建号还在）")
        await pgs.close()

        # --- 7. 桌面回归：纯鼠标设备一个像素都不该动 ---
        pg2=await b.new_page(viewport={"width":1600,"height":900})
        pg2.on("pageerror",lambda e:errs.append(str(e)))
        await pg2.goto("http://127.0.0.1:8821/player.html?direct=1")
        await pg2.set_input_files("#fPdf",PDF)
        await pg2.wait_for_function("()=>document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=40000)
        await pg2.wait_for_timeout(300)
        mqd=await pg2.evaluate("""()=>({coarse:matchMedia('(pointer:coarse)').matches,
                                        any:matchMedia('(any-pointer:coarse)').matches})""")
        print(ok(not mqd["coarse"] and not mqd["any"]), f"桌面视口两个查询都不匹配: {mqd}")
        d=await pg2.evaluate("""()=>{
          const g=s=>{const e=document.querySelector(s);const r=e.getBoundingClientRect();
            return {w:Math.round(r.width),h:Math.round(r.height)}};
          const row=document.querySelector('#bar .row');
          return {bMenu:g('#bMenu'),bBar:g('#bBar'),bPlay:g('#bPlay'),
                  rowWrap:getComputedStyle(row).flexWrap,rowOx:getComputedStyle(row).overflowX,
                  chipWrap:getComputedStyle(document.querySelector('#chips')).flexWrap}}""")
        print(ok(d["bPlay"]["w"]==d["bPlay"]["h"]==40), f"桌面播放键仍是 40×40 正圆: {d['bPlay']['w']}×{d['bPlay']['h']}")
        print(ok(d["rowWrap"]=="wrap" and d["rowOx"]=="visible"),
              f"桌面工具栏仍然折行、不横滑: flex-wrap={d['rowWrap']} overflow-x={d['rowOx']}")
        print(ok(d["chipWrap"]=="wrap"), f"桌面段落条仍然折行铺开: flex-wrap={d['chipWrap']}")
        print(ok(d["bBar"]["h"]<44 and d["bMenu"]["h"]<44),
              f"桌面按钮保持紧凑密度: 收起键 {d['bBar']['h']}px / 菜单 {d['bMenu']['h']}px")
        # 桌面同样切出段落条，量一下 chip 没被触屏规则带大
        await pg2.evaluate("""()=>{M=[];E=[];
          for(let r=0;r<2;r++)for(let m=1;m<=4;m++){
            if(r===0)M.push({page:1,nx:.1+.11*m,ny:.3,m,h:.06});
            E.push({m,t:(r*4+m)*2,src:'tap'});}
          M.push({page:1,nx:.7,ny:.3,m:5,h:.06});syncNext();layout()}""")
        await pg2.wait_for_timeout(400)
        ch=await pg2.evaluate("""()=>{const c=document.querySelector('.chip');
            if(!c)return null;const r=c.getBoundingClientRect();
            return {h:Math.round(r.height),n:document.querySelectorAll('#chips .chip').length}}""")
        print(ok(ch and ch["h"]<44), f"桌面 chip 保持 28px 高: {ch['h'] if ch else '没有 chip'}px（{ch['n'] if ch else 0} 个）")

        # --- 手机：菜单内容远高于可视高度，帮助/安装必须在第一屏 ---
        pgm=await b.new_page(viewport={"width":390,"height":844},has_touch=True,device_scale_factor=2)
        pgm.on("pageerror",lambda e:errs.append(str(e)))
        await pgm.goto("http://127.0.0.1:8821/player.html?direct=1")
        await pgm.set_input_files("#fPdf",PDF)
        await pgm.wait_for_function("()=>document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=40000)
        await pgm.wait_for_timeout(300)
        await pgm.evaluate("$('bMenu').onclick()"); await pgm.wait_for_timeout(300)
        rm=await pgm.evaluate("""()=>{const m=$('menu'),mr=m.getBoundingClientRect();
          const chk=id=>{const r=$(id).getBoundingClientRect();
            return {inView:r.top>=mr.top-1&&r.bottom<=mr.bottom+1,top:Math.round(r.top)}};
          return {inst:chk('bInstall'),help:chk('bHelp'),mb:Math.round(mr.bottom),
                  needsScroll:m.scrollHeight>m.clientHeight+1,
                  scrollH:m.scrollHeight,clientH:m.clientHeight}}""")
        print(ok(rm["inst"]["inView"] and rm["help"]["inView"]),
              f"[手机] 帮助/安装都在菜单第一屏: 安装 y={rm['inst']['top']}、帮助 y={rm['help']['top']}"
              f" ≤ 下沿 {rm['mb']}（菜单内容 {rm['scrollH']} / 可视 {rm['clientH']}，本来就要滚）")
        await pgm.close()

        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
