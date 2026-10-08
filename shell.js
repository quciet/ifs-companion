'use strict';
const $ = id => document.getElementById(id);
const frame = $('comparison');
let jobs = [], installation = null;
const names = {companion:'Companion',compare:'Compare Runs',settings:'Settings',manage:'Manage tools',optional:'Tool',tune:'Tune Model',code:'Explore Code',scenario:'Create Scenario'};
async function api(path,body){const response=await fetch(path,body?{method:'POST',headers:{'Content-Type':'application/json','X-Companion-Token':document.querySelector('meta[name=companion-token]').content},body:JSON.stringify(body)}:{});const data=await response.json();if(!response.ok)throw Error(data.error||'Request failed');return data;}
function status(error){$('shellStatus').textContent=error?error.message:'';}
function navigate(view){if(view==='manage'){refreshTools().then(renderOfficialTools).catch(status);loadOfficialTools();}if(view==='compare'&&frame.getAttribute('src')==='about:blank')frame.src='/compare';const target=['companion','compare','settings','manage','optional'].includes(view)?view:'unavailable';for(const id of ['companion','compare','settings','manage','optional','unavailable'])$(id+'View').classList.toggle('hidden',id!==target);$('viewTitle').textContent=names[view];$('newChat').classList.toggle('hidden',view!=='companion');document.querySelector('[data-view="companion"]').classList.toggle('active',view==='companion');$('unavailableTitle').textContent=names[view];}
document.querySelectorAll('[data-view]').forEach(button=>button.onclick=()=>navigate(button.dataset.view));
document.querySelectorAll('[data-prompt]').forEach(button=>button.onclick=()=>{$('prompt').value=button.dataset.prompt;$('prompt').focus();});
function message(content,reply=false){const element=document.createElement('div');element.className='message'+(reply?' reply':'');element.textContent=content;$('messages').append(element);$('welcome').classList.add('hidden');$('messages').classList.remove('hidden');element.scrollIntoView({block:'nearest'});return element;}
function action(parent,label,callback){const button=document.createElement('button');button.type='button';button.textContent=label;button.onclick=callback;parent.append(button);}
$('composer').onsubmit=event=>{event.preventDefault();const prompt=$('prompt').value.trim();if(!prompt)return;message(prompt);$('prompt').value='';if(/compar|runfiles?|run\.db/i.test(prompt)){const reply=message('Open Compare Runs to select the two runfiles, variables, and tolerances. The comparison uses the existing IFs model-vetting engine.',true);action(reply,'Open Compare Runs',()=>navigate('compare'));}else{message('AI is not connected yet, so I cannot interpret model questions or generate scenarios. You can use Compare Runs directly from Tools.',true);}};
$('newChat').onclick=()=>{$('messages').replaceChildren();$('messages').classList.add('hidden');$('welcome').classList.remove('hidden');$('prompt').value='';navigate('companion');};
// Expansion preferences survive the randomly assigned local engine port.
async function preferences(){try{const data=await api('/api/ui-preferences');for(const id of ['toolsGroup','recentGroup'])$(id).open=Boolean(data[id]);}catch(error){status(error);}for(const id of ['toolsGroup','recentGroup'])$(id).addEventListener('toggle',()=>{api('/api/ui-preferences',{toolsGroup:$('toolsGroup').open,recentGroup:$('recentGroup').open}).catch(status);});}
function applyInstallation(data){installation=data;$('installation').value=data.installation||'';$('installationLabel').textContent=data.installation?'IFs · '+data.installation.split(/[/\\]/).pop():'No IFs installation selected';$('settingsStatus').textContent=data.installation?data.runs.length+' supported runfiles found.':'Choose the folder containing DATA and RUNFILES.';}
$('saveInstallation').onclick=async()=>{const button=$('saveInstallation');button.disabled=true;try{const data=await api('/api/installation',{installation:$('installation').value});applyInstallation(data);if(frame.contentWindow.applyInstallation)frame.contentWindow.applyInstallation(data);status(null);}catch(error){$('settingsStatus').textContent=error.message;}finally{button.disabled=false;}};
$('browse').onclick=async()=>{try{const data=await api('/api/select-installation',{installation:$('installation').value});if(data.installation){$('installation').value=data.installation;await $('saveInstallation').onclick();}}catch(error){$('settingsStatus').textContent=error.message;}};
async function openRecent(id){try{const running=jobs.find(j=>j.status==='running');if(running&&running.id!==id){status(Error('A comparison is running. Wait for it to finish before opening a different report.'));return;}const win=frame.contentWindow;if(!win.openCompanionReport)throw Error('Compare Runs is still loading. Please try again.');await win.openCompanionReport(id);navigate('compare');status(null);}catch(error){status(error);}}
async function refreshRecent(){try{const data=await api('/api/recent');jobs=data.jobs;$('recent').replaceChildren();$('running').textContent=jobs.some(j=>j.status==='running')?'1 running':'';if(!jobs.length)$('recent').textContent='No comparisons yet.';for(const item of jobs){const button=document.createElement('button');button.textContent=item.title;const note=document.createElement('small');note.textContent=item.status+(item.created?' · '+new Date(item.created*1000).toLocaleDateString():'');button.append(note);button.onclick=()=>openRecent(item.id);$('recent').append(button);}}catch(error){status(error);}}
frame.addEventListener('load',()=>{const win=frame.contentWindow;const link=win.document.getElementById('openSettings');if(link)link.onclick=()=>navigate('settings');});
api('/api/installation').then(applyInstallation).catch(error=>{$('settingsStatus').textContent=error.message;status(error);});preferences();refreshRecent();setInterval(refreshRecent,3000);

