import asyncio, http.server, socketserver, threading, functools, statistics
from playwright.async_api import async_playwright
ROOT="/home/xiaoyuanzhu/my-life-db/data/assets"
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=ROOT+"/SheetPlayer")
socketserver.TCPServer.allow_reuse_address=True
srv=socketserver.TCPServer(("127.0.0.1",8753),H); threading.Thread(target=srv.serve_forever,daemon=True).start()

# 找出"高置信度"小节线：同一系统里两个相邻谱表都出现的位置
TRUTH = r"""
()=>{
  const c=cvs[1],W=c.width,Hh=c.height;
  const d=c.getContext('2d',{willReadFrequently:true}).getImageData(0,0,W,Hh).data;
  const lum=(x,y)=>{const p=(y*W+x)*4;return d[p]*.299+d[p+1]*.587+d[p+2]*.114};
  const rf=[];for(let y=0;y<Hh;y++){let n=0;for(let x=0;x<W;x++)if(lum(x,y)<140)n++;rf.push(n/W)}
  const ls=[];for(let y=0;y<Hh;y++)if(rf[y]>0.35)ls.push(y);
  const mg=[];for(const y of ls){const l=mg[mg.length-1];if(l&&y-l[l.length-1]<=2)l.push(y);else mg.push([y])}
  const ct=mg.map(g=>Math.round(g.reduce((a,b)=>a+b)/g.length));
  const st=[];for(let i=0;i+4<ct.length;){const g=ct.slice(i,i+5),sp=(g[4]-g[0])/4;
    if(g.every((v,k)=>k===0||Math.abs(v-g[k-1]-sp)<=2.5)){st.push({top:g[0],bot:g[4]});i+=5}else i++}
  const cols=s=>{const y0=s.top,y1=s.bot,hh=y1-y0+1,out=[];
    for(let x=1;x<W-1;x++){let n=0;
      for(let y=y0;y<=y1;y++){let dk=false;
        for(let k=x-1;k<=x+1;k++)if(lum(k,y)<175){dk=true;break}
        if(dk)n++}
      if(n/hh>=0.95)out.push(x)}
    return out};
  const res=[];
  for(let i=0;i+1<st.length;i+=2){                 // 相邻两个谱表当作同一系统
    if(st[i+1].top-st[i].bot>90)continue;
    const a=cols(st[i]),b=new Set(cols(st[i+1]));
    const both=a.filter(x=>b.has(x)||b.has(x-1)||b.has(x+1));
    const ded=[];for(const x of both)if(!ded.length||x-ded[ded.length-1]>5)ded.push(x);
    if(ded.length>=3)res.push({top:st[i].top,bot:st[i+1].bot,xs:ded});
  }
  return {W,Hh,systems:res};
}
"""
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={"width":1400,"height":900})
        await pg.goto("http://127.0.0.1:8753/player.html")
        import os
        WIN=int(os.environ.get("WIN","20"))
        grand=[]
        for name in ["SK_斯卡布罗集市[线][TTBB+NA+WO].pdf","DN_等你到天明[线][TTBB+NA+NA]_修改.pdf",
                     "BW_不忘初心[线][SATB+NA+Pn].pdf","WH_我和我的祖国[线][SATB+NA+Pn].pdf"]:
            await pg.evaluate("localStorage.clear()"); await pg.reload()
            await pg.set_input_files("#fPdf",ROOT+"/线谱合集/"+name)
            await pg.wait_for_function("()=>cvs[1]&&document.querySelector('.page[data-page=\"1\"]')?.dataset.done",timeout=40000)
            T=await pg.evaluate(TRUTH)
            W,Hh=T["W"],T["Hh"]
            byoff={}
            onreal=nearest=miss=bogus=0
            for sysi,sysm in enumerate(T["systems"][:6]):
                ny=sysm["top"]/Hh; h=(sysm["bot"]-sysm["top"])/Hh
                truth=sysm["xs"]
                for x in truth:
                    for off in [round(f*WIN) for f in (-0.9,-0.6,-0.3,0.3,0.6,0.9)]:
                        drop=x+off
                        got=await pg.evaluate("""([nx,ny,h,win])=>{
                            const mk={page:1,nx,ny,h};const r=snapBarX(mk,win);
                            return r==null?null:r*cvs[1].width}""",[drop/W,ny,h,WIN])
                        k=abs(off); byoff.setdefault(k,[0,0])
                        if got is None: miss+=1; continue
                        real = min(abs(got-t) for t in truth)<=3          # 落在某条真小节线上
                        near = min(truth,key=lambda t:abs(t-drop))        # 离落点最近的真小节线
                        if real:
                            onreal+=1; byoff[k][1]+=1
                            if abs(got-near)<=3: nearest+=1; byoff[k][0]+=1
                        else: bogus+=1
            tot=onreal+miss+bogus
            print(f"  {name.split('[')[0]:12} 系统 {len(T['systems'][:6])} 个, 基准小节线 {sum(len(s['xs']) for s in T['systems'][:6])} 条")
            print(f"               落在真小节线上 {onreal}/{tot} ({onreal/tot*100:.0f}%) · 其中就是最近那条 {nearest} ({nearest/tot*100:.0f}%) · 吸到非小节线 {bogus} ({bogus/tot*100:.0f}%)")
            print("             按放偏距离: "+" ".join(f"±{k}px {v[0]*100//max(1,sum(1 for _ in range(v[1]) )+0) if False else round(v[0]/max(1,(tot//3))*100)}%" for k in [] ))
            grand.append((onreal,nearest,miss,bogus))
        o=sum(g[0] for g in grand);n=sum(g[1] for g in grand);m=sum(g[2] for g in grand);bg=sum(g[3] for g in grand)
        t=o+m+bg
        print(f"\n合计 {t} 次: 落在真小节线 {o} ({o/t*100:.0f}%) · 其中最近那条 {n} ({n/t*100:.0f}%) · 吸到非小节线 {bg} ({bg/t*100:.0f}%) · 没吸 {m}")
        await b.close()
asyncio.run(main())
