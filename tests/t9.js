// 曲目库纯逻辑：sha256 回退 / 前 1MB 哈希 / legacy 键 / 项目 id 与名字匹配。
// 与 t*.js 不同：不拷贝代码，直接从 player.html 提取 /*PURE-START*/…/*PURE-END*/ 块，
// 测的就是线上代码本身，不存在"副本漂移"。
// ⚠ 往 PURE 块里加函数，必须同步改下面这行解构，否则整个文件直接抛 ReferenceError。
const fs=require('fs'),path=require('path'),crypto=require('crypto');
const src=fs.readFileSync(path.join(__dirname,'..','player.html'),'utf-8');
const m=src.match(/\/\*PURE-START\*\/([\s\S]*?)\/\*PURE-END\*\//);
if(!m)throw new Error('player.html 里找不到 PURE 块');
const P=new Function(m[1]+'; return {sha256Js,hexOf,sha256Hex,legacyKey,lsNameOf,'+
  'newId,dispName,splitName,nameKeysOf,nameKeys,findByNameIn,claimProjFor,nameSim,nameTaken};')();

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
  // 大文件：大小 + 前 1MB + 中间 128KB + 末尾 128KB。后两段是修「换谱静默不生效」的关键——
  // 增量保存（加完笔记重新导出的那份）前面一个字节都不改，只动后面
  const big=new Uint8Array(3e6);for(let i=0;i<3e6;i++)big[i]=i&255;
  const fpBuf=(b)=>{
    const head=b.subarray(0,1<<20),mo=Math.max(0,(b.length>>1)-(1<<16));
    const mid=b.subarray(mo,mo+(1<<17)),tail=b.subarray(b.length-(1<<17));
    const out=Buffer.concat([Buffer.from(head),Buffer.from(mid),Buffer.from(tail),Buffer.alloc(8)]);
    out.writeDoubleBE(b.length,out.length-8);return out;};
  eq('sha256Hex 大文件 = 大小+前1MB+中128KB+末128KB',await P.sha256Hex(new Blob([big])),
    crypto.createHash('sha256').update(fpBuf(big)).digest('hex'));
  // 只改后半段（增量保存）→ 指纹必须变。这一条就是那个 bug 的回归钉子
  const edited=Uint8Array.from(big);edited[edited.length-100]^=0xff;
  eq('只改末尾一个字节 → 指纹变了',
    (await P.sha256Hex(new Blob([edited])))!==(await P.sha256Hex(new Blob([big]))),true);
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

// --- 曲名拆分：卡片上曲名放大、[线][SATB+T+Pn] 这类标记收成一行小字 ---
eq('splitName 带方括号',P.splitName('SH_松花江上[线][SATB+T+Pn]标注'),{title:'松花江上',tags:['线','SATB+T+Pn']});
eq('splitName 不带标记',P.splitName('四海'),{title:'四海',tags:[]});
eq('splitName 多段标记（最后一段是人名）',P.splitName('ZS_在水一方[线][SATB+NA+Pn][金巍]'),
  {title:'在水一方',tags:['线','SATB+NA+Pn','金巍']});
eq('splitName 方括号在中间',P.splitName('SK_[线]斯卡布罗集市'),{title:'斯卡布罗集市',tags:['线']});
eq('splitName 尾缀「校对」同样去掉',P.splitName('CQ_传奇[线]校对'),{title:'传奇',tags:['线']});
eq('splitName 只有标记、没剩曲名时退回整串',P.splitName('标注'),{title:'标注',tags:[]});
eq('splitName 空方括号不算标记',P.splitName('BJ_北京喜讯[]'),{title:'北京喜讯',tags:[]});
eq('splitName 不动名字中间的「标注」',P.splitName('标注说明[线]'),{title:'标注说明',tags:['线']});
eq('splitName 空',P.splitName(''),{title:'',tags:[]});
eq('splitName 入参已去扩展名',P.splitName(P.dispName('WH_我和我的祖国[线][SATB+NA+Pn]标注.pdf')),
  {title:'我和我的祖国',tags:['线','SATB+NA+Pn']});

// 库里真实存在的 12 个名字（annotations.json）跑一遍：曲名里不该再剩方括号、XX_ 前缀、扩展名。
// 后两条——「四海」「十送红军」不按这套约定命名——正是"拆不出来就整串当曲名"要保护的
const realNames=['SH_松花江上[线][SATB+T+Pn]标注.pdf','MT_明天会更好[线][SATB+S+Pn].pdf','四海',
  'BJ_北京喜讯到边寨[线][SATB+ST+Pn].pdf','AD_Anotherdayofsun[线][SATB+NA+Pn].pdf',
  'ZS_在水一方[线][SATB+NA+Pn][金巍].pdf','CQ_传奇[线][SATB+NA+Pn]标注.pdf',
  'SK_斯卡布罗集市[线][TTBB+NA+WO]标注','AL_AslongasIhavemusic[线][SATB+NA+Pn]标注.pdf',
  'WH_我和我的祖国[线][SATB+NA+Pn]标注.pdf','十送红军','DN_当那一天来临[线][SATB+ST+Pn].pdf'];
const split=realNames.map(n=>{const r=P.splitName(P.dispName(n));return {...r,raw:n}});
eq('12 个真实曲名全部拆干净（没剩方括号/前缀/扩展名）',
  split.filter(r=>/[\[\]]/.test(r.title)||/^[A-Z]{2}_/.test(r.title)||/\./.test(r.title)).map(r=>r.raw),[]);
eq('真实数据：带标记的曲名',split.filter(r=>r.tags.length).map(r=>r.title),
  ['松花江上','明天会更好','北京喜讯到边寨','Anotherdayofsun','在水一方','传奇','斯卡布罗集市',
   'AslongasIhavemusic','我和我的祖国','当那一天来临']);
eq('真实数据：不带标记的整串当曲名',split.filter(r=>!r.tags.length).map(r=>r.title),['四海','十送红军']);

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

// --- 认领规则：① 内容哈希 → ② 历史谱子 → ③ 名字。
// 下载弹窗的预选和真导入共用这一份，所以这几条同时钉住两边的行为；
// why 必须严格是这几个字面量——调用方按它分派（②/③ 的处理不一样）---
const HA='a'.repeat(64),HB='b'.repeat(64),HC='c'.repeat(64),HX='f'.repeat(64);
const cps=[
  {id:'p1',name:'CQ_传奇[线].pdf',aka:[],pdf:{hash:HA},pdfHistory:[]},
  {id:'p2',name:'SK_斯卡布罗集市[线]标注',aka:[],pdf:{hash:HB},pdfHistory:[{hash:HC,name:'旧的.pdf'}]},
  {id:'p3',name:'ZG_战歌[线][TTBB]',aka:[],pdf:null,pdfHistory:[]},   // 还没谱子，等着导入
];
const claim=(H,n)=>{const r=P.claimProjFor(cps,H,n);return [r.p&&r.p.id,r.why]};
eq('① 内容哈希命中当前谱子',claim(HA,'完全无关.pdf'),['p1','hash']);
eq('① 优先于 ③（文件名指向别人也不动）',claim(HA,'ZG_战歌[线][TTBB]'),['p1','hash']);
eq('② 历史谱子（用过的换回去）',claim(HC,'完全无关.pdf'),['p2','hist']);
eq('② 优先于 ③',claim(HC,'ZG_战歌[线][TTBB]'),['p2','hist']);
eq('③ 名字对得上（带不带 .pdf 都行）',claim(HX,'ZG_战歌[线][TTBB].pdf'),['p3','name']);
eq('③ 认得回还没谱子的项目（「等待导入谱子」那种）',claim(HX,'ZG_战歌[线][TTBB]'),['p3','name']);
eq('三步都不中就交回 null（调用方走新建）',claim(HX,'从来没见过的谱子.pdf'),[null,'']);
eq('空项目表 / 空文件名都不炸',[P.claimProjFor([],HA,'x.pdf').p,P.claimProjFor(null,HA,'x.pdf').p,claim(HX,'')],[null,null,[null,'']]);

// --- 名字相似度：只用于弹窗排序（把同一首歌的各个版本排到一起），绝不参与认领。
// 认领走 nameKeys 精确键——拿相似度去合并会变成"看着像就吞" ---
const sim=(a,b)=>Math.round(P.nameSim(a,b)*1000)/1000;
eq('一字不差 = 1',P.nameSim('ZG_战歌[线][TTBB]','ZG_战歌[线][TTBB]'),1);
eq('同曲不同版本（前缀/标记全不一样）= 1：拆出曲名后就是同一首',
  P.nameSim('ZG_中国人民志愿军战歌[线][TTBB+NA+Pn]','ZG_中国人民志愿军战歌[简][TB+NA+WO]'),1);
eq('带不带扩展名不影响',P.nameSim('CQ_传奇[线].pdf','CQ_传奇[线]'),1);
eq('毫不相干 = 0',P.nameSim('ZG_战歌[线]','十送红军'),0);
eq('不按约定命名的也不乱配',P.nameSim('四海','十送红军'),0);
eq('空名字 = 0',[P.nameSim('','战歌'),P.nameSim('战歌',''),P.nameSim('','')],[0,0,0]);
eq('包含关系按长度打折',sim('战歌','中国人民志愿军战歌'),0.222);
// 真实曲库跑一遍排序：下载「志愿军战歌[简]」那一版时，[线] 那版必须顶到最前——
// 这正是现在文件名精确匹配认不上、于是一首曲子分叉成好几个项目的那一步
const libRank=['MT_明天会更好[线][SATB+S+Pn]','ZG_中国人民志愿军战歌[线][TTBB+NA+Pn]',
  'SH_松花江上[线][SATB+T+Pn]','十送红军','CQ_传奇[线][SATB+NA+Pn]']
  .sort((a,b)=>P.nameSim(b,'ZG_中国人民志愿军战歌[简][TB+NA+WO]')-P.nameSim(a,'ZG_中国人民志愿军战歌[简][TB+NA+WO]'));
eq('排序把同曲的另一版顶到最前',libRank[0],'ZG_中国人民志愿军战歌[线][TTBB+NA+Pn]');
// 「十送红军」只跟「志愿军」共用一个「军」字，于是拿了 0.111 分排到第二——
// 只是排序里挪个位置，无伤大雅；要是拿它去认领就成了笑话，这就是两个概念必须分开的原因
eq('只撞一个字也能拿到一点分（所以只能拿来排序）',sim('十送红军','ZG_中国人民志愿军战歌[简][TB+NA+WO]'),0.111);
eq('一个共同字都没有的保持原序',libRank.slice(2),
  ['MT_明天会更好[线][SATB+S+Pn]','SH_松花江上[线][SATB+T+Pn]','CQ_传奇[线][SATB+NA+Pn]']);

// --- 重名硬拦：撞 name 或 aka 都要拦（撞了同步必然分叉）---
eq('撞 name',P.nameTaken(projs,'CQ_传奇[线].pdf',null)?.id,'p1');
eq('撞 name 的显示名',P.nameTaken(projs,'CQ_传奇[线]',null)?.id,'p1');
eq('撞别的项目的 aka',P.nameTaken(projs,'改名前.pdf',null)?.id,'p2');
eq('不撞',P.nameTaken(projs,'全新的名字',null),null);
eq('排除自己后不算撞（改名不动）',P.nameTaken(projs,'CQ_传奇[线].pdf','p1'),null);
eq('排除自己但撞别人仍然拦',P.nameTaken(projs,'改名前.pdf','p1')?.id,'p2');
eq('空名字不拦（由调用方校验非空）',P.nameTaken(projs,'',null),null);
