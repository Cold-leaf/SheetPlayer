
let E=[],OCC=[],RUNS=[],repeats=0,loop={a:null,b:null,on:false};
const aud={currentTime:0,duration:200};
function buildOcc(){
  OCC=[];repeats=0;
  const ev=[...E].sort((a,b)=>a.t-b.t);
  for(let i=0;i<ev.length;i++){
    OCC.push({m:ev[i].m,t:ev[i].t,exact:true});
    if(i+1>=ev.length)continue;
    if(ev[i+1].m>ev[i].m){
      const A=ev[i],B=ev[i+1];
      for(let m=A.m+1;m<B.m;m++)OCC.push({m,t:A.t+(B.t-A.t)*(m-A.m)/(B.m-A.m),exact:false});
    }else if(ev[i+1].m<ev[i].m)repeats++;
  }
  buildRuns();
}
function buildRuns(){
  RUNS=[];
  for(let i=0;i<OCC.length;i++){
    if(i===0||OCC[i].m<=OCC[i-1].m)RUNS.push({t0:OCC[i].t,m0:OCC[i].m,m1:OCC[i].m});
    else{const r=RUNS[RUNS.length-1];r.m1=OCC[i].m}
    OCC[i].run=RUNS.length-1;
  }
}
function occIndex(t){                     // OCC 按 t 递增，二分找最后一个 <= t
  let lo=0,hi=OCC.length-1,r=-1;
  while(lo<=hi){const mid=(lo+hi)>>1;if(OCC[mid].t<=t){r=mid;lo=mid+1}else hi=mid-1}
  return r;
}
function runAt(t){const i=occIndex(t);return i<0?-1:OCC[i].run}
function pickOcc(m){
  const c=OCC.filter(o=>o.m===m);
  if(!c.length)return null;
  const r=runAt(aud.currentTime);
  let i=c.findIndex(o=>o.run===r);
  if(i<0){let bd=1/0;i=0;c.forEach((o,k)=>{const d=Math.abs(o.t-aud.currentTime);if(d<bd){bd=d;i=k}})}
  return {c,i};
}
function loopRange(){
  if(!loop.a||!loop.b)return null;
  const [lo,hi]=loop.a.t<=loop.b.t?[loop.a,loop.b]:[loop.b,loop.a];
  const gi=OCC.findIndex(o=>o.m===hi.m&&o.t===hi.t);
  const end=(gi>=0&&gi+1<OCC.length)?OCC[gi+1].t                 // B 要唱完，所以终点取下一小节的起点
           :(isFinite(aud.duration)&&aud.duration>hi.t?aud.duration:hi.t+5);
  return {t0:lo.t,t1:end,m0:lo.m,m1:hi.m};
}
function fmt(t){t=Math.max(0,t||0);return Math.floor(t/60)+':'+String(Math.floor(t%60)).padStart(2,'0')}
function eq(l,a,b){const A=JSON.stringify(a),B=JSON.stringify(b);
  console.log((A===B?'OK   ':'FAIL ')+l+(A===B?'':'\n   got '+A+'\n   exp '+B))}

/* 典型合唱曲：1–8 主歌，反复回 3 再唱到 8，然后 9–12 尾声 */
E=[{m:1,t:0},{m:3,t:4},{m:8,t:14},{m:3,t:16},{m:8,t:26},{m:9,t:28},{m:12,t:34}];
buildOcc();
eq('切出 2 段（反复后直接接尾声，中间没有断点）', RUNS.length, 2);
eq('段落范围', RUNS.map(r=>r.m0+'-'+r.m1+'@'+r.t0), ['1-8@0','3-12@16']);
eq('每个 OCC 都归属某段', OCC.every(o=>o.run>=0), true);
eq('段号随时间不倒退', OCC.map(o=>o.run), [...OCC.map(o=>o.run)].sort((a,b)=>a-b));

/* 段落上下文选遍：正在听第①段时点小节 5 → 落在①段 */
aud.currentTime=10;
eq('①段内点小节5 -> t=%s', Math.round(pickOcc(5).c[pickOcc(5).i].t), 8);
eq('当前是①段', runAt(aud.currentTime), 0);
aud.currentTime=22;
eq('②段内点小节5 -> t=20', Math.round(pickOcc(5).c[pickOcc(5).i].t), 20);
eq('当前是②段', runAt(aud.currentTime), 1);

/* 关键回归：在①段末尾(t=13,小节7)点小节3。时间上②段的3(t=16)更近，
   但按段落走应该回到①段的3(t=4) —— 这正是旧"取时间最近"会跳错的场景 */
aud.currentTime=13;
const p=pickOcc(3);
eq('①段末点小节3 -> 回①段的 t=4（旧逻辑会跳到 16）', p.c[p.i].t, 4);

/* 当前段落没有该小节 -> 退回时间最近 */
aud.currentTime=10;                       // 在①段(1-8)里，小节11只存在于②段
eq('当前段没有该小节 -> 退回时间最近', Math.round(pickOcc(11).c[pickOcc(11).i].t), 32);
eq('无时间信息返回 null', pickOcc(99), null);

/* A-B 循环：B 要唱完，终点取下一小节起点 */
aud.currentTime=0;
loop.a={m:3,t:4}; loop.b={m:5,t:8};
eq('循环 3→5，终点=小节6起点', loopRange(), {t0:4,t1:10,m0:3,m1:5});
loop.a={m:5,t:8}; loop.b={m:3,t:4};       // 反着设
eq('A/B 反着设也正确', loopRange(), {t0:4,t1:10,m0:3,m1:5});
loop.a={m:12,t:34}; loop.b={m:12,t:34};   // 最后一个小节
eq('最后一小节用音频时长收尾', loopRange().t1, 200);
loop.a=null;
eq('只设了一半 -> null', loopRange(), null);

/* D.S. al Coda 式：两次回跳 -> 3 段 */
E=[{m:1,t:0},{m:8,t:14},{m:1,t:16},{m:16,t:40},{m:9,t:42},{m:12,t:50}];
buildOcc();
eq('两次回跳切出 3 段', RUNS.map(r=>r.m0+'-'+r.m1+'@'+r.t0), ['1-8@0','1-16@16','9-12@42']);
aud.currentTime=45;
eq('在③段点小节10 -> 落在③段', pickOcc(10).c[pickOcc(10).i].run, 2);
aud.currentTime=20;
eq('在②段点小节10 -> 落在②段', pickOcc(10).c[pickOcc(10).i].run, 1);

/* 无反复时不该切出多段 */
E=[{m:1,t:0},{m:4,t:6},{m:9,t:16}];buildOcc();
eq('无反复 = 1 段', RUNS.length, 1);
E=[];buildOcc();
eq('空数据 0 段', RUNS.length, 0);
eq('空数据 runAt=-1', runAt(5), -1);
eq('时间格式', [fmt(0),fmt(72),fmt(605)], ['0:00','1:12','10:05']);
