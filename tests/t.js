
let M=[],E=[],OCC=[],repeats=0,hist=[];
function pureM(){return M.map(({page,nx,ny,m})=>({page,nx,ny,m}))}
function snap(){hist.push(JSON.stringify({M:pureM(),E}))}
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
}
function occIndex(t){                     // OCC 按 t 递增，二分找最后一个 <= t
  let lo=0,hi=OCC.length-1,r=-1;
  while(lo<=hi){const mid=(lo+hi)>>1;if(OCC[mid].t<=t){r=mid;lo=mid+1}else hi=mid-1}
  return r;
}
function sortedM(){return [...new Set(M.map(x=>x.m))].sort((a,b)=>a-b)}
function stepM(m,dir){
  const L=sortedM();if(!L.length)return null;
  if(m==null)return dir>0?L[0]:L[L.length-1];
  const i=L.indexOf(m);
  if(i<0)return dir>0?(L.find(x=>x>m)??L[L.length-1]):([...L].reverse().find(x=>x<m)??L[0]);
  return L[Math.min(L.length-1,Math.max(0,i+dir))];
}
function firstUntimed(){
  const has=new Set(E.map(e=>e.m)),L=sortedM();
  return L.find(m=>!has.has(m))??L[0]??null;
}
function maxM(){return M.reduce((a,x)=>x.m>a?x.m:a,0)}
function addTime(m,t){
  snap();
  const i=E.findIndex(e=>e.m===m&&Math.abs(e.t-t)<1);   // 同一小节 1 秒内视作手抖重复，覆盖而非新增
  if(i>=0)E[i].t=t;else E.push({m,t});
}

function eq(label,a,b){const A=JSON.stringify(a),B=JSON.stringify(b);
  console.log((A===B?'PASS  ':'FAIL  ')+label+(A===B?'':'\n   got '+A+'\n   exp '+B))}

/* --- 1. 插值 + 反复识别 --- */
E=[{m:1,t:0},{m:2,t:2},{m:5,t:8},{m:1,t:10},{m:2,t:12}];
buildOcc();
eq('OCC 按时间单调递增', OCC.map(o=>o.t), [...OCC.map(o=>o.t)].sort((a,b)=>a-b));
eq('插值补出 3/4 小节', OCC.map(o=>o.m+':'+o.t.toFixed(1)),
   ['1:0.0','2:2.0','3:4.0','4:6.0','5:8.0','1:10.0','2:12.0']);
eq('反复计数=1', repeats, 1);
eq('exact 标记正确', OCC.map(o=>o.exact?1:0), [1,1,0,0,1,1,1]);

/* --- 2. 二分查找当前小节 --- */
eq('t=0 -> 小节1',   OCC[occIndex(0)].m, 1);
eq('t=5.9 -> 小节3', OCC[occIndex(5.9)].m, 3);
eq('t=9.9 -> 小节5', OCC[occIndex(9.9)].m, 5);
eq('t=10.5 -> 小节1(第二遍)', OCC[occIndex(10.5)].m, 1);
eq('t=99 -> 最后一个', OCC[occIndex(99)].m, 2);
eq('t=-1 -> 无', occIndex(-1), -1);

/* 与线性扫描逐点对齐 */
let mism=0;
for(let t=-0.5;t<14;t+=0.01){
  let lin=-1; for(let i=0;i<OCC.length;i++){ if(OCC[i].t<=t) lin=i; else break }
  if(lin!==occIndex(t)) mism++;
}
eq('二分与线性扫描一致', mism, 0);

/* --- 3. 打点目标推进（含缺号谱） --- */
M=[1,2,3,7,8].map(m=>({page:1,nx:0,ny:0,m}));
eq('stepM 跳过缺号 3->7', stepM(3,1), 7);
eq('stepM 到头不越界',  stepM(8,1), 8);
eq('stepM 到头不越界(左)', stepM(1,-1), 1);
eq('stepM(null,+1)=首',  stepM(null,1), 1);
eq('stepM 目标不在M里(+)', stepM(5,1), 7);
eq('stepM 目标不在M里(-)', stepM(5,-1), 3);
E=[{m:1,t:0},{m:2,t:1}];
eq('firstUntimed 找第一个没时间的', firstUntimed(), 3);
E=[{m:1,t:0},{m:2,t:1},{m:3,t:2},{m:7,t:3},{m:8,t:4}];
eq('全打完则回到首', firstUntimed(), 1);

/* --- 4. 手抖去重 --- */
E=[];M=[{page:1,nx:0,ny:0,m:1}];
addTime(1,10.00); addTime(1,10.12);
eq('1秒内重复打点 -> 覆盖', E, [{m:1,t:10.12}]);
addTime(1,40.0);
eq('远处的反复 -> 新增', E.length, 2);

/* --- 5. 编号推导 --- */
M=[1,2,3,4,5,6,7,8,9,10].map(m=>({page:1,nx:0,ny:0,m}));
M=M.filter(x=>x.m!==10);                 // 面板删掉小节10
eq('nextM 由 M 推导 = 10', maxM()+1, 10);
M.pop();                                  // 再撤销掉小节9
eq('撤销后 nextM = 9（旧版这里会算成10，小节9永久丢失）', maxM()+1, 9);

/* --- 6. 边界 --- */
E=[];buildOcc(); eq('空E不炸', OCC.length, 0);
E=[{m:3,t:5}];buildOcc(); eq('单点', OCC.map(o=>o.m), [3]);
E=[{m:1,t:5},{m:4,t:5}];buildOcc();
eq('零时长区间插值不产生NaN', OCC.every(o=>isFinite(o.t)), true);
