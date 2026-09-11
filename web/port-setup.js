import {isPort as suitable,nativeUnit} from './definition-role.js';
export const customPort=()=>({face:'front',size:'Custom',diameter:12,depth:16,clearance:20,mode:'custom',definition:null,search:''});

export function portSetup(ctx,parent,port,label,redraw,context=ctx.get?.().project_context||'metric'){
  const {element,field,action,api}=ctx;
  const card=element('section',null,'port-row');parent.append(card);card.append(element('h3',label));
  field(card,label+' · Face',port.face,v=>port.face=v,Object.fromEntries(['left','right','front','back','bottom','top'].map(f=>[f,f.toUpperCase()])));
  field(card,label+' · Machining',port.mode,v=>{port.mode=v;port.definition=null;redraw();},{custom:'Custom straight bore',catalog:'MDTools external-port definitions',pmc:'Saved PMC definition · engineer selected'});
  if(port.mode==='custom'){
    field(card,label+' · Specification / note',port.size,v=>port.size=v);
    for(const [key,title]of [['diameter','Diameter'],['depth','Cylinder depth'],['clearance','Fitting / tool clearance diameter']])field(card,label+' · '+title+' / mm',port[key],v=>port[key]=v,null,true);
    return;
  }
  if(port.definition){card.append(element('p',port.definition.label+' · '+port.definition.source),element('p','Exact pinned machining profile; thread recipe and manufacturing review retained.'));action(card,'Change '+label+' definition',()=>{port.definition=null;redraw();});return;}
  port.unit??=context;field(card,label+' · Native units',port.unit,v=>{port.unit=v;redraw();},{metric:'Metric',inch:'Inch','':'All native units'});
  const input=field(card,label+' · Search port definition',port.search,v=>port.search=v),results=element('div');card.append(results);let request=0,timer;
  async function search(){const token=++request;results.replaceChildren(element('p','Loading port definitions…','loading-state'));results.setAttribute('aria-busy','true');try{
    const rows=port.mode==='catalog'?(await api('/api/catalog?'+new URLSearchParams({kind:'port_definition',unit:port.unit,q:port.search,limit:30}))).items:(await api('/api/library?reusable_only=true')).filter(r=>r.preferred&&!r.deleted&&suitable(r.definition)&&(!port.unit||!nativeUnit(r.definition)||nativeUnit(r.definition)===port.unit)&&(r.definition.label+' '+r.definition.thread_note).toLowerCase().includes(port.search.toLowerCase()));
    if(token!==request||!card.isConnected)return;results.replaceChildren();
    for(const row of rows){const item=element('div',null,'library-card');results.append(item);item.append(element('p',row.name||row.definition.label),element('p',row.definition?row.definition.thread_note:`${row.thread} · ${row.unit} · ${row.manufacturer} · ${row.id}`));
      action(item,'Use for '+label,async()=>{const buttons=[...results.querySelectorAll('button')];buttons.forEach(b=>b.disabled=true);const status=element('p','Preparing full machining definition…','loading-state');item.append(status);try{const d=row.definition||await api('/api/catalog/definition?'+new URLSearchParams({id:row.id}));if(!suitable(d))throw Error('This definition does not provide a single centered port interface. Select another definition or use a reviewed custom bore.');port.definition=d;port.size=d.thread_note||d.label;redraw();}catch(e){status.textContent=e.message;buttons.forEach(b=>b.disabled=false);}});
    }
    if(!rows.length)results.append(element('p','No matching port definitions. Search another size or use Custom straight bore. No standard dimensions are inferred.'));
  }catch(e){if(token===request)results.replaceChildren(element('p',e.message));}finally{if(token===request)results.removeAttribute('aria-busy');}}
  input.oninput=()=>{port.search=input.value;++request;clearTimeout(timer);results.replaceChildren(element('p','Searching port definitions…','loading-state'));timer=setTimeout(search,200);};search();
}
