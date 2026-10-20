const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync(require('path').join(__dirname,'../player.html'),'utf8');
const ctx=vm.createContext({performance,requestAnimationFrame:fn=>setImmediate(fn)});
vm.runInContext(html.slice(html.indexOf('function fftIP('),html.indexOf('const SP_LUT='))+
  html.slice(html.indexOf('async function analyzeOnsetCurves('),html.indexOf('/* 谱通量峰值')),ctx);
(async()=>{
  const sr=11025,mono=new Float32Array(sr*2),times=[0,.5,.58,.66,1.98];
  times.forEach((t,j)=>{for(let k=0;k<sr*.03&&Math.round(t*sr)+k<mono.length;k++)
    mono[Math.round(t*sr)+k]+=(j===2?.15:.8)*Math.exp(-k/(sr*.004))*Math.sin(2*Math.PI*1500*k/sr)});
  const r=await ctx.analyzeOnsetCurves(mono,sr);
  for(const t of times)assert([...r.onsets].some(x=>Math.abs(x-t)<.015),`missing attack ${t}: ${[...r.onsets]}`);
  assert.equal(r.onsets.length,times.length);
  assert(r.curveStep<=.0051);
  console.log('PASS rapid weak attacks and audio boundaries within 15ms');
  for(const [hz,band] of [[220,1],[1200,2],[3500,3]]){
    const m=Float32Array.from({length:sr},(_,i)=>i<sr*.3||i>sr*.7?0:Math.sin(Math.PI*(i/sr-.3)/.4)**2*Math.sin(2*Math.PI*hz*i/sr));
    const b=await ctx.analyzeOnsetCurves(m,sr);
    assert(b.curveMax[band]>Math.max(...b.curveMax.slice(1).filter((_,i)=>i+1!==band)));
  }
  console.log('PASS frequency bands distinguish low, middle and high attacks');
  for(const kind of ['backing','pitch','soft']){
    const m=Float32Array.from({length:sr},(_,i)=>{
      const t=i/sr,u=t-.5,old=.65*Math.sin(2*Math.PI*220*t);
      if(kind==='pitch')return u<0?old:.65*Math.sin(2*Math.PI*660*u);
      return old+(u<0?0:.2*(kind==='soft'?Math.min(1,u/.025):1)*Math.sin(2*Math.PI*1200*u));
    });
    const r=await ctx.analyzeOnsetCurves(m,sr);
    assert([...r.onsets].some(t=>Math.abs(t-.5)<.020),`${kind}: ${[...r.onsets]}`);
  }
  console.log('PASS sustained backing, pitch changes and soft attacks within 20ms');
  const silent=await ctx.analyzeOnsetCurves(new Float32Array(10),sr);
  assert.equal(silent.onsets.length,0);assert(silent.curves.every(c=>[...c].every(Number.isFinite)));
  assert.equal(await ctx.analyzeOnsetCurves(mono,sr,()=>true),null);
  console.log('PASS short silence and cancelled analysis');
})().catch(e=>{console.error(e);process.exitCode=1});
