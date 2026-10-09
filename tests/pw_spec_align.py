# 频谱上的声能必须落在它**真实响**的那一刻。
#
# 背景：谱图第 f 列是 [f*hop, f*hop+SP_N) 这段窗算出来的，能量重心在**窗中心**；按窗起点
# 摆放会让画出来的声能早半个窗（1024 样本 @11025Hz = 46.4ms，实测 46.8ms）。肉眼看就是
# 「谱图上的声音总在红色游标左边一点」。修法：画图时把源坐标减掉半窗的列数。
#
# 四条断言各盯一件事：
#   0. 起音刻度的时刻 = 真实点击（谱通量的峰只能定位到 93ms 宽的窗，时间戳取窗起点会早 63–85ms；
#      现在在窗内用时间域包络精修，检出哪几帧不变、只把时刻挪到真正的起音点）
#   1. 声能条纹的重心换算回时间 = 真实点击时刻（半窗没补就会偏早约 47ms）
#   2. 修图像不能把别的一起挪了：E 竖线仍按真实时刻画（把偏移误加进 X() 是最容易犯的错）
#   3. 端到端：声能条纹与 E 竖线同一列——「谱图里的声音」和「谱面上的竖线」同一时刻
#
# 夹具：自制点击轨（10 个点击，严格每 0.5s 一个）+ 与之对齐的 10 根竖线。点击时刻是已知真值，
# 所以偏移是量出来的，不是对实现的复述。
#
# 量声能条纹那两步（1、3）要先把「起音刻度」关掉：它那条极淡的通天线也是一条竖直的亮线，
# 会在旁边竖出一道假条纹把重心拉偏。断言 0 读的是 SPEC.onsets，与画不画无关，不受影响。
import asyncio, http.server, socketserver, threading, functools, wave, struct, math
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
PDF=ROOT+"/线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf"
WAV="/tmp/spec_align_click.wav"
CLICKS=[0.5*i for i in range(1,11)]

def click_wav(path,times,dur=6.0,sr=44100):
    n=int(dur*sr); buf=[0.0]*n
    for t in times:
        i0=int(round(t*sr))
        for k in range(int(0.03*sr)):
            i=i0+k
            if 0<=i<n: buf[i]+=0.92*math.exp(-k/(0.004*sr))*math.sin(2*math.pi*1500*k/sr)
    with wave.open(path,'w') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(b''.join(struct.pack('<h',int(max(-1,min(1,v))*32767)) for v in buf))
click_wav(WAV,CLICKS)

class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*a): pass
H=functools.partial(Quiet,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8855),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
def ok(c): return "OK   " if c else "FAIL "

