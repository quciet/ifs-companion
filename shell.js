'use strict';
const $ = id => document.getElementById(id);
const frame = $('comparison');
let jobs = [], installation = null;
const names = {companion:'Companion',compare:'Compare Runs',settings:'Settings',manage:'Manage tools',optional:'Tool',tune:'Tune Model',code:'Explore Code',scenario:'Create Scenario'};
async function api(path,body){const response=await fetch(path,body?{method:'POST',headers:{'Content-Type':'application/json','X-Companion-Token':document.querySelector('meta[name=companion-token]').content},body:JSON.stringify(body)}:{});const data=await response.json();if(!response.ok)throw Error(data.error||'Request failed');return data;}
function status(error){$('shellStatus').textContent=error?error.message:'';}
let currentView='companion';
const toolFrames=new Map();
function activeToolFrame(){return currentView==='compare'?frame:currentView==='optional'?(toolFrames.get(activeToolId)||$('optionalTool')):null;}
function updateToolControls(){
  const session=activeToolFrame()?.contentWindow?.companionSession;
  $('backView').classList.toggle('hidden',currentView!=='manage'&&!session?.canGoBack());
  $('stopTool').classList.toggle('hidden',!activeToolFrame());
}
$('backView').onclick=()=>{if(currentView==='manage')navigate('settings');else activeToolFrame()?.contentWindow?.companionSession?.back();updateToolControls();};
$('stopTool').onclick=async()=>{
  const target=activeToolFrame(),button=$('stopTool');if(!target||button.disabled)return;
  const session=target.contentWindow.companionSession;
  if(!session){status(Error('Update this tool to use Stop while preserving selections.'));return;}
  button.disabled=true;button.textContent='Stopping...';
  try{await session.stop();status(null);await refreshRecent();await refreshTools();}
  catch(error){status(error);}finally{button.disabled=false;button.textContent='Stop';updateToolControls();}
};
window.addEventListener('message',event=>{if(event.origin===location.origin&&event.source===activeToolFrame()?.contentWindow&&event.data?.type==='tool-navigation')updateToolControls();});
function navigate(view){if(view==='compare'&&!comparisonEnabled){view='manage';toolMessage('Install Compare Runs to use this tool.');}currentView=view; if(view==='manage'){refreshTools().then(renderOfficialTools).catch(status);loadOfficialTools(true);}if(view==='compare'&&frame.getAttribute('src')==='about:blank')frame.src='/compare';const target=['companion','compare','settings','manage','optional'].includes(view)?view:'unavailable';for(const id of ['companion','compare','settings','manage','optional','unavailable'])$(id+'View').classList.toggle('hidden',id!==target);$('viewTitle').textContent=names[view];$('newChat').classList.toggle('hidden',view!=='companion');document.querySelector('[data-view="companion"]').classList.toggle('active',view==='companion');$('unavailableTitle').textContent=names[view];updateToolControls();}
document.querySelectorAll('[data-view]').forEach(button=>button.onclick=()=>navigate(button.dataset.view));
document.querySelectorAll('[data-prompt]').forEach(button=>button.onclick=()=>{$('prompt').value=button.dataset.prompt;$('prompt').focus();});
function message(content,reply=false){const element=document.createElement('div');element.className='message'+(reply?' reply':'');element.textContent=content;$('messages').append(element);$('welcome').classList.add('hidden');$('messages').classList.remove('hidden');element.scrollIntoView({block:'nearest'});return element;}
function action(parent,label,callback){const button=document.createElement('button');button.type='button';button.textContent=label;button.onclick=callback;parent.append(button);}
$('composer').onsubmit=event=>{event.preventDefault();const prompt=$('prompt').value.trim();if(!prompt)return;message(prompt);$('prompt').value='';if(/compar|runfiles?|run\.db/i.test(prompt)){const reply=message('Open Compare Runs to select the two runfiles, variables, and tolerances. The comparison uses the existing IFs model-vetting engine.',true);action(reply,'Open Compare Runs',()=>navigate('compare'));}else{message('AI is not connected yet, so I cannot interpret model questions or generate scenarios. You can use Compare Runs directly from Tools.',true);}};
$('newChat').onclick=()=>{$('messages').replaceChildren();$('messages').classList.add('hidden');$('welcome').classList.remove('hidden');$('prompt').value='';navigate('companion');};
// Expansion preferences survive the randomly assigned local engine port.
async function preferences(){try{const data=await api('/api/ui-preferences');for(const id of ['toolsGroup','recentGroup'])$(id).open=Boolean(data[id]);}catch(error){status(error);}for(const id of ['toolsGroup','recentGroup'])$(id).addEventListener('toggle',()=>{api('/api/ui-preferences',{toolsGroup:$('toolsGroup').open,recentGroup:$('recentGroup').open}).catch(status);});}
function applyInstallation(data){
  installation=data;
  $('installation').value=data.installation||'';
  const version=String(data.version||'').replace(/^\s*(?:IFs\s+)?Version\s*/i,'').trim();
  $('installationLabel').textContent=data.installation?'IFs '+version+' Base: '+data.base_year:'No IFs installation selected';
  $('settingsStatus').textContent=data.installation?'IFs '+version+' | Base year '+data.base_year+' | '+data.runs.length+' supported runfiles found.':'Choose the folder containing DATA and RUNFILES.';
}
$('saveInstallation').onclick=async()=>{const button=$('saveInstallation');button.disabled=true;try{const data=await api('/api/installation',{installation:$('installation').value});applyInstallation(data);if(frame.contentWindow.applyInstallation)frame.contentWindow.applyInstallation(data);status(null);}catch(error){$('settingsStatus').textContent=error.message;}finally{button.disabled=false;}};
function selectInstallationFolder(){
  const initial=$('installation').value;
  if(!window.chrome?.webview)return api('/api/select-installation',{installation:initial});
  return new Promise((resolve,reject)=>{
    const bridge=window.chrome.webview;
    const receive=event=>{
      if(event.data?.type!=='installation-selected')return;
      bridge.removeEventListener('message',receive);
      if(event.data.error)reject(Error(event.data.error));else resolve(event.data);
    };
    bridge.addEventListener('message',receive);
    try{bridge.postMessage({type:'select-installation',installation:initial});}
    catch(error){bridge.removeEventListener('message',receive);reject(error);}
  });
}
$('browse').onclick=async()=>{const button=$('browse');if(button.disabled)return;button.disabled=true;try{const data=await selectInstallationFolder();if(data.installation){$('installation').value=data.installation;await $('saveInstallation').onclick();}}catch(error){$('settingsStatus').textContent=error.message;}finally{button.disabled=false;}};
async function openRecent(id){try{const running=jobs.find(j=>j.status==='running');if(running&&running.id!==id){status(Error('A comparison is running. Wait for it to finish before opening a different report.'));return;}const win=frame.contentWindow;if(!win.openCompanionReport)throw Error('Compare Runs is still loading. Please try again.');await win.openCompanionReport(id);navigate('compare');status(null);}catch(error){status(error);}}
async function refreshRecent(){try{const data=await api('/api/recent');jobs=data.jobs;$('recent').replaceChildren();$('running').textContent=jobs.some(j=>j.status==='running')?'1 running':'';if(!jobs.length)$('recent').textContent='No comparisons yet.';for(const item of jobs){const button=document.createElement('button');button.textContent=item.title;const note=document.createElement('small');note.textContent=item.status+(item.created?' · '+new Date(item.created*1000).toLocaleDateString():'');button.append(note);button.onclick=()=>openRecent(item.id);$('recent').append(button);}}catch(error){status(error);}}
frame.addEventListener('load',()=>{updateToolControls();const win=frame.contentWindow;const link=win.document.getElementById('openSettings');if(link)link.onclick=()=>navigate('settings');});
api('/api/installation').then(applyInstallation).catch(error=>{$('settingsStatus').textContent=error.message;status(error);});preferences();refreshRecent();setInterval(refreshRecent,3000);

