"""Shared-song sync, local edits, ancestry conflicts, direct uploads, and directory discovery."""
import asyncio
import functools
import hashlib
import http.server
import json
from pathlib import Path
import socketserver
import threading
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
server = socketserver.TCPServer(('127.0.0.1', 0), handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
URL = f'http://127.0.0.1:{server.server_address[1]}/player.html'


def song(n=1, ts=100, ident='p-shared-test'):
    return {'id': ident, 'name': ident, 'aka': [], 'sheets': [], 'pdf': None, 'pdfHistory': [],
            'data': {'v': 6, 'M': [{'page': 1, 'nx': .1, 'ny': .2, 'm': i + 1} for i in range(n)],
                     'modes': {'标准': {'E': [], 'TEMPO': [], 'METER': [], 'FORM': [], 'offset': 0}},
                     'activeMode': '标准', 'ts': ts}}


def remote(item, revision):
    return [{'item': item, 'revision': revision}]


async def main():
    errors = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page()
        page.on('pageerror', lambda e: errors.append(str(e)))
        await page.goto(URL)
        await page.wait_for_function('idb !== null')
        sync = lambda records: page.evaluate('(records)=>syncSharedSongs(records)', records)
        changes = lambda: page.evaluate('changedSongs()')
        await sync(remote(song(), 'r1'))
        assert await page.evaluate("(async()=> (await idbAll(idb,'projects'))[0].id)()") == 'p-shared-test'
        assert await changes() == []
        print('OK   首次同步继承共享 ID，归一化后无待提交修改')

        # Remote changed but its clock is older: ancestry wins.
        await sync(remote(song(2, 1), 'r2'))
        assert await page.evaluate("(async()=> (await idbGet(idb,'marks','p-shared-test')).data.M.length)()") == 2
        await page.evaluate("""async()=>{const m=await idbGet(idb,'marks','p-shared-test');
          m.data.M.push({page:1,nx:.5,ny:.2,m:3});m.data.ts=9999;await idbPut(idb,'marks',m)}""")
        assert len(await changes()) == 1
        await sync(remote(song(2, 1), 'r2'))
        assert len((await changes())[0]['item']['data']['M']) == 3
        print('OK   不依赖设备时钟；远端未变时保留本地编辑')

        # Real conflict dialog: cancel preserves both versions and blocks export.
        pending = asyncio.create_task(sync(remote(song(4), 'r3')))
        await page.wait_for_selector('#dlgPick', state='visible')
        await page.keyboard.press('Escape')
        result = await pending
        assert result['conflicts'] == 1
        assert await page.evaluate("(async()=>!!(await idbGet(idb,'projects','p-shared-test')).sharedConflict)()")
        await page.evaluate("exportSharedSong('p-shared-test')")
        assert '处理这首曲目的冲突' in await page.inner_text('#msg')
        pending = asyncio.create_task(sync(remote(song(4), 'r3')))
        await page.wait_for_selector('#dlgPick', state='visible')
        await page.click('#dlgPickBtns button:has-text("保留本机并准备提交")')
        await pending
        c = (await changes())[0]
        assert c['baseRevision'] == 'r3' and len(c['item']['data']['M']) == 3
        assert await page.evaluate("(async()=>!!(await idbGet(idb,'projects','p-shared-test')).sharedBackup)()")
        print('OK   冲突取消保留双方；明确保留本机后采用新基础版本')

        # The card downloads the final uploadable file directly, without a bundle or script.
        await page.evaluate('drawLib()')
        async with page.expect_download() as event:
            await page.click('.share[data-h="p-shared-test"]')
        download = await event.value
        filename = download.suggested_filename
        uploaded_raw = Path(await download.path()).read_text()
        uploaded = json.loads(uploaded_raw)
        assert uploaded['app'] == 'sheetplayer-song' and uploaded['baseRevision'] == 'r3'
        assert filename == 'p-shared-test.json'
        assert await page.evaluate("sharedFilename({id:'p92af7050-rest',name:'新名字',sharedFile:'斯卡布罗集市--92af7050.json'})") == '斯卡布罗集市.json'
        assert len(await changes()) == 1  # Export is not publishing.
        await sync([{'item': uploaded['item'], 'revision': 'r4', 'filename': filename}])
        assert await changes() == []
        # Renaming a song must not change its upload destination, even after reloading.
        await page.evaluate("""async()=>{const p=await idbGet(idb,'projects','p-shared-test');
          p.name='新曲名';await idbPut(idb,'projects',p)}""")
        await page.reload(); await page.wait_for_function('idb !== null')
        async with page.expect_download() as event:
            await page.evaluate("exportSharedSong('p-shared-test')")
        renamed = await event.value
        assert renamed.suggested_filename == filename
        assert json.loads(Path(await renamed.path()).read_text())['item']['name'] == '新曲名'
        print('OK   卡片直接导出共享文件；同步确认；改名与刷新后保持原上传文件名')

        # Choosing remote preserves a restorable local backup.
        await page.evaluate("""async()=>{const m=await idbGet(idb,'marks','p-shared-test');m.data.M=[];
          await idbPut(idb,'marks',m)}""")
        pending = asyncio.create_task(sync(remote(song(5), 'r5')))
        await page.wait_for_selector('#dlgPick', state='visible')
        await page.click('#dlgPickBtns button:has-text("使用共享版本")')
        await pending
        assert await changes() == []
        async with page.expect_download() as event:
            pending = asyncio.create_task(page.evaluate("$('libConflictBackup').onclick()"))
            await page.wait_for_selector('#dlgPick', state='visible')
            await page.click('#dlgPickBtns button:has-text("本机版本")')
            await pending
        backup = json.loads(Path(await (await event.value).path()).read_text())
        assert backup['app'] == 'sheetplayer' and backup['items'][0]['data']['M'] == []
        print('OK   使用共享版本后可导出、恢复冲突前本机标注')

        # Distinct shared IDs never coalesce even when their PDF/name match.
        other = song(1, ident='p-second'); other['name'] = 'p-shared-test'
        await sync(remote(other, 'b1'))
        assert await page.evaluate("(async()=> (await idbAll(idb,'projects')).length)()") == 2
        print('OK   不同共享 ID 不会因同名被误合并')

        # Emulate GitHub directory uploads, including a newly exported song, without index/script.
        context = await browser.new_context()
        real = await context.new_page()
        real.on('pageerror', lambda e: errors.append(str(e)))
        files = {p.name: p.read_bytes() for p in (ROOT / 'annotations').glob('*.json')}
        files[filename] = uploaded_raw.encode()
        status = [200]
        async def directory(route):
            await route.fulfill(status=status[0], content_type='application/json',
                body=json.dumps([{'type': 'file', 'name': name} for name in files]))
        async def serve(route):
            from urllib.parse import unquote
            name = unquote(route.request.url.rsplit('/', 1)[-1])
            await route.fulfill(status=200 if name in files else 404,
                content_type='application/json', body=files.get(name, b'{}'))
        await real.route('**api.github.com/**', directory)
        await real.route('**raw.githubusercontent.com/**', serve)
        await real.goto(URL)
        await real.wait_for_function('idb !== null')
        await real.evaluate("$('bSync').onclick()")
        assert await real.evaluate("(async()=> (await idbAll(idb,'projects')).length)()") == 15
        assert await real.evaluate('changedSongs()') == []
        # A receiver re-exports using the exact uploaded name, including Chinese characters.
        first_name = next(n for n in files if n != filename)
        first_id = json.loads(files[first_name])['item']['id']
        async with real.expect_download() as event:
            await real.evaluate('(id)=>exportSharedSong(id)', first_id)
        assert (await event.value).suggested_filename == first_name
        # Upload a replacement to the same path. No index update is involved.
        replacement = song(8); files[filename] = json.dumps({'app': 'sheetplayer-song', 'v': 1, 'item': replacement}).encode()
        await real.evaluate("$('bSync').onclick()")
        assert await real.evaluate("(async()=> (await idbGet(idb,'marks','p-shared-test')).data.M.length)()") == 8
        assert await real.evaluate('changedSongs()') == []
        print('OK   14 首原曲目加直接导出的新曲目自动发现；原名覆盖更新无需索引')
        files['重复下载 (1).json'] = files[filename]
        await real.evaluate("$('bSync').onclick()")
        assert '重复文件' in await real.inner_text('#msg')
        assert await real.evaluate("(async()=> (await idbAll(idb,'projects')).length)()") == 15
        del files['重复下载 (1).json']
        status[0] = 403
        await real.evaluate("$('bSync').onclick()")
        assert '暂时受限' in await real.inner_text('#msg')
        print('OK   重复上传不会静默覆盖，GitHub 读取受限时保留本机并提示')
        # Unified menu export also works without IndexedDB; new and historic imports remain valid.
        direct = await browser.new_page()
        direct.on('pageerror', lambda e: errors.append(str(e)))
        await direct.goto(URL + '?direct=1')
        await direct.wait_for_function("typeof annotationData==='function'")
        await direct.evaluate("pdfName='测试曲目.pdf'")
        assert await direct.locator('#bExpShared').count() == 0
        cases = [
            uploaded,
            song(3)['data'],
            {'v': 5, 'M': song(2)['data']['M'], 'E': [{'m': 1, 't': 2}]},
            [{'page': 1, 'nx': .1, 'ny': .2, 'm': 1, 't': 3}],
            {'1': 4, '2': 8},
        ]
        for value in cases:
            await direct.set_input_files('#fMap', {'name': '标注.json', 'mimeType': 'application/json',
                'buffer': json.dumps(value).encode()})
            await direct.wait_for_function("$('fMap').value === ''")
            assert '已导入' in await direct.inner_text('#msg')
        async with direct.expect_download() as event:
            await direct.evaluate("$('bExp').onclick()")
        menu_export = json.loads(Path(await (await event.value).path()).read_text())
        assert menu_export['app'] == 'sheetplayer-song'
        assert menu_export['item']['data']['modes']['标准']['E'] == [{'m': 1, 't': 4}, {'m': 2, 't': 8}]
        async with direct.expect_download() as event:
            await direct.evaluate("$('bExp').onclick()")
        repeated = json.loads(Path(await (await event.value).path()).read_text())
        assert repeated['item']['id'] == menu_export['item']['id']
        print('OK   菜单统一导出；新格式和四种历史格式可恢复；降级模式 ID 稳定')
        assert not errors, errors
        await browser.close()
    server.shutdown()


asyncio.run(main())
