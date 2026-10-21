'use strict';
(()=>{
  let session=null,source=null,draft=null,busy=false,selectedRow=null,pending=null,research=null;
  const el=id=>document.getElementById(id);
  const controls=['scenarioSend','scenarioAttach','scenarioReplace','scenarioRemove','scenarioNew','scenarioSave','scenarioViewFile'];
  function updateComposer(){el('scenarioSend').disabled=busy||(!el('scenarioPrompt').value.trim()&&!(source&&!session));el('scenarioSend').setAttribute('aria-label',busy?'Waiting for response':'Send message');el('scenarioSend').title=busy?'Waiting for response':'Send message';el('scenarioComposer').classList.toggle('is-busy',busy);el('scenarioComposer').setAttribute('aria-busy',String(busy));}
  function setBusy(value){busy=value;for(const id of controls)el(id).disabled=value;el('scenarioStop').hidden=!value;updateComposer();}
  function sizePrompt(){const input=el('scenarioPrompt');input.style.height='auto';input.style.height=Math.min(200,Math.max(64,input.scrollHeight))+'px';updateComposer();}
  function note(text,error=false){el('scenarioStatus').textContent=text;el('scenarioStatus').classList.toggle('scenario-error',error);}
  function message(text,role,label=role==='user'?'You':'Scenario Builder'){
    const div=document.createElement('div');div.className='scenario-message '+role;div.setAttribute('aria-label',label);
    const speaker=document.createElement('div');speaker.className='scenario-speaker';speaker.textContent=label;
    const body=document.createElement('div');body.className='scenario-message-body';body.textContent=text;
    div.append(speaker,body);el('scenarioMessages').append(div);div.scrollIntoView({block:'nearest'});return div;
  }
  function resetDraft(){draft=null;pending=null;research=null;for(const button of document.querySelectorAll('.scenario-confirm-button,.scenario-continue-button'))button.disabled=true;selectedRow=null;el('scenarioSummary').hidden=true;el('scenarioExportResult').replaceChildren();el('scenarioInspector').close();el('scenarioFileDialog').close();el('scenarioFileText').textContent='';}
  function reset(preservePrompt=false){session=null;resetDraft();el('scenarioMessages').replaceChildren();if(!preservePrompt)el('scenarioPrompt').value='';message(source?'Scenario attached. Ask me to inspect it, explain its assumptions, or propose changes.':'Describe a new scenario, or attach a .sce file to inspect or modify.','assistant');note('');sizePrompt();}
  function sourceChip(){el('scenarioSource').hidden=!source;el('scenarioSourceName').textContent=source?.name||'';}
  el('scenarioAttach').onclick=el('scenarioReplace').onclick=()=>el('scenarioFile').click();
  async function attachFile(file){
    if(!file||busy)return;
    if(!file.name.toLowerCase().endsWith('.sce')||file.size>1_000_000){note('Choose a .sce file smaller than 1 MB.',true);return;}
    setBusy(true);
    try{
    if((draft||session)&&!await confirmTool('Replace scenario source?','The working draft and conversation will be cleared. Your typed message and saved scenario files will be kept.','Replace'))return;
    const bytes=new Uint8Array(await file.arrayBuffer());
    let text;try{text=new TextDecoder('utf-8',{fatal:true}).decode(bytes);}catch{note('This file is not UTF-8. Convert a copy to UTF-8 before attaching it.',true);return;}
    source={name:file.name,text};sourceChip();reset(true);note('Attached locally. Send your message when ready, or send the file alone for an overview.');el('scenarioPrompt').focus();
    }catch(error){note('Could not read the attached file. '+error.message,true);}finally{setBusy(false);}
  }
  el('scenarioFile').onchange=async()=>{const file=el('scenarioFile').files[0];el('scenarioFile').value='';await attachFile(file);};
  let dragDepth=0;
  el('scenarioComposer').ondragenter=event=>{if(event.dataTransfer?.types.includes('Files')){event.preventDefault();dragDepth++;if(!busy)el('scenarioComposer').classList.add('is-dragging');}};
  el('scenarioComposer').ondragover=event=>{if(event.dataTransfer?.types.includes('Files')){event.preventDefault();event.dataTransfer.dropEffect=busy?'none':'copy';}};
  el('scenarioComposer').ondragleave=()=>{if(--dragDepth<=0){dragDepth=0;el('scenarioComposer').classList.remove('is-dragging');}};
  el('scenarioComposer').ondrop=async event=>{event.preventDefault();dragDepth=0;el('scenarioComposer').classList.remove('is-dragging');const files=event.dataTransfer?.files;if(!files?.length||busy)return;if(files.length!==1){note('Attach one .sce file at a time.',true);return;}await attachFile(files[0]);};
  el('scenarioPrompt').oninput=sizePrompt;
  el('scenarioPrompt').onkeydown=event=>{if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing){event.preventDefault();if(!busy)el('scenarioForm').requestSubmit();}};
  el('scenarioRemove').onclick=async()=>{if((draft||session)&&!await confirmTool('Remove scenario source?','This clears the conversation and working draft. Your original file and typed message are kept.','Remove'))return;source=null;sourceChip();reset(true);};
  el('scenarioNew').onclick=async()=>{if((draft||session)&&!await confirmTool('Start a new scenario chat?','This clears the conversation, attachment and unsaved draft. Saved files remain available.','New chat'))return;source=null;sourceChip();reset();};
  function renderDraft(value){resetDraft();draft=value;if(!draft)return;
    const parameters=new Set(draft.rows.map(r=>r.parameter)),countries=new Set();let global=false;
    for(const row of draft.rows){const flags=draft.dimensions[row.parameter];if(flags[0]===1)countries.add(row.targets[0]);else if(flags[0]===0)global=true;}
    const start=Math.min(...draft.rows.map(r=>r.changed_start_year)),end=Math.max(...draft.rows.map(r=>r.changed_end_year));
    el('scenarioSummaryCounts').textContent=[parameters.size+' parameter'+(parameters.size===1?'':'s'),...(countries.size?[countries.size+' countr'+(countries.size===1?'y':'ies')]:[]),...(global?['Global inputs']:[]),start+'–'+end,draft.rows.length+' trajector'+(draft.rows.length===1?'y':'ies')].join(' · ');
    el('scenarioPurpose').textContent=draft.purpose;el('scenarioSummary').hidden=false;
    el('scenarioFilename').value=draft.filename;el('scenarioRegeneration').textContent=draft.regeneration_prompt;
    options(el('scenarioParameter'),[...parameters].sort().map(p=>[p,p]));
  }
  function receive(result){
    session=result.session;message(result.reply,'assistant');renderDraft(result.draft);updateComposer();
    el('scenarioContext').textContent=result.context.version+' · Base year '+result.context.base_year+' · '+result.context.installation;
    pending=result.confirmation||null;
    research=result.research||null;
    if(research){
      const value=research,card=message(value.lookups+' metadata results preserved · '+value.cache_hits+' repeated lookups served from cache.','assistant','Scenario Builder · Research paused');
      const resume=document.createElement('button');resume.type='button';resume.className='scenario-continue-button';resume.textContent='Continue researching';
      resume.onclick=async()=>{if(busy||research?.id!==value.id)return;setBusy(true);resume.disabled=true;note('Continuing with preserved research…');try{receive(await api('/api/scenario/chat',{session,continue_research:value.id}));}catch(error){note(error.message,true);resume.disabled=false;}finally{setBusy(false);}};
      const revise=document.createElement('button');revise.type='button';revise.textContent='Revise request';revise.onclick=()=>el('scenarioPrompt').focus();card.append(resume,revise);
    }
    if(pending){
      const value=pending,card=message('','assistant','Scenario Builder · Confirmation');
      const summary=document.createElement('p');summary.textContent='Confirm scenario: '+value.purpose+'\nParameters: '+value.parameters.join(', ')+' · '+value.trajectories+' trajectories';card.append(summary);
      const intent=document.createElement('p');intent.textContent=value.regeneration_prompt;card.append(intent);
      if(value.merged_duplicates){const merged=document.createElement('p');merged.textContent=value.merged_duplicates+' identical overlapping definitions merged; each parameter/target is applied once.';card.append(merged);}
      for(const warning of value.warnings||[]){const p=document.createElement('p');p.textContent=warning;card.append(p);}
      if(value.semantics?.length||value.presets?.length||value.group_writing?.length){
        const details=document.createElement('details'),label=document.createElement('summary');label.textContent='IFs interpretation, baseline defaults and file writing';details.append(label);
        for(const rule of value.semantics||[]){const p=document.createElement('p');p.textContent=rule.parameter+' · Intended '+rule.direction+' · '+(rule.verified?'Audited control':'Polarity needs review')+' · '+rule.interpretation;details.append(p);}
        if(value.presets?.length){const p=document.createElement('p');p.textContent=value.presets.length+' IFs preset calculations from '+value.presets[0].source+'. High/low describe input values, not outcome severity.';details.append(p);const list=document.createElement('details'),title=document.createElement('summary');title.textContent='See calculated country defaults';list.append(title);for(const item of value.presets){const row=document.createElement('p');row.textContent=item.parameter+' / '+item.targets.join(' / ')+' · '+item.level+': '+item.baseline+' → '+item.endpoint+' over '+item.years+' years';list.append(row);}details.append(list);}
        for(const group of value.group_writing||[]){const p=document.createElement('p');p.textContent=group.parameter+' / '+group.group+' · '+(group.native_group?'Native group record':'Explicit country records')+' · '+group.reason;details.append(p);}
        card.append(details);
      }
      for(const group of value.geographies){const details=document.createElement('details'),label=document.createElement('summary'),members=document.createElement('p');label.textContent=group.kind+' · '+group.name+' · '+group.countries.length+' countries';members.textContent=group.countries.join(', ');details.append(label,members);card.append(details);}
      const approve=document.createElement('button');approve.type='button';approve.className='scenario-confirm-button';approve.textContent='Confirm and build draft';
      approve.onclick=async()=>{if(busy||pending?.id!==value.id)return;setBusy(true);approve.disabled=true;note('Building confirmed draft…');try{const result=await api('/api/scenario/chat',{session,confirmation:value.id});receive(result);}catch(error){note(error.message,true);approve.disabled=false;}finally{setBusy(false);}};
      const revise=document.createElement('button');revise.type='button';revise.textContent='Revise in chat';revise.onclick=()=>el('scenarioPrompt').focus();card.append(approve,revise);el('scenarioMessages').append(card);card.scrollIntoView({block:'nearest'});
    }
    note(research?'Research is paused. Continue or send a revised request; your progress is kept.':pending?'Review the scope and country membership, then confirm or describe a revision.':result.draft?'Confirmed draft ready to inspect. Saving is a separate step.':'');
  }
  function options(select,items){select.replaceChildren();for(const [value,label] of items){const option=document.createElement('option');option.value=value;option.textContent=label;select.append(option);}}
  function selectParameter(){if(!draft)return;const name=el('scenarioParameter').value,rows=draft.rows.filter(r=>r.parameter===name),flags=draft.dimensions[name];
    const geography=el('scenarioGeography');el('scenarioSubgroups').replaceChildren();
    if(flags[0]===1){options(geography,[...new Set(rows.map(r=>r.targets[0]))].sort().map(n=>[n,n]));geography.disabled=false;}
    else{options(geography,[['',flags[0]===0?'Global (no country dimension)':'Subgroup-specific (no country dimension)']]);geography.disabled=true;}
    const active=flags.map((flag,axis)=>({flag,axis})).filter(d=>d.flag>0);
    let candidates=rows;
    for(const [index,{flag,axis}] of active.entries()){
      if(axis===0&&flag===1){candidates=candidates.filter(r=>r.targets[index]===geography.value);continue;}
      const label=document.createElement('label'),select=document.createElement('select');label.textContent=flag===1?'Partner country (dimension '+(axis+1)+')':'Subgroup (dimension '+(axis+1)+')';select.dataset.targetIndex=index;
      const members=new Map(candidates.map(r=>[r.targets[index],r.target_labels?.[index]||r.targets[index]]));options(select,[...members.entries()].sort((a,b)=>a[1].localeCompare(b[1])));label.append(select);el('scenarioSubgroups').append(label);
      candidates=candidates.filter(r=>r.targets[index]===select.value);select.onchange=()=>selectSubgroups(index);
    }
    selectRow();
  }
  function selectSubgroups(changedIndex){const rows=draft.rows.filter(r=>r.parameter===el('scenarioParameter').value),flags=draft.dimensions[el('scenarioParameter').value];let candidates=flags[0]===1?rows.filter(r=>r.targets[0]===el('scenarioGeography').value):rows;
    for(const select of el('scenarioSubgroups').querySelectorAll('select')){const index=Number(select.dataset.targetIndex);if(index>changedIndex){const old=select.value,members=new Map(candidates.map(r=>[r.targets[index],r.target_labels?.[index]||r.targets[index]]));options(select,[...members]);if(members.has(old))select.value=old;}candidates=candidates.filter(r=>r.targets[index]===select.value);}selectRow();
  }
  function selectRow(){const name=el('scenarioParameter').value,flags=draft.dimensions[name];let rows=draft.rows.filter(r=>r.parameter===name);if(flags[0]===1)rows=rows.filter(r=>r.targets[0]===el('scenarioGeography').value);for(const select of el('scenarioSubgroups').querySelectorAll('select'))rows=rows.filter(r=>r.targets[Number(select.dataset.targetIndex)]===select.value);selectedRow=rows[0]||null;
    el('scenarioAnnualTable').replaceChildren();el('scenarioAnnualDetails').open=false;
    el('scenarioSelection').textContent=selectedRow?name+' · '+(selectedRow.target_labels?.join(' / ')||'Global')+' · '+selectedRow.start_year+'–'+selectedRow.end_year+(selectedRow.before?' · Changed '+selectedRow.changed_start_year+'–'+selectedRow.changed_end_year:''): 'No matching trajectory.';
    el('scenarioOriginalKey').hidden=!selectedRow?.before;drawGraph();
  }
  el('scenarioParameter').onchange=selectParameter;
  el('scenarioGeography').onchange=()=>selectSubgroups(-1);
  el('scenarioInspect').onclick=()=>{if(!draft)return;el('scenarioInspector').showModal();selectParameter();};
  el('scenarioInspectorClose').onclick=()=>el('scenarioInspector').close();
  el('scenarioAnnualDetails').ontoggle=()=>{if(!el('scenarioAnnualDetails').open||!selectedRow||el('scenarioAnnualTable').childElementCount)return;const row=selectedRow,table=document.createElement('table'),header=table.createTHead().insertRow();
    for(const text of ['Year',...(row.before?['Original']:[]),'Proposed']){const th=document.createElement('th');th.scope='col';th.textContent=text;header.append(th);}const body=table.createTBody();row.after.forEach((v,i)=>{const tr=body.insertRow();for(const text of [row.start_year+i,...(row.before?[row.before[i]]:[]),v])tr.insertCell().textContent=text;});el('scenarioAnnualTable').append(table);
  };
  function drawGraph(){const host=el('scenarioChart');host.replaceChildren();el('scenarioPoint').textContent='';if(!selectedRow||!el('scenarioInspector').open)return;const row=selectedRow,after=row.after.map(Number),before=row.before?.map(Number),all=after.concat(before||[]);
    if(all.some(v=>!Number.isFinite(v))){host.textContent='Values exceed the graph numeric range. Inspect the exact annual values below.';return;}
    const width=Math.max(280,host.clientWidth),height=320,left=76,right=20,top=24,bottom=50,low=Math.min(...all),high=Math.max(...all),padding=(high-low||Math.abs(high)||1)*.1,min=low-padding,max=high+padding;
    if(!Number.isFinite(max-min)||max===min){host.textContent='The value range cannot be plotted reliably. Inspect the exact annual values below.';return;}
    const x=i=>left+(width-left-right)*(after.length===1?.5:i/(after.length-1)),y=v=>top+(height-top-bottom)*(1-(v-min)/(max-min)),ns='http://www.w3.org/2000/svg';
    const svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox',`0 0 ${width} ${height}`);svg.setAttribute('role','img');svg.setAttribute('aria-label',row.parameter+' annual scenario input values, '+row.start_year+' through '+row.end_year);host.append(svg);
    function add(tag,attrs,text){const node=document.createElementNS(ns,tag);for(const [key,value] of Object.entries(attrs))node.setAttribute(key,value);if(text!==undefined)node.textContent=text;svg.append(node);return node;}
    add('text',{x:left,y:13},'Scenario input value');
    for(let i=0;i<=4;i++){const value=min+(max-min)*i/4,yy=y(value);add('line',{x1:left,y1:yy,x2:width-right,y2:yy,class:'scenario-grid'});add('text',{x:left-8,y:yy+4,'text-anchor':'end'},Number(value.toPrecision(4)).toString());}
    const ticks=Math.min(width<460?3:5,after.length),indices=new Set(Array.from({length:ticks},(_,i)=>ticks===1?0:Math.round(i*(after.length-1)/(ticks-1))));for(const i of indices)add('text',{x:x(i),y:height-bottom+22,'text-anchor':'middle'},row.start_year+i);add('text',{x:(width+left-right)/2,y:height-4,'text-anchor':'middle'},'Year');
    function path(values,style){add('path',{d:values.map((v,i)=>(i?'L':'M')+x(i)+','+y(v)).join(' '),class:style});if(values.length===1)add('circle',{cx:x(0),cy:y(values[0]),r:4,fill:style==='scenario-after'?'#35694f':'#7c879b'});}
    if(before)path(before,'scenario-before');path(after,'scenario-after');
    const guide=add('line',{x1:left,y1:top,x2:left,y2:height-bottom,stroke:'#9ba99f','stroke-dasharray':'3 3',visibility:'hidden'});
    const describe=i=>{guide.setAttribute('x1',x(i));guide.setAttribute('x2',x(i));guide.setAttribute('visibility','visible');el('scenarioPoint').textContent=(row.start_year+i)+' · Proposed: '+row.after[i]+(row.before?' · Original: '+row.before[i]:'');};
    const overlay=add('rect',{x:left,y:top,width:width-left-right,height:height-top-bottom,fill:'transparent'});overlay.onpointermove=event=>{const rect=svg.getBoundingClientRect(),xx=(event.clientX-rect.left)*width/rect.width;describe(Math.max(0,Math.min(after.length-1,Math.round((xx-left)/(width-left-right)*(after.length-1)))));};overlay.onpointerleave=()=>guide.setAttribute('visibility','hidden');describe(after.length-1);
  }
  new ResizeObserver(()=>{if(el('scenarioInspector').open)drawGraph();}).observe(el('scenarioChart'));
  function showFile(text,name,note){el('scenarioFileTitle').textContent=name;el('scenarioFileNote').textContent=note;el('scenarioFileText').textContent=text;el('scenarioFileDialog').showModal();}
  el('scenarioFileClose').onclick=()=>el('scenarioFileDialog').close();
  el('scenarioSourceFile').onclick=()=>{if(source)showFile(source.text,source.name,'Original attached file · unchanged');};
  el('scenarioViewFile').onclick=async()=>{if(!draft||busy)return;const identity=draft.id;setBusy(true);try{const result=await api('/api/scenario/preview',{session,draft:identity});if(draft?.id===identity)showFile(result.text,result.filename,'Unsaved draft · creation time is finalized when saved');}catch(error){note(error.message,true);}finally{setBusy(false);}};
  el('scenarioForm').onsubmit=async event=>{event.preventDefault();if(busy)return;const typed=el('scenarioPrompt').value;const text=typed.trim()||(source&&!session?'Inspect the attached scenario and summarize its parameters and scope. Do not propose changes yet.':'');if(!text)return;
    message((source&&!session?'Attached: '+source.name+'\n\n':'')+text,'user');el('scenarioPrompt').value='';sizePrompt();resetDraft();setBusy(true);note('Checking model metadata and contacting the AI provider…');
    try{const result=await api('/api/scenario/chat',{message:text,session,source:session?null:source});receive(result);}
    catch(error){if(!el('scenarioPrompt').value)el('scenarioPrompt').value=typed;sizePrompt();note(error.message,true);}finally{setBusy(false);el('scenarioPrompt').focus();}
  };
  el('scenarioSave').onclick=async()=>{if(busy||!draft)return;const filename=el('scenarioFilename').value.trim();setBusy(true);note('Saving reviewed scenario…');try{const result=await api('/api/scenario/export',{session,draft:draft.id,filename});const parent=el('scenarioExportResult');parent.replaceChildren();const text=document.createElement('p');text.textContent='Saved: '+result.path;const link=document.createElement('a');link.href=result.download;link.download=result.filename;link.textContent='Download .sce';parent.append(text,link);note('Saved with descriptive comments. Existing files were not overwritten.');}catch(error){note(error.message,true);}finally{setBusy(false);}};
  async function stopResearch(){note('Stopping after the current AI call returns…');try{await api('/bridge/stop',{});}catch(error){note(error.message,true);}}
  el('scenarioStop').onclick=stopResearch;
  window.scenarioChat={start(prompt=''){navigate('scenario');el('scenarioPrompt').value=prompt;sizePrompt();el('scenarioPrompt').focus();},stop:stopResearch};
  reset();
})();
