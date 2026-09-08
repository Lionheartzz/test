export const axes = {top:[0,1,2,-1],bottom:[0,1,2,1],front:[0,2,1,1],back:[0,2,1,-1],left:[1,2,0,1],right:[1,2,0,-1]};
export const sizes = b => [b.length,b.width,b.height];
export function pose(f,b) { const [u,v,a,s]=axes[f.face], p=[0,0,0],d=[0,0,0]; p[u]=f.u;p[v]=f.v;p[a]=s>0?0:sizes(b)[a]; d[a]=s;return {origin:p,direction:d}; }
export function bounds(f,design) {
  const d=design.library.find(d=>d.id===f.definition);
  const r=(d?Math.max(d.clearance_diameter,...d.stages.map(s=>s.diameter)):Math.max(f.diameter,f.kind==='port'||f.plugged?f.clearance_diameter:0))/2;
  const [u,v]=axes[f.face], b=sizes(design.block);return {minU:r,maxU:b[u]-r,minV:r,maxV:b[v]-r,fits:r*2<=b[u]&&r*2<=b[v]};
}
export function clamp(f,design,u,v,snap=1) { const b=bounds(f,design);if(!b.fits)throw Error('Component envelope does not fit on this face');const round=n=>snap?Math.round(n/snap)*snap:n;return [Math.max(b.minU,Math.min(b.maxU,round(u))),Math.max(b.minV,Math.min(b.maxV,round(v)))]; }
export function syncNets(d) {
  const members={};for(const f of d.features) {if(f.kind==='cavity')for(const [z,n]of Object.entries(f.circuits))(members[n]??=[]).push(`${f.id}:${z}`);else if(f.kind==='port')(members[f.circuit]??=[]).push(f.id);}
  d.nets=(d.nets||[]).map(n=>({...n,members:members[n.id]||[]}));for(const [id,m]of Object.entries(members))if(!d.nets.some(n=>n.id===id))d.nets.push({id,label:id,members:m,routing:'manual',diameter:8});
}
