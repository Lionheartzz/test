export function profileEditor(ctx,parent,def){
  const {element,field}=ctx,ns='http://www.w3.org/2000/svg';
  const box=element('section',null,'library-card');box.append(element('h3','Axial section / top view · mm'));
  const svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox','0 0 760 300');svg.setAttribute('role','img');svg.setAttribute('aria-label','Live cavity axial profile and hydraulic window top view');svg.style.width='100%';box.append(svg);parent.append(box);
  function draw(){svg.replaceChildren();const cuts=def.cutting_primitives?.length?def.cutting_primitives:def.stages,depth=Math.max(1,...cuts.map(c=>c.end)),diam=Math.max(1,...cuts.map(c=>c.diameter)),scale=Math.min(220/depth,260/diam);
    const shape=(tag,attrs)=>{const e=document.createElementNS(ns,tag);for(const [k,v]of Object.entries(attrs))e.setAttribute(k,v);svg.append(e);return e;};
    shape('line',{x1:180,y1:15,x2:180,y2:280,stroke:'#8296a8','stroke-dasharray':'5 4'});
    for(const c of cuts){const r=c.diameter*scale/2,r2=(c.kind==='cone'?c.end_diameter:c.diameter)*scale/2,y=30+c.start*scale,y2=30+c.end*scale;shape('polygon',{points:`${180-r},${y} ${180+r},${y} ${180+r2},${y2} ${180-r2},${y2}`,fill:c.kind==='annulus'?'#806342':'#263c50',stroke:'#9cc8e8'});if(c.inner_diameter)shape('rect',{x:180-c.inner_diameter*scale/2,y,width:c.inner_diameter*scale,height:y2-y,fill:'#101c28'});}
    const extent=Math.max(diam,...cuts.map(c=>2*Math.hypot(c.offset_u||0,c.offset_v||0)+c.diameter),...(def.boundaries||[]).flatMap(b=>b.points.map(p=>2*Math.hypot(...p))));const topScale=230/extent;
    for(const c of cuts)shape('circle',{cx:540+(c.offset_u||0)*topScale,cy:150+(c.offset_v||0)*topScale,r:c.diameter*topScale/2,fill:'none',stroke:'#9cc8e8',opacity:.6});
    for(const b of def.boundaries||[])shape('polygon',{points:b.points.map(([x,y])=>`${540+x*topScale},${150+y*topScale}`).join(' '),fill:'none',stroke:'#f2d454'});
    for(const z of def.zones){shape('rect',{x:180-z.diameter*scale/2,y:30+z.start*scale,width:z.diameter*scale,height:(z.end-z.start)*scale,fill:'#41ca8b',opacity:.35});shape('circle',{cx:540+(z.offset_u||0)*topScale,cy:150+(z.offset_v||0)*topScale,r:z.diameter*topScale/2,fill:'none',stroke:'#41ca8b'});}
    shape('text',{x:15,y:290,fill:'#c6d6e5'}).textContent=`Depth ${depth.toFixed(3)} · max Ø${diam.toFixed(3)} · section schematic; exact CAD validates cuts`;
  }
  const table=element('div',null,'editor-grid');box.append(table);
  for(const [i,c]of (def.cutting_primitives?.length?def.cutting_primitives:def.stages).entries()){
    for(const k of ['start','end','diameter',...(c.kind==='cone'?['end_diameter']:[])])field(table,`Profile ${i+1} ${k} / mm`,c[k],v=>{c[k]=v;draw();},null,true);
    if(c.kind==='cone')field(table,`Profile ${i+1} included angle / degrees`,2*Math.atan(Math.abs(c.diameter-c.end_diameter)/(2*(c.end-c.start)))*180/Math.PI,v=>{if(v>0&&v<180)c.end=c.start+Math.abs(c.diameter-c.end_diameter)/(2*Math.tan(v*Math.PI/360));draw();},null,true);
  }
  parent.addEventListener('change',draw);draw();
}