$('optionalTool').addEventListener('load',updateToolControls);
let installedTools = [], updateToolId = null, activeToolId = null, toolBusy = false;
function toolMessage(text,error=false) { $('toolStatus').textContent=text;$('toolStatus').classList.toggle('error',error); }
function confirmTool(title,body,label){
  const dialog=$('toolDialog');$('toolDialogTitle').textContent=title;$('toolDialogBody').textContent=body;$('toolDialogConfirm').textContent=label;
  return new Promise(resolve=>{dialog.addEventListener('close',()=>resolve(dialog.returnValue==='confirm'),{once:true});dialog.returnValue='cancel';dialog.showModal();});
}
function forgetTool(id){
  if(id==='ifs-model-vetting')frame.src='about:blank';
  if(toolFrames.has(id)){toolFrames.get(id).remove();toolFrames.delete(id);}
  if(activeToolId===id)activeToolId=null;
}
async function closeForUpdate(id){if(installedTools.some(t=>t.id===id)){await api('/api/tools/close',{id});forgetTool(id);}}
let comparisonEnabled=true;
async function refreshTools() {
  const data = await api('/api/tools'); installedTools = data.tools;comparisonEnabled=data.comparison_enabled!==false;
  document.querySelector('#toolsGroup [data-view=compare]').hidden=!comparisonEnabled;
  if(comparisonEnabled&&frame.getAttribute('src')==='about:blank')frame.src='/compare';
  $('installedTools').replaceChildren();
  for (const tool of installedTools) {
    if(tool.id!=='ifs-model-vetting')action($('installedTools'), tool.name, () => openTool(tool));
  }
  renderOfficialTools();
}
async function uninstallTool(tool){
  if(toolBusy||!await confirmTool('Uninstall '+tool.name+'?', 'The tool will close and be removed from your sidebar. Your settings and saved work will be kept. If work is running, stop it before uninstalling.', 'Uninstall'))return;
  toolBusy=true;renderOfficialTools();toolMessage('Uninstalling '+tool.name+'…');
  try{await api('/api/tools/uninstall',{id:tool.id});forgetTool(tool.id);await refreshTools();toolMessage(tool.name+' uninstalled. Your saved work was kept.');}
  catch(error){toolMessage(error.message,true);}
  finally{toolBusy=false;renderOfficialTools();}
}
function chooseTool(id=null){if(toolBusy)return;updateToolId=id;$('toolPackage').value='';$('toolPackage').click();}
$('installTool').onclick=()=>chooseTool();
$('toolPackage').onchange=async()=>{
  const file=$('toolPackage').files[0];if(!file)return;
  if(!await confirmTool('Install package from file?',file.name+'\nOnly install packages from people you trust. This may replace an installed version, including with a beta or older version. Saved work is kept, but older tools may not support newer data.','Install'))return;
  toolBusy=true;$('installTool').disabled=true;renderOfficialTools();toolMessage('Installing '+file.name+'… Large tools can take a few minutes.');
  try {
    if(updateToolId)await closeForUpdate(updateToolId);
    const response=await fetch('/api/tools/install?allow_older=1'+(updateToolId?'&id='+encodeURIComponent(updateToolId):''),{method:'POST',headers:{'Content-Type':'application/octet-stream','X-Companion-Token':document.querySelector('meta[name=companion-token]').content},body:file});
    const result=await response.json();if(!response.ok)throw Error(result.error||'Installation failed.');
    await refreshTools();if(result.id==='ifs-model-vetting')frame.src='/compare';renderOfficialTools();toolMessage(result.name+' '+result.version+' is ready. Open it from Tools.');
  }catch(error){toolMessage(error.message,true);}finally{toolBusy=false;$('installTool').disabled=false;renderOfficialTools();}
};
async function openTool(tool){
  if(tool.id==='ifs-model-vetting'){navigate('compare');return;}
  try{status(null);$('viewTitle').textContent='Opening '+tool.name+'…';const result=await api('/api/tools/open',{id:tool.id});
    let target=toolFrames.get(tool.id);
    if(!target){target=document.createElement('iframe');target.title=tool.name;target.src=result.url;target.addEventListener('load',updateToolControls);toolFrames.set(tool.id,target);$('optionalView').append(target);}
    $('optionalTool').classList.add('hidden');for(const [id,item] of toolFrames)item.classList.toggle('hidden',id!==tool.id);activeToolId=tool.id;
    navigate('optional');$('viewTitle').textContent=tool.name;await refreshTools();
  }catch(error){status(error);navigate('manage');toolMessage(error.message);}
}
refreshTools().catch(status);

