import {isCavity} from './definition-role.js';

export function libraryUI(ctx,{open,insert}){
  const {$,element,field,action,api}=ctx,content=$('workflow-content');
  const guard=fn=>async()=>{try{await fn();$('workflow-error').textContent='';}catch(e){$('workflow-error').textContent=e.message;}};
  let generation=0;
  return async function library(){
    const token=++generation;open('Engineering Library · SQLite');
    content.append(element('p','Search the runtime engineering database. A selected cavity is referenced by ID; its full definition is loaded for this session and is not embedded in the project.'));
    const filters=element('div',null,'editor-grid'),list=element('div',null,'library-list'),pager=element('div',null,'action-row');content.append(filters,list,pager);
    const query={q:'',unit:ctx.get().project_context||'',kind:'cavity',offset:0,limit:30};let timer;
    const load=guard(async()=>{
      const request=++generation;list.replaceChildren(element('p','Loading SQLite engineering data…'));pager.replaceChildren();
      const result=await api('/api/catalog?'+new URLSearchParams(query));if(token!==generation||request!==generation)return;
      list.replaceChildren(element('p',`${result.total.toLocaleString()} matching cavities`));
      for(const row of result.items){
        const card=element('section',null,'library-card');list.append(card);card.append(element('h3',row.name),element('p',`${row.manufacturer||'Manufacturer unspecified'} · ${row.unit_system.toUpperCase()}\n${row.thread_spec||'No thread specification'}\n${row.id}`));
        if(!row.usable)card.append(element('p','Unavailable: '+row.unusable_reason,'error'));
        if(row.usable)action(card,'Place cavity',guard(async()=>{const definition=await api('/api/catalog/definition?'+new URLSearchParams({id:row.id}));if(!isCavity(definition))throw Error('Selected record is not a cavity.');insert(definition);}));
      }
      if(query.offset>0)action(pager,'Previous page',()=>{query.offset=Math.max(0,query.offset-query.limit);load();});
      pager.append(element('span',result.total?`${query.offset+1}–${Math.min(query.offset+query.limit,result.total)} / ${result.total}`:'0 results'));
      if(query.offset+query.limit<result.total)action(pager,'Next page',()=>{query.offset+=query.limit;load();});
    });
    const update=(key,value)=>{query[key]=value;query.offset=0;clearTimeout(timer);timer=setTimeout(load,180);};
    const search=field(filters,'Search cavity',query.q,v=>update('q',v));search.oninput=()=>update('q',search.value);
    field(filters,'Engineering units',query.unit,v=>update('unit',v),{'':'All units',metric:'Metric',inch:'Inch'});
    content.append(element('p','External-port definitions are selected from Add External Port. Cartridge assignments are chosen on a placed cavity and validated by the explicit database relationship.'));
    await load();
  };
}
