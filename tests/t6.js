
let M=[],E=[],FORM=[];
let TEMPO=[{m:1,bpm:120}],METER=[{sig:[4,4],ranges:[]}];
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
function meterCoverage(hi){
  const owner=new Array(hi+1).fill(-1),dup=new Set();
  METER.forEach((r,i)=>{
    for(const g of r.ranges)
      for(let m=Math.max(1,g.from);m<=Math.min(hi,g.to);m++){
        if(owner[m]<0)owner[m]=i;else if(owner[m]!==i)dup.add(m);
      }
  });
  const fb=METER.filter(r=>!r.ranges.length).length;
  const gaps=[];
  if(!fb)for(let m=1;m<=hi;m++)if(owner[m]<0)gaps.push(m);
  return {owner,dup:[...dup].sort((a,b)=>a-b),gaps,fb};
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
function migrateSig(sig,hi){
  const s=[...(sig||[])].sort((a,b)=>a.m-b.m);
  const top=Math.max(hi||1,s.length?s[s.length-1].m:1);
  const T=[],by=new Map();
  s.forEach((x,i)=>{
    if(!T.length||T[T.length-1].bpm!==x.bpm)T.push({m:x.m,bpm:x.bpm});
    const to=i+1<s.length?s[i+1].m-1:top;
    if(to<x.m)return;
    const k=x.n+'/'+x.d;
    if(!by.has(k))by.set(k,{sig:[x.n,x.d],ranges:[]});
    by.get(k).ranges.push({from:x.m,to});
  });
  const ME=[...by.values()].map(r=>({sig:r.sig,ranges:normRanges(r.ranges)}));
  return {TEMPO:T.length?T:[{m:1,bpm:120}],METER:ME.length?ME:[{sig:[4,4],ranges:[]}]};
}
function migrateSeq(meter,hi){
  const s=[...(meter||[])].sort((a,b)=>a.m-b.m);
  const top=Math.max(hi||1,s.length?s[s.length-1].m:1),by=new Map();
  s.forEach((r,i)=>{
    const to=i+1<s.length?s[i+1].m-1:top,L=r.seq.length;
    if(!L)return;
    for(let m=r.m;m<=to;m++){
      const g=r.seq[(((m-r.m)%L)+L)%L],k=g[0]+'/'+g[1];
      if(!by.has(k))by.set(k,{sig:[g[0],g[1]],ranges:[]});
      by.get(k).ranges.push({from:m,to:m});
    }
  });
  const ME=[...by.values()].map(r=>({sig:r.sig,ranges:normRanges(r.ranges)}));
  return ME.length?ME:[{sig:[4,4],ranges:[]}];
}
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
  for(const a of taps){
    const k=seq.findIndex((s,i)=>i>=from&&s.m===a.m);
    if(k<0)continue;
    out.push({k,t:a.t});from=k+1;
  }
  return out;
}
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

  const rel=[];let acc=0;                                  // 相对时间轴（只管比例）
  for(const s of seq){rel.push(acc);acc+=measDur(s.m)}

  const taps=ignoreTaps?[]:E.filter(e=>e.src!=='gen').sort((a,b)=>a.t-b.t);
  let anc=matchAnchors(seq,taps),fromE=anc.length>0;
  if(!fromE){
    if(!manual)throw new Error('没有可用的锚点');
    const k=seq.findIndex(s=>s.m===manual.m);
    if(k<0)throw new Error('锚点小节 '+manual.m+' 不在播放顺序里');
    anc=[{k,t:manual.t}];
  }
  const mapT=k=>{
    if(anc.length===1)return anc[0].t+(rel[k]-rel[anc[0].k]);
    let i=0;while(i<anc.length-2&&k>=anc[i+1].k)i++;      // 首尾之外用最近一段的比例外推
    const A=anc[i],B=anc[i+1],dr=rel[B.k]-rel[A.k];
    return A.t+(rel[k]-rel[A.k])*(Math.abs(dr)>1e-9?(B.t-A.t)/dr:1);
  };
  const drop=fromE?new Set(anc.map(a=>a.k)):new Set();    // 锚点本身已经在 E 里，别生成重复的
  const gen=seq.map((s,k)=>({m:s.m,t:Math.max(0,mapT(k)),src:'gen',seg:s.seg}))
               .filter((_,k)=>!drop.has(k));
  return {E:[...taps,...gen],seq,anc,fromE,unmatched:taps.length-anc.length,
          span:[mapT(0),mapT(seq.length-1)]};
}
function eq(l,a,b){const A=JSON.stringify(a),B=JSON.stringify(b);
  console.log((A===B?'OK   ':'FAIL ')+l+(A===B?'':'\n   got '+A+'\n   exp '+B))}
const R=s=>normRanges(parseForm(s));
const at=ms=>ms.map(m=>sigText(meterAt(m)));

/* ===== 你截图那张表用新写法 ===== */
METER=[{sig:[6,8],ranges:R('1, 3, 5-25, 27')},
       {sig:[9,8],ranges:R('2, 4, 26, 28')}];
eq('2 行覆盖你原来 8 行', at([1,2,3,4,5,26,27,28]),
   ['6/8','9/8','6/8','9/8','6/8','9/8','6/8','9/8']);
