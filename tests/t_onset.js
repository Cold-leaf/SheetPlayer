// Exercise production timing against known attacks, including a sustained backing tone.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync(require('path').join(__dirname,'../player.html'),'utf8');
const ctx=vm.createContext({});
vm.runInContext('const SP_N=1024;'+html.slice(html.indexOf('function fftIP('),html.indexOf('const SP_LUT='))+html.slice(html.indexOf('function refineOnset('),html.indexOf('// 窗口内综合')),ctx);
const sr=11025;
for(const kind of ['click','backing','pitch','soft']){
  let worst=0;
  for(const offset of [0,31,89,157,233]){
    const start=5500+offset,mono=new Float32Array(sr);
    for(let i=0;i<mono.length;i++){
      const t=i/sr,u=(i-start)/sr;
      const old=.65*Math.sin(2*Math.PI*220*t);
      if(kind==='click')mono[i]=u>=0?.9*Math.exp(-u/.004)*Math.sin(2*Math.PI*1500*u):0;
      if(kind==='backing')mono[i]=old+(u>=0?.2*Math.sin(2*Math.PI*1200*u):0);
      if(kind==='pitch')mono[i]=u<0?old:.65*Math.sin(2*Math.PI*660*u);
      if(kind==='soft')mono[i]=old+(u>=0?.3*Math.min(1,u/.025)*Math.sin(2*Math.PI*1200*u):0);
    }
    // Run the production candidate detector too, with the same long-window flux as buildSpec.
    ctx.mono=mono;
    const onsets=vm.runInContext(`(()=>{
      const hop=256,frames=Math.floor((mono.length-SP_N)/hop)+1;
      const flux=new Float32Array(frames),prev=new Float32Array(SP_N/2);
      const re=new Float32Array(SP_N),im=new Float32Array(SP_N);
      for(let f=0;f<frames;f++){
        for(let k=0;k<SP_N;k++){re[k]=mono[f*hop+k]*(.5-.5*Math.cos(2*Math.PI*k/SP_N));im[k]=0}
        fftIP(re,im);
        for(let k=Math.round(60*SP_N/11025);k<=Math.round(3000*SP_N/11025);k++){
          const v=Math.log1p(100*Math.hypot(re[k],im[k]));
          flux[f]+=Math.max(0,v-prev[k]);prev[k]=v;
        }
      }
      return [...pickOnsets(flux,frames,hop,11025,mono).t];
    })()`,ctx);
    assert(onsets.some(t=>Math.abs(t-start/sr)<.020),`${kind}: missing true attack: ${onsets}`);
    for(const lead of [400,650,850]){
      const t=ctx.refineOnset(mono,sr,start-lead),err=(t-start/sr)*1000;
      worst=Math.max(worst,Math.abs(err));
      assert(Math.abs(err)<20,`${kind} lead=${lead}: ${err.toFixed(1)}ms`);
    }
  }
  console.log(`PASS ${kind}: worst timing error ${worst.toFixed(1)}ms`);
}
assert(Number.isFinite(ctx.refineOnset(new Float32Array(10),sr,0)));
console.log('PASS short/silent audio has finite timing');
