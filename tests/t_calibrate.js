// Execute production calibration and its timing helpers with known measure durations.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync(require('path').join(__dirname,'../player.html'),'utf8');
const ctx=vm.createContext({});
vm.runInContext(`let TEMPO=[],METER=[],E=[],FORM=[],M=[];function maxM(){return Math.max(1,...M.map(x=>x.m))}`+
 html.slice(html.indexOf('function measDurOf('),html.indexOf('function parseSig('))+
 html.slice(html.indexOf('function expandForm('),html.indexOf('// 锚点体检'))+
 html.slice(html.indexOf('function calibrate('),html.indexOf('/* ---------- 高亮跟随')),ctx);
function run(code){return vm.runInContext(code,ctx)}
function setup(tempo,anchors,form=[]){
 ctx.input={tempo,anchors,form};run(`TEMPO=input.tempo;E=input.anchors.map(([m,t])=>({m,t,src:'tap'}));FORM=input.form;M=[{m:1},{m:24}];METER=[{sig:[4,4],ranges:[]}];`);
}
function bpms(){return Array.from(run('TEMPO.map(t=>t.bpm)'))}
setup([{m:1,bpm:65.508},{m:10,bpm:65.508}],[[1,2],[10,38],[14,50]]);
let r=run('calibrate()');assert.deepEqual(bpms(),[60,80]);assert.equal(r.segments[0].intervals,1);
console.log('PASS independent tempos 60/80 from identical initial values, boundary anchor belongs to preceding interval');
setup([{m:10,bpm:120},{m:1,bpm:60}],[[1,2],[10,38],[14,50]]);
run('calibrate()');assert.deepEqual(bpms(),[80,60]);
console.log('PASS unsorted tempo rows retain correct ownership');
setup([{m:1,bpm:120},{m:10,bpm:120}],[[1,0],[5,16],[14,50]]);
r=run('calibrate()');assert.deepEqual(bpms(),[60,120]);assert.equal(r.crossing,1);assert.equal(r.segments[1].bpm,null);
console.log('PASS cross-tempo interval skipped and unsupported segment unchanged');
setup([{m:1,bpm:120},{m:10,bpm:90}],[[1,0],[14,50]]);
assert.throws(()=>run('calibrate()'),/没有可独立/);assert.deepEqual(bpms(),[120,90]);
console.log('PASS only cross-tempo anchors cannot silently scale all rows');
setup([{m:1,bpm:10}],[[1,.42],[24,37.22]]);
run('METER=[{sig:[3,4],ranges:[]}]');run('calibrate()');assert.deepEqual(bpms(),[112.5]);
console.log('PASS single segment result independent of initial BPM');
setup([{m:1,bpm:120},{m:3,bpm:120}],[[1,0],[3,5],[5,11],[1,11],[3,16],[5,22]], [{from:1,to:4},{from:1,to:5}]);
// Remove simultaneous anchors (end of first pass isn't a separate measure in this form).
run("E=E.filter((e,i)=>i!==2);METER=[{sig:[3,4],ranges:[{from:1,to:1}]},{sig:[2,4],ranges:[{from:2,to:2}]},{sig:[6,8],ranges:[]}]");
run('calibrate()');assert.deepEqual(bpms(),[60,60]);
console.log('PASS repeated playback and changing meters use actual quarter-note counts');
setup([{m:1,bpm:120},{m:10,bpm:90}],[[1,0],[5,16],[10,30],[14,30]]);
assert.throws(()=>run('calibrate()'),/严格递增/);assert.deepEqual(bpms(),[120,90]);
setup([{m:1,bpm:120},{m:1,bpm:90}],[[1,0],[5,16]]);
assert.throws(()=>run('calibrate()'),/不同的正整数/);
console.log('PASS invalid timestamps and duplicate tempo boundaries leave table unchanged');
setup([{m:1,bpm:120},{m:10,bpm:120}],[[1,0],[10,36],[14,48]]);
run("E.push({m:5,t:1,src:'gen'})");run('calibrate()');assert.deepEqual(bpms(),[60,80]);
setup([{m:1,bpm:120},{m:10,bpm:90}],[[1,0],[10,36],[14,48]]);
run('METER=[{sig:[4,4],ranges:[{from:1,to:9}]}]');
assert.throws(()=>run('calibrate()'),/没有拍号/);assert.deepEqual(bpms(),[120,90]);
console.log('PASS generated points ignored; missing meter fails without partial mutation');