eq('6-25 按你的原意保持 6/8', at([6,10,17,25]), ['6/8','6/8','6/8','6/8']);
eq('区间自动排序合并', formText(R('27, 5-20, 3, 21-25, 1')), '1, 3, 5-25, 27');
eq('相邻区间合并', formText(R('1-4, 5-8')), '1-8');
eq('重叠区间合并', formText(R('1-10, 5-8, 9-14')), '1-14');

/* ===== 兜底行 ===== */
METER=[{sig:[9,8],ranges:R('2, 4, 26, 28')},{sig:[6,8],ranges:[]}];
eq('留空行兜底', at([1,2,3,4,5,100]), ['6/8','9/8','6/8','9/8','6/8','6/8']);
eq('全部有拍号', [1,5,999].every(meterCovered), true);
METER=[{sig:[9,8],ranges:R('2,4')}];
eq('没有兜底 -> 未覆盖的小节报缺', [meterCovered(2),meterCovered(3)], [true,false]);

/* ===== 覆盖检查 ===== */
METER=[{sig:[6,8],ranges:R('1-10')},{sig:[9,8],ranges:R('8-12')}];
let c=meterCoverage(14);
eq('重叠小节被检出', c.dup, [8,9,10]);
eq('重叠时按最靠上那行', at([8,9,10]), ['6/8','6/8','6/8']);
eq('未覆盖小节被检出', c.gaps, [13,14]);
METER=[{sig:[6,8],ranges:R('1-10')},{sig:[9,8],ranges:[]}];
c=meterCoverage(14);
eq('有兜底就没有缺口', [c.gaps.length,c.fb], [0,1]);
METER=[{sig:[6,8],ranges:[]},{sig:[9,8],ranges:[]}];
eq('两个兜底行被检出', meterCoverage(5).fb, 2);

/* ===== 迁移：v3 单表 -> 区间表 ===== */
const OLD=[[1,6],[2,9],[3,6],[4,9],[5,6],[26,9],[27,6],[28,9]]
  .map(([m,n])=>({m,n,d:8,bpm:74.374}));
let g=migrateSig(OLD,28);
eq('v3 迁移 -> 速度 1 行', g.TEMPO, [{m:1,bpm:74.374}]);
eq('v3 迁移 -> 拍号 2 行', g.METER.map(r=>sigText(r.sig)+': '+formText(r.ranges)),
   ['6/8: 1, 3, 5-25, 27','9/8: 2, 4, 26, 28']);
TEMPO=g.TEMPO;METER=g.METER;
eq('迁移后逐小节结果与原表一致', at([1,2,3,4,5,6,17,25,26,27,28]),
   ['6/8','9/8','6/8','9/8','6/8','6/8','6/8','6/8','9/8','6/8','9/8']);

/* v4 短命格式 -> 区间表 */
eq('v4 循环序列迁移', migrateSeq([{m:1,seq:[[6,8],[9,8]]}],6)
     .map(r=>sigText(r.sig)+': '+formText(r.ranges)), ['6/8: 1, 3, 5','9/8: 2, 4, 6']);

/* ===== 时长 ===== */
TEMPO=[{m:1,bpm:74.374}];
METER=[{sig:[6,8],ranges:R('1, 3, 5-25, 27')},{sig:[9,8],ranges:R('2, 4, 26, 28')}];
console.log('     每小节:', measDur(1).toFixed(3)+'s (6/8) /', measDur(2).toFixed(3)+'s (9/8)');
eq('6/8 = 2.420s', +measDur(1).toFixed(3), 2.420);
eq('9/8 = 3.630s', +measDur(2).toFixed(3), 3.630);

/* ===== 解析错误 ===== */
for(const bad of ['','6-8','6/5','0/4','abc'])
  try{parseSig(bad);console.log('FAIL 应报错 '+JSON.stringify(bad))}
  catch(e){console.log('OK   拒绝拍号 '+JSON.stringify(bad))}
for(const bad of ['8-3','xyz'])
  try{parseForm(bad);console.log('FAIL 应报错 '+JSON.stringify(bad))}
  catch(e){console.log('OK   拒绝区间 '+JSON.stringify(bad))}

/* ===== 端到端生成 ===== */
M=Array.from({length:28},(_,i)=>({page:1,nx:0,ny:0,m:i+1}));
FORM=[];E=[];
const r=genTimeline({m:1,t:0});
const D6=6*0.5*(60/74.374),D9=9*0.5*(60/74.374);
eq('小节1-5 累加(6,9,6,9,6)', r.E.sort((a,b)=>a.m-b.m).slice(0,5).map(e=>+e.t.toFixed(4)),
   [0,D6,D6+D9,2*D6+D9,2*D6+2*D9].map(x=>+x.toFixed(4)));
eq('生成 28 个点', r.E.length, 28);

/* 缺拍号要挡住生成 */
METER=[{sig:[6,8],ranges:R('1-10')}];
try{genTimeline({m:1,t:0});console.log('FAIL 缺拍号应报错')}
catch(e){console.log('OK   缺拍号挡住生成: '+e.message.slice(0,50))}
METER=[{sig:[6,8],ranges:[]},{sig:[9,8],ranges:[]}];
try{genTimeline({m:1,t:0});console.log('FAIL 双兜底应报错')}
catch(e){console.log('OK   双兜底挡住生成: '+e.message)}
