const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync(require('path').join(__dirname,'../player.html'),'utf8');
const ctx=vm.createContext({});
vm.runInContext(html.slice(html.indexOf('function fftIP('),html.indexOf('const SP_LUT='))+html.slice(html.indexOf('function pitchScores('),html.indexOf('async function buildPitchSpec(')),ctx);
function scores(notes){
 const n=4096,sr=11025,re=new Float32Array(n),im=new Float32Array(n);
 for(let i=0;i<n;i++)for(const note of notes){const hz=440*2**((note-69)/12);for(let h=1;h<=6;h++)re[i]+=Math.sin(2*Math.PI*hz*h*i/sr)/h*(.5-.5*Math.cos(2*Math.PI*i/n))}
 ctx.fftIP(re,im);return ctx.pitchScores(Float32Array.from(re.slice(0,n/2), (v,i)=>Math.hypot(v,im[i])),sr,n);
}
for(const note of [36,48,60,69,84]){const s=scores([note]);assert.equal(84-s.indexOf(Math.max(...s)),note,`wrong pitch ${note}`)}
console.log('PASS harmonic tones C2–C6 peak at their fundamental');
const s=scores([48,64,67]);for(const note of [48,64,67])assert(s[84-note]>s[84-note-1]&&s[84-note]>s[84-note+1]);
assert([...ctx.pitchScores(new Float32Array(2048),11025,4096)].every(v=>v===0));
console.log('PASS simultaneous chord tones are distinct; silence stays dark');
