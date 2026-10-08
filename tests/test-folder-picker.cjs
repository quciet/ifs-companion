const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('shell.js','utf8');
const picker = source.slice(source.indexOf('function selectInstallationFolder'), source.indexOf('async function openRecent'));
async function check(result) {
  const elements = {installation:{value:'D:\\IFs'},browse:{disabled:false},settingsStatus:{textContent:''},saveInstallation:{onclick:async()=>{saved++;}}};
  let saved=0, posted=0;
  const listeners=new Set();
  const bridge={addEventListener:(_,fn)=>listeners.add(fn),removeEventListener:(_,fn)=>listeners.delete(fn),postMessage:message=>{assert.equal(message.type,'select-installation');assert.equal(message.installation,'D:\\IFs');posted++;}};
  const context=vm.createContext({window:{chrome:{webview:bridge}},$:id=>elements[id],api:()=>{throw Error('Desktop picker must not call the HTTP helper');}});
  vm.runInContext(picker,context);
  const pending=elements.browse.onclick();
  assert.equal(elements.browse.disabled,true);
  await elements.browse.onclick();assert.equal(posted,1);
  for(const receive of listeners)receive({data:{type:'unrelated'}});
  assert.equal(listeners.size,1);
  for(const receive of listeners)receive({data:{type:'installation-selected',...result}});
  await pending;
  assert.equal(elements.browse.disabled,false);assert.equal(listeners.size,0);
  assert.equal(saved,result.installation?1:0);
  assert.equal(elements.installation.value,result.installation||'D:\\IFs');
  assert.equal(elements.settingsStatus.textContent,result.error||'');
}
(async()=>{
  await check({installation:'D:\\Chosen'});
  await check({installation:null});
  await check({error:'Could not open picker'});
  let called=false;
  const context=vm.createContext({window:{},$:()=>({value:'D:\\IFs'}),api:async(path,body)=>{called=true;assert.equal(path,'/api/select-installation');assert.equal(body.installation,'D:\\IFs');return {installation:null};}});
  vm.runInContext(picker,context);await context.selectInstallationFolder();assert.equal(called,true);
  console.log('Browse bridge: selection, cancellation, error, duplicate clicks, and browser fallback passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
