
let M=[],E=[],OCC=[],RUNS=[],FORM=[],repeats=0;
let TEMPO=[{m:1,bpm:120}],METER=[{sig:[4,4],ranges:[]}];
const aud={currentTime:0,duration:189};
function measDurOf(n,d,bpm){return n*(4/d)*(60/bpm)}
function meterAt(m){
  let fb=null;
  for(const r of METER){
    if(!r.ranges.length){if(!fb)fb=r;continue}           // 留空的行 = 兜底
    for(const g of r.ranges)if(m>=g.from&&m<=g.to)return r.sig;
  }
  return fb?fb.sig:(METER[0]?METER[0].sig:[4,4]);
}
function meterCovered(m){
  for(const r of METER){
    if(!r.ranges.length)return true;
    for(const g of r.ranges)if(m>=g.from&&m<=g.to)return true;
  }
  return false;
}
function bpmAt(m){
  let r=null;
  for(const x of TEMPO)if(x.m<=m)r=x;else break;
  if(!r)r=TEMPO[0];
  return r&&r.bpm>0?r.bpm:120;
}
function measDur(m){const s=meterAt(m);return measDurOf(s[0],s[1],bpmAt(m))}
function minM(){return M.length?M.reduce((a,x)=>x.m<a?x.m:a,1/0):1}
function parseSig(s){
  const mm=String(s||'').trim().match(/^(\d+)\s*\/\s*(\d+)$/);
  if(!mm)throw new Error('看不懂拍号 "'+s+'"，应该写成 6/8');
  const n=+mm[1],d=+mm[2];
  if(!(n>0&&n<=64))throw new Error('拍数不合理："'+s+'"');
  if(![1,2,4,8,16,32].includes(d))throw new Error('分母只能是 1/2/4/8/16/32："'+s+'"');
  return [n,d];
}
function sigText(s){return s[0]+'/'+s[1]}
function normRanges(rs){                                  // 排序 + 合并相邻/重叠
  const a=[...rs].sort((x,y)=>x.from-y.from),out=[];
  for(const g of a){
    const l=out[out.length-1];
    if(l&&g.from<=l.to+1)l.to=Math.max(l.to,g.to);
    else out.push({from:g.from,to:g.to});
  }
  return out;
}
function rangeCount(rs){return rs.reduce((a,g)=>a+(g.to-g.from+1),0)}
function maxM(){return M.reduce((a,x)=>x.m>a?x.m:a,0)}
function parseForm(s){
  s=String(s||'').trim();
  if(!s)return [];
  return s.split(/[,，;；]+/).map(x=>x.trim()).filter(Boolean).map(p=>{
    const mm=p.match(/^(\d+)\s*(?:[-–—~～至到]\s*(\d+))?$/);
    if(!mm)throw new Error('看不懂 "'+p+'"，应该写成 1-8 或 12');
    const a=+mm[1],b=mm[2]?+mm[2]:a;
    if(b<a)throw new Error('"'+p+'" 的区间反了');
    return {from:a,to:b};
  });
}
function formText(f){return f.map(x=>x.from===x.to?String(x.from):x.from+'-'+x.to).join(', ')}
function expandForm(form){
  const seq=[];
  form.forEach((f,si)=>{for(let m=f.from;m<=f.to;m++)seq.push({m,seg:si})});
  return seq;
}
function matchAnchors(seq,taps){
  const out=[];let from=0;
  for(let ai=0;ai<taps.length;ai++){
    const a=taps[ai];
    const k=seq.findIndex((s,i)=>i>=from&&s.m===a.m);
    if(k<0)continue;
    out.push({k,t:a.t,ai});from=k+1;
  }
  return out;
}
function relTimeline(seq){                                // 相对时间轴（只管比例）
  const rel=[];let acc=0;
  for(const s of seq){rel.push(acc);acc+=measDur(s.m)}
  return rel;
}
function formOrAll(){return FORM.length?FORM:[{from:minM(),to:Math.max(minM(),maxM())}]}
function genTimeline(manual,ignoreTaps){
  if(!TEMPO.length)throw new Error('速度表是空的');
  if(!METER.length)throw new Error('拍号表是空的');
  for(const t of TEMPO)if(!(t.bpm>0))throw new Error('速度表里有非法 BPM');
  for(const r of METER)if(!(r.sig[0]>0&&r.sig[1]>0))throw new Error('拍号表里有非法拍号');
  if(METER.filter(r=>!r.ranges.length).length>1)throw new Error('只能有一行留空当兜底');
  TEMPO.sort((a,b)=>a.m-b.m);
  const form=FORM.length?FORM:[{from:minM(),to:Math.max(minM(),maxM())}];
  const seq=expandForm(form);
  if(!seq.length)throw new Error('播放顺序展开后是空的');
  if(seq.length>20000)throw new Error('小节数过多（'+seq.length+'），检查一下播放顺序');
  const nosig=[...new Set(seq.map(s=>s.m))].filter(m=>!meterCovered(m));
  if(nosig.length)throw new Error('这些小节没有指定拍号：'+nosig.slice(0,10).join(',')+
    (nosig.length>10?'…（共 '+nosig.length+' 个）':''));

  const rel=relTimeline(seq);
  const taps=ignoreTaps?[]:E.filter(e=>e.src!=='gen').sort((a,b)=>a.t-b.t);
  let anc=matchAnchors(seq,taps),fromE=anc.length>0;
  if(!fromE){
    if(!manual)throw new Error('没有可用的锚点');
    const k=seq.findIndex(s=>s.m===manual.m);
    if(k<0)throw new Error('锚点小节 '+manual.m+' 不在播放顺序里');
    anc=[{k,t:manual.t}];
  }
  const A0=anc[0],AZ=anc[anc.length-1];
  const gdr=anc.length>1?rel[AZ.k]-rel[A0.k]:0;
  const gs=(anc.length>1&&Math.abs(gdr)>1e-9)?(AZ.t-A0.t)/gdr:1;
  const scales=[];
  for(let i=0;i+1<anc.length;i++){
    const dr=rel[anc[i+1].k]-rel[anc[i].k];
    scales.push(Math.abs(dr)>1e-9?(anc[i+1].t-anc[i].t)/dr:null);
  }
  // 首尾之外用【首末锚点的全局比例】外推。原来拿相邻那一小段的比例外推，
  // 只要那一段短又不准（比如相邻两小节被打歪了），后面几十小节会被整体放大到离谱。
  const mapT=k=>{
    if(anc.length===1)return anc[0].t+(rel[k]-rel[anc[0].k]);
    if(k<=A0.k)return A0.t+(rel[k]-rel[A0.k])*gs;
    if(k>=AZ.k)return AZ.t+(rel[k]-rel[AZ.k])*gs;
    let i=0;while(i<anc.length-2&&k>=anc[i+1].k)i++;
    const A=anc[i],B=anc[i+1],dr=rel[B.k]-rel[A.k];
    return A.t+(rel[k]-rel[A.k])*(Math.abs(dr)>1e-9?(B.t-A.t)/dr:gs);
  };
  const drop=fromE?new Set(anc.map(a=>a.k)):new Set();    // 锚点本身已经在 E 里，别生成重复的
  // 保留的实测点要按【这一次】匹配到的位置重新定段号，否则上次生成留下的 seg
  // 会在段落条上劈出一个假的单小节段（就是 ② 小节 17–17 那种）
  const segOf=new Map(anc.map(a=>[a.ai,seq[a.k].seg]));
  const keptTaps=taps.map((tp,i)=>{
    const o={m:tp.m,t:tp.t,src:'tap'};
    if(segOf.has(i))o.seg=segOf.get(i);
    return o;
  });
  const gen=seq.map((s,k)=>({m:s.m,t:Math.max(0,mapT(k)),src:'gen',seg:s.seg}))
               .filter((_,k)=>!drop.has(k));
  return {E:[...keptTaps,...gen],seq,anc,fromE,scales,gs,
          unmatched:taps.length-anc.length,
          span:[mapT(0),mapT(seq.length-1)]};
}
function buildOcc(){
  OCC=[];repeats=0;
  const ev=[...E].sort((a,b)=>a.t-b.t);
  for(let i=0;i<ev.length;i++){
    OCC.push({m:ev[i].m,t:ev[i].t,exact:true,gen:ev[i].src==='gen',seg:ev[i].seg});
    if(i+1>=ev.length)continue;
    if(ev[i+1].m>ev[i].m){
      const A=ev[i],B=ev[i+1];
      for(let m=A.m+1;m<B.m;m++)
        OCC.push({m,t:A.t+(B.t-A.t)*(m-A.m)/(B.m-A.m),exact:false,gen:true,seg:A.seg});
    }else if(ev[i+1].m<ev[i].m)repeats++;
  }
  buildRuns();
}
function buildRuns(){
  RUNS=[];
  let lastSeg=null;
  for(let i=0;i<OCC.length;i++){
    const b=OCC[i];
    const bs=b.seg!=null?b.seg:lastSeg;                    // 没段号的野点跟随前一个点所在的段
    let split;
    if(i===0)split=true;
    else if(lastSeg!=null&&bs!=null)split=bs!==lastSeg;    // 声明过播放顺序就完全按它切，不再叠加启发式
    else split=b.m<=OCC[i-1].m;                            // 没声明才用"小节号不再前进 = 新的一遍"
    if(split)RUNS.push({t0:b.t,m0:b.m,m1:b.m});
    else{const r=RUNS[RUNS.length-1];
      if(b.m<r.m0)r.m0=b.m;if(b.m>r.m1)r.m1=b.m}          // 取 min/max，个别乱序点不会让标签变怪
    OCC[i].run=RUNS.length-1;lastSeg=bs;
  }
}
function occIndex(t){                     // OCC 按 t 递增，二分找最后一个 <= t
  let lo=0,hi=OCC.length-1,r=-1;
  while(lo<=hi){const mid=(lo+hi)>>1;if(OCC[mid].t<=t){r=mid;lo=mid+1}else hi=mid-1}
  return r;
}
function eq(l,a,b){const A=JSON.stringify(a),B=JSON.stringify(b);
  console.log((A===B?'OK   ':'FAIL ')+l+(A===B?'':'\n   got '+A+'\n   exp '+B))}
