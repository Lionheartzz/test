import {isCavity} from './definition-role.js';
import {customPort,portSetup} from './port-setup.js';
import {syncNets,clamp,axes,sizes} from './kinematics.js';

export function guided(ctx,open){
  const {$,element,field,action,post,api,notice,newProject}=ctx;
  const content=$('workflow-content'),dialog=$('workflow-dialog');
  $('project-new').onclick=()=>{
    let context='metric',name='New manifold',material='Aluminium · engineer to specify grade',length=160,width=100,height=100,ids='P, T, A, B',portConfig=Object.create(null);
    let selected=[],names=[],search='',mode='cavity',generation=0;
    const guard=fn=>async()=>{try{await fn();}catch(e){$('workflow-error').textContent=e.message;for(const status of content.querySelectorAll('.loading-state'))status.textContent='Unable to finish: '+e.message;for(const area of content.querySelectorAll('[aria-busy]'))area.removeAttribute('aria-busy');for(const button of content.querySelectorAll('button:disabled'))button.disabled=false;}};
    const block=()=>{
      open('New Manifold · 1 / 5 · Block');
      field(content,'Project name',name,v=>name=v);
      field(content,'Project context',context,v=>{const scale=v==='inch'?1/25.4:25.4;length*=scale;width*=scale;height*=scale;context=v;block();},{metric:'Metric',inch:'Inch'});
      field(content,'Block material / grade',material,v=>material=v);
      for(const [label,value,assign]of [['Length',length,v=>length=v],['Width',width,v=>width=v],['Height',height,v=>height=v]])field(content,label+' / '+(context==='inch'?'in':'mm'),value,assign,null,true);
      action(content,'Next · Nets and ports',()=>{if(!name.trim()||[length,width,height].some(x=>!Number.isFinite(x)||x<=0||x*(context==='inch'?25.4:1)>2000)){$('workflow-error').textContent='Enter a name and block dimensions between 0 and 2000 mm.';return;}connections();});
    };
    const connections=()=>{
      ++generation;open('New Manifold · 2 / 5 · Nets and ports');
      names=ids.split(',').map(x=>x.trim()).filter(Boolean);
      field(content,'Net IDs (comma separated)',ids,v=>{ids=v;connections();});
      content.append(element('p','Configure each network independently. Set quantity to zero for an internal-only net. Each external port may use a different face and machining definition. Dimensions below are mm.'));
      for(const n of names){const group=element('section',null,'library-card');content.append(group);group.append(element('h3','Net '+n));const ports=portConfig[n]??=[customPort()];
        field(group,n+' · External port quantity',ports.length,v=>{if(!Number.isInteger(v)||v<0||v>8){$('workflow-error').textContent='Use 0–8 external ports per net.';return;}while(ports.length<v)ports.push(customPort());ports.length=v;connections();},null,true);
        ports.forEach((p,i)=>portSetup(ctx,group,p,ports.length===1?n:n+(i+1),connections,context));
      }
      action(content,'Back · Block',block);action(content,'Next · Cartridges and cavities',()=>{
        if(!names.length||new Set(names).size!==names.length||names.some(x=>!/^[A-Za-z][A-Za-z0-9_-]{0,39}$/.test(x))){$('workflow-error').textContent='Use unique hydraulic net IDs.';return;}
        for(const n of names)for(const p of portConfig[n]){if(p.mode!=='custom'&&!p.definition){$('workflow-error').textContent='Select a machining definition for every configured port.';return;}if(p.mode==='custom'&&(!(p.diameter>0)||!(p.depth>0)||p.clearance<p.diameter)){ $('workflow-error').textContent='Port bore dimensions must be positive and fitting clearance must cover its diameter.';return;}}
        choose();
      });
    };
    const add=(def,compatibility=null)=>{if(!isCavity(def))throw Error('Select a cartridge-cavity definition; engineering reuse requires a reviewed role revision.');selected.push({def,quantity:1,face:'top',model:compatibility?.model||'',compatibility,mapping:Object.fromEntries(def.zones.map((z,i)=>[z.id,names[i%names.length]]))});choose();};
    const choose=()=>{
      open('New Manifold · 3 / 5 · Cartridges and cavities');const token=++generation;
      content.append(element('p','Select components before placement. Only selected definitions enter this project. Compatibility is listed only with an explicit source; cavity-only selection remains available.'));
      const basket=element('section',null,'library-card');content.append(basket);basket.append(element('h3','Selected · '+selected.length));
      selected.forEach((s,i)=>{const row=element('div',null,'action-row');row.append(element('span',s.def.label+(s.model?' · '+s.model:' · cavity only')));action(row,'Remove '+(i+1),()=>{selected.splice(i,1);choose();});basket.append(row);});
      const nav=element('div',null,'action-row');content.append(nav);action(nav,'Back · Nets',connections);action(nav,selected.length?'Next · Placement':'Continue without cavities',placement);
      field(content,'Selection workflow',mode,v=>{mode=v;choose();},{cavity:'Cavity first',cartridge:'Cartridge first · known relationships',local:'Saved PMC cavity definitions'});
      const input=field(content,mode==='cartridge'?'Cartridge model or manufacturer':'Search cavity',search,v=>search=v),results=element('div');content.append(results);let timer,request=0;
      const render=guard(async()=>{
        const requestId=++request;let rows;results.replaceChildren(element('p','Loading cavity catalog…','loading-state'));results.setAttribute('aria-busy','true');
        if(mode==='cavity')rows=(await api('/api/catalog?'+new URLSearchParams({q:search,unit:context,kind:'cavity',limit:30}))).items;
        else rows=(await api('/api/library?reusable_only=true')).filter(x=>x.preferred&&!x.deleted&&isCavity(x.definition));
        if(token!==generation||requestId!==request)return;results.removeAttribute('aria-busy');results.replaceChildren();let count=0;
        for(const row of rows){
          if(mode==='cavity'){count++;const card=element('section',null,'library-card');card.append(element('h3',row.name),element('p',`${row.manufacturer} · ${row.id}`));action(card,'Select cavity',guard(async()=>{card.append(element('p','Preparing complete cavity geometry and source records…','loading-state'));for(const b of card.querySelectorAll('button'))b.disabled=true;const d=await api('/api/catalog/definition?'+new URLSearchParams({id:row.id}));if(token===generation&&dialog.open&&card.isConnected)add(d);}));results.append(card);continue;}
          const d=row.definition;
          if(mode==='local'){if(!(d.label+' '+d.manufacturer).toLowerCase().includes(search.toLowerCase()))continue;count++;const card=element('section',null,'library-card');card.append(element('h3',d.label));action(card,'Select cavity',()=>add(d));results.append(card);}
          else for(const c of d.compatible_cartridges||[]){if(c.status==='unconfirmed'||!(c.model+' '+c.manufacturer).toLowerCase().includes(search.toLowerCase()))continue;count++;const card=element('section',null,'library-card');card.append(element('h3',c.model+' → '+d.label),element('p',`${c.manufacturer} · ${c.status} · ${c.source}`));action(card,'Select cartridge and cavity',()=>add(d,c));results.append(card);}
        }
        if(!count)results.append(element('p',mode==='cartridge'?'No documented relationship found. Choose Cavity first and enter an unconfirmed model during placement, or continue with a cavity only.':'No matches. Refine your search or use the other selection workflow.'));
        if(mode==='cavity'&&rows.length===30)results.append(element('p','Showing the first 30 matches. Refine your search to locate a specific cavity.'));
      });input.oninput=()=>{search=input.value;++request;results.replaceChildren(element('p','Searching cavities…','loading-state'));clearTimeout(timer);timer=setTimeout(render,200);};render();
    };
    const placement=()=>{
      ++generation;open('New Manifold · 4 / 5 · Placement and interfaces');
      content.append(element('p','Choose quantities, faces and interface nets. Initial positions are proposals you can refine in 3D. Known compatibility does not confirm the hydraulic interface mapping.'));
      for(const [i,s]of selected.entries()){
        const card=element('section',null,'library-card');content.append(card);card.append(element('h3',s.def.label));
        field(card,`Quantity · ${i+1}`,s.quantity,v=>s.quantity=v,null,true);field(card,`Mounting face · ${i+1}`,s.face,v=>s.face=v,Object.fromEntries(Object.keys(axes).map(f=>[f,f])));
        const known=(s.def.compatible_cartridges||[]).filter(c=>c.status!=='unconfirmed');
        field(card,`Known compatible cartridge · ${i+1}`,s.compatibility?String(known.findIndex(c=>c.model===s.compatibility.model)):'',v=>{s.compatibility=v===''?null:known[Number(v)];s.model=s.compatibility?.model||'';placement();},{'':'Cavity only / unconfirmed model',...Object.fromEntries(known.map((c,j)=>[String(j),`${c.model} · ${c.status}`]))});
        if(s.compatibility)card.append(element('p',s.compatibility.source));
        else {field(card,`Unconfirmed cartridge model · ${i+1}`,s.model,v=>s.model=v);card.append(element('p','Compatibility unknown; engineering review will remain open.'));}
        for(const z of s.def.zones)field(card,`${i+1} · Interface ${z.id} → Net`,s.mapping[z.id],v=>s.mapping[z.id]=v,Object.fromEntries(names.map(n=>[n,n])));
      }
      action(content,'Back · Selection',choose);action(content,'Next · Review',()=>{if(selected.some(s=>!Number.isInteger(s.quantity)||s.quantity<1||s.quantity>20)){$('workflow-error').textContent='Each quantity must be 1–20.';return;}review();});
    };
    const review=()=>{
      open('New Manifold · 5 / 5 · Review');
      content.append(element('p',`${name} · ${length.toFixed(2)} × ${width.toFixed(2)} × ${height.toFixed(2)} ${context==='inch'?'in':'mm'} · ${names.join(', ')} · ${selected.reduce((n,s)=>n+s.quantity,0)} cavities`));
      for(const n of names)content.append(element('p',n+': '+(portConfig[n].map(p=>`${p.face.toUpperCase()} · ${p.definition?.label||p.size+' · custom Ø'+p.diameter+' × '+p.depth}`).join('; ')||'No external ports')));
      action(content,'Back · Placement',placement);
      action(content,'Create editable draft',guard(async()=>{
        const scale=context==='inch'?25.4:1,d={schema_version:1,name,units:'mm',project_context:context,block:{length:length*scale,width:width*scale,height:height*scale,material},library:[],features:[],components:[],nets:names.map((id,i)=>({id,label:id,members:[],routing:'automatic',diameter:8,color:['#ef5959','#459cff','#41ca8b','#f2d454','#f79b42','#b08bea'][i%6]})),origin:{method:'manual',notes:'Guided setup'},review_items:[]};
        const dims=sizes(d.block),configured=names.flatMap(n=>portConfig[n].map((p,i,rows)=>({p,net:n,label:rows.length===1?n:n.slice(0,37)+(i+1)})));
        for(const {p,net,label}of configured){const sameFace=configured.filter(x=>x.p.face===p.face),index=sameFace.findIndex(x=>x.p===p),[u,v]=axes[p.face];
          const id='PORT_'+crypto.randomUUID().replaceAll('-','');
          const f={id:id.slice(0,40),kind:'port',face:p.face,u:dims[u]*(index+1)/(sameFace.length+1),v:dims[v]/2,circuit:net,size:p.size.slice(0,80),port_type:p.definition?p.definition.label:'Custom straight bore',diameter:p.diameter,depth:p.depth,clearance_diameter:p.clearance};
          if(p.definition){if(!d.library.some(x=>x.id===p.definition.id))d.library.push(structuredClone(p.definition));f.definition=p.definition.id;f.diameter=Math.min(...p.definition.stages.map(s=>s.diameter));f.depth=p.definition.zones[0].end;f.clearance_diameter=p.definition.clearance_diameter;f.clearance_height=p.definition.clearance_height;f.tip_angle=180;}
          [f.u,f.v]=clamp(f,d,f.u,f.v);d.features.push(f);
        }
        let count=0,total=selected.reduce((n,s)=>n+s.quantity,0);
        for(const s of selected){if(!d.library.some(x=>x.id===s.def.id))d.library.push(structuredClone(s.def));for(let j=0;j<s.quantity;j++){
          const [u,v]=axes[s.face],f={id:'CV'+(++count),kind:'cavity',face:s.face,u:dims[u]*count/(total+1),v:dims[v]/2,definition:s.def.id,circuits:{...s.mapping},cartridge_model:s.model};[f.u,f.v]=clamp(f,d,f.u,f.v);d.features.push(f);
          d.components.push({id:'COMP'+count,label:s.def.label,cartridge_model:s.model,cavity_definition:s.def.id,feature_id:f.id,ports:{...s.mapping},status:'unconfirmed'});
          d.review_items.push({id:'REVIEW_CV'+count,kind:'component',subject:f.id,description:s.compatibility?`Compatibility recorded: ${s.compatibility.model} / ${s.compatibility.source}. Confirm interfaces and placement.`:'Cavity selected with unknown cartridge compatibility. Confirm the intended valve, interfaces and installation envelope.',status:'open'});
        }}
        if(configured.length)d.review_items.push({id:'PORT_SPEC',kind:'component',subject:'External ports',description:'Confirm port standards, sizes, depths and material grade. Source machining profiles are pinned where selected; custom bores and fitting installation require engineering review.',status:'open'});
        syncNets(d);const checked=await post('/api/check-design',d);if(newProject(checked)){dialog.close();notice('New project ready. Refine placement and routes, then Save Project or Save & Validate.');}
      }));
    };block();
  };
}
