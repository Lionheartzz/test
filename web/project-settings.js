import {setDesignPriority} from './engineering-inputs.js';

export function projectSettings(ctx,{open}){
  const {get,field,element,change,$}=ctx;
  return ()=>{
    open('Project Settings');const content=$('workflow-content'),d=get();if(!d)return;
    d.project_defaults??={pressure_bar:null,flow_lpm:null,velocity_limit:6,drilling_mode:'orthogonal'};
    const section=name=>{const card=element('section',null,'library-card');card.append(element('h3',name));content.append(card);return card;};
    const edit=(parent,label,value,apply,options=null,numeric=false)=>field(parent,label,value,v=>change(()=>{
      apply(v);for(const n of d.nets)if(n.routing==='automatic')n.routing_variant=null;
    }),options,numeric);
    const general=section('General');edit(general,'Project name',d.name,v=>d.name=v);
    edit(general,'Project unit preference',d.project_context,v=>d.project_context=v,{metric:'Metric',inch:'Imperial'});
    general.append(element('p','Controls defaults and ordering. Metric and inch standards may be mixed.','property-note'));
    const hydraulic=section('Hydraulic defaults');
    for(const [key,label,numeric]of [['pressure_bar','Default design pressure / bar','optional'],['flow_lpm','Default flow / L/min','optional'],['velocity_limit','Default velocity limit / m/s',true]])
      edit(hydraulic,label,d.project_defaults[key]??'',v=>d.project_defaults[key]=v,null,numeric);
    edit(hydraulic,'Pressure safety factor',d.rules.pressure_safety_factor,v=>d.rules.pressure_safety_factor=v,null,true);
    const limits=section('Engineering limits');
    edit(limits,'Minimum wall / ligament (optional) / mm',d.rules.minimum_wall??'',v=>d.rules.minimum_wall=v,null,'optional');
    edit(limits,'Preferred wall margin (optional) / mm',d.constraints.preferred_wall_margin??'',v=>d.constraints.preferred_wall_margin=v,null,'optional');
    limits.append(element('p','Blank minimum uses calculated local pressure ligament. A project floor can only raise it. Preferred margin affects routing rank, never PASS/FAIL.','property-note'));
    const routing=section('Routing');edit(routing,'Design priority',d.constraints.priority,v=>setDesignPriority(d,v),{fewer_plugs:'Fewer plugs',simple_machining:'Simple machining',short_drills:'Short drills',compact:'Compact'});
    edit(routing,'Default drilling mode',d.project_defaults.drilling_mode,v=>d.project_defaults.drilling_mode=v,{orthogonal:'Orthogonal','allow-angled':'Allow angled',simplest:'Simplest'});
    if(d.rules.allowable_stress_mpa!=null){const advanced=element('details');advanced.append(element('summary','Advanced Project Settings'));content.append(advanced);
      edit(advanced,'Legacy material stress basis override / MPa (before safety factor)',d.rules.allowable_stress_mpa,v=>d.rules.allowable_stress_mpa=v,null,'optional');
      advanced.append(element('p','Retains the previous explicit basis and safety-factor calculation. Clear it to use applicable resolved material yield/proof strength.','property-note'));
    }
  };
}
