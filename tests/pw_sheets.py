"""Multiple score layouts share audio/timelines without sharing page coordinates."""
import asyncio, functools, http.server, socketserver, threading, tempfile, wave, json
from pathlib import Path
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parents[1]
A=ROOT.parent/'线谱合集/SK_斯卡布罗集市[线][TTBB+NA+WO].pdf'
B=ROOT.parent/'线谱合集/BW_不忘初心[线][SATB+NA+Pn].pdf'
class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*a): pass
srv=socketserver.TCPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(ROOT)))
threading.Thread(target=srv.serve_forever,daemon=True).start()
URL=f'http://127.0.0.1:{srv.server_address[1]}/player.html'
def check(value,label):
    assert value,label
    print('OK   '+label,flush=True)
async def ready(pg):
    await pg.wait_for_function("()=>idb && $('lib').style.display==='flex'")
async def main():
  with tempfile.TemporaryDirectory() as temp:
    tone=Path(temp)/'tone.wav'
    with wave.open(str(tone),'wb') as f:
      f.setnchannels(1);f.setsampwidth(2);f.setframerate(8000);f.writeframes(b'\0\0'*8000*60)
    async with async_playwright() as pw:
      b=await pw.chromium.launch()
      pg=await b.new_page(viewport={'width':1440,'height':900})
      errors=[];pg.on('pageerror',lambda e:errors.append(str(e)))
      await pg.goto(URL);await ready(pg)
      await pg.set_input_files('#fPdf',str(A));await pg.wait_for_function("()=>pdf && $('lib').style.display==='none'")
      await pg.evaluate("()=>{M=[{m:1,page:1,nx:.2,ny:.3,h:.06},{m:2,page:1,nx:.5,ny:.3,h:.06}];E=[{m:1,t:0,src:'tap'},{m:2,t:10,src:'tap'}];syncNext();layout();save()}")
      check(await pg.evaluate("""()=>{
        const legacy={pdf:{name:'原名_0_1787155482878.PDF'},sheets:[{id:'default',name:'默认谱面',pdf:{name:'原名_0_1787155482878.PDF'}}]};
        ensureSheets(legacy);
        const good=legacy.sheets[0].name==='原名_0_1787155482878';
        legacy.sheets[0].name='自定义';ensureSheets(legacy);
        return good&&legacy.sheets[0].name==='自定义';
      }"""), '旧默认名迁移仅去 PDF 扩展名，自定义名称保留')
      await pg.wait_for_function("()=>document.querySelector('.page')?.dataset.done")
      check(await pg.evaluate("""async()=>{
        const oldM=M,oldSys=systemAt,oldBars=detectRowBars,oldMode=$('mode').value;
        try{
          M=[{m:1,page:1,nx:.5,ny:.1,h:.05}];syncNext();
          systemAt=()=>({top:.6,bot:.7,staves:[]});detectRowBars=()=>[.5,.9];
          $('mode').value='mark';$('chkAutoRow').checked=true;
          const el=document.querySelector('.page'),r=el.getBoundingClientRect();
          await pagesEl.onclick({target:el,clientX:r.left+r.width*.2,clientY:r.top+r.height*.6});
          return M.some(m=>m.nx===.5&&m.ny===.6)&&M.length===3;
        }finally{
          systemAt=oldSys;detectRowBars=oldBars;M=oldM;syncNext();
          $('mode').value=oldMode;$('chkAutoRow').checked=false;layout();save();
        }
      }"""), '整行补齐不会把其他行同一横坐标的标记误判为重复')
      await pg.set_input_files('#fAud',str(tone));await pg.wait_for_selector('#dlgMode',state='visible');await pg.click('#dlgModeOk')
      await pg.wait_for_function('()=>aud.duration===60 && track.audios.length===1')
      await pg.evaluate("()=>{aud.currentTime=12;setRate(1.25)}")
      await pg.click('#bPlay')
      before=await pg.evaluate('({src:aud.src,t:aud.currentTime,E:JSON.stringify(E),id:pid,hash:pdfHash})')
      check(await pg.evaluate('track.sheets[0].name')==A.stem, '首份谱面使用 PDF 原文件名')
      await pg.click('#bMenu')
      async with pg.expect_file_chooser() as fc:
        await pg.click('#bAddSheet')
      await (await fc.value).set_files(str(B))
      await pg.wait_for_function("()=>track.sheets.length===2 && activeSheet!=='default' && !sheetBusy")
      check(await pg.evaluate('track.sheets.find(s=>s.id===activeSheet).name')==B.stem, '新增谱面使用 PDF 原文件名')
      alternate=await pg.evaluate('activeSheet')
      check(await pg.evaluate('M.length===0'), '新增谱面从空位置开始，不复制旧版坐标')
      check(await pg.evaluate('JSON.stringify(E)')==before['E'], '新增谱面保留共享时间点')
      check(await pg.evaluate('aud.src')==before['src'] and await pg.evaluate('!aud.paused && aud.currentTime>=12 && aud.playbackRate===1.25'), '新增/切谱不重载音频，播放与倍速连续')
      check(await pg.inner_text('#sheetStatus')=='仅看谱','未标位置的谱面显示仅看谱')
      await pg.evaluate("()=>{M=[{m:1,page:2,nx:.3,ny:.6,h:.08},{m:2,page:2,nx:.6,ny:.6,h:.08}];syncNext();layout();save()}")
      await pg.select_option('#sheetSel','default');await pg.wait_for_function("()=>activeSheet==='default' && !sheetBusy")
      check(await pg.evaluate('M[0].page===1 && M[0].nx===.2'),'切回默认谱面恢复原位置')
      await pg.select_option('#sheetSel',alternate);await pg.wait_for_function("()=>activeSheet!=='default' && !sheetBusy")
      check(await pg.evaluate('M[0].page===2 && M[0].nx===.3'),'切回简谱恢复独立位置')
      check(await pg.evaluate('aud.src')==before['src'] and await pg.evaluate('!aud.paused'),'反复切谱仍连续播放')
      await pg.evaluate("()=>{$('mode').value='mark';syncMode();openPanel(1)}")
      await pg.click('#pDelMk')
      check(await pg.evaluate('M.length===1 && M[0].m===2'),'多谱面删位置不重编号其他位置')
      check(await pg.evaluate('JSON.stringify(E)')==before['E'],'删位置不删除或重编号共享时间点')
      await pg.evaluate('undo()')
      await pg.evaluate('openPanel(1)');await pg.fill('#pEnd','3');await pg.locator('#pEnd').dispatch_event('change')
      check(await pg.evaluate('JSON.stringify(E)')==before['E'],'改休止范围不移动共享时间点')
      await pg.evaluate('undo();panel.style.display="none"')
      # Updating the currently selected version must not alter the other layout.
      updated=Path(temp)/'简谱更新.pdf'
      updated.write_bytes(B.read_bytes()+b'\n% SheetPlayer updated revision\n')
      old_hash=await pg.evaluate('pdfHash')
      await pg.click('#bMenu');await pg.click('#bReplaceSheet')
      pg.once('dialog',lambda dialog:asyncio.create_task(dialog.accept()))
      await pg.set_input_files('#fPdf',str(updated))
      await pg.wait_for_function('(h)=>pdfHash!==h && M.length===2',arg=old_hash)
      await pg.evaluate('flushSave()')
      check(await pg.evaluate('activeSheet')==alternate and await pg.evaluate('M[0].page===2 && SHEET_MARKS.default[0].page===1'), '替换简谱 PDF 只更新简谱，两个版本位置都保留')
      check(await pg.evaluate('JSON.stringify(E)')==before['E'],'替换谱面也保留共用时间轴')
      async with pg.expect_download() as dl:
        await pg.evaluate("$('bExp').click()")
      export=Path(temp)/'score.json';await (await dl.value).save_as(export)
      data=json.loads(export.read_text())
      check(data['v']==7 and len(data['sheets'])==2 and data['sheets']['default']['M'][0]['page']==1 and data['sheets'][alternate]['M'][0]['page']==2,'单曲导出包含两份独立位置与一套共享时间轴')
      await pg.reload();await ready(pg);await pg.click('.libCard .open');await pg.wait_for_function('()=>pdf && M.length===2')
      check(await pg.evaluate('activeSheet')==alternate and await pg.evaluate('M[0].page===2'),'刷新记住团员选用的谱面并恢复标注')
      check(await pg.evaluate('JSON.stringify(E)')==before['E'],'刷新保留共享时间轴')
      await pg.evaluate("showLib(true)");await pg.wait_for_timeout(300)
      async with pg.expect_download() as dl:
        await pg.click('#libMore');await pg.click('#libExpAll')
      bundle=Path(temp)/'all.json';await (await dl.value).save_as(bundle)
      payload=json.loads(bundle.read_text())
      check(payload['v']==3 and len(payload['items'][0]['sheets'])==2,'批量导出包含谱面目录')
      # A second device imports only annotations, then attaches its preferred PDF.
      other=await b.new_page(viewport={'width':390,'height':844},has_touch=True)
      other.on('pageerror',lambda e:errors.append(str(e)))
      await other.goto(URL);await ready(other)
      await other.set_input_files('#libImpAll',str(bundle))
      await other.wait_for_selector('.libCard')
      check(await other.locator('.libSheet option').count()==2,'新设备同步后可选择两份谱面')
      await other.select_option('.libSheet select',alternate)
      await other.click('.libCard .open')
      async with other.expect_file_chooser() as fc:
        await other.click('#dlgPickBtns button',strict=False)
      await (await fc.value).set_files(str(updated))
      await other.wait_for_function("()=>pdf && $('lib').style.display==='none'")
      check(await other.evaluate('activeSheet')==alternate and await other.evaluate('M[0].page===2'),'新设备补入简谱 PDF 后接回正确位置')
      check(await other.evaluate('JSON.stringify(E)')==before['E'],'新设备简谱使用同一时间轴')
      await other.evaluate('flushSave()')
      await other.evaluate('(d)=>importAnns([d],{force:true})',payload['items'][0])
      check(await other.evaluate('activeSheet')==alternate,'重新同步保留本机选用的简谱')
      await other.evaluate("setBarHidden(false)")
      check(await other.is_visible('#lblSheet') and await other.evaluate("document.body.classList.contains('perf')"),'团员演奏态可选择谱面')
      # Legacy import updates default layout only; alternate marks survive.
      legacy={'name':payload['items'][0]['name'],'data':{'v':6,'M':[{'page':1,'nx':.1,'ny':.2,'m':1,'h':.06}],'modes':data['modes'],'activeMode':'标准','ts':data['ts']+10000}}
      await pg.evaluate('(it)=>importAnns([it],{force:true})',legacy)
      check(await pg.evaluate('M[0].page===2'),'旧版标注同步不覆盖当前简谱位置')
      await pg.evaluate("switchSheet('default')")
      check(await pg.evaluate('M.length===1 && M[0].nx===.1'),'旧版标注归入默认谱面')
      # History collection must never delete another live score version.
      await pg.evaluate("$('libGcHist').onclick()")
      check(await pg.evaluate('(async()=>!!(await idbGet(idb,"files",track.sheets[1].pdf.hash)))()'),'历史清理保留其他谱面正在使用的 PDF')
      check(not errors,'浏览器无运行错误: '+str(errors))
      await b.close()
  srv.shutdown()
asyncio.run(main())