# 亮度剖面 → 连通段 → 重心。阈值取背景中位数的 1.5 倍（不取局部均值：条纹自己很宽，
# 局部均值会被它自己抬起来，于是宽的条纹被从中间切成两段——上一版就栽在这）
PROFILE="""(skip)=>{
  const cv=$('specCv'),ctx=cv.getContext('2d'),W=cv.clientWidth,H=cv.clientHeight;
  const y0=Math.round(H*0.15),y1=H-40,n=y1-y0;   // 上避标签、下避秒刻度/起音竖条
  const d=ctx.getImageData(0,y0,W,n).data;
  const prof=new Float32Array(W);
  for(let y=0;y<n;y++)for(let x=0;x<W;x++){const i=(y*W+x)*4;prof[x]+=d[i]+d[i+1]+d[i+2]}
  // 红色播放头自己也是一条通天的亮线，排掉；skip 里的列同理（找声能时要排掉 E 竖线）
  for(const s of [Math.round(W/2)].concat(skip||[]))
    for(let x=Math.max(0,s-2);x<=Math.min(W-1,s+2);x++)prof[x]=0;
  const srt=Float32Array.from(prof).sort();const bg=srt[Math.floor(W*0.7)];
  const th=bg*1.5,out=[];
  let run=null;
  for(let x=0;x<W;x++){
    if(prof[x]>th){const o=Math.max(0,x-1);
      if(run&&o-run.x1<=3){run.x1=x}else{if(run)out.push(run);run={x0:x,x1:x}}}
  }
  if(run)out.push(run);
  const res=out.filter(r=>r.x1-r.x0+1<=30).map(r=>{
    let sw=0,sx=0;
    for(let x=r.x0;x<=r.x1;x++){const w=prof[x]-bg;sw+=w;sx+=x*w}
    return {x:+(sx/sw).toFixed(2),wpx:r.x1-r.x0+1,x0:r.x0,x1:r.x1};
  }).filter(r=>r.wpx>=2);
  return {W:W,pps:specPPS,ct:aud.currentTime,t0:aud.currentTime-(W/2)/specPPS,bg:Math.round(bg),
          stripes:res.map(r=>r.x),widths:res.map(r=>r.wpx),
          spans:res.map(r=>[r.x0,r.x1])};
}"""
YELLOW="""()=>{
  const cv=$('specCv'),ctx=cv.getContext('2d'),W=cv.clientWidth,H=cv.clientHeight;
  const d=ctx.getImageData(0,Math.round(H*0.5),W,1).data;const out=[];
  for(let x=0;x<W;x++){const i=x*4;if(d[i]>225&&d[i+1]>180&&d[i+1]<235&&d[i+2]<110)out.push(x)}
  return out}"""

async def measure(pg):
    await pg.evaluate("()=>{aud.currentTime=2.75}")
    await pg.wait_for_timeout(400)
    await pg.evaluate("()=>{specDirty=true;drawSpec()}")
    return await pg.evaluate(PROFILE,None)