let officialTools = [], catalogLoaded = false, catalogLoading = false, downloadTimer = null;
function compareVersion(a,b){const [ac,ap]=a.split('-'),[bc,bp]=b.split('-'),x=ac.split('.').map(Number),y=bc.split('.').map(Number);for(let i=0;i<3;i++)if(x[i]!==y[i])return x[i]-y[i];return ap===bp?0:!ap?1:!bp?-1:ap.localeCompare(bp,undefined,{numeric:true});}
const includedTools=[
  {id:'ifs-model-vetting',name:'Compare Runs',description:'Compare IFs runfiles and inspect differences.',included:true},
  {id:'ifs-code-reader',name:'Explore Code',description:'Explore the model and its relationships.',status:'coming-soon'},
  {id:'ifs-scenario-builder',name:'Create Scenario',description:'Build scenarios for your IFs model.',status:'coming-soon'}
];
function directoryTools(){
  const merged=new Map(includedTools.map(tool=>[tool.id,{...tool,official:{...tool,status:'coming-soon'},included:tool.included&&comparisonEnabled}]));
  merged.set('ifs-autotune',{id:'ifs-autotune',name:'IFs Autotune',official:{status:'coming-soon'},status:'coming-soon'});
  for(const tool of officialTools)merged.set(tool.id,{...merged.get(tool.id),...tool,official:tool});
  for(const tool of installedTools)merged.set(tool.id,{...merged.get(tool.id),...tool,installed:tool});
  for(const tool of merged.values()){const builtIn=includedTools.find(item=>item.id===tool.id);if(builtIn){tool.name=builtIn.name;tool.description=builtIn.description;}if(tool.id==='ifs-autotune')tool.description='Tune parameters and review model fit.';}
  return [...merged.values()].sort((a,b)=>Number(!!(b.installed||b.included))-Number(!!(a.installed||a.included))||a.name.localeCompare(b.name));
}
async function installOfficial(tool){
  if(toolBusy)return;
  toolBusy=true;renderOfficialTools();
  try{await closeForUpdate(tool.id);await api('/api/tools/official-install',{id:tool.id});await pollDownload();}
  catch(error){toolBusy=false;$('catalogStatus').textContent=error.message;renderOfficialTools();}
}
function renderOfficialTools(){
  const directory=$('toolDirectory');directory.replaceChildren();
  const query=$('toolSearch').value.trim().toLowerCase(),filter=$('toolFilter').value;
  const tools=directoryTools().filter(tool=>{
    const ready=!!(tool.installed||tool.included);
    return (filter==='all'||filter==='installed'&&ready||filter==='available'&&!ready)&&((tool.name+' '+(tool.description||'')).toLowerCase().includes(query));
  });
  $('toolCount').textContent=tools.length+' tool'+(tools.length===1?'':'s');
  if(!tools.length){const empty=document.createElement('p');empty.className='muted';empty.textContent='No tools match your search.';directory.append(empty);}
  for(const tool of tools){
    const row=document.createElement('article');row.className='tool-row';
    const icon=document.createElement('div');icon.className='tool-icon';icon.setAttribute('aria-hidden','true');icon.textContent=tool.name.split(/\s+/).map(word=>word[0]).slice(0,2).join('');
    const info=document.createElement('div');info.className='tool-info';
    const title=document.createElement('h3');title.textContent=tool.name;
    const description=document.createElement('p');description.textContent=tool.description||'An installed IFs tool.';
    const note=document.createElement('small');
    const official=tool.official,installed=tool.installed,ready=!!(installed||tool.included);
    const published=official&&official.status!=='coming-soon';
    const installedVersion=installed?.version||(tool.included?'0.1.0':null);
    const newer=published&&official.compatible&&installedVersion&&compareVersion(official.version,installedVersion)>0;
    note.textContent=installed?'v'+installed.version+' / Installed':tool.included?'v0.1.0 / Included':published?'v'+official.version:'Online release coming soon';
    if(official)note.textContent+=' / Official tool';
    if(newer)note.textContent+=' / Update available';
    else if(ready&&published&&official.compatible)note.textContent+=' / Up to date';
    if(published&&!official.compatible)note.textContent+=' / Requires Companion '+official.min_companion_version;
    info.append(title,description,note);row.append(icon,info);
    const controls=document.createElement('div');controls.className='tool-controls';
    const menu=document.createElement('details');menu.className='tool-menu';
    const trigger=document.createElement('summary');trigger.textContent=ready?'\u2026':'+';trigger.setAttribute('aria-label',(ready?'Manage ':'Add ')+tool.name);
    const items=document.createElement('div');items.className='tool-menu-items';
    function option(label,callback,disabled=false){action(items,label,()=>{menu.open=false;callback();});items.lastElementChild.disabled=toolBusy||disabled;}
    if(ready){
      if(official)option('Update',()=>installOfficial(official),!newer);
      option('Update from file',()=>chooseTool(tool.id));
      option('Uninstall',()=>uninstallTool(installed||tool));items.lastElementChild.className='danger';
    }else{
      option('Install',()=>installOfficial(official),!published||!official.compatible);
      option('Install from file',()=>chooseTool(tool.id));
    }
    menu.append(trigger,items);controls.append(menu);
    menu.addEventListener('toggle',()=>{if(menu.open)document.querySelectorAll('.tool-menu[open]').forEach(other=>{if(other!==menu)other.open=false;});});
    row.append(controls);directory.append(row);
  }
}
$('toolSearch').oninput=renderOfficialTools;
$('toolFilter').onchange=renderOfficialTools;
document.addEventListener('click',event=>{document.querySelectorAll('.tool-menu[open]').forEach(menu=>{if(!menu.contains(event.target))menu.open=false;});});
document.addEventListener('keydown',event=>{if(event.key==='Escape')document.querySelectorAll('.tool-menu[open]').forEach(menu=>{menu.open=false;menu.querySelector('summary').focus();});});
async function loadOfficialTools(force=false){
  if(catalogLoading || catalogLoaded&&!force)return;
  catalogLoading=true;$('catalogStatus').textContent='Checking official tools…';
  try{const data=await api('/api/tools/catalog');officialTools=data.tools;catalogLoaded=true;renderOfficialTools();$('catalogStatus').textContent='Official catalog checked.';}
  catch(error){$('catalogStatus').textContent=error.message;}
  finally{catalogLoading=false;}
}
async function pollDownload(){
  clearTimeout(downloadTimer);
  try{
    const state=await api('/api/tools/download');
    const active=['checking','downloading','verifying','installing'].includes(state.status);
    toolBusy=active;$('installTool').disabled=active;renderOfficialTools();
    if(state.status!=='idle')$('catalogStatus').textContent=state.message;
    $('downloadProgress').hidden=!active;
    if(state.total&&state.status==='downloading'){$('downloadProgress').max=state.total;$('downloadProgress').value=state.received;}
    else $('downloadProgress').removeAttribute('value');
    if(active){downloadTimer=setTimeout(pollDownload,750);return;}
    if(state.status==='complete'){
      await refreshTools();renderOfficialTools();
      if(state.id==='ifs-model-vetting')frame.src='/compare';
    }
  }catch(error){$('catalogStatus').textContent=error.message;toolBusy=false;$('installTool').disabled=false;}
}

pollDownload();