const f=s=>Math.floor(s/60)+':'+String(Math.floor(s%60)).padStart(2,'0');

/* ===== 复现你截图：FORM=1-32,1-32,33-42 ===== */
M=Array.from({length:42},(_,i)=>({page:1,nx:0,ny:0,m:i+1}));
FORM=parseForm('1-32, 1-32, 33-42');
METER=[{sig:[4,4],ranges:[]}]; TEMPO=[{m:1,bpm:120}];   // 每小节 2s，74 小节 = 148s
eq('播放顺序 3 段 74 小节', [FORM.length, expandForm(FORM).length], [3,74]);

/* --- 1) 陈旧 seg 造出假段落 --- */
E=[]; let r=genTimeline({m:1,t:0}); E=r.E; buildOcc();
eq('干净生成 -> 正好 3 段', RUNS.map(x=>x.m0+'-'+x.m1), ['1-32','1-32','33-42']);
// 模拟：修正过小节17（addTime 把 gen 变 tap 但留着旧 seg），然后改了播放顺序重新生成
const i17=E.findIndex(e=>e.m===17);
E[i17].src='tap'; E[i17].seg=2;                          // 上一次生成留下的陈旧段号
buildOcc();
eq('陈旧 seg 会劈出假段（修之前）', RUNS.length>3, true);
console.log('     修之前段落:', RUNS.map(x=>x.m0+'-'+x.m1).join(' | '));
r=genTimeline(null); E=r.E; buildOcc();
eq('重新生成后段号被重定 -> 回到 3 段', RUNS.map(x=>x.m0+'-'+x.m1), ['1-32','1-32','33-42']);
eq('保留的实测点段号正确', E.filter(e=>e.src==='tap').map(e=>e.seg), [0]);

