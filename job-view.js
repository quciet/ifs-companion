'use strict';
(() => {
  const el=id=>document.getElementById(id),query=new URLSearchParams(location.search);
  let job=query.get('id'),approval,closed=false,current;
  async function api(path,body){
    const token=parent.document.querySelector('meta[name=companion-token]')?.content||'';
    const response=await fetch(path,body?{method:'POST',headers:{'Content-Type':'application/json','X-Companion-Token':token},body:JSON.stringify(body)}:{});
    const data=await response.json();if(!response.ok)throw Error(data.error||'Request failed.');return data;
  }
  function details(values,target='details'){el(target).replaceChildren();for(const [key,value] of Object.entries(values)){const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=key;dd.textContent=String(value);el(target).append(dt,dd);}}
  function failure(error){el('error').textContent=error.message;}
  async function refresh(){
    if(!job||closed)return;
    try{
      const value=await api('/api/jobs?id='+encodeURIComponent(job)),data=value.data;current=value;
      el('title').textContent=value.kind==='scenario_run'?'Scenario run':'Job';el('status').textContent=value.status+' · '+(data.stage||'')+(data.progress?' · '+data.progress:'');
      if(value.kind==='scenario_run'){
        const stages={preparing:'Preparing IFs',running:'Running model',stopping:'Stopping model',saving:'Saving result to task',restoring:'Restoring IFs working files',recovery_required:'Working-file recovery required',recovered:'Working files restored'};
        el('title').textContent=data.scenario_name||data.filename||'Scenario run';
        el('status').textContent=value.status==='running'?(stages[data.stage]||'Running'):({complete:'Run completed',failed:'Run failed',cancelled:'Run cancelled',interrupted:'Run interrupted'}[value.status]||value.status);
        if(data.recovery_required&&value.status!=='running')el('status').textContent='Working-file recovery required';
        else if(value.status==='failed'&&data.save_status==='saved')el('status').textContent='Result saved';
        el('summary').textContent=data.save_status==='saved'?'Result saved with this task. Use Save to IFs to keep independent copies.':'Scenario and logs are kept with this task.';
        const duration=Math.max(0,Math.floor((data.finished_at||Date.now()/1000)-(data.started_at||value.created)));
        const state={'restored':'IFs working files restored','restoring':'Restoring IFs working files','required':'Recovery required — restore working files before continuing','backup_ready':'Working files backed up','not_needed':'Working files unchanged'};
        details({'Model year':(data.current_year??'Waiting for model')+' / '+data.end_year,'Elapsed':Math.floor(duration/60)+'m '+duration%60+'s','Last model update':data.last_progress_at?new Date(data.last_progress_at*1000).toLocaleTimeString():'No year reported yet','Task result':({pending:'Not saved yet',saving:'Saving and validating',failed:'Save failed',saved:'Saved'}[data.save_status]||'Not saved'),'Recovery':state[data.recovery_status]||(data.recovery_required?'Recovery required':'No recovery pending')},'runStatus');
        el('save').hidden=!((value.status==='complete'||data.save_status==='saved')&&value.status!=='running'&&data.output&&!data.recovery_required);
        el('saved').textContent=data.saved_to_ifs?'Independent copies saved to IFs: '+data.saved_to_ifs.scenario+' and '+data.saved_to_ifs.run:'';
        el('logs').hidden=!data.log_tail;el('log').textContent=data.log_tail||'';
      }
      const fields={Job:value.id};
      if(value.kind==='scenario_run')Object.assign(fields,{File:data.filename||'—',Installation:data.installation||'—','End year':data.end_year||'—',SHA256:data.sha256||'—',Output:value.status==='complete'?(data.output||'—'):'Not available'});
      else if(value.kind==='comparison')fields.Comparison=data.backend_id;
      else if(value.kind==='chat')fields.Conversation=value.owner;
      else fields.Action=data.action||value.kind;
      details(fields);
      el('error').textContent=[data.error,data.cleanup_warning].filter(Boolean).join(' ');el('cancel').hidden=value.status!=='running';
      el('recover').hidden=value.status==='running'||!(data.recovery_required||(value.status==='interrupted'&&value.kind==='scenario_run'));
      el('compare').hidden=!((value.status==='complete'||data.save_status==='saved')&&value.status!=='running'&&data.output&&!data.recovery_required);
      el('compare').onclick=()=>parent.postMessage({type:'companion-run-compare',run:data.output},location.origin);
      if(value.kind==='comparison'){
        el('compare').hidden=value.status!=='complete';el('compare').textContent='Open comparison results';
        el('compare').onclick=()=>parent.postMessage({type:'companion-job-report',report:data.backend_id},location.origin);
      }
      if(value.status==='running')setTimeout(refresh,1000);
    }catch(error){failure(error);}
  }
  el('approve').onclick=async()=>{
    el('approve').disabled=true;el('error').textContent='';
    try{
      const value=await api('/api/runs/start',{chat:approval.owner,approval:approval.id,sha256:approval.sha256});
      job=value.id;el('technical').open=false;el('approve').hidden=true;el('content').hidden=true;
      parent.postMessage({type:'companion-run-started',job},location.origin);await refresh();
    }catch(error){failure(error);el('approve').disabled=false;}
  };
  el('save').onclick=()=>{
    el('saveForm').hidden=!el('saveForm').hidden;
    if(!el('saveForm').hidden){el('saveName').value=current.data.scenario_name||(current.data.filename||'Scenario.sce').replace(/\.sce$/i,'');el('saveName').focus();}
  };
  el('saveForm').onsubmit=async event=>{
    event.preventDefault();const button=event.submitter;button.disabled=true;el('error').textContent='';
    try{await api('/api/runs/save',{id:job,name:el('saveName').value});el('saveForm').hidden=true;await refresh();}
    catch(error){failure(error);}finally{button.disabled=false;}
  };
  el('cancel').onclick=async()=>{try{await api('/api/jobs/cancel',{id:job});await refresh();}catch(error){failure(error);}};
  el('recover').onclick=async()=>{try{await api('/api/jobs/recover',{id:job});await refresh();}catch(error){failure(error);}};
  window.companionSession={canGoBack:()=>false,stop:async()=>{if(job)await api('/api/jobs/cancel',{id:job});await refresh();}};
  window.addEventListener('pagehide',()=>{closed=true;});
  if(query.has('approval')){
    api('/api/runs/approval?chat='+encodeURIComponent(query.get('chat'))+'&id='+encodeURIComponent(query.get('approval'))).then(value=>{
      approval=value;el('technical').open=true;el('title').textContent='Review and approve model execution';
      el('status').textContent='This will run the exact scenario below. IFs working files are backed up and restored afterward.';
      details({File:value.filename,Installation:value.installation,'End year':value.end_year,SHA256:value.sha256});
      el('content').textContent=value.text;el('content').hidden=false;el('approve').hidden=false;
    }).catch(failure);
  }else refresh();
})();
