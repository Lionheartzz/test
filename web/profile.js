export function profileEditor(ctx,parent,def){
  const {element,field,action}=ctx,ns='http://www.w3.org/2000/svg';
  const box=element('section',null,'library-card');box.append(element('h3','Cavity definition · geometry and interfaces'));
  box.append(element('p',`${def.native?def.native.geometry_status+' · '+def.native.datum_mode:'PMC engineering definition'} · mm. Select a cut, interface or boundary to inspect it. Native dimensions are retained separately; this view shows the active CAD interpretation.`));
  const scroll=element('div',null,'profile-scroll'),svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox','0 0 1000 430');svg.setAttribute('role','img');svg.setAttribute('aria-label','Dimensioned cavity section and top view');svg.classList.add('profile-drawing');svg.style.width='100%';scroll.append(svg);box.append(scroll);parent.append(box);
  const selection=element('p',null,'property-note'),legend=element('div',null,'profile-legend');box.append(selection,legend);
  let active={kind:'cut',index:0};
  const fmt=n=>Number.isFinite(n)?Number(n.toFixed(3)).toString():'?';
  const cuts=()=>def.cutting_primitives?.length?def.cutting_primitives:def.stages;
  const ref=c=>c.source_ref||'PMC authored geometry';
  const angle=c=>2*Math.atan(Math.abs(c.diameter-c.end_diameter)/(2*(c.end-c.start)))*180/Math.PI;
  function draw(){
    svg.replaceChildren();const all=cuts(),chosen=active.kind==='cut'?all[active.index]:active.kind==='interface'?def.zones[active.index]:null;
    const offset=[chosen?.offset_u||0,chosen?.offset_v||0],section=all.filter(c=>(c.offset_u||0)===offset[0]&&(c.offset_v||0)===offset[1]);
    const depth=Math.max(1,...all.map(c=>c.end)),diam=Math.max(1,...all.map(c=>c.diameter)),scale=Math.min(280/depth,290/diam);
    const shape=(tag,attrs,text)=>{const e=document.createElementNS(ns,tag);for(const [k,v]of Object.entries(attrs))e.setAttribute(k,v);if(text!==undefined)e.textContent=text;svg.append(e);return e;};
    const text=(x,y,value,color='#c6d6e5',size=13)=>shape('text',{x,y,fill:color,'font-size':size,'font-family':'system-ui'},value);
    const line=(x1,y1,x2,y2,color='#8296a8',dash='')=>shape('line',{x1,y1,x2,y2,stroke:color,'stroke-dasharray':dash});
    text(24,24,`AXIAL SECTION · local U ${fmt(offset[0])}, V ${fmt(offset[1])}`, '#e4f0f7',15);
    text(600,24,'TOP VIEW · looking into entry face','#e4f0f7',15);
    const cx=218,base=70;line(cx,46,cx,base+depth*scale+25,'#8296a8','5 4');line(34,base,450,base,'#fff');text(35,60,'ENTRY DATUM · depth 0');
    const foreground=[],clip=shape('clipPath',{id:'profile-cut-mask'});
    for(const c of section){const i=all.indexOf(c),on=active.kind==='cut'&&active.index===i,r=c.diameter*scale/2,r2=(c.kind==='cone'?c.end_diameter:c.diameter)*scale/2,y=base+c.start*scale,y2=base+c.end*scale;
      const ir=(c.inner_diameter||0)*scale/2,outline=c.inner_diameter?{d:`M${cx-r},${y}H${cx+r}V${y2}H${cx-r}Z M${cx-ir},${y}H${cx+ir}V${y2}H${cx-ir}Z`,'fill-rule':'evenodd'}:{points:`${cx-r},${y} ${cx+r},${y} ${cx+r2},${y2} ${cx-r2},${y2}`};const polygon=shape(c.inner_diameter?'path':'polygon',{...outline,fill:c.kind==='annulus'?'#5c4334':'#263c50',stroke:'#7092ad','stroke-width':1});polygon.dataset.cut=String(i+1);const mask=polygon.cloneNode();mask.setAttribute('fill','#fff');mask.setAttribute('stroke','none');if(c.inner_diameter){const ir=c.inner_diameter*scale/2,path=document.createElementNS(ns,'path');path.setAttribute('d',`M${cx-r},${y}H${cx+r}V${y2}H${cx-r}Z M${cx-ir},${y}H${cx+ir}V${y2}H${cx-ir}Z`);path.setAttribute('clip-rule','evenodd');clip.append(path);}else clip.append(mask);

      if(on){const annotationStart=svg.childElementCount;shape(c.inner_diameter?'path':'polygon',{...outline,fill:'#70b4d733',stroke:'#d6f2ff','stroke-width':3});
        line(cx-r,y-12,cx+r,y-12,'#d6f2ff');line(cx-r,y-17,cx-r,y-7,'#d6f2ff');line(cx+r,y-17,cx+r,y-7,'#d6f2ff');text(cx+10,Math.max(42,y-18),`C${i+1} · Ø${fmt(c.diameter)}`,'#fff');
        line(cx+r,y,485,y,'#d6f2ff');line(cx+r2,y2,485,y2,'#d6f2ff');line(475,y,475,y2,'#d6f2ff');text(486,y+4,fmt(c.start));text(486,Math.max(y+20,y2+4),fmt(c.end));
        if(c.kind==='cone')text(28,392,`C${i+1} CONE · Ø${fmt(c.diameter)} → Ø${fmt(c.end_diameter)} · included ${fmt(angle(c))}°`,'#d6f2ff');
        if(c.kind==='annulus')text(28,392,`C${i+1} ANNULAR CUT · outer Ø${fmt(c.diameter)} / inner Ø${fmt(c.inner_diameter)}`,'#e3b580');
        foreground.push(...Array.from(svg.children).slice(annotationStart));
      }
    }
    let iy=0;for(const [i,z]of def.zones.entries()){if((z.offset_u||0)!==offset[0]||(z.offset_v||0)!==offset[1])continue;const y=base+z.start*scale,h=(z.end-z.start)*scale,on=active.kind==='interface'&&active.index===i;
      const band=shape('rect',{x:cx-z.diameter*scale/2,y,width:z.diameter*scale,height:h,fill:'#41ca8b',opacity:on?.5:.16,stroke:'#41ca8b','stroke-width':on?3:1});if(z.clip_to_cut)band.setAttribute('clip-path','url(#profile-cut-mask)');const ly=90+iy++*25;line(42,ly,cx-z.diameter*scale/2,y+h/2,'#70dca4');text(26,ly-5,`I${i+1} ${z.id}`,'#83e4b6',11);
    }
    foreground.forEach(e=>svg.append(e));
    const maxR=Math.max(1,...all.map(c=>Math.hypot(c.offset_u||0,c.offset_v||0)+c.diameter/2),...(def.boundaries||[]).flatMap(b=>b.circle?[Math.hypot(b.circle[0],b.circle[1])+b.circle[2]]:b.points.map(p=>Math.hypot(...p))));
    const topScale=155/maxR,tx=786,ty=225;line(tx-170,ty,tx+170,ty,'#526578','4 4');line(tx,ty-170,tx,ty+170,'#526578','4 4');text(tx+150,ty-8,'+U');text(tx+7,ty-160,'+V');
    for(const [i,c]of all.entries()){const on=active.kind==='cut'&&active.index===i;shape('circle',{cx:tx+(c.offset_u||0)*topScale,cy:ty-(c.offset_v||0)*topScale,r:c.diameter*topScale/2,fill:'none',stroke:on?'#e3f6ff':'#66869e','stroke-width':on?3:1});if(c.inner_diameter)shape('circle',{cx:tx+(c.offset_u||0)*topScale,cy:ty-(c.offset_v||0)*topScale,r:c.inner_diameter*topScale/2,fill:'none',stroke:'#d4a874'});}
    for(const [i,b]of (def.boundaries||[]).entries()){const attrs={fill:'none',stroke:active.kind==='boundary'&&active.index===i?'#fff29a':'#b79b50','stroke-width':active.kind==='boundary'&&active.index===i?3:1.5};
      if(b.circle){const [x,y,r]=b.circle;shape('circle',{...attrs,cx:tx+x*topScale,cy:ty-y*topScale,r:r*topScale});if((def.boundaries||[]).length===1||active.kind==='boundary'&&active.index===i){text(610,382,`B${i+1} ${b.category.toUpperCase()} · ${b.height?'height '+fmt(b.height)+' mm':'planar region'}`,'#e6ce7c',12);text(610,402,`Exact circle Ø${fmt(2*r)} · center ${fmt(x)}, ${fmt(y)}`,'#e6ce7c',12);}}
      else shape('polygon',{...attrs,points:b.points.map(([x,y])=>`${tx+x*topScale},${ty-y*topScale}`).join(' ')});
    }
    for(const [i,z]of def.zones.entries())if(active.kind==='interface'&&active.index===i){shape('circle',{cx:tx+(z.offset_u||0)*topScale,cy:ty-(z.offset_v||0)*topScale,r:z.diameter*topScale/2,fill:'none',stroke:'#83e4b6','stroke-width':3});}
    text(24,418,`Depth + inward · extent ${fmt(depth)} mm · section through selected axis; other offset cuts appear in top view`, '#a4bbcc',12);
    const c=all[active.index],z=def.zones[active.index],b=def.boundaries?.[active.index];
    selection.textContent=active.kind==='cut'?`C${active.index+1} · ${c.kind||'cylinder'} · Ø${fmt(c.diameter)}${c.kind==='cone'?' → Ø'+fmt(c.end_diameter):''} · datum depths ${fmt(c.start)}–${fmt(c.end)} mm · local offset U ${fmt(c.offset_u||0)}, V ${fmt(c.offset_v||0)} · source: ${ref(c)}`:active.kind==='interface'?`I${active.index+1} · hydraulic interface ${z.id} · Ø${fmt(z.diameter)} · depth ${fmt(z.start)}–${fmt(z.end)} · offset ${fmt(z.offset_u||0)}, ${fmt(z.offset_v||0)} · ${z.clip_to_cut?'clipped to actual cutting volume':'declared cylindrical window'} · circuit assigned on placed component`:`B${active.index+1} · ${b.category} · height ${fmt(b.height)} mm${b.height===0?' (planar only)':''} · ${b.association} · source role: ${b.source_role||'unspecified'} · ${b.source}`;
    for(const button of legend.querySelectorAll('button'))button.classList.toggle('active',button.dataset.selection===active.kind+active.index);
  }
  for(const [kind,rows]of [['cut',cuts()],['interface',def.zones],['boundary',def.boundaries||[]]]){
    const details=element('details');details.open=kind!=='cut';details.append(element('summary',`${kind==='cut'?'Machining profile':kind==='interface'?'Hydraulic interfaces':'Footprint and clearance boundaries'} · ${rows.length}`));legend.append(details);
    rows.forEach((r,i)=>{const title=kind==='cut'?`C${i+1} · ${r.kind||'cylinder'} · Ø${fmt(r.diameter)} · ${fmt(r.start)}–${fmt(r.end)} mm · ${ref(r)}`:kind==='interface'?`I${i+1} · ${r.id} · depth ${fmt(r.start)}–${fmt(r.end)} mm`:`B${i+1} · ${r.category} · ${r.circle?'exact circle':'polygon'} · ${r.source_role||r.association}`;action(details,title,()=>{active={kind,index:i};draw();});details.lastElementChild.dataset.selection=kind+i;});
  }
  const source=element('details');source.append(element('summary','Threads, seals and source interpretation'));box.append(source);
  source.append(element('p',def.thread_note||'No thread specification supplied.'));
  if(def.native){const r=def.native.mapping_record||def.native.record;source.append(element('p',`Source datum: ${def.native.datum_mode}. ${def.native.mapping_record?'An explicit PMC interpretation is active; original source retained.':'Mapped from the pinned source record.'}`));
    for(const t of r.threads||[])source.append(element('p','Thread record: '+JSON.stringify(t)));
    for(const [k,v]of Object.entries(r.engineering||{}))if(/seal|insert|thread|groove|ring|undercut/i.test(k))source.append(element('p',k+': '+JSON.stringify(v)));
    for(const rel of def.native.related_records||[])if(/groove|ring|undercut/i.test(rel.kind||''))source.append(element('p',`${rel.kind} · ${rel.name||rel.id} · retained source record; only explicit CAD cuts are drawn.`));
  }
  source.append(element('p','Thread flanks and unspecified seal envelopes are not drawn. Source metadata without a mapped axial extent stays textual; a thread note alone does not define a cutting operation.'));
  const edits=element('details');edits.append(element('summary','Edit numerical profile · live preview'));box.append(edits);
  for(const [i,c]of cuts().entries()){
    const row=element('section',null,'port-row');row.append(element('h4',`C${i+1} · ${c.kind||'cylinder'} · ${ref(c)}`));edits.append(row);
    for(const k of ['start','end','diameter',...(c.kind==='cone'?['end_diameter']:[]),...(c.kind==='annulus'?['inner_diameter']:[]),...(def.cutting_primitives?.length?['offset_u','offset_v']:[])]){
      const input=field(row,`C${i+1} ${k} / mm`,c[k]||0,v=>{c[k]=v;active={kind:'cut',index:i};draw();},null,true);input.oninput=()=>{if(input.value!==''&&Number.isFinite(Number(input.value))){c[k]=Number(input.value);active={kind:'cut',index:i};draw();}};
    }
    if(c.kind==='cone')field(row,`C${i+1} included angle / degrees`,angle(c),v=>{if(v>0&&v<180)c.end=c.start+Math.abs(c.diameter-c.end_diameter)/(2*Math.tan(v*Math.PI/360));active={kind:'cut',index:i};draw();},null,true);
  }
  parent.addEventListener('change',draw);draw();
}