/* --- 2) 外推放大 --- */
E=[{m:1,t:0,src:'tap'},{m:17,t:32,src:'tap'},{m:18,t:45,src:'tap'}];  // 17->18 打歪成 13 秒
r=genTimeline(null);
const last=Math.max(...r.E.map(e=>e.t));
console.log('     首末锚点全局比例 ×'+r.gs.toFixed(3), '| 各段比例', r.scales.map(s=>'×'+s.toFixed(2)).join(' '));
console.log('     生成总长', f(last), '（音频 '+f(aud.duration)+'）');
eq('不再被一小段坏比例放大到离谱', last < 200, true);
eq('坏段比例会被标出来', r.scales.some(s=>s<0.5||s>2), true);

/* --- 3) 段落条严格跟播放顺序走 --- */
E=[]; r=genTimeline({m:1,t:0}); E=r.E;
E.push({m:9,t:200,src:'tap'});                            // 塞一个乱序的野点
buildOcc();
eq('野点不再凭空多切段', RUNS.length, 3);

/* --- 4) 没有播放顺序时仍用启发式 --- */
FORM=[]; E=[{m:1,t:0},{m:8,t:14},{m:1,t:16},{m:8,t:26}];
buildOcc();
eq('无播放顺序 -> 启发式切 2 段', RUNS.map(x=>x.m0+'-'+x.m1), ['1-8','1-8']);
