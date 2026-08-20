
let M=[],E=[],OCC=[],RUNS=[],repeats=0;
let SIG=[{m:1,n:4,d:4,bpm:120}],FORM=[];
function measDurOf(s){return s.n*(4/s.d)*(60/s.bpm)}
function sigAt(m){let r=SIG[0];for(const s of SIG)if(s.m<=m)r=s;else break;return r}
function measDur(m){return measDurOf(sigAt(m))}
function minM(){return M.length?M.reduce((a,x)=>x.m<a?x.m:a,1/0):1}
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
  if(!SIG.length)throw new Error('速度表是空的');
  for(const s of SIG)if(!(s.n>0&&s.d>0&&s.bpm>0))throw new Error('速度表里有非法数值');
  SIG.sort((a,b)=>a.m-b.m);
  const form=FORM.length?FORM:[{from:minM(),to:Math.max(minM(),maxM())}];
  const seq=expandForm(form);
  if(!seq.length)throw new Error('播放顺序展开后是空的');
  if(seq.length>20000)throw new Error('小节数过多（'+seq.length+'），检查一下播放顺序');

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
function calibrate(){
  const taps=E.filter(e=>e.src!=='gen').sort((a,b)=>a.t-b.t);
  if(taps.length<2)throw new Error('至少要有 2 个实测时间点才能反推');
  const form=FORM.length?FORM:[{from:minM(),to:Math.max(minM(),maxM())}];
  const seq=expandForm(form),anc=matchAnchors(seq,taps);
  if(anc.length<2)throw new Error('实测点对不上播放顺序');
  const rel=[];let acc=0;
  for(const s of seq){rel.push(acc);acc+=measDur(s.m)}
  const A=anc[0],B=anc[anc.length-1],dr=rel[B.k]-rel[A.k];
  if(Math.abs(dr)<1e-9)throw new Error('两个锚点之间没有跨度');
  const scale=(B.t-A.t)/dr;                               // 实际用时 / 按当前速度表预测用时
  if(!(scale>0.1&&scale<10))throw new Error('反推结果离谱（×'+scale.toFixed(2)+'），检查拍号或锚点');
  SIG.forEach(s=>s.bpm=+(s.bpm/scale).toFixed(3));         // 时长 ∝ 1/BPM
  return {scale,span:[A,B]};
}
function maxM(){return M.reduce((a,x)=>x.m>a?x.m:a,0)}
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
  for(let i=0;i<OCC.length;i++){
    const a=OCC[i-1],b=OCC[i];
    // 有显式播放顺序就按声明的段切；没有就退回启发式（小节号不再前进 = 新的一遍）
    const segSplit=a&&a.seg!=null&&b.seg!=null&&a.seg!==b.seg;
    if(i===0||segSplit||b.m<=a.m)RUNS.push({t0:b.t,m0:b.m,m1:b.m});
    else RUNS[RUNS.length-1].m1=b.m;
    OCC[i].run=RUNS.length-1;
  }
}
function occIndex(t){                     // OCC 按 t 递增，二分找最后一个 <= t
  let lo=0,hi=OCC.length-1,r=-1;
  while(lo<=hi){const mid=(lo+hi)>>1;if(OCC[mid].t<=t){r=mid;lo=mid+1}else hi=mid-1}
  return r;
}
function eq(l,a,b){const A=JSON.stringify(a),B=JSON.stringify(b);
  console.log((A===B?'OK   ':'FAIL ')+l+(A===B?'':'\n   got '+A+'\n   exp '+B))}
function close(l,a,b,tol){const c=Math.abs(a-b)<=(tol||1e-9);
  console.log((c?'OK   ':'FAIL ')+l+(c?'':'  got '+a+' exp '+b))}

/* ---- 每小节时长公式 ---- */
close('3/4 ♩=120 -> 1.5s',      measDurOf({n:3,d:4,bpm:120}), 1.5);
close('4/4 ♩=96  -> 2.5s',      measDurOf({n:4,d:4,bpm:96}),  2.5);
close('6/8 ♩.=52(=♩78) -> 2.3077s', measDurOf({n:6,d:8,bpm:78}), 6*(60/78)/2, 1e-9);
close('2/2 ♩=120 -> 2.0s',      measDurOf({n:2,d:2,bpm:120}),  2.0);

/* ---- 播放顺序解析 ---- */
eq('解析 1-8, 3-8, 9-12', parseForm('1-8, 3-8, 9-12'), [{from:1,to:8},{from:3,to:8},{from:9,to:12}]);
eq('中文逗号/破折号/单小节', parseForm('1–4，7；9'), [{from:1,to:4},{from:7,to:7},{from:9,to:9}]);
eq('空串 -> 空', parseForm('  '), []);
try{parseForm('8-3');console.log('FAIL 区间反了应该报错')}catch(e){console.log('OK   区间反了报错: '+e.message)}
try{parseForm('abc');console.log('FAIL 乱输应该报错')}catch(e){console.log('OK   乱输报错: '+e.message)}
eq('往返', formText(parseForm('1-8,3-8,12')), '1-8, 3-8, 12');
eq('展开带段号', expandForm([{from:1,to:3},{from:2,to:3}]).map(s=>s.m+'/'+s.seg),
   ['1/0','2/0','3/0','2/1','3/1']);

/* ---- 匀速无重复：单锚点 ---- */
M=Array.from({length:40},(_,i)=>({page:1,nx:0,ny:0,m:i+1}));
SIG=[{m:1,n:3,d:4,bpm:120}]; FORM=[]; E=[];
let r=genTimeline({m:1,t:0});
eq('生成 40 个点', r.E.length, 40);
close('小节 1  -> 0.0',  r.E.find(e=>e.m===1).t, 0);
close('小节 5  -> 6.0',  r.E.find(e=>e.m===5).t, 6.0);
close('小节 40 -> 58.5', r.E.find(e=>e.m===40).t, 58.5);
eq('全是 gen', r.E.every(e=>e.src==='gen'), true);

