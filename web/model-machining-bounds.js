import {axes,sizes,pose,bounds} from './kinematics.js';
import {objectName} from './api-errors.js';

const epsilon=1e-6;
export function machiningFits(row,block){
  const dims=sizes(block),[u,v,a]=axes[row.face];
  if(row.kind==='chamfer')return row.size>0&&row.size<Math.min(...dims)/2;
  if(row.kind!=='rectangular-cutout')return row.u>=0&&row.v>=0&&row.u<=dims[u]&&row.v<=dims[v]&&row.depth<=dims[a];
  const angle=(row.rotation||0)*Math.PI/180;
  const eu=(Math.abs(row.width*Math.cos(angle))+Math.abs(row.height*Math.sin(angle)))/2;
  const ev=(Math.abs(row.width*Math.sin(angle))+Math.abs(row.height*Math.cos(angle)))/2;
  return row.u+epsilon>=eu&&row.u+eu<=dims[u]+epsilon&&row.v+epsilon>=ev&&row.v+ev<=dims[v]+epsilon&&row.depth<=dims[a]+epsilon;
}

function resolvedFeatures(design){
  const features=structuredClone(design.features),byId=new Map(features.map(row=>[row.id,row])),done=new Set();
  function resolve(row,visiting=new Set()){
    if(done.has(row.id)||visiting.has(row.id))return;
    visiting.add(row.id);
    const parent=byId.get(row.parent_id);
    if(parent){resolve(parent,visiting);const angle=(parent.rotation||0)*Math.PI/180,[u,v]=row.local_offset||[0,0];row.face=parent.face;row.u=parent.u+u*Math.cos(angle)-v*Math.sin(angle);row.v=parent.v+u*Math.sin(angle)+v*Math.cos(angle);row.suppressed||=parent.suppressed;}
    done.add(row.id);
  }
  for(const row of features)resolve(row);
  return features;
}

function featureFits(row,design){
  const dims=sizes(design.block),definition=design.library?.find(value=>value.id===(row.cavity_id||row.port_definition_id));
  const thread=design.threads?.find(value=>value.id===row.thread_definition_id);
  if((row.cavity_id||row.port_definition_id)&&!definition||row.thread_definition_id&&!thread)throw Error(`${objectName(row,design)}: machining definition is not loaded. Reopen the project before changing the block size.`);
  const diameter=Number(thread?.tap_diameter_mm??row.diameter??0),feature={...row,diameter,clearance_diameter:row.clearance_diameter??0};
  const entry=bounds(feature,design);
  if(!entry.fits||row.u<entry.minU-epsilon||row.u>entry.maxU+epsilon||row.v<entry.minV-epsilon||row.v>entry.maxV+epsilon)return false;
  const [u,v,axis,sign]=axes[row.face],{origin,direction}=pose(row,design.block);
  if(row.kind==='mounting'&&row.through&&Math.abs(row.depth-dims[axis])>epsilon)return false;
  const cuts=definition?(definition.cutting_primitives?.length?definition.cutting_primitives:definition.stages):[{start:0,end:row.depth,diameter}];
  const angle=(row.rotation||0)*Math.PI/180;
  // Analytic cylinder/cone extents; no CAD work or hydraulic inference.
  for(const cut of cuts||[]){
    const p=[...origin],du=cut.offset_u||0,dv=cut.offset_v||0;
    p[u]+=du*Math.cos(angle)-dv*Math.sin(angle);p[v]+=du*Math.sin(angle)+dv*Math.cos(angle);
    for(const [depth,radius]of [[cut.start,cut.diameter/2],[cut.end,(cut.kind==='cone'?cut.end_diameter:cut.diameter)/2]]){
      for(let i=0;i<3;i++){
        const center=p[i]+direction[i]*depth,extent=radius*Math.sqrt(Math.max(0,1-direction[i]**2));
        // Angled bores are trimmed at the declared entry half-space in CAD.
        const low=i===axis&&sign>0?Math.max(0,center-extent):center-extent;
        const high=i===axis&&sign<0?Math.min(dims[i],center+extent):center+extent;
        if(low<-epsilon||high>dims[i]+epsilon)return false;
      }
    }
  }
  if(!definition&&!(row.kind==='mounting'&&row.through)&&row.tip_angle!==180){
    const tip=diameter/2/Math.tan((row.tip_angle??118)*Math.PI/360);
    if(origin.some((value,i)=>value+direction[i]*(row.depth+tip)<-epsilon||value+direction[i]*(row.depth+tip)>dims[i]+epsilon))return false;
  }
  return true;
}

export function assertBlockResize(design,key,value){
  const label={length:'Length X',width:'Width Y',height:'Height Z'}[key];
  if(!Number.isFinite(value)||value<=0||value>2000)throw Error(`${label} must be greater than zero and no more than 2000 mm.`);
  const next={...design,library:design.library||[],threads:design.threads||[],block:{...design.block,[key]:value}},invalid=[];
  for(const row of resolvedFeatures(next)){
    if(row.suppressed)continue;
    if(row.kind==='mounting'&&row.through&&Math.abs(row.depth-sizes(next.block)[axes[row.face][2]])>epsilon)invalid.push({row,reason:'through depth would no longer match the block thickness'});
    else if(!featureFits(row,next))invalid.push({row,reason:`would lie outside the ${row.face.replace(/^./,c=>c.toUpperCase())} face or block thickness`});
  }
  for(const row of [...(next.engravings||[]),...(next.block_modifiers||[])])if(!machiningFits(row,next.block))invalid.push({row,reason:`would lie outside the ${row.face.replace(/^./,c=>c.toUpperCase())} face or block thickness`});
  if(!invalid.length)return;
  const names=invalid.slice(0,3).map(({row})=>objectName(row,design));
  const reason=invalid.length===1?`${names[0]} ${invalid[0].reason}.`:`${invalid.length} existing objects would no longer fit the finished block: ${names.join(', ')}${invalid.length>3?'…':''}.`;
  throw Error(`Cannot change ${label} to ${value} mm. ${reason}`);
}
