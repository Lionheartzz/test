import {syncNets,clamp,axes,sizes} from './kinematics.js';

export function guided(ctx,open,library,nets){
  const {$,element,field,action,get,set,change,post,notice}=ctx;
  const content=$('workflow-content'),dialog=$('workflow-dialog');
  $('project-new').onclick=()=>{
    let context='metric',name='New manifold',material='Aluminium · engineer to specify grade',length=160,width=100,height=100,ids='P, T, A, B',ports=1,face='front';
    open('New Manifold · 1 / 3 · Block');
    const block=()=>{
      open('New Manifold · 1 / 3 · Block');
      field(content,'Project name',name,v=>name=v);
      field(content,'Project context',context,v=>{const scale=v==='inch'?1/25.4:25.4;length*=scale;width*=scale;height*=scale;context=v;block();},{metric:'Metric',inch:'Inch'});
      field(content,'Block material / grade',material,v=>material=v);
      for(const [label,value,assign]of [['Length',length,v=>length=v],['Width',width,v=>width=v],['Height',height,v=>height=v]])field(content,label+' / '+(context==='inch'?'in':'mm'),value,assign,null,true);
      content.append(element('p','Only stock and connection intent are needed to begin. Exact CAD coordinates are stored in mm. Material stock can also be inspected and pinned from the Library.'));
      action(content,'Next · Nets and ports',connections);
    };
    const connections=()=>{
      open('New Manifold · 2 / 3 · Nets and ports');
      field(content,'Net IDs (comma separated)',ids,v=>ids=v);
      field(content,'External ports per net',ports,v=>ports=v,null,true);
      field(content,'Initial port face',face,v=>face=v,Object.fromEntries(Object.keys(axes).map(x=>[x,x])));
      content.append(element('p','Ports start as editable straight bores. Confirm the actual port specification in Review. Assign cavity interfaces to these nets to propose connections automatically.'));
      action(content,'Back · Block',block);action(content,'Next · Review draft',review);
    };
    const review=()=>{
      const names=ids.split(',').map(x=>x.trim()).filter(Boolean);
      if(!names.length||new Set(names).size!==names.length||names.some(x=>!/^[A-Za-z][A-Za-z0-9_-]{0,39}$/.test(x))||!Number.isInteger(ports)||ports<0||ports>4){$('workflow-error').textContent='Use unique net IDs and 0–4 ports per net.';return;}
      open('New Manifold · 3 / 3 · Review');
      content.append(element('p',`${name} · ${material} · ${length.toFixed(3)} × ${width.toFixed(3)} × ${height.toFixed(3)} ${context==='inch'?'in':'mm'} · ${names.join(', ')} · ${ports*names.length} ports`));
      content.append(element('p','Create the draft, choose cavities in the Library, set quantity and face, then place components. Use Hydraulic Nets to review routes and colors. Save & Validate runs exact CAD checks.'));
      action(content,'Back · Nets',connections);
      action(content,'Create editable draft',async()=>{try{
        const scale=context==='inch'?25.4:1,d={schema_version:1,name,units:'mm',project_context:context,block:{length:Number((length*scale).toFixed(8)),width:Number((width*scale).toFixed(8)),height:Number((height*scale).toFixed(8)),material},library:structuredClone(get().library),features:[],nets:names.map((id,i)=>({id,label:id,members:[],routing:'automatic',diameter:8,color:['#ef5959','#459cff','#41ca8b','#f2d454','#f79b42','#b08bea'][i%6]})),origin:{method:'manual',notes:'Guided setup'},review_items:[]};
        const [u,v]=axes[face],dims=sizes(d.block);
        for(const [i,n]of d.nets.entries())for(let j=0;j<ports;j++){const f={id:`PORT_${i+1}_${j+1}`,kind:'port',face,u:dims[u]*(i+1)/(names.length+1),v:dims[v]*(j+1)/(ports+1),circuit:n.id,diameter:12,depth:16,clearance_diameter:20};[f.u,f.v]=clamp(f,d,f.u,f.v);d.features.push(f);}
        if(ports)d.review_items.push({id:'PORT_SPEC',kind:'component',subject:'External ports',description:'Confirm port standards, sizes, depths and material grade. Initial ports are straight-bore proposals.',status:'open'});
        syncNets(d);const checked=await post('/api/check-design',d);if(change(()=>set(checked))){dialog.close();notice('Draft created. Continue: Cavities → Placement → Hydraulic Nets → Engineering Review → Save & Validate.');}
      }catch(e){$('workflow-error').textContent=e.message;}});
    };block();
  };
}
