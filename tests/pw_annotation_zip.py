import asyncio,functools,http.server,pathlib,threading,json,zipfile,io
from playwright.async_api import async_playwright
ROOT=pathlib.Path(__file__).resolve().parents[1]
class Quiet(http.server.SimpleHTTPRequestHandler):
 def log_message(self,*args):pass
srv=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(ROOT)))
threading.Thread(target=srv.serve_forever,daemon=True).start()
def package(files):
 b=io.BytesIO()
 with zipfile.ZipFile(b,'w',zipfile.ZIP_DEFLATED) as z:
  for name,data in files.items():z.writestr(name,json.dumps(data) if not isinstance(data,str) else data)
 return list(b.getvalue())
async def main():
 async with async_playwright() as pw:
  b=await pw.chromium.launch();p=await b.new_page();errors=[];p.on('pageerror',lambda e:errors.append(str(e)))
  await p.goto(f'http://127.0.0.1:{srv.server_port}/player.html');await p.wait_for_function('()=>idb!==null')
  item={'id':'pzip1','name':'同名.pdf','aka':[],'pdf':None,'sheets':[], 'data':{'v':7,'ts':100,'M':[],'sheets':{'default':{'M':[]}},'modes':{'标准':{'E':[],'BEATS':{'1:0:3/4:3:1':{'t':1.2,'src':'tap'}}}}}}
  await p.evaluate('async it=>{await idbPut(idb,"projects",{id:it.id,name:it.name,aka:[],audios:[]});await idbPut(idb,"marks",{pid:it.id,data:it.data})}',item)
  other=json.loads(json.dumps(item));other['id']='pzip2'
  await p.evaluate('async it=>{await idbPut(idb,"projects",{id:it.id,name:it.name,aka:[],audios:[]});await idbPut(idb,"marks",{pid:it.id,data:it.data})}',other)
  async with p.expect_download() as dl:await p.evaluate("$('libExpAll').click()")
  download=await dl.value;assert download.suggested_filename=='annotations.zip'
  data=pathlib.Path(await download.path()).read_bytes()
  with zipfile.ZipFile(io.BytesIO(data)) as z:
   assert len(z.namelist())==2 and len(set(z.namelist()))==2
   assert all(n.startswith('annotations/') for n in z.namelist())
   exported=[json.loads(z.read(n)) for n in z.namelist()]
   assert all(x['app']=='sheetplayer-song' and x['item']['data']['modes']['标准']['BEATS'] for x in exported)
  async def read(raw):return await p.evaluate('(bytes)=>readAnnotationPackage(new File([new Uint8Array(bytes)],"test.zip"))',raw)
  repo=package({'annotations/'+f.name:json.loads(f.read_text()) for f in (ROOT/'annotations').glob('*.json') if f.name!='index.json'})
  assert len(await read(repo))>0

  assert len(await read(list(data)))==2
  assert len(await read(package({'SheetPlayer-main/annotations/同名.json':exported[0],'SheetPlayer-main/player.html':'ignore','annotations/index.json':'ignore'})))==1
  legacy={'app':'sheetplayer','v':3,'items':[item]}
  assert len(await read(list(json.dumps(legacy).encode())))==1
  for bad in [package({'annotations/a.json':exported[0],'annotations/b.json':'bad json'}),package({'annotations/a.json':exported[0],'annotations/b.json':exported[0]}),package({'other.json':exported[0]})]:
   try:await read(bad);raise AssertionError('Accepted bad archive')
   except Exception as e:assert 'Accepted bad archive' not in str(e)
  rows=await p.evaluate('(items)=>previewAnnotationPackage(items)',[item]);assert rows[0]['state']=='相同'
  changed=json.loads(json.dumps(item));changed['data']['ts']=200;changed['data']['sheets']['default']['M']=[{'m':1,'page':1,'nx':.1,'ny':.1}]
  rows=await p.evaluate('(items)=>previewAnnotationPackage(items)',[changed]);assert rows[0]['state']=='更新'
  changed['data']['ts']=50
  rows=await p.evaluate('(items)=>previewAnnotationPackage(items)',[changed]);assert rows[0]['state']=='冲突'
  # Real upload must wait for preview confirmation; cancel leaves the database intact.
  await p.set_input_files('#libImpAll',{'name':'annotations.zip','mimeType':'application/zip','buffer':bytes(package({'annotations/a.json':{'app':'sheetplayer-song','v':1,'item':changed}}))})
  await p.wait_for_selector('#dlgPick',state='visible')
  assert '冲突' in await p.inner_text('#dlgPick')
  assert await p.evaluate('(async()=> (await idbGet(idb,"marks","pzip1")).data.ts)()')==100
  await p.keyboard.press('Escape')
  assert await p.evaluate('(async()=> (await idbGet(idb,"marks","pzip1")).data.ts)()')==100
  # Confirm force import through the UI, while preserving absent songs.
  await p.set_input_files('#libImpAll',{'name':'annotations.zip','mimeType':'application/zip','buffer':bytes(package({'annotations/a.json':{'app':'sheetplayer-song','v':1,'item':changed}}))})
  await p.wait_for_selector('#dlgPick',state='visible')
  await p.get_by_role('button',name='导入并覆盖冲突',exact=True).click()
  await p.wait_for_function('(async()=> (await idbGet(idb,"marks","pzip1")).data.ts===50)')
  assert await p.evaluate('(async()=>!!(await idbGet(idb,"marks","pzip2")))()')
  await p.evaluate('async()=>{for(const store of ["projects","marks"])for(const rec of await idbAll(idb,store))await idbDel(idb,store,rec.id||rec.pid)}')
  await p.evaluate('(items)=>importAnns(items)',[item,other])
  assert await p.evaluate('(async()=> (await idbAll(idb,"projects")).length)()')==2
  assert not errors,errors
  print('OK ZIP export roundtrip, duplicate filenames, repository ZIP, legacy JSON, full validation, preview classifications and cancel')
  await b.close()
try:asyncio.run(main())
finally:srv.shutdown()
