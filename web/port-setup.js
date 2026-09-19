import {isPort as suitable,nativeUnit} from './definition-role.js';
export const customPort=()=>({face:'front',size:'Custom',diameter:12,depth:16,clearance:20,mode:'oneoff',definition:null,search:''});

export function portSetup(ctx,parent,port,label,redraw,context=ctx.get?.().project_context||'metric'){
  const {element,field,action,api}=ctx;
  const card=element('section',null,'port-row');parent.append(card);card.append(element('h3',label));
  field(card,label+' · Face',port.face,v=>port.face=v,Object.fromEntries(['left','right','front','back','bottom','top'].map(f=>[f,f.toUpperCase()])));
  field(card,label+' · Port source',port.mode,v=>{port.mode=v;port.definition=null;redraw();},{standard:'Standard Hydraulic Port',reusable:'Reusable Custom SQLite Port',oneoff:'One-off Custom Straight Bore'});
  if(port.mode==='oneoff'){
    field(card,label+' · Specification / note',port.size,v=>port.size=v);
    for(const [key,title]of [['diameter','Diameter'],['depth','Cylinder depth'],['clearance','Fitting / tool clearance diameter']])field(card,label+' · '+title+' / mm',port[key],v=>port[key]=v,null,true);
    if(ctx.createCustomExternalPort)action(card,'Create reusable custom external port',()=>ctx.createCustomExternalPort({onSelect:definition=>{port.mode='reusable';port.definition=definition;port.size=definition.thread_note||definition.label;redraw();},actionLabel:'Use External Port'}));
    return;
  }
  if(port.definition){card.append(element('p',port.definition.label+' · '+port.definition.id),element('p','Exact runtime machining profile from the engineering database.'));if(ctx.viewExternalPort)action(card,'View Definition',()=>ctx.viewExternalPort(port.definition,{onSelect:definition=>{port.definition=definition;port.size=definition.thread_note||definition.label;redraw();},actionLabel:'Use External Port'}));action(card,'Change '+label+' definition',()=>{port.definition=null;redraw();});return;}
  const scope=port.mode==='reusable'?'custom':'master';
  if(ctx.externalPortLibrary)action(card,port.mode==='reusable'?'Browse Reusable Custom Ports':'Browse Standard Hydraulic Ports',()=>ctx.externalPortLibrary({scope,onSelect:definition=>{port.definition=definition;port.size=definition.thread_note||definition.label;redraw();},actionLabel:'Use External Port'}));
  port.unit??=context;field(card,label+' · Native units',port.unit,v=>{port.unit=v;redraw();},{metric:'Metric',inch:'Inch','':'All native units'});
  const input=field(card,label+' · Search port definition',port.search,v=>port.search=v),results=element('div');card.append(results);let request=0,timer;
  async function search(){const token=++request;results.replaceChildren(element('p','Loading port definitions…','loading-state'));results.setAttribute('aria-busy','true');try{
    const rows=(await api('/api/catalog?'+new URLSearchParams({kind:'port_definition',unit:port.unit,q:port.search,scope,limit:30}))).items;
    if(token!==request||!card.isConnected)return;results.replaceChildren();
    for(const row of rows){const item=element('div',null,'library-card');results.append(item);item.append(element('p',row.name||row.definition.label),element('p',row.definition?row.definition.thread_note:`${row.thread_spec||'No thread specification'} · ${(row.unit_system||'').toUpperCase()||'Units unspecified'} · ${row.manufacturer||'Manufacturer unspecified'} · ${row.id}`));
      if(ctx.viewExternalPort)action(item,'View Definition',async()=>{const payload=await api('/api/catalog/record?'+new URLSearchParams({id:row.id}));ctx.viewExternalPort(payload.definition,{onSelect:definition=>{port.definition=definition;port.size=definition.thread_note||definition.label;redraw();},actionLabel:'Use External Port'});});
      action(item,'Use for '+label,async()=>{const buttons=[...results.querySelectorAll('button')];buttons.forEach(b=>b.disabled=true);const status=element('p','Preparing full machining definition…','loading-state');item.append(status);try{const d=row.definition||await api('/api/catalog/definition?'+new URLSearchParams({id:row.id}));if(!suitable(d))throw Error('This definition does not provide a single centered port interface. Select another definition or use a reviewed custom bore.');port.definition=d;port.size=d.thread_note||d.label;redraw();}catch(e){status.textContent=e.message;buttons.forEach(b=>b.disabled=false);}});
    }
    if(!rows.length)results.append(element('p',port.mode==='reusable'?'No reusable custom port definitions match. Create one from the one-off workflow if its engineering geometry is complete.':'No matching standard hydraulic port definitions. Search another family or size, or explicitly choose a one-off custom straight bore. No standard dimensions are inferred.'));
  }catch(e){if(token===request)results.replaceChildren(element('p',e.message));}finally{if(token===request)results.removeAttribute('aria-busy');}}
  input.oninput=()=>{port.search=input.value;++request;clearTimeout(timer);results.replaceChildren(element('p','Searching port definitions…','loading-state'));timer=setTimeout(search,200);};search();
}
