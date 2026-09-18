// 曲目库纯逻辑：sha256 回退 / 前 1MB 哈希 / legacy 键 / 项目 id 与名字匹配。
// 与 t*.js 不同：不拷贝代码，直接从 player.html 提取 /*PURE-START*/…/*PURE-END*/ 块，
// 测的就是线上代码本身，不存在"副本漂移"。
// ⚠ 往 PURE 块里加函数，必须同步改下面这行解构，否则整个文件直接抛 ReferenceError。
const fs=require('fs'),path=require('path'),crypto=require('crypto');
const src=fs.readFileSync(path.join(__dirname,'..','player.html'),'utf-8');
const m=src.match(/\/\*PURE-START\*\/([\s\S]*?)\/\*PURE-END\*\//);
if(!m)throw new Error('player.html 里找不到 PURE 块');
const P=new Function(m[1]+'; return {sha256Js,hexOf,sha256Hex,legacyKey,lsNameOf,'+
  'newId,dispName,nameKeysOf,nameKeys,findByNameIn,nameTaken};')();

function eq(l,a,b){const A=JSON.stringify(a),B=JSON.stringify(b);
  console.log((A===B?'PASS  ':'FAIL  ')+l+(A===B?'':'\n   got '+A+'\n   exp '+B))}

// --- NIST 标准向量 ---
const te=new TextEncoder();
eq('sha256("")',P.hexOf(P.sha256Js(te.encode(''))),
  'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855');
eq('sha256("abc")',P.hexOf(P.sha256Js(te.encode('abc'))),
  'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad');
eq('sha256(56B 标准向量)',P.hexOf(P.sha256Js(te.encode('abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq'))),
  '248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1');
eq('sha256(a×1e6 多块路径)',P.hexOf(P.sha256Js(new Uint8Array(1e6).fill(97))),
  'cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0');

// --- 长度填充边界（55/56 = 单块多块的边界，63/64/65 = 长度字段跨越块边界）与 node crypto 对照 ---
for(const n of [1,3,54,55,56,57,63,64,65,119,120,121,127,128,129,1000]){
  const b=new Uint8Array(n);for(let i=0;i<n;i++)b[i]=(i*7+3)&255;
  eq('sha256 vs node ('+n+'B)',P.hexOf(P.sha256Js(b)),crypto.createHash('sha256').update(b).digest('hex'));
}

// --- 前 1MB 哈希 ---
(async()=>{
  eq('sha256Hex("abc")',await P.sha256Hex(new Blob([te.encode('abc')])),
    'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad');
  const big=new Uint8Array(3e6);for(let i=0;i<3e6;i++)big[i]=i&255;
  eq('sha256Hex 只取前 1MB',await P.sha256Hex(new Blob([big])),
    crypto.createHash('sha256').update(big.subarray(0,1<<20)).digest('hex'));
  const mid=new Uint8Array(1e5);for(let i=0;i<1e5;i++)mid[i]=(i*13+5)&255;
  eq('sha256Hex <1MB 全量',await P.sha256Hex(new Blob([mid])),
    crypto.createHash('sha256').update(mid).digest('hex'));
  eq('sha256Hex 空文件',await P.sha256Hex(new Blob([])),
    'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855');
})();

// --- legacy 键 ---
eq('legacyKey',P.legacyKey('斯卡布罗集市.pdf'),'legacy:斯卡布罗集市.pdf');
eq('legacyKey 空',P.legacyKey(''),'legacy:');
eq('lsNameOf 正常',P.lsNameOf('player:abc.pdf'),'abc.pdf');
eq('lsNameOf 中文',P.lsNameOf('player:传奇.pdf'),'传奇.pdf');
eq('lsNameOf 非 player 前缀',P.lsNameOf('other:abc.pdf'),null);
eq('lsNameOf 恰好是 player:',P.lsNameOf('player:'),'');

// --- 项目 id：必须永远以 p 开头（因此永不等于任何 64 位 hex 的内容哈希）---
const ids=new Set();
for(let i=0;i<2000;i++)ids.add(P.newId());
eq('newId 唯一',ids.size,2000);
eq('newId 一律 p 开头',[...ids].every(x=>x[0]==='p'),true);
eq('newId 不可能撞上内容哈希',[...ids].some(x=>/^[0-9a-f]{64}$/.test(x)),false);

// --- 显示名 ---
eq('dispName 去扩展名',P.dispName('SK_斯卡布罗集市[线].pdf'),'SK_斯卡布罗集市[线]');
eq('dispName 去下载器尾缀',P.dispName('传奇_0_1787155482878.pdf'),'传奇');
eq('dispName 不误伤 _2024_08',P.dispName('传奇_2024_08.pdf'),'传奇_2024_08');
eq('dispName 音频',P.dispName('现场.mp3'),'现场');
eq('dispName 空',P.dispName(''),'');

// --- 名字匹配键：原名 + 去后缀的显示名，annotations.json 里两种都出现过 ---
eq('nameKeysOf 带后缀',P.nameKeysOf('CQ_传奇[线].pdf'),['CQ_传奇[线].pdf','CQ_传奇[线]']);
eq('nameKeysOf 不带后缀',P.nameKeysOf('SK_斯卡布罗集市[线]标注'),['SK_斯卡布罗集市[线]标注']);
eq('nameKeysOf 空',P.nameKeysOf(''),[]);
eq('nameKeys 含 aka',
  P.nameKeys({name:'新名.pdf',aka:['老名.pdf']}),['新名.pdf','新名','老名.pdf','老名']);

// --- 靠名字认领：两侧键集合有交集即同一个项目 ---
const projs=[
  {id:'p1',name:'CQ_传奇[线].pdf',aka:[]},
  {id:'p2',name:'SK_斯卡布罗集市[线]标注',aka:['改名前.pdf']},
];
eq('按带后缀的名字找到',P.findByNameIn(projs,'CQ_传奇[线].pdf')?.id,'p1');
eq('按不带后缀的名字也能找到（库里的名字带 .pdf）',P.findByNameIn(projs,'CQ_传奇[线]')?.id,'p1');
eq('按 aka 找到',P.findByNameIn(projs,'改名前.pdf')?.id,'p2');
eq('按 aka 的显示名也能找到',P.findByNameIn(projs,'改名前')?.id,'p2');
eq('对不上就是 null',P.findByNameIn(projs,'完全无关.pdf'),null);
eq('空名字不匹配任何项目',P.findByNameIn(projs,''),null);

// --- 重名硬拦：撞 name 或 aka 都要拦（撞了同步必然分叉）---
eq('撞 name',P.nameTaken(projs,'CQ_传奇[线].pdf',null)?.id,'p1');
eq('撞 name 的显示名',P.nameTaken(projs,'CQ_传奇[线]',null)?.id,'p1');
eq('撞别的项目的 aka',P.nameTaken(projs,'改名前.pdf',null)?.id,'p2');
eq('不撞',P.nameTaken(projs,'全新的名字',null),null);
eq('排除自己后不算撞（改名不动）',P.nameTaken(projs,'CQ_传奇[线].pdf','p1'),null);
eq('排除自己但撞别人仍然拦',P.nameTaken(projs,'改名前.pdf','p1')?.id,'p2');
eq('空名字不拦（由调用方校验非空）',P.nameTaken(projs,'',null),null);
