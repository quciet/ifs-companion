'use strict';
async function api(path,body){
  const token=parent.document.querySelector('meta[name=companion-token]')?.content;
  const response=await fetch(path.replace(/^\//,''),body?{method:'POST',headers:{'Content-Type':'application/json','X-Companion-Token':token||''},body:JSON.stringify(body)}:{});
  const data=await response.json();if(!response.ok)throw Error(data.error||'Request failed.');
  if(data.download)data.download=data.download.replace(/^\//,'');return data;
}
function confirmTool(title,body,label){return Promise.resolve(window.confirm(title+'\n\n'+body));}
function navigate(view){if(view==='settings')parent.companionTools.openAISettings();}
document.querySelectorAll('[data-view="settings"]').forEach(button=>button.onclick=()=>navigate('settings'));
window.companionSession={canGoBack:()=>Boolean(document.querySelector('dialog[open]')),back:()=>{document.querySelector('dialog[open]')?.close();},stop:async()=>{if(window.scenarioChat?.stop)await window.scenarioChat.stop();else await api('/bridge/stop',{});}};
document.addEventListener('close',()=>parent.postMessage({type:'tool-navigation'},location.origin),true);
new MutationObserver(()=>parent.postMessage({type:'tool-navigation'},location.origin)).observe(document.body,{subtree:true,attributes:true,attributeFilter:['open']});
