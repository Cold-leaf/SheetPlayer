"""Mode edits persist audio bindings; shared imports immediately refresh mode controls."""
import asyncio, functools, http.server, socketserver, threading
from pathlib import Path
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parents[1]
class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*args): pass
srv=socketserver.TCPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(ROOT)))
threading.Thread(target=srv.serve_forever,daemon=True).start()
URL=f'http://127.0.0.1:{srv.server_address[1]}/player.html'
NAME='《雪花的快乐》博士合唱团2025"雪之舞，声之韵”新年音乐会'
async def main():
    async with async_playwright() as p:
        browser=await p.chromium.launch()
        pg=await browser.new_page(viewport={'width':390,'height':844},is_mobile=True,has_touch=True)
        errors=[];pg.on('pageerror',lambda e:errors.append(str(e)))
        await pg.goto(URL);await pg.wait_for_function('idb!==null')
        await pg.evaluate('''async name=>{
          pid='p-mode-persistence';track={id:pid,name:'模式测试',audios:[{hash:'test-audio',name:'现场.wav',mode:'现场'}],lastAudio:'test-audio',pdf:null};
          MODES={'标准':defaultModeData(),'现场':defaultModeData()};activeMode='现场';
          loadMode(activeMode);E=[{m:1,t:3.5,src:'tap'}];
          $('renMode').value=name;await $('bRenMode').onclick();
          const saved=await idbGet(idb,'projects',pid),marks=await idbGet(idb,'marks',pid);
          if(saved.audios[0].mode!==name)throw Error('音频绑定未落盘');
          if(marks.data.modes['现场']||marks.data.modes[name].E[0].t!==3.5)throw Error('模式名或时间点未保存');
        }''',NAME)
        await pg.reload();await pg.wait_for_function('idb!==null')
        # Resolve the expected local-vs-remote conflict explicitly in the test.
        await pg.evaluate('''async name=>{
          pid='p-mode-persistence';track=await idbGet(idb,'projects',pid);
          if(!applySave((await idbGet(idb,'marks',pid)).data))throw Error('不能恢复');
          if(activeMode!==name||track.audios[0].mode!==name||Object.keys(MODES).length!==2)throw Error('重开恢复旧模式');
          switchAudio=async()=>{};
          await selectAudio('test-audio',new Blob());
          if(Object.keys(MODES).length!==2||E[0].t!==3.5)throw Error('加载音频复活旧模式');
          window.confirm=()=>true;await $('bDelMode').onclick();
          if((await idbGet(idb,'projects',pid)).audios[0].mode!=='标准')throw Error('删除模式后的绑定未保存');
          askPick=async()=> 'remote';
          const remote={id:pid,name:track.name,data:{v:6,M:[],modes:{'标准':defaultModeData(),[name]:{...defaultModeData(),E:[{m:1,t:7}]}},activeMode:name,ts:Date.now()+1000}};
          await syncSharedSongs([{item:remote,revision:'mode-revision'}]);
          if($('modeSel').value!==name||$('lblMode').style.display==='none'||!Array.from($('modeSel').options).some(o=>o.value===name))throw Error('同步后模式控件未刷新');
          if(!$('audSel').textContent.includes('还没有音频'))throw Error('音频控件仍显示旧模式');
          // Old installations may still have an orphaned binding. Never invent a mode.
          track.audios[0].mode='现场';let asked=false;
          askPick=async()=>{asked=true;return null};
          await selectAudio('test-audio',new Blob());
          if(!asked||MODES['现场'])throw Error('取消修复时创建了旧模式');
          askPick=async()=>name;
          await selectAudio('test-audio',new Blob());
          if(MODES['现场']||(await idbGet(idb,'projects',pid)).audios[0].mode!==name)throw Error('修复绑定失败');
          if(!applySave({modes:{'标准':defaultModeData(),[name]:defaultModeData()},activeMode:name}))throw Error('空模式未恢复');
          if(Object.keys(MODES).length!==2)throw Error('空模式丢失');
          askMode=async()=> 'new:导入时新建';
          await importAudioFile(new File(['audio-test'],'new.wav',{type:'audio/wav'}));
          await flushSave();
          const imported=await idbGet(idb,'marks',pid);
          if(!imported.data.modes['导入时新建']||imported.data.activeMode!=='导入时新建')throw Error('导入音频的新模式未保存');
        }''',NAME)
        assert not errors,errors
        print('OK   重命名/删除绑定持久化、刷新重开、GitHub 同步即时显示、旧绑定修复和空模式恢复')
        await browser.close()
try: asyncio.run(main())
finally: srv.shutdown();srv.server_close()
