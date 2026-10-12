"""Modal keyboard isolation, cancellation, focus and library entry paths."""
import asyncio
import functools
import http.server
from pathlib import Path
import socketserver
import threading
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass
server = socketserver.TCPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=str(ROOT)))
threading.Thread(target=server.serve_forever, daemon=True).start()
URL = f'http://127.0.0.1:{server.server_address[1]}/player.html'

def check(value, message):
    assert value, message
    print('OK   ' + message)

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={'width': 1440, 'height': 900})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        await page.goto(URL)
        await page.wait_for_function("()=>idb && $('lib').style.display==='flex'")
        await page.click('#libClose')
        await page.evaluate("()=>{M=[{page:1,nx:.2,ny:.3,m:1,h:.06}];E=[];syncNext();$('mode').value='time';syncMode()}")
        await page.click('#bMenu')
        await page.click('#bHelp')
        await page.locator('#helpClose').focus()
        for key in ['Equal', 'Backspace', 'ArrowRight']:
            await page.keyboard.press(key)
        check(await page.evaluate('aud.playbackRate===1 && aud.currentTime===0 && E.length===0'), '帮助内快捷键不改变音频或标注')
        await page.keyboard.press('Space')
        check(await page.evaluate("E.length===0 && !topModal()"), '空格正常激活关闭按钮，不穿透为打点')
        check(await page.evaluate("document.activeElement.id==='bMenu'"), '帮助关闭后焦点回到可见菜单入口')

        await page.evaluate("()=>{window.answer='pending';askText('输入测试','').then(v=>window.answer=v)}")
        for _ in range(9):
            await page.keyboard.press('Tab')
            check(await page.evaluate("$('dlg').contains(document.activeElement)"), 'Tab 保持在输入弹窗内')
        await page.locator('#dlgInp').focus()
        await page.keyboard.press('Shift+Tab')
        check(await page.evaluate("document.activeElement.id==='dlgOk'"), 'Shift+Tab 从首个控件循环到末尾')
        await page.fill('#dlgInp', '确认内容')
        await page.keyboard.press('Enter')
        check(await page.evaluate("window.answer==='确认内容' && E.length===0"), 'Enter 提交输入后不穿透为打点')
        check(await page.evaluate("!document.querySelector('[inert]')"), '关闭最后一个弹窗后恢复背景交互')

        for kind, expression in [
            ('选择', "askPick('选择测试',[{v:'yes',label:'确定'}])"),
            ('模式', "askMode('模式测试','标准')"),
        ]:
            await page.evaluate("()=>{window.answer='pending';" + expression + ".then(v=>window.answer=v)}")
            await page.keyboard.press('Escape')
            check(await page.evaluate("window.answer===null && !topModal()"), kind + '弹窗 Esc 正常取消并结束等待')

        await page.evaluate("()=>{window.answer='pending';askPick('返回测试',[{v:'yes',label:'确定'}]).then(v=>window.answer=v)}")
        await page.evaluate('history.back()')
        await page.wait_for_function("()=>window.answer===null")
        check(await page.evaluate("!topModal() && $('lib').style.display==='none' && history.state.v==='score'"), '浏览器返回先取消选择弹窗，留在谱面')

        await page.evaluate("showModal('davPop')")
        await page.locator('#davClose').focus()
        await page.evaluate("()=>{askPick('嵌套测试',[{v:'yes',label:'确定'}])}")
        await page.keyboard.press('Escape')
        check(await page.evaluate("topModal().id==='davPop' && document.activeElement.id==='davClose' && !$('davPop').inert && $('bar').inert"), '嵌套窗口关闭后恢复父窗口焦点，背景仍隔离')
        await page.keyboard.press('Escape')
        check(await page.evaluate("!topModal() && !document.querySelector('[inert]')"), '父窗口关闭后恢复所有背景')

        await page.evaluate('showLib(true)')
        await page.wait_for_timeout(200)
        check(not await page.is_visible('#libManage'), '曲目库默认收起低频管理操作')
        await page.click('#libMore')
        check(await page.is_visible('#bSync') and await page.is_visible('#libImpAll >> xpath=..'), '管理展开后备份与同步可达')
        await page.keyboard.press('Escape')
        check(not await page.is_visible('#libManage'), 'Esc 收起管理区')
        await page.fill('#libQ', '不匹配的关键词')
        await page.click('#libNew')
        await page.fill('#dlgInp', '新排练曲')
        await page.keyboard.press('Enter')
        await page.wait_for_selector('.libCard')
        check(await page.input_value('#libQ') == '', '新建后清除旧搜索，显示新项目')
        check('新排练曲' in await page.inner_text('.libCard'), '新项目卡片可见')
        check('＋ 导入谱子' in await page.inner_text('#msg'), '成功提示与实际按钮文案一致')
        await page.evaluate("()=>{window.answer='pending';askProj(new File(['test'],'test.pdf'),true).then(v=>window.answer=v)}")
        await page.wait_for_selector('#dlgProj', state='visible')
        await page.locator('.pjRow').focus()
        await page.keyboard.press('Space')
        check(await page.get_attribute('.pjRow', 'aria-checked') == 'true', '项目选择行支持键盘选中')
        await page.keyboard.press('Escape')
        check(await page.evaluate("window.answer===null && !topModal()"), '选项目弹窗正常取消并结束等待')
        check(not await page.is_visible('#plStart'), '空播放列表不展示无效播放操作')
        await page.click('.libCard .pladd')
        await page.wait_for_selector('#plStart', state='visible')
        check(await page.is_visible('#plStart'), '加入曲目后恢复完整播放列表操作')
        page.once('dialog', lambda dialog: asyncio.create_task(dialog.accept()))
        await page.click('#plClear')
        await page.wait_for_selector('#plStart', state='hidden')
        check(not await page.is_visible('#plStart'), '清空后恢复紧凑空态')
        for width in [320, 390, 820, 1440]:
            await page.set_viewport_size({'width':width,'height':900})
            check(await page.evaluate("$('lib').scrollWidth<=innerWidth"), f'{width}px 曲目库无横向溢出')
            check(await page.evaluate("Math.abs($('libNew').getBoundingClientRect().top-$('libClose').getBoundingClientRect().top)<2"), f'{width}px 主操作与关闭键保持同行')
        check(not errors, '无浏览器运行错误: ' + str(errors))
        await browser.close()
    server.shutdown()

asyncio.run(main())