/* 锚点不在 0：整条轴平移 */
r=genTimeline({m:1,t:0.42});
close('锚点 0.42 -> 小节40 = 58.92', r.E.find(e=>e.m===40).t, 58.92, 1e-9);
/* 锚点挂在中间某小节 */
r=genTimeline({m:20,t:30});
close('锚点在小节20=30s -> 小节1 = 1.5', r.E.find(e=>e.m===1).t, 30-19*1.5, 1e-9);

/* ---- 变速：速度表分段 ---- */
SIG=[{m:1,n:3,d:4,bpm:120},{m:11,n:4,d:4,bpm:60}];   // 1-10 每小节1.5s，11起每小节4s
r=genTimeline({m:1,t:0});
close('变速前 小节11 = 15.0', r.E.find(e=>e.m===11).t, 15.0);
close('变速后 小节13 = 23.0', r.E.find(e=>e.m===13).t, 15+2*4);
eq('sigAt 边界', [sigAt(10).bpm, sigAt(11).bpm], [120,60]);

/* ---- 弱起：第1小节只有1拍 ---- */
SIG=[{m:1,n:1,d:4,bpm:120},{m:2,n:3,d:4,bpm:120}];
r=genTimeline({m:1,t:0});
close('弱起 小节2 = 0.5s', r.E.find(e=>e.m===2).t, 0.5);
close('弱起 小节3 = 2.0s', r.E.find(e=>e.m===3).t, 2.0);

/* ---- 反复：播放顺序展开 ---- */
SIG=[{m:1,n:3,d:4,bpm:120}]; FORM=parseForm('1-8, 3-8, 9-12'); E=[];
r=genTimeline({m:1,t:0});
eq('展开 8+6+4 = 18 个点', r.E.length, 18);
const t=m=>r.E.filter(e=>e.m===m).map(e=>+e.t.toFixed(3));
eq('小节3 出现两次', t(3), [3, 12]);      // 第一遍 t=3；第二遍 8*1.5=12
eq('小节9 只出现一次', t(9), [21]);        // 12+6*1.5=21
eq('段号 0/1/2 都在', [...new Set(r.E.map(e=>e.seg))].sort(), [0,1,2]);
E=r.E; buildOcc();
eq('段落条按声明切成 3 段', RUNS.map(x=>x.m0+'-'+x.m1), ['1-8','3-8','9-12']);

/* ---- 硬锚点拉伸校正 ---- */
FORM=[]; SIG=[{m:1,n:3,d:4,bpm:120}];
E=[{m:1,t:0,src:'tap'},{m:40,t:60,src:'tap'}];   // 实际 60s，速度表预测 58.5s
r=genTimeline(null);
eq('2 个锚点', r.anc.length, 2);
close('锚点处精确对齐 小节1', r.E.find(e=>e.m===1).t, 0);
close('锚点处精确对齐 小节40', r.E.find(e=>e.m===40).t, 60);
close('中间按比例拉伸 小节20 = 60*19/39', r.E.find(e=>e.m===20).t, 60*19/39, 1e-9);
eq('锚点保留为 tap，不被 gen 覆盖', r.E.filter(e=>e.src!=='gen').length, 2);
eq('锚点小节不重复生成', r.E.filter(e=>e.m===40).length, 1);

/* 中间加一个手改的点 -> 分段拉伸，rit. 场景 */
E=[{m:1,t:0,src:'tap'},{m:20,t:30,src:'tap'},{m:40,t:70,src:'tap'}];
r=genTimeline(null);
close('第一段比例 小节10 = 30*9/19', r.E.find(e=>e.m===10).t, 30*9/19, 1e-9);
close('第二段比例(变慢) 小节30 = 30+40*10/20', r.E.find(e=>e.m===30).t, 30+40*10/20, 1e-9);

/* ignoreTaps 丢弃实测点 */
r=genTimeline({m:1,t:5},true);
eq('ignoreTaps 后没有 tap 点', r.E.filter(e=>e.src!=='gen').length, 0);
close('ignoreTaps 用手动锚点', r.E.find(e=>e.m===1).t, 5);

/* ---- 反推 BPM ---- */
E=[{m:1,t:0,src:'tap'},{m:40,t:60,src:'tap'}];
SIG=[{m:1,n:3,d:4,bpm:120}]; FORM=[];
const c=calibrate();
close('反推 scale = 60/58.5', c.scale, 60/58.5, 1e-9);
close('反推 BPM = 120*58.5/60 = 117', SIG[0].bpm, 117, 0.001);
E=[{m:1,t:0,src:'tap'}];
try{calibrate();console.log('FAIL 单锚点应该报错')}catch(e){console.log('OK   单锚点报错: '+e.message)}

/* ---- 边界 ---- */
SIG=[{m:1,n:3,d:4,bpm:120}];E=[];FORM=[];
try{genTimeline(null);console.log('FAIL 无锚点应该报错')}catch(e){console.log('OK   无锚点报错: '+e.message)}
try{genTimeline({m:999,t:0});console.log('FAIL 锚点越界应该报错')}catch(e){console.log('OK   锚点不在顺序里报错: '+e.message)}
SIG=[{m:1,n:3,d:0,bpm:120}];
try{genTimeline({m:1,t:0});console.log('FAIL 非法拍号应该报错')}catch(e){console.log('OK   非法数值报错: '+e.message)}
