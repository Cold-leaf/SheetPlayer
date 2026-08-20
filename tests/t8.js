
let SPEC=null;
function pickOnsets(flux,frames,hop,sr){
  let mx=0;for(let i=0;i<frames;i++)if(flux[i]>mx)mx=flux[i];
  const ts=[],ss=[];
  if(!mx)return {t:new Float32Array(0),s:new Float32Array(0)};
  const W=6,MINGAP=0.035;
  for(let i=W;i<frames-W;i++){
    const v=flux[i];let mean=0;
    for(let j=i-W;j<=i+W;j++)mean+=flux[j];
    mean/=(2*W+1);
    // 左侧严格、右侧非严格：平台期只认最左那一帧，否则一段渐强会每 MINGAP 冒一个假起音
    let peak=true;
    for(let j=i-W;j<i;j++)if(flux[j]>=v){peak=false;break}
    if(peak)for(let j=i+1;j<=i+W;j++)if(flux[j]>v){peak=false;break}
    if(!(peak&&v>mean*1.45&&v>mx*0.05))continue;
    const t=i*hop/sr;
    if(ts.length&&t-ts[ts.length-1]<MINGAP){            // 挨太近的只留强的那个
      if(v/mx>ss[ss.length-1]){ts[ts.length-1]=t;ss[ss.length-1]=v/mx}
      continue;
    }
    ts.push(t);ss.push(v/mx);
  }
  return {t:Float32Array.from(ts),s:Float32Array.from(ss)};
}
function bestOnset(t,win){
  const O=SPEC&&SPEC.onsets;
  if(!O||!O.length||!(win>0))return null;
  let lo=0,hi=O.length-1,i=O.length;
  while(lo<=hi){const m=(lo+hi)>>1;if(O[m]>=t-win){i=m;hi=m-1}else lo=m+1}
  let best=null,bs=-1;
  for(let k=i;k<O.length&&O[k]<=t+win;k++){
    const d=(O[k]-t)/(win*0.6),sc=SPEC.onsetStr[k]*Math.exp(-0.5*d*d);
    if(sc>bs){bs=sc;best=O[k]}
  }
  return best;
}
function eq(l,a,b){const A=JSON.stringify(a),B=JSON.stringify(b);
  console.log((A===B?'OK   ':'FAIL ')+l+(A===B?'':'\n   got '+A+'\n   exp '+B))}

/* ---- 峰值检测 ---- */
const SR=11025,HOP=256,FPS=SR/HOP;
function mk(peaks,frames){                 // 在指定帧位置放尖峰
  const f=new Float32Array(frames);
  for(let i=0;i<frames;i++)f[i]=0.05+0.02*Math.sin(i);
  for(const [pos,amp] of peaks){for(let d=-1;d<=1;d++)if(f[pos+d]!==undefined)f[pos+d]=Math.max(f[pos+d],amp*(d?0.5:1))}
  return f;
}
let r=pickOnsets(mk([[50,1],[100,.8],[150,.6]],300),300,HOP,SR);
eq('检出 3 个峰', r.t.length, 3);
eq('位置正确', [...r.t].map(x=>Math.round(x*FPS)), [50,100,150]);
eq('强度归一化到 1', +r.s[0].toFixed(3), 1);
eq('强度有序', r.s[0]>r.s[1]&&r.s[1]>r.s[2], true);

r=pickOnsets(mk([[50,1],[51,1],[52,1]],300),300,HOP,SR);
eq('挨太近的合并成 1 个', r.t.length, 1);

r=pickOnsets(new Float32Array(300),300,HOP,SR);
eq('全零不炸', r.t.length, 0);
r=pickOnsets(mk([[50,1]],300),300,HOP,SR);
eq('单峰', r.t.length, 1);

/* ---- 窗口内择优 ---- */
SPEC={onsets:Float32Array.from([1.00,1.50,2.00,2.05]),onsetStr:Float32Array.from([1,0.2,0.9,0.3])};
eq('窗口内只有一个 -> 选它', bestOnset(1.02,0.1), 1.00);
eq('窗口外 -> null', bestOnset(1.30,0.1), null);
eq('近但很弱 vs 稍远但很强：综合打分', +bestOnset(2.04,0.08).toFixed(2), 2.00);
eq('极近的弱音头也能赢（差距够大时）', +bestOnset(2.05,0.005).toFixed(2), 2.05);
eq('窗口为 0 -> null', bestOnset(1.0,0), null);
SPEC={onsets:new Float32Array(0),onsetStr:new Float32Array(0)};
eq('没有起音数据 -> null', bestOnset(1,0.1), null);
SPEC=null;
eq('SPEC 为空 -> null', bestOnset(1,0.1), null);

/* 平台期 / 渐强不该冒出一串假起音 */
const ramp=new Float32Array(300);
for(let i=0;i<300;i++)ramp[i]=i>=60&&i<=160?0.3+(i-60)*0.004:0.05;
r=pickOnsets(ramp,300,HOP,SR);
eq('100 帧的渐强只出 <=2 个起音', r.t.length<=2, true);
console.log('     渐强段检出:', r.t.length, '个');