let installedTools = [], updateToolId = null, activeToolId = null, toolBusy = false;
function toolMessage(text) { $('toolStatus').textContent = text; }
async function refreshTools() {
  const data = await api('/api/tools'); installedTools = data.tools;
  $('installedTools').replaceChildren(); $('toolCards').replaceChildren();
  if (!installedTools.length) $('toolCards').textContent = 'No optional tools installed. Ask your team for the IFs Autotune package.';
  for (const tool of installedTools) {
    if(tool.id!=='ifs-model-vetting')action($('installedTools'), tool.name, () => openTool(tool));
    const card = document.createElement('section');
    const title = document.createElement('h3'); title.textContent = tool.name; card.append(title);
    const description = document.createElement('p'); description.textContent = 'Version ' + tool.version + (tool.running ? ' · Open' : ' · Installed'); card.append(description);
    const buttons = document.createElement('div'); buttons.className = 'actions'; card.append(buttons);
    action(buttons, 'Open', () => openTool(tool));
    if (tool.running) action(buttons, 'Close tool', async () => {
      try { await api('/api/tools/close', {id:tool.id}); if(tool.id==='ifs-model-vetting')frame.src='about:blank'; if(activeToolId===tool.id){$('optionalTool').src='about:blank';activeToolId=null;} await refreshTools();toolMessage(tool.name+' closed.'); }
      catch(error){toolMessage(error.message);}
    });
    action(buttons, 'Update from file…', () => chooseTool(tool.id));
    action(buttons, 'Uninstall', async () => {
      if (!confirm('Uninstall '+tool.name+'? Your settings and saved work will be kept.')) return;
      try { await api('/api/tools/uninstall',{id:tool.id});if(tool.id==='ifs-model-vetting')frame.src='/compare';await refreshTools();renderOfficialTools();toolMessage(tool.name+' uninstalled. Your saved work was kept.'); }
      catch(error){toolMessage(error.message);}
    });
    $('toolCards').append(card);
  }
}
function chooseTool(id=null){if(toolBusy)return;updateToolId=id;$('toolPackage').value='';$('toolPackage').click();}
$('installTool').onclick=()=>chooseTool();
$('toolPackage').onchange=async()=>{
  const file=$('toolPackage').files[0];if(!file)return;
  if(!confirm('Install software from '+file.name+'? Only continue if this package came from someone you trust.'))return;
  toolBusy=true;$('installTool').disabled=true;toolMessage('Installing '+file.name+'… Large tools can take a few minutes.');
  try {
    const response=await fetch('/api/tools/install'+(updateToolId?'?id='+encodeURIComponent(updateToolId):''),{method:'POST',headers:{'Content-Type':'application/octet-stream','X-Companion-Token':document.querySelector('meta[name=companion-token]').content},body:file});
    const result=await response.json();if(!response.ok)throw Error(result.error||'Installation failed.');
    await refreshTools();if(result.id==='ifs-model-vetting')frame.src='/compare';renderOfficialTools();toolMessage(result.name+' '+result.version+' is ready. Open it from Tools.');
  }catch(error){toolMessage(error.message);}finally{toolBusy=false;$('installTool').disabled=false;}
};
async function openTool(tool){
  if(tool.id==='ifs-model-vetting'){frame.src='/compare';navigate('compare');return;}
  try{status(null);$('viewTitle').textContent='Opening '+tool.name+'…';const result=await api('/api/tools/open',{id:tool.id});
    if(activeToolId!==tool.id){$('optionalTool').src=result.url;activeToolId=tool.id;}
    $('optionalTool').title=tool.name;navigate('optional');$('viewTitle').textContent=tool.name;await refreshTools();
  }catch(error){status(error);navigate('manage');toolMessage(error.message);}
}
refreshTools().catch(status);

