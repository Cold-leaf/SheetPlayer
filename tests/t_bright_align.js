const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync(require('path').join(__dirname,'../player.html'),'utf8'),ctx=vm.createContext({});
vm.runInContext(html.slice(html.indexOf('/* BRIGHT-ALIGN-CORE:'),html.indexOf('/* BRIGHT-ALIGN-CORE-END */')),ctx);
const grid=Array.from({length:9},(_,i)=>({m:i+1,t:1+i*2,seg:0,tempo:0,beats:4,fixed:i===0||i===8}));
function candidates(shift){return Array.from({length:33},(_,i)=>({t:1+i*.5+(typeof shift==='function'?shift(i):shift),score:50}))}
let plan=ctx.planBrightRegions(grid,candidates(.06),.12,20);
for(let i=1;i<8;i++)assert(Math.abs(plan.times[i]-grid[i].t-.06)<1e-6);
assert.equal(plan.times[0],1);assert.equal(plan.times[8],17);
assert.equal(grid[1].t,3);
console.log('PASS consistent segment shift protects both anchors and does not mutate input');
plan=ctx.planBrightRegions(grid,[],.12,20);assert.deepEqual(Array.from(plan.times),grid.map(p=>p.t));
plan=ctx.planBrightRegions(grid,candidates(i=>i%2?.09:-.09),.12,20);assert.deepEqual(Array.from(plan.times),grid.map(p=>p.t));
plan=ctx.planBrightRegions(grid,[...candidates(-.06),...candidates(.06)].sort((a,b)=>a.t-b.t),.12,20);assert.deepEqual(Array.from(plan.times),grid.map(p=>p.t));
console.log('PASS silence, inconsistent offsets and ambiguous neighboring attacks preserve prediction');
const divided=grid.map((p,i)=>({...p,tempo:i<4?0:1}));
plan=ctx.planBrightRegions(divided,candidates(i=>i<16?.06:-.05),.12,20);
assert(Math.abs(plan.times[2]-grid[2].t-.06)<1e-6);assert(Math.abs(plan.times[5]-grid[5].t+.05)<1e-6);
assert(plan.regions.some(r=>r.start===4));
const manual=grid.map((p,i)=>({...p,manualBeat:i===3}));
plan=ctx.planBrightRegions(manual,candidates(.06),.12,20);assert.deepEqual(Array.from(plan.times),grid.map(p=>p.t));
console.log('PASS separate tempo regions and manual beat protection');
const levels=new Uint8Array(600),dt=.01,center=.05;
for(let f=200;f<220;f++)levels[f]=245; // bright target attack
for(let f=400;f<420;f++)levels[f]=160; // dim accompaniment attack
let result=ctx.brightEvidence(levels,600,1,dt,center,[2.02,4.02],230);
assert.equal(result.length,1);assert.equal(result[0].t,2.02);
result=ctx.brightEvidence(new Uint8Array(600).fill(245),600,1,dt,center,[2.02],230);assert.equal(result.length,0);
console.log('PASS bright evidence selects strong attack, rejects dim attacks and sustained bright tones');
