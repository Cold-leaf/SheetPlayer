"""Shared-song sync, local edits, ancestry conflicts, exports, and legacy fallback."""
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
        await page.evaluate("$('libExpChanges').onclick()")
        assert '处理待定冲突' in await page.inner_text('#msg')
        pending = asyncio.create_task(sync(remote(song(4), 'r3')))
        await page.wait_for_selector('#dlgPick', state='visible')
        await page.click('#dlgPickBtns button:has-text("保留本机并准备提交")')
        await pending
        c = (await changes())[0]
        assert c['baseRevision'] == 'r3' and len(c['item']['data']['M']) == 3
        assert await page.evaluate("(async()=>!!(await idbGet(idb,'projects','p-shared-test')).sharedBackup)()")
        print('OK   冲突取消保留双方；明确保留本机后采用新基础版本')

        # Exercise actual download and acknowledgement.
        async with page.expect_download() as event:
            pending = asyncio.create_task(page.evaluate("$('libExpChanges').onclick()"))
            await page.wait_for_selector('#dlgPick', state='visible')
            await page.click('#dlgPickBtns button:has-text("导出修改")')
            await pending
        download = await event.value
        bundle = json.loads(Path(await download.path()).read_text())
        assert bundle['app'] == 'sheetplayer-changes' and len(bundle['changes']) == 1
        assert len(await changes()) == 1  # Export is not publishing.
        await sync(remote(bundle['changes'][0]['item'], 'r4'))
        assert await changes() == []
        print('OK   修改包下载含基础版本；导出不清状态，合并后同步才确认')

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

        # Actual repository format and SHA hashes via the sync button, in a clean browser.
        context = await browser.new_context()
        real = await context.new_page()
        real.on('pageerror', lambda e: errors.append(str(e)))
        async def serve(route):
            name = route.request.url.rsplit('/', 1)[-1]
            path = ROOT / 'annotations' / name
            await route.fulfill(status=200 if path.exists() else 404,
                                content_type='application/json', body=path.read_bytes() if path.exists() else b'{}')
        await real.route('**raw.githubusercontent.com/**', serve)
        await real.goto(URL)
        await real.wait_for_function('idb !== null')
        await real.evaluate("$('bSync').onclick()")
        assert await real.evaluate("(async()=> (await idbAll(idb,'projects')).length)()") == 14
        assert await real.evaluate('changedSongs()') == []
        print('OK   实际 14 首迁移数据通过索引同步，全部建立干净基线')
        assert not errors, errors
        await browser.close()
    server.shutdown()


asyncio.run(main())
