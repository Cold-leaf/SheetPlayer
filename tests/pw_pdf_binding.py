"""PDF ownership is selected explicitly; member notes survive annotation sync."""
import asyncio, functools, http.server, threading
from pathlib import Path
from playwright.async_api import async_playwright
ROOT = Path(__file__).resolve().parents[1]
class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args): pass

def pdf_bytes():
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>',
               b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 400] /Resources << >> >>']
    data = b'%PDF-1.4\n'; offsets = [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(data)); data += f'{i} 0 obj\n'.encode() + obj + b'\nendobj\n'
    start = len(data)
    data += b'xref\n0 4\n0000000000 65535 f \n'
    data += b''.join(f'{o:010d} 00000 n \n'.encode() for o in offsets[1:])
    return data + f'trailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n'.encode()

async def main():
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=str(ROOT)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
      async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page(); errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        await page.goto(f'http://127.0.0.1:{server.server_port}/player.html')
        await page.wait_for_function('()=>!!idb')
        item = {'id':'ptest', 'name':'合唱曲', 'sheets':[
            {'id':'default','name':'五线谱','pdf':{'hash':'remote-original','name':'原谱.pdf'}},
            {'id':'numbered','name':'简谱','pdf':{'hash':'remote-numbered','name':'简谱.pdf'}}],
            'data':{'v':7,'ts':100,'sheets':{
                'default':{'M':[{'m':1,'page':1,'nx':.2,'ny':.3}]},
                'numbered':{'M':[{'m':1,'page':1,'nx':.6,'ny':.7}]}},
                'modes':{'标准':{'E':[{'m':1,'t':2}], 'BEATS':{}}}}}
        await page.evaluate('(it)=>importAnns([it])', item)
        upload = {'name':'我的手写笔记.pdf','mimeType':'application/pdf','buffer':pdf_bytes()}
        await page.set_input_files('#fPdf', upload)
        await page.wait_for_selector('#dlgProj', state='visible')
        assert await page.evaluate('(async()=> (await idbAll(idb,"files")).length)()') == 0
        await page.click('#dlgProjOk')
        await page.wait_for_selector('#dlgPick', state='visible')
        await page.keyboard.press('Escape')
        assert await page.evaluate('(async()=> (await idbAll(idb,"files")).length)()') == 0
        print('OK   取消谱面选择不导入文件')
        await page.set_input_files('#fPdf', upload)
        await page.click('#dlgProjOk')
        await page.get_by_role('button', name='简谱', exact=True).click()
        await page.wait_for_function('()=>pdf && activeSheet==="numbered" && M.length===1')
        assert await page.evaluate('pid==="ptest" && M[0].nx===.6 && E[0].t===2')
        local_hash = await page.evaluate('pdfHash')
        await page.evaluate('flushSave()')
        ann_time = await page.evaluate('(async()=> (await idbGet(idb,"marks","ptest")).data.ts)()')
        media_time = await page.evaluate('track.mediaUpdatedAt')
        assert media_time > 0
        print('OK   新设备不同文件名、不同内容接回所选谱面的坐标和时间轴')
        await page.evaluate('(it)=>importAnns([it],{force:true})', item)
        assert await page.evaluate('pdfHash') == local_hash
        assert await page.evaluate('track.sheets.find(s=>s.id==="numbered").pdf.hash') == local_hash
        print('OK   后续同步保留本机笔记 PDF')
        await page.evaluate('flushSave()')
        await page.reload()
        await page.wait_for_function('()=>!!idb')
        await page.evaluate('openTrack("ptest")')
        await page.wait_for_function('()=>pdf && activeSheet==="numbered"')
        assert await page.evaluate('pdfHash') == local_hash
        assert await page.evaluate('M[0].nx===.6 && E[0].t===2')
        print('OK   刷新后恢复本机文件绑定与标注')
        # Same bytes may be explicitly bound to a different sheet, without hash redirection.
        await page.set_input_files('#fPdf', upload)
        await page.click('#dlgProjOk')
        await page.get_by_role('button', name='五线谱', exact=True).click()
        await page.wait_for_function('()=>activeSheet==="default" && M[0].nx===.2')
        assert await page.evaluate('E[0].t===2')
        print('OK   相同文件也严格绑定用户选择的谱面')
        # The explicit missing-sheet attach path accepts a different member PDF too.
        await page.evaluate('()=>{pendPid="ptest";pendSheet={kind:"attach",sheetId:"numbered"}}')
        upload['buffer'] += b'\n% member notes\n'
        await page.set_input_files('#fPdf', upload)
        await page.get_by_role('button', name='简谱', exact=True).click()
        await page.wait_for_function('(old)=>activeSheet==="numbered" && pdfHash!==old && M[0].nx===.6', arg=local_hash)
        print('OK   从已有谱面补文件不再校验原 PDF 指纹')
        # Actual library replacement entry: current numbered score must not be overwritten.
        numbered_hash = await page.evaluate('pdfHash')
        await page.evaluate('async()=>{showLib(true);await drawLib()}')
        await page.locator('.libCard .repl').click()
        async with page.expect_file_chooser() as chooser:
            await page.get_by_role('button', name='从本机选一份…', exact=True).click()
        replacement = dict(upload, name='线谱笔记.pdf', buffer=pdf_bytes()+b'\n% staff notes\n')
        await (await chooser.value).set_files(replacement)
        await page.wait_for_selector('#dlgPick', state='visible')
        assert await page.evaluate('pdfHash') == numbered_hash
        await page.keyboard.press('Escape')
        assert await page.evaluate('pdfHash') == numbered_hash
        assert await page.evaluate('(async()=> (await idbGet(idb,"projects","ptest")).sheets.find(s=>s.id==="numbered").pdf.hash)()') == numbered_hash
        print('OK   曲目库换谱先选目标，取消不改简谱绑定')
        # Menu replacement also must allow choosing a sheet other than the active one.
        await page.evaluate('()=>{showLib(false);$("bReplaceSheet").click()}')
        await page.set_input_files('#fPdf', replacement)
        await page.get_by_role('button', name='五线谱', exact=True).click()
        await page.wait_for_function('()=>activeSheet==="default" && M[0].nx===.2 && pdfName==="线谱笔记.pdf"')
        assert await page.evaluate('track.sheets.find(s=>s.id==="numbered").pdf.hash') == numbered_hash
        assert await page.evaluate('SHEET_MARKS.numbered[0].nx===.6 && E[0].t===2')
        print('OK   当前简谱时换入线谱，只更新所选线谱，简谱文件和标注保留')
        await page.evaluate('flushSave()')
        assert await page.evaluate('(async()=> (await idbGet(idb,"marks","ptest")).data.ts)()') == ann_time
        assert await page.evaluate('track.mediaUpdatedAt') > media_time
        media_time = await page.evaluate('track.mediaUpdatedAt')
        await page.evaluate('async()=>{M[0].nx=.25;save();await flushSave()}')
        assert await page.evaluate('(async()=> (await idbGet(idb,"marks","ptest")).data.ts)()') > ann_time
        assert await page.evaluate('track.mediaUpdatedAt') == media_time
        await page.evaluate('drawLib()')
        assert '标注／时间点' in await page.locator('.annotationUpdated').inner_text()
        assert '本机谱子／音频' in await page.locator('.mediaUpdated').inner_text()
        print('OK   文件更新不刷新标注时间，编辑标注不刷新文件时间，曲目库分开展示')
        await page.set_input_files('#fPdf', upload)
        await page.click('#dlgProjOk')
        await page.get_by_role('button', name='＋ 新增谱面', exact=True).click()
        await page.wait_for_function('()=>track.sheets.length===3 && M.length===0')
        assert await page.evaluate('E[0].t===2')
        print('OK   新增谱面使用空坐标并保留时间轴')
        upload['name']='新曲.pdf'
        await page.set_input_files('#fPdf', upload)
        await page.click('#dlgProjNew')
        await page.wait_for_function('()=>track.name==="新曲"')
        assert await page.evaluate('(async()=> (await idbAll(idb,"projects")).length)()') == 2
        assert not errors, errors
        print('OK   同一 PDF 可明确新建项目，浏览器无运行错误')
        await browser.close()
    finally: server.shutdown()
asyncio.run(main())
