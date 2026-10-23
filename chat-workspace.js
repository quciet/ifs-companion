'use strict';
// Reuse existing local application views, retaining a separate DOM per chat tab.
(() => {
  let current=null, sequence=0;
  const busy=new Set(), drafts=new Map(), spaces=new Map();
  const notifiedJobs=new Set();
  const attachments=new Map();
  let inlineCleanup=[];
  let runningTasks=new Set(), recentSignature='';
  const list=document.createElement('div');list.id='chatList';
  $('taskRecents').append(list);
  const workspace=document.createElement('section');workspace.id='chatWorkspace';
  const tabs=document.createElement('div');tabs.id='workspaceTabs';tabs.setAttribute('role','tablist');
  const views=document.createElement('div');views.id='workspaceViews';
  workspace.append(tabs,views);
  const layout=document.createElement('div');layout.id='chatLayout';
  $('companionView').before(layout);layout.append($('companionView'),workspace);
  workspace.hidden=true;
  // Keep resize state outside individual chats so switching tasks preserves the split.
  let sidebarWidth=244, chatRatio=.44;
  function divider(id,label,controls){
    const bar=document.createElement('div');bar.id=id;bar.className='panelDivider';bar.tabIndex=0;
    bar.setAttribute('role','separator');bar.setAttribute('aria-orientation','vertical');
    bar.setAttribute('aria-label',label);bar.setAttribute('aria-controls',controls);
    return bar;
  }
  const sidebar=document.querySelector('body>aside'),main=document.querySelector('body>main');
  const sidebarDivider=divider('sidebarDivider','Resize sidebar','companionSidebar');sidebar.id='companionSidebar';sidebar.after(sidebarDivider);
  const workspaceDivider=divider('workspaceDivider','Resize chat and workspace','companionView chatWorkspace');
  workspace.before(workspaceDivider);workspaceDivider.hidden=true;
  const clamp=(value,min,max)=>Math.min(Math.max(value,min),Math.max(min,max));
  function sidebarMax(){return Math.min(360,document.body.clientWidth-6-(layout.classList.contains('has-workspace')&&!layout.classList.contains('hidden')?622:360));}
  function resizePanels(){
    sidebarWidth=clamp(sidebarWidth,180,sidebarMax());sidebar.style.width=sidebarWidth+'px';
    sidebarDivider.setAttribute('aria-valuemin','180');sidebarDivider.setAttribute('aria-valuemax',String(Math.max(180,sidebarMax())));sidebarDivider.setAttribute('aria-valuenow',String(Math.round(sidebarWidth)));
    if(!layout.classList.contains('has-workspace'))return;
    const available=layout.clientWidth-6,chatWidth=clamp(available*chatRatio,280,available-320);
    layout.style.setProperty('--chat-width',chatWidth+'px');
    workspaceDivider.setAttribute('aria-valuemin','280');workspaceDivider.setAttribute('aria-valuemax',String(Math.round(Math.max(280,available-320))));workspaceDivider.setAttribute('aria-valuenow',String(Math.round(chatWidth)));
  }
  function setDivider(bar,x){
    if(bar===sidebarDivider)sidebarWidth=clamp(x-sidebar.getBoundingClientRect().left,180,sidebarMax());
    else{const available=layout.clientWidth-6;chatRatio=clamp(x-layout.getBoundingClientRect().left,280,available-320)/available;}
    resizePanels();
  }
  function enableDivider(bar){
    bar.onpointerdown=event=>{
      if(event.button!==0)return;event.preventDefault();bar.setPointerCapture(event.pointerId);document.body.classList.add('resizingPanels');
      const move=e=>setDivider(bar,e.clientX);
      const end=()=>{bar.removeEventListener('pointermove',move);bar.removeEventListener('pointerup',end);bar.removeEventListener('pointercancel',end);bar.removeEventListener('lostpointercapture',end);document.body.classList.remove('resizingPanels');};
      bar.addEventListener('pointermove',move);bar.addEventListener('pointerup',end);bar.addEventListener('pointercancel',end);bar.addEventListener('lostpointercapture',end);
    };
    bar.onkeydown=event=>{
      if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;event.preventDefault();
      const current=Number(bar.getAttribute('aria-valuenow')),min=Number(bar.getAttribute('aria-valuemin')),max=Number(bar.getAttribute('aria-valuemax'));
      const value=event.key==='Home'?min:event.key==='End'?max:current+(event.key==='ArrowLeft'?-1:1)*(event.shiftKey?40:10);
      setDivider(bar,(bar===sidebarDivider?sidebar:layout).getBoundingClientRect().left+clamp(value,min,max));
    };
  }
  enableDivider(sidebarDivider);enableDivider(workspaceDivider);
  const resizeObserver=new ResizeObserver(resizePanels);resizeObserver.observe(main);window.addEventListener('resize',resizePanels);resizePanels();
  const stop=document.createElement('button');stop.type='button';stop.textContent='■';stop.className='stopResponse';stop.title='Stop response';stop.setAttribute('aria-label','Stop response');stop.hidden=true;
  $('composer').querySelector('.composerActions').prepend(stop);
  stop.onclick=async()=>{if(current){await api('/api/chats/stop',{id:current});status(Error('Stopping after the current provider call returns…'));}};
  const hint=$('composer').querySelector('small');hint.hidden=true;
  const submit=$('composer').querySelector('[type=submit]');
  async function refreshTaskResults(){
    const owner=current;if(!owner)return;
    try{
      const data=await api('/api/jobs?chat='+encodeURIComponent(owner));if(owner!==current)return;
      const newlyFinished=data.jobs.filter(j=>j.data.notification_sent&&!notifiedJobs.has(j.id));
      for(const job of newlyFinished)notifiedJobs.add(job.id);
      if(newlyFinished.length){const chat=await api('/api/chats?id='+owner);if(owner===current)render(chat);}
    }catch(error){status(error);}
  }
  function updateBusy(){const active=busy.has(current);submit.disabled=active;stop.hidden=!active;submit.textContent='↑';submit.title=active?'Companion is responding':'Send message';submit.setAttribute('aria-label',submit.title);updateTaskIndicators();}
  function space(){if(!spaces.has(current))spaces.set(current,[]);return spaces.get(current);}
  function showTabs(){
    tabs.replaceChildren();const entries=space();
    for(const entry of entries){
      const group=document.createElement('div');group.className='workspaceTab';
      const tab=document.createElement('button');tab.type='button';tab.textContent=entry.title;tab.title=entry.title;
      tab.setAttribute('role','tab');tab.setAttribute('aria-selected',String(entry.active));
      tab.onclick=()=>{entries.forEach(t=>t.active=t===entry);showTabs();};
      const close=document.createElement('button');close.type='button';close.textContent='×';close.className='closeTab';close.setAttribute('aria-label','Close '+entry.title);
      close.onclick=()=>{entry.dispose?.();entry.frame.remove();entries.splice(entries.indexOf(entry),1);if(entries.length&&!entries.some(t=>t.active))entries.at(-1).active=true;showTabs();};
      group.append(tab,close);tabs.append(group);
    }
    for(const [id,items] of spaces)for(const item of items)item.frame.hidden=id!==current||!item.active;
    workspace.hidden=!entries.length;layout.classList.toggle('has-workspace',!!entries.length);workspaceDivider.hidden=!entries.length;resizePanels();
  }
  async function open(link){
    if(link.kind==='tool'&&link.id==='ifs-scenario-builder'){navigate('companion');$('prompt').focus();return;}
    const owner=current, entries=space(), key=JSON.stringify(link);
    let entry=entries.find(t=>t.key===key);
    if(entry){entries.forEach(t=>t.active=t===entry);showTabs();return;}
    let url='/compare';
    if(link.kind==='job')url='/job-view?id='+encodeURIComponent(link.id);
    if(link.kind==='run-review')url='/run-review?chat='+encodeURIComponent(owner)+'&approval='+encodeURIComponent(link.id);
    if(link.kind==='tool'||link.kind==='scenario'){
      try{url=(await api('/api/tools/open',{id:link.id})).url;}
      catch(error){status(error);navigate('manage');return;}
    }
    const iframe=document.createElement('iframe');iframe.title=link.title;iframe.className='workspaceFrame';
    entry={key,title:link.title,frame:iframe,active:true};entries.forEach(t=>t.active=false);entries.push(entry);
    if(['scenario','job','run-review'].includes(link.kind)){
      const listener=async event=>{
        if(event.origin!==location.origin||event.source!==iframe.contentWindow)return;
        try{
          if(event.data?.type==='companion-scenario-run'){
            const review=await api('/api/runs/prepare',{chat:owner,session:event.data.session,draft:event.data.draft,end_year:event.data.end_year});
            if(current===owner)await open({kind:'run-review',id:review.id,title:'Approve scenario run'});
          }
          if(event.data?.type==='companion-run-started'&&current===owner)render(await api('/api/chats?id='+owner));
          if(event.data?.type==='companion-job-report'&&current===owner)await open({kind:'report',id:event.data.report,title:'Comparison results'});
          if(event.data?.type==='companion-run-compare'&&current===owner){
            const installation=await api('/api/installation');
            await open({kind:'comparison',title:'Compare scenario run',context:{a:installation.runs.find(p=>/IFsBase\.run\.db$/i.test(p)),comparisons:[event.data.run],variables:[]}});
          }
        }catch(error){status(error);}
      };
      window.addEventListener('message',listener);entry.dispose=()=>window.removeEventListener('message',listener);
    }
    if(link.kind==='comparison'){
      const listener=async event=>{
        if(event.origin!==location.origin||event.source!==iframe.contentWindow||event.data?.type!=='companion-comparison')return;
        try{await api('/api/chats/event',{id:owner,kind:'comparison',job:event.data.job});if(owner===current)render(await api('/api/chats?id='+owner));}
        catch(error){status(error);}
      };
      window.addEventListener('message',listener);
      entry.dispose=()=>window.removeEventListener('message',listener);
    }
    iframe.addEventListener('load',async()=>{
      try{
        const win=iframe.contentWindow;
        if(link.kind==='comparison'){
          if(!win.companionView)throw Error('Update Model Vetting to review a comparison selection from chat.');
          await win.companionView.open(link.context);
        }
        if(link.kind==='report'){
          if(win.companionView)await win.companionView.open({report:link.id});
          else await win.openCompanionReport(link.id);
        }
        if(link.kind==='scenario'){
          if(!win.companionScenario)throw Error('Update Scenario Builder to review a proposal from the main chat.');
          win.companionScenario.open(link.context);
        }
      }catch(error){status(error);}
    },{once:true});
    iframe.src=url;views.append(iframe);if(current===owner)showTabs();
  }
  function render(chat){
    for(const cleanup of inlineCleanup)cleanup();inlineCleanup=[];
    $('messages').replaceChildren();$('welcome').classList.toggle('hidden',!!chat.messages.length);$('messages').classList.toggle('hidden',!chat.messages.length);
    const latest=chat.messages.flatMap(m=>m.links||[]).filter(l=>l.kind==='scenario').at(-1);
    for(const m of chat.messages){const element=message(m.content,m.role==='assistant');for(const link of m.links||[]){
      if(link.kind==='scenario'){if(link===latest)inlineScenario(element,link,chat.id);}
      else action(element,link.title,()=>open(link));
    }}
    if(chat.research){
      const card=document.createElement('div');card.className='researchCheckpoint';
      const proceed=document.createElement('button');proceed.type='button';proceed.textContent='Continue researching';proceed.disabled=!!chat.busy;
      proceed.onclick=async()=>{
        const owner=chat.id;if(busy.has(owner))return;busy.add(owner);updateBusy();proceed.disabled=true;status(null);
        try{const result=await api('/api/chats/send',{id:owner,continue_research:chat.research.id});if(current===owner)render({...result,busy:false});}
        catch(error){status(error);}
        finally{busy.delete(owner);updateBusy();if(current===owner)render(await api('/api/chats?id='+owner));await refresh();}
      };
      const revise=document.createElement('button');revise.type='button';revise.textContent='Revise request';revise.onclick=()=>$('prompt').focus();
      card.append(proceed,revise);$('messages').append(card);
    }
    if(chat.busy)busy.add(chat.id);else busy.delete(chat.id);updateBusy();
  }
  async function inlineScenario(host,link,owner){
    const frame=document.createElement('iframe');frame.title='Scenario proposal and file';frame.className='inlineScenario';host.append(frame);
    const listener=async event=>{
      if(!frame.isConnected){window.removeEventListener('message',listener);return;}
      if(event.origin!==location.origin||event.source!==frame.contentWindow)return;
      try{
        if(event.data?.type==='companion-scenario-height')frame.style.height=Math.max(180,Math.min(1200,event.data.height))+'px';
        if(event.data?.type==='companion-scenario-revise')$('prompt').focus();
        if(event.data?.type==='companion-scenario-run'){
          const review=await api('/api/runs/prepare',{chat:owner,session:event.data.session,draft:event.data.draft,end_year:event.data.end_year});
          if(current===owner)await open({kind:'run-review',id:review.id,title:'Approve scenario run'});
        }
      }catch(error){status(error);}
    };
    window.addEventListener('message',listener);inlineCleanup.push(()=>window.removeEventListener('message',listener));
    try{
      const result=await api('/api/tools/open',{id:'ifs-scenario-builder'});if(!frame.isConnected)return;
      frame.onload=()=>{try{frame.contentWindow.companionScenario.open(link.context,{inline:true,chat:owner});}catch(error){status(error);}};
      frame.src=result.url;
    }catch(error){window.removeEventListener('message',listener);frame.remove();status(error);}
  }
  function updateTaskIndicators(){
    for(const row of list.children){
      const active=busy.has(row.dataset.taskId)||runningTasks.has(row.dataset.taskId);
      const spinner=row.querySelector('.taskSpinner');if(!spinner)continue;
      spinner.hidden=!active;
      const button=row.querySelector('.taskTitle');
      button.setAttribute('aria-label',button.title+(active?' (Running)':''));
    }
  }
  let refreshing=null;
  async function refresh(){
    if(refreshing)return refreshing;
    refreshing=(async()=>{
      const data=await api('/api/tasks/recent',{});runningTasks=new Set(data.running||data.busy||[]);
      const signature=JSON.stringify([data.chats,current]);if(signature===recentSignature){updateTaskIndicators();return;}recentSignature=signature;list.replaceChildren();
      if(!data.chats.length){const empty=document.createElement('small');empty.textContent='No saved tasks yet.';list.append(empty);}
      for(const chat of data.chats.sort((a,b)=>b.updated-a.updated)){
        const row=document.createElement('div');row.className='recentTask';row.dataset.taskId=chat.id;
        const button=document.createElement('button');button.textContent=chat.title;button.title=chat.title;
        button.className='taskTitle'+(chat.id===current?' active':'');button.onclick=()=>select(chat.id).catch(status);
        const remove=document.createElement('button');remove.type='button';remove.className='deleteTask';remove.textContent='×';
        remove.setAttribute('aria-label','Delete task: '+chat.title);remove.title='Delete task and saved data';
        remove.onclick=async()=>{
          if(!await confirmTool('Delete task?', 'Permanently delete “'+chat.title+'” and its chat history, saved reports, scenario drafts, and generated run data? Copies saved to IFs and files shared with other tasks are kept. This cannot be undone.', 'Delete task'))return;
          remove.disabled=true;
          try{
            await api('/api/tasks/delete',{id:chat.id});
            for(const entry of spaces.get(chat.id)||[]){entry.dispose?.();entry.frame.remove();}
            spaces.delete(chat.id);drafts.delete(chat.id);busy.delete(chat.id);
            if(current===chat.id)$('newTask').click();
            await refresh();status(null);
          }catch(error){status(error);}finally{remove.disabled=false;}
        };
        const spinner=document.createElement('span');spinner.className='taskSpinner';spinner.setAttribute('aria-hidden','true');spinner.hidden=true;
        row.append(spinner,button,remove);list.append(row);
      }
      updateTaskIndicators();
    })();
    try{await refreshing;}finally{refreshing=null;}
  }
  async function select(id){
    if(current)drafts.set(current,$('prompt').value);
    current=id;const ticket=++sequence;const chat=await api('/api/chats?id='+encodeURIComponent(id));if(ticket!==sequence)return;
    navigate('companion');$('prompt').value=drafts.get(id)||'';attachmentChip();render(chat);showTabs();await refresh();await refreshTaskResults();
  }
  const observer=new MutationObserver(()=>{layout.classList.toggle('hidden',$('companionView').classList.contains('hidden'));resizePanels();});
  observer.observe($('companionView'),{attributes:true,attributeFilter:['class']});
  $('newTask').onclick=()=>{drafts.set(current,$('prompt').value);current=null;++sequence;navigate('companion');$('prompt').value='';drafts.delete(null);attachmentChip();render({messages:[],busy:false});showTabs();status(null);refresh().catch(status);$('prompt').focus();};
  $('composer').onsubmit=async event=>{
    event.preventDefault();const source=attachments.get(current);const text=$('prompt').value.trim()||(source?'Inspect the attached scenario and summarize its parameters and scope. Do not propose changes yet.':'');if(!text||busy.has(current))return;
    try{
      if(!current){const chat=await api('/api/chats/create',{});await select(chat.id);}
      const owner=current;busy.add(owner);$('prompt').value='';drafts.set(owner,'');message((source?'Attached: '+source.name+'\n\n':'')+text);updateBusy();refresh().catch(status);status(null);
      try{const chat=await api('/api/chats/send',{id:owner,message:text,...(source?{source}:{})});attachments.delete(owner);if(source)attachments.delete(null);if(owner===current)attachmentChip();if(owner===current)render({...chat,busy:false});}
      finally{busy.delete(owner);updateBusy();await refresh();}
    }catch(error){status(error);if(current){const chat=await api('/api/chats?id='+current);render(chat);}}
  };
  window.companionWorkspace={refreshRecents:refresh,openReport:id=>open({kind:'report',id,title:'Comparison '+id.slice(0,8)}),open};
  setInterval(async()=>{
    const owner=current;if(!owner||!busy.has(owner))return;
    try{const chat=await api('/api/chats?id='+owner);if(current===owner)render(chat);}
    catch(error){status(error);}
  },1500);
  setInterval(refreshTaskResults,1500);
  const runFile=document.createElement('input');runFile.type='file';runFile.accept='.sce';runFile.hidden=true;
  const runFileButton=document.createElement('button');runFileButton.type='button';runFileButton.textContent='+';runFileButton.className='attachFile';runFileButton.title='Upload .sce file for review';runFileButton.setAttribute('aria-label','Upload .sce file');
  runFileButton.onclick=()=>runFile.click();$('composer').querySelector('.composerActions').prepend(runFileButton,runFile);
  const chip=document.createElement('div');chip.className='chatAttachment';chip.hidden=true;$('composer').prepend(chip);
  function attachmentChip(){chip.replaceChildren();const source=attachments.get(current);chip.hidden=!source;if(!source)return;const label=document.createElement('span');label.textContent=source.name;const remove=document.createElement('button');remove.type='button';remove.textContent='×';remove.setAttribute('aria-label','Remove attachment');remove.onclick=()=>{attachments.delete(current);attachmentChip();};chip.append(label,remove);}
  async function attach(file){
    if(!file||busy.has(current))return;
    try{if(file.size>1_000_000||!file.name.toLowerCase().endsWith('.sce'))throw Error('Choose a .sce file up to 1 MB.');
      const text=new TextDecoder('utf-8',{fatal:true}).decode(await file.arrayBuffer());
      if(!current){const chat=await api('/api/chats/create',{});await select(chat.id);}
      attachments.set(current,{name:file.name,text});attachmentChip();$('prompt').focus();
    }catch(error){status(error);}
  }
  runFile.onchange=async()=>{const file=runFile.files[0];runFile.value='';await attach(file);};
  $('composer').addEventListener('dragover',event=>{if(event.dataTransfer?.types.includes('Files'))event.preventDefault();});
  $('composer').addEventListener('drop',async event=>{if(!event.dataTransfer?.files.length)return;event.preventDefault();if(event.dataTransfer.files.length!==1){status(Error('Attach one .sce file at a time.'));return;}await attach(event.dataTransfer.files[0]);});
  const knowledge=document.createElement('section');const heading=document.createElement('h3');heading.textContent='IFs knowledge';
  const description=document.createElement('p');description.textContent='Prepare or inspect the shared source and wiki index used by all chats.';
  const prepare=document.createElement('button');prepare.textContent='Manage IFs knowledge';prepare.type='button';
  const knowledgeStatus=document.createElement('p');knowledgeStatus.setAttribute('role','status');
  function knowledgeState(){
    const installed=installedTools.some(t=>t.id==='ifs-code-reader');
    prepare.textContent=installed?'Manage IFs knowledge':'Install IFs knowledge backend';
    knowledgeStatus.textContent=installed?'Code Interpreter provides the shared source and wiki index.':'The Code Interpreter backend is not installed. Install it to prepare and inspect shared IFs knowledge.';
  }
  prepare.onclick=async()=>{
    prepare.disabled=true;
    try{
      await refreshTools();
      const tool=installedTools.find(t=>t.id==='ifs-code-reader');
      if(tool){await openTool(tool);return;}
      if(toolBusy)throw Error('Wait for the current tool installation to finish.');
      await api('/api/tools/official-install',{id:'ifs-code-reader'});
      knowledgeStatus.textContent='Installing the IFs knowledge backend...';
      await pollDownload();
    }catch(error){knowledgeStatus.textContent=error.message;}
    finally{prepare.disabled=false;}
  };
  window.addEventListener('companion-tools-updated',knowledgeState);
  window.addEventListener('companion-tool-download',event=>{
    if(event.detail.id==='ifs-code-reader'){
      knowledgeStatus.textContent=event.detail.message;
      prepare.disabled=['checking','downloading','verifying','installing'].includes(event.detail.status);
    }
  });
  knowledge.append(heading,description,prepare,knowledgeStatus);$('settingsView').append(knowledge);knowledgeState();
  refresh().catch(status);
})();
