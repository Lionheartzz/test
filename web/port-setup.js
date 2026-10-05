import {isPort as suitable} from './definition-role.js';
import {customPortDescription} from './engineering-inputs.js';
export const customPort=()=>({face:'front',size:'Custom',diameter:12,depth:16,clearance:20,mode:'oneoff',definition:null,search:'',unit:'',standard:'',standardOptions:null});

export function portSetup(ctx,parent,port,label,redraw,context=ctx.get?.().project_context||'metric'){
  const {element,field,action,api}=ctx;
  const card=element('section',null,'port-row');parent.append(card);card.append(element('h3',label));
  field(card,label+' · Face',port.face,v=>port.face=v,Object.fromEntries(['left','right','front','back','bottom','top'].map(f=>[f,f.toUpperCase()])));
  field(card,label+' · Port source',port.mode,v=>{port.mode=v;port.definition=null;redraw();},{standard:'Standard Hydraulic Port',reusable:'Reusable Custom Port',oneoff:'One-off Custom Straight Bore'});
  if(port.mode==='oneoff'){
    const description=element('p',customPortDescription(port.diameter,port.depth));
    for(const [key,title]of [['diameter','Diameter'],['depth','Cylinder depth'],['clearance','Fitting / tool clearance diameter']])field(card,label+' · '+title+' / mm',port[key],v=>{port[key]=v;description.textContent=customPortDescription(port.diameter,port.depth);},null,true);
    card.append(description);
    return;
  }
  if(port.definition){card.append(element('p',port.definition.label),element('p',(port.definition.family||'Family unspecified')+' · '+(port.definition.thread_note||'Thread specification not recorded')+' · Complete machining definition.'));action(card,'Change '+label+' definition',()=>{port.definition=null;redraw();});return;}
  const scope=port.mode==='reusable'?'custom':'master';
  if(port.mode==='standard'){
    if(port.standardOptions===null){port.standardOptions=[];api('/api/catalog/standards?kind=port').then(result=>{port.standardOptions=result.items||[];if(card.isConnected)redraw();}).catch(()=>{});}
    field(card,label+' · Port standard',port.standard,v=>{port.standard=v;redraw();},{'':'All standards',...Object.fromEntries(port.standardOptions.map(value=>[value,value.replaceAll('_',' ')]))});
  }
  port.unit??='';field(card,label+' · Native definition',port.unit,v=>{port.unit=v;redraw();},{'':'All',metric:'Metric-native',inch:'Inch-native'});
  const input=field(card,label+' · Search port definition',port.search,v=>port.search=v),results=element('div');card.append(results);let request=0,timer;
  async function search(){const token=++request;results.replaceChildren(element('p','Loading port definitions…','loading-state'));results.setAttribute('aria-busy','true');try{
    const rows=(await api('/api/catalog?'+new URLSearchParams({kind:'port_definition',unit:port.unit,standard:port.standard||'',q:port.search,scope,status:'usable',limit:30}))).items;
    if(token!==request||!card.isConnected)return;results.replaceChildren();
    for(const row of rows){const item=element('div',null,'library-card');results.append(item);item.append(element('p',row.name||row.definition.label),element('p',row.definition?row.definition.thread_note:`${row.thread_spec||'No thread specification'} · ${(row.unit_system||'').toUpperCase()||'Units unspecified'} · ${row.manufacturer||'Manufacturer unspecified'} · ${row.id}`));
      action(item,'Use for '+label,async()=>{const buttons=[...results.querySelectorAll('button')];buttons.forEach(b=>b.disabled=true);const status=element('p','Preparing full machining definition…','loading-state');item.append(status);try{const d=row.definition||await api('/api/catalog/definition?'+new URLSearchParams({id:row.id}));if(!suitable(d))throw Error('This definition does not provide a single centered port interface. Select another definition or use a reviewed custom bore.');port.definition=d;port.size=d.thread_note||d.label;redraw();}catch(e){status.textContent=e.message;buttons.forEach(b=>b.disabled=false);}});
    }
    if(!rows.length)results.append(element('p',port.mode==='reusable'?'No reusable custom port definitions match. Create reusable definitions in Engineering Library → External Ports.':'No matching standard hydraulic port definitions. Search another family or size, or explicitly choose a one-off custom straight bore. No standard dimensions are inferred.'));
  }catch(e){if(token===request)results.replaceChildren(element('p',e.message));}finally{if(token===request)results.removeAttribute('aria-busy');}}
  input.oninput=()=>{port.search=input.value;++request;clearTimeout(timer);results.replaceChildren(element('p','Searching port definitions…','loading-state'));timer=setTimeout(search,200);};search();
}
