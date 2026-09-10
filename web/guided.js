import {syncNets,clamp,axes,sizes} from './kinematics.js';

export function guided(ctx,open){
  const {$,element,field,action,post,api,notice,newProject}=ctx;
  const content=$('workflow-content'),dialog=$('workflow-dialog');
  $('project-new').onclick=()=>{
    let context='metric',name='New manifold',material='Aluminium · engineer to specify grade',length=160,width=100,height=100,ids='P, T, A, B',ports=1,face='front';
    let selected=[],names=[],search='',mode='cavity',generation=0;
    const guard=fn=>async()=>{try{await fn();}catch(e){$('workflow-error').textContent=e.message;}};
    const block=()=>{
      open('New Manifold · 1 / 5 · Block');
      field(content,'Project name',name,v=>name=v);
      field(content,'Project context',context,v=>{const scale=v==='inch'?1/25.4:25.4;length*=scale;width*=scale;height*=scale;context=v;block();},{metric:'Metric',inch:'Inch'});
      field(content,'Block material / grade',material,v=>material=v);
      for(const [label,value,assign]of [['Length',length,v=>length=v],['Width',width,v=>width=v],['Height',height,v=>height=v]])field(content,label+' / '+(context==='inch'?'in':'mm'),value,assign,null,true);
      action(content,'Next · Nets and ports',()=>{if(!name.trim()||[length,width,height].some(x=>!Number.isFinite(x)||x<=0||x*(context==='inch'?25.4:1)>2000)){$('workflow-error').textContent='Enter a name and block dimensions between 0 and 2000 mm.';return;}connections();});
    };
    const connections=()=>{
      open('New Manifold · 2 / 5 · Nets and ports');
      field(content,'Net IDs (comma separated)',ids,v=>ids=v);field(content,'External ports per net',ports,v=>ports=v,null,true);
      field(content,'Initial port face',face,v=>face=v,Object.fromEntries(Object.keys(axes).map(x=>[x,x])));
      content.append(element('p','Ports start as editable straight bores. Confirm the actual port specification in Review.'));
      action(content,'Back · Block',block);action(content,'Next · Cartridges and cavities',()=>{
        names=ids.split(',').map(x=>x.trim()).filter(Boolean);
        if(!names.length||new Set(names).size!==names.length||names.some(x=>!/^[A-Za-z][A-Za-z0-9_-]{0,39}$/.test(x))||!Number.isInteger(ports)||ports<0||ports>4){$('workflow-error').textContent='Use unique net IDs and 0–4 ports per net.';return;}
        choose();
      });
    };
    const add=(def,compatibility=null)=>{selected.push({def,quantity:1,face:'top',model:compatibility?.model||'',compatibility,mapping:Object.fromEntries(def.zones.map((z,i)=>[z.id,names[i%names.length]]))});choose();};
    const choose=()=>{
      open('New Manifold · 3 / 5 · Cartridges and cavities');const token=++generation;
      content.append(element('p','Select components before placement. Only selected definitions enter this project. Compatibility is listed only with an explicit source; cavity-only selection remains available.'));
      const basket=element('section',null,'library-card');content.append(basket);basket.append(element('h3','Selected · '+selected.length));
      selected.forEach((s,i)=>{const row=element('div',null,'action-row');row.append(element('span',s.def.label+(s.model?' · '+s.model:' · cavity only')));action(row,'Remove '+(i+1),()=>{selected.splice(i,1);choose();});basket.append(row);});
      const nav=element('div',null,'action-row');content.append(nav);action(nav,'Back · Nets',connections);action(nav,selected.length?'Next · Placement':'Continue without cavities',placement);
      field(content,'Selection workflow',mode,v=>{mode=v;choose();},{cavity:'Cavity first',cartridge:'Cartridge first · known relationships',local:'Saved PMC cavity definitions'});
      const input=field(content,mode==='cartridge'?'Cartridge model or manufacturer':'Search cavity',search,v=>search=v),results=element('div');content.append(results);let timer,request=0;
      const render=guard(async()=>{
        const requestId=++request;let rows;
        if(mode==='cavity')rows=(await api('/api/catalog?'+new URLSearchParams({q:search,unit:context,kind:'cavity',limit:30}))).items;
        else rows=(await api('/api/library?reusable_only=true')).filter(x=>x.preferred&&!x.deleted);
        if(token!==generation||requestId!==request)return;results.replaceChildren();let count=0;
        for(const row of rows){
          if(mode==='cavity'){count++;const card=element('section',null,'library-card');card.append(element('h3',row.name),element('p',`${row.manufacturer} · ${row.id}`));action(card,'Select cavity',guard(async()=>{const d=await api('/api/catalog/definition?'+new URLSearchParams({id:row.id}));if(token===generation)add(d);}));results.append(card);continue;}
          const d=row.definition;
          if(mode==='local'){if(!(d.label+' '+d.manufacturer).toLowerCase().includes(search.toLowerCase()))continue;count++;const card=element('section',null,'library-card');card.append(element('h3',d.label));action(card,'Select cavity',()=>add(d));results.append(card);}
          else for(const c of d.compatible_cartridges||[]){if(c.status==='unconfirmed'||!(c.model+' '+c.manufacturer).toLowerCase().includes(search.toLowerCase()))continue;count++;const card=element('section',null,'library-card');card.append(element('h3',c.model+' → '+d.label),element('p',`${c.manufacturer} · ${c.status} · ${c.source}`));action(card,'Select cartridge and cavity',()=>add(d,c));results.append(card);}
        }
        if(!count)results.append(element('p',mode==='cartridge'?'No documented relationship found. Choose Cavity first and enter an unconfirmed model during placement, or continue with a cavity only.':'No matches. Refine your search or use the other selection workflow.'));
        if(mode==='cavity'&&rows.length===30)results.append(element('p','Showing the first 30 matches. Refine your search to locate a specific cavity.'));
      });input.oninput=()=>{search=input.value;clearTimeout(timer);timer=setTimeout(render,200);};render();
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
      action(content,'Back · Placement',placement);
      action(content,'Create editable draft',guard(async()=>{
        const scale=context==='inch'?25.4:1,d={schema_version:1,name,units:'mm',project_context:context,block:{length:length*scale,width:width*scale,height:height*scale,material},library:[],features:[],components:[],nets:names.map((id,i)=>({id,label:id,members:[],routing:'automatic',diameter:8,color:['#ef5959','#459cff','#41ca8b','#f2d454','#f79b42','#b08bea'][i%6]})),origin:{method:'manual',notes:'Guided setup'},review_items:[]};
        const [u,v]=axes[face],dims=sizes(d.block);
        for(const [i,n]of d.nets.entries())for(let j=0;j<ports;j++){const f={id:`PORT_${i+1}_${j+1}`,kind:'port',face,u:dims[u]*(i+1)/(names.length+1),v:dims[v]*(j+1)/(ports+1),circuit:n.id,diameter:12,depth:16,clearance_diameter:20};[f.u,f.v]=clamp(f,d,f.u,f.v);d.features.push(f);}
        let count=0,total=selected.reduce((n,s)=>n+s.quantity,0);
        for(const s of selected){if(!d.library.some(x=>x.id===s.def.id))d.library.push(structuredClone(s.def));for(let j=0;j<s.quantity;j++){
          const [u,v]=axes[s.face],f={id:'CV'+(++count),kind:'cavity',face:s.face,u:dims[u]*count/(total+1),v:dims[v]/2,definition:s.def.id,circuits:{...s.mapping},cartridge_model:s.model};[f.u,f.v]=clamp(f,d,f.u,f.v);d.features.push(f);
          d.components.push({id:'COMP'+count,label:s.def.label,cartridge_model:s.model,cavity_definition:s.def.id,feature_id:f.id,ports:{...s.mapping},status:'unconfirmed'});
          d.review_items.push({id:'REVIEW_CV'+count,kind:'component',subject:f.id,description:s.compatibility?`Compatibility recorded: ${s.compatibility.model} / ${s.compatibility.source}. Confirm interfaces and placement.`:'Cavity selected with unknown cartridge compatibility. Confirm the intended valve, interfaces and installation envelope.',status:'open'});
        }}
        if(ports)d.review_items.push({id:'PORT_SPEC',kind:'component',subject:'External ports',description:'Confirm port standards, sizes, depths and material grade. Initial ports are straight-bore proposals.',status:'open'});
        syncNets(d);const checked=await post('/api/check-design',d);if(newProject(checked)){dialog.close();notice('New project ready. Refine placement and routes, then Save Project or Save & Validate.');}
      }));
    };block();
  };
}
