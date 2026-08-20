
let E=[];function snap(){}
function addTime(m,t){
  snap();
  const i=E.findIndex(e=>e.m===m&&Math.abs(e.t-t)<1);   // 同一小节 1 秒内视作手抖重复，覆盖而非新增
  if(i>=0){E[i].t=t;E[i].src='tap';return}              // 手改过的点升级为实测，重新生成时当硬锚点保留
  // 修正生成的点：替换时间上最近的那个。生成值是推导出来的，覆盖没有损失；
  // 而实测点是真数据，隔得远就当成另一遍新增，不动它。
  let gi=-1,bd=1/0;
  E.forEach((e,k)=>{if(e.m===m&&e.src==='gen'){const d=Math.abs(e.t-t);if(d<bd){bd=d;gi=k}}});
  if(gi>=0){E[gi].t=t;E[gi].src='tap';return}
  E.push({m,t,src:'tap'});
}
function eq(l,a,b){const A=JSON.stringify(a),B=JSON.stringify(b);
  console.log((A===B?'OK   ':'FAIL ')+l+(A===B?'':'\n   got '+A+'\n   exp '+B))}

E=[{m:5,t:10,src:'gen'}];
addTime(5,10.3);
eq('生成点附近微调 -> 覆盖并升级为 tap', E, [{m:5,t:10.3,src:'tap'}]);

E=[{m:5,t:10,src:'gen'}];
addTime(5,16.9);
eq('生成点差很远也覆盖（这是"修正"，不是新增一遍）', E, [{m:5,t:16.9,src:'tap'}]);

E=[{m:5,t:10,src:'gen',seg:0},{m:5,t:40,src:'gen',seg:1}];
addTime(5,38.5);
eq('有反复时替换时间最近的那一遍', E, [{m:5,t:10,src:'gen',seg:0},{m:5,t:38.5,src:'tap',seg:1}]);

E=[{m:5,t:10,src:'tap'}];
addTime(5,40);
eq('实测点隔得远 -> 当作另一遍新增，不破坏原数据',
   E, [{m:5,t:10,src:'tap'},{m:5,t:40,src:'tap'}]);

E=[{m:5,t:10,src:'tap'}];
addTime(5,10.4);
eq('实测点 1 秒内 -> 覆盖', E, [{m:5,t:10.4,src:'tap'}]);

E=[];
addTime(7,3);
eq('全新小节 -> 新增', E, [{m:7,t:3,src:'tap'}]);

E=[{m:5,t:10,src:'tap'},{m:5,t:40,src:'gen'}];
addTime(5,25);
eq('tap 和 gen 混存时优先替换 gen', E, [{m:5,t:10,src:'tap'},{m:5,t:25,src:'tap'}]);