async def main():
    errs=[]
    async with async_playwright() as p:
        b=await p.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"])
        pg=await b.new_page(viewport={"width":1400,"height":950})
        pg.on("pageerror",lambda e:errs.append(str(e)))
        await pg.goto("http://127.0.0.1:8855/player.html")
        await pg.wait_for_function("()=>idb!==null&&$('lib').style.display==='flex'",timeout=10000)
        await pg.set_input_files("#fPdf",PDF)
        await pg.wait_for_function("()=>document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=30000)
        await pg.set_input_files("#fAud",WAV)
        await pg.wait_for_function("()=>$('dlgMode').style.display==='flex'",timeout=5000)
        await pg.click("#dlgModeOk")
        await pg.wait_for_function("()=>SPEC!==null",timeout=90000)
        print(ok(await pg.evaluate("()=>SPEC.onsets.length")==10),
              "夹具：音频里检出 10 个起音（真值 10 个点击）")
        # --- 0. 起音刻度的时刻 ---
        ons=await pg.evaluate("()=>[...SPEC.onsets]")
        o0=[(o-c)*1000 for o,c in zip(ons,CLICKS)]
        print(ok(len(ons)==10 and max(abs(v) for v in o0)<=15),
              "0. 起音刻度的时刻 = 真实点击（±15ms）：平均 %+.1f ms，最大 |偏移| %.1f ms（时间戳取窗起点时是 -63…-85ms）"%(
                 sum(o0)/len(o0) if o0 else 0,max(abs(v) for v in o0) if o0 else -1))
        pid=await pg.evaluate("pid")
        await pg.evaluate("()=>{$('bSpec').onclick()}")
        await pg.wait_for_function("()=>specOn()&&$('specCv').clientWidth>0",timeout=5000)
        await pg.evaluate("()=>{$('chkOnset').checked=false}")     # 见文件头：淡引导线是另一个问题

        # --- 1. 声能条纹 vs 真实点击时刻 ---
        m=await measure(pg)
        st=[m["t0"]+x/m["pps"] for x in m["stripes"]]
        st=[s for s in st if min(abs(s-c) for c in CLICKS)<0.3]     # 只留下点击附近的
        off=[(s-min(CLICKS,key=lambda c:abs(c-s)))*1000 for s in st]
        print("     ct=%.3f s，条纹重心：%s"%(m["ct"],[round(s,3) for s in st]))
        print(ok(len(off)==10 and abs(sum(off)/len(off))<=20 and max(abs(o) for o in off)<=25),
              "1. 声能条纹落在真实点击上：%d/10 条，重心平均 %+.1f ms，最大 |偏移| %.1f ms（未补半窗时约 -47 ms）"%(
                 len(off),sum(off)/len(off) if off else 0,max(abs(o) for o in off) if off else -1))

        # 写一组与点击对齐的竖线，刷新重开（顺带验重开面板后仍然对）
        await pg.evaluate("""(pid)=>{const M=[],E=[];
          for(let k=1;k<=10;k++){M.push({page:1,nx:+(0.05+0.09*(k-1)).toFixed(4),ny:0.35,m:k,h:0.32});
            E.push({m:k,t:0.5*k,src:'tap',seg:0});}
          return idbPut(idb,'marks',{pid:pid,data:{v:6,M:M,
            modes:{'标准':{E:E,TEMPO:[{m:1,bpm:120}],METER:[{sig:[4,4],ranges:[]}],FORM:[],offset:0}},
            activeMode:'标准',ts:Date.now()}})}""",pid)
        await pg.reload()
        await pg.wait_for_function("()=>idb!==null&&$('lib').style.display==='flex'",timeout=10000)
        await pg.wait_for_timeout(400)
        await pg.click(".libCard button.open")
        await pg.wait_for_function("()=>document.querySelectorAll('.mk').length===10",timeout=30000)
        await pg.wait_for_function("()=>SPEC!==null",timeout=20000)
        await pg.evaluate("()=>{$('bSpec').onclick();$('chkOnset').checked=false}")
        await pg.wait_for_function("()=>specOn()",timeout=5000)
        m2=await measure(pg)
        yel=await pg.evaluate(YELLOW)
        W,pps,ct=m2["W"],m2["pps"],m2["ct"]
        t0=ct-(W/2)/pps
        # --- 2. E 竖线仍是真实时刻（图像偏移不能漏进 X()）---
        # 正好落在红色游标上的那根会被盖住，排掉
        pred=[round((c-ct)*pps+W/2) for c in CLICKS
              if 0<=(c-ct)*pps+W/2<W and abs(round((c-ct)*pps+W/2)-W/2)>3]
        hit=[min([abs(y-p) for y in yel]) for p in pred]
        print(ok(yel and hit and max(hit)<=2),
              "2. E 竖线的像素列仍按真实时刻：%d 根，最大偏差 %d px（时间→像素的映射没被带偏）"%(
                 len(hit),max(hit) if hit else -1))
        # --- 3. 声能条纹应当**左右对称地裹住** E 竖线（谱图的「声音」与谱面的「竖线」同一时刻）---
        # 不比重心：竖线本身又亮又宽，压在条纹中心，比重心等于在比竖线自己。比左右边界：
        # 补半窗之后声能是围绕真实时刻对称展开的，没补的话整条都落在竖线左边
        off3=[]
        for c in CLICKS:
            xl=(c-t0)*pps
            if not (15<xl<W-15): continue
            seg=[sp for sp in m2["spans"] if sp[0]-2<=xl<=sp[1]+2]
            if not seg: continue
            x0=min(sp[0] for sp in seg);x1=max(sp[1] for sp in seg)
            if not (x1-x0+1<=40): continue
            off3.append(((x0+x1)/2-xl))
        print(ok(len(off3)>=9 and max(abs(v) for v in off3)<=4),
              "3. 声能条纹裹住 E 竖线：%d 根，条纹中点与竖线差 ≤%.1f px（%.1f ms/px；未补半窗时整条偏在左边）"%(
                 len(off3),max(abs(v) for v in off3) if off3 else -1,1000/pps))
        print("     背景亮度 %s（剖面基线），条纹宽 %s px"%(m2["bg"],m2["widths"][:6]))
        print("\npage errors:",errs or "(none)")
        await b.close()
asyncio.run(main())
