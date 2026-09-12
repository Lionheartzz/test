export const axes = {top:[0,1,2,-1],bottom:[0,1,2,1],front:[0,2,1,1],back:[0,2,1,-1],left:[1,2,0,1],right:[1,2,0,-1]};
export const sizes = b => [b.length,b.width,b.height];
export function featureLabel(f,design){
  if(f.kind!=='port')return design.components?.find(c=>c.feature_id===f.id)?.label||f.id;
  if(f.schematic_id)return f.schematic_id;
  const ports=design.features.filter(p=>p.kind==='port'&&p.circuit===f.circuit);
  return ports.length===1?f.circuit:f.circuit+(ports.findIndex(p=>p.id===f.id)+1);
}
export function pose(f,b) { const [u,v,a,s]=axes[f.face], p=[0,0,0],d=[0,0,0]; p[u]=f.u;p[v]=f.v;p[a]=s>0?0:sizes(b)[a]; d[a]=s;return {origin:p,direction:f.direction||d}; }
export function bounds(f,design) {
  const d=design.library.find(d=>d.id===f.definition);
  const r=(d?Math.max(d.clearance_diameter,...d.stages.map(s=>s.diameter)):Math.max(f.diameter,f.kind==='port'||f.plugged?f.clearance_diameter:0))/2;
  const [u,v]=axes[f.face], b=sizes(design.block),a=(f.rotation||0)*Math.PI/180,points=[[-r,-r],[r,r],...(d?.boundaries||[]).flatMap(b=>b.circle?(()=>{const [x,y,r]=b.circle,cx=x*Math.cos(a)-y*Math.sin(a),cy=x*Math.sin(a)+y*Math.cos(a);return [[cx-r,cy-r],[cx+r,cy+r]];})():b.points.map(([x,y])=>[x*Math.cos(a)-y*Math.sin(a),x*Math.sin(a)+y*Math.cos(a)]))];const minU=-Math.min(...points.map(p=>p[0])),maxU=b[u]-Math.max(...points.map(p=>p[0])),minV=-Math.min(...points.map(p=>p[1])),maxV=b[v]-Math.max(...points.map(p=>p[1]));return {minU,maxU,minV,maxV,fits:minU<=maxU&&minV<=maxV};
}
export function clamp(f,design,u,v,snap=1) { const b=bounds(f,design);if(!b.fits)throw Error('Component envelope does not fit on this face');const round=n=>snap?Math.round(n/snap)*snap:n;return [Math.max(b.minU,Math.min(b.maxU,round(u))),Math.max(b.minV,Math.min(b.maxV,round(v)))]; }
export function syncNets(d) {
  const members=Object.create(null);for(const f of d.features) {if(f.kind==='cavity')for(const [z,n]of Object.entries(f.circuits))(members[n]??=[]).push(`${f.id}:${z}`);else if(f.kind==='port')(members[f.circuit]??=[]).push(f.id);}
  d.nets??=[];for(const n of d.nets)n.members=members[n.id]||[];for(const [id,m]of Object.entries(members))if(!d.nets.some(n=>n.id===id))d.nets.push({id,label:id,members:m,routing:'manual',diameter:8});
}

export function smartAlign(f,design,u,v,tolerance=2,referenceFeatures=design.features){
  const [au,av]=axes[f.face],dims=sizes(design.block),refs=[{p:[0,0,0],label:'Origin'},{p:dims.map(x=>x/2),label:'Block center'}];
  for(const other of design.features){if(other.id===f.id||other.suppressed)continue;const p=pose(other,design.block);refs.push({p:p.origin,label:other.id+' axis'});if(other.kind==='cavity'){const d=design.library.find(d=>d.id===other.definition),[a,b]=axes[other.face],r=(other.rotation||0)*Math.PI/180;for(const z of d.zones){const point=p.origin.map((x,i)=>x+p.direction[i]*(z.start+z.end)/2);point[a]+=(z.offset_u||0)*Math.cos(r)-(z.offset_v||0)*Math.sin(r);point[b]+=(z.offset_u||0)*Math.sin(r)+(z.offset_v||0)*Math.cos(r);refs.push({p:point,label:other.id+':'+z.id});}}}
  for(const other of referenceFeatures){if(other.id===f.id||other.suppressed||!['drilling','port'].includes(other.kind))continue;const p=pose(other,design.block),end=p.origin.map((x,i)=>x+p.direction[i]*other.depth);refs.push({p:p.origin,axes:p.direction.map((x,i)=>Math.abs(x)<1e-8?i:-1),label:other.id+' centerline'});refs.push({p:end,label:other.id+(other.definition?' hydraulic window end':' cylinder end')});}
  const guides=[];const values=[u,v].map((value,i)=>{const axis=[au,av][i],sorted=refs.filter(r=>!r.axes||r.axes.includes(axis)).map(r=>({...r,gap:Math.abs(r.p[axis]-value)})).sort((a,b)=>a.gap-b.gap);if(sorted[0]?.gap<=tolerance){guides.push({axis,value:sorted[0].p[axis],label:sorted[0].label});return sorted[0].p[axis];}return Math.round(value);});return {values:clamp(f,design,...values,0),guides};
}