let officialTools = [], catalogLoaded = false, catalogLoading = false, downloadTimer = null;
function compareVersion(a,b){const x=a.split('.').map(Number),y=b.split('.').map(Number);for(let i=0;i<3;i++)if(x[i]!==y[i])return x[i]-y[i];return 0;}
function renderOfficialTools(){
  $('officialTools').replaceChildren();
  for(const tool of officialTools){
    const card=document.createElement('section');const title=document.createElement('h4');title.textContent=tool.name;card.append(title);
    const description=document.createElement('p');description.textContent=tool.description;card.append(description);
    const note=document.createElement('p');card.append(note);
    if(tool.status==='coming-soon'){note.textContent='Online package coming soon';$('officialTools').append(card);continue;}
    const installed=installedTools.find(item=>item.id===tool.id);
    note.textContent='Version '+tool.version+' · '+Math.ceil(tool.size/1024/1024)+' MB';
    let label='Install';
    if(!tool.compatible){note.textContent+=' · Requires Companion '+tool.min_companion_version;label=null;}
    else if(installed){
      const difference=compareVersion(tool.version,installed.version);
      if(difference>0){note.textContent+=' · Update available (installed '+installed.version+')';label='Update';}
      else if(difference<0){note.textContent+=' · Newer version installed';label=null;}
      else if(installed.official_sha256===tool.sha256){note.textContent+=' · Up to date';label=null;}
      else{note.textContent+=' · Installed from file';label='Install official version';}
    }else if(tool.id==='ifs-model-vetting'){note.textContent+=' · Basic version included with Companion';label='Install separate tool updates';}
    if(label){action(card,label,async()=>{
      if(toolBusy)return;
      try{await api('/api/tools/official-install',{id:tool.id});pollDownload();}
      catch(error){$('catalogStatus').textContent=error.message;}
    });}
    $('officialTools').append(card);
  }
}
async function loadOfficialTools(force=false){
  if(catalogLoading || catalogLoaded&&!force)return;
  catalogLoading=true;$('checkOfficial').disabled=true;$('catalogStatus').textContent='Checking official tools…';
  try{const data=await api('/api/tools/catalog');officialTools=data.tools;catalogLoaded=true;renderOfficialTools();$('catalogStatus').textContent='Official catalog checked.';}
  catch(error){$('catalogStatus').textContent=error.message;}
  finally{catalogLoading=false;$('checkOfficial').disabled=false;}
}
async function pollDownload(){
  clearTimeout(downloadTimer);
  try{
    const state=await api('/api/tools/download');
    const active=['checking','downloading','verifying','installing'].includes(state.status);
    toolBusy=active;$('installTool').disabled=active;
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
$('checkOfficial').onclick=()=>loadOfficialTools(true);
pollDownload();
