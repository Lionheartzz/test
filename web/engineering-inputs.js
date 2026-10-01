export function setDesignPriority(design,priority){
  if(design.constraints.priority===priority)return;
  design.constraints.priority=priority;
  for(const net of design.nets)if(net.routing==='automatic')net.routing_variant=null;
}

export function clearStock(block){
  block.stock_id=null;block.stock_dimensions=null;block.machining_allowance=null;block.stock_excess=null;
}

export function selectEngineeringMaterial(design,material){
  if(design.block.material_id===(material?.id||null))return;
  clearStock(design.block);
  design.block.material_id=material?.id||null;
  if(material)design.block.material=material.display_name;
  // Only a resolved directly sourced allowable can initialize this field.
  // Yield/tensile reference values never become allowable stress.
  const stress=material?.engineering_facts_summary?.facts?.allowable_stress_mpa;
  design.rules.allowable_stress_mpa=stress?.status==='SOURCE_BACKED'?stress.value:null;
  design.rules.pressure_safety_factor=2;
  design.rules.minimum_wall=7;
  design.constraints.preferred_wall_margin=4;
}

export function validStockSizes(design,material){
  return (material?.stock||[]).filter(row=>row.active&&row.material_id===material.id&&
    [row.size_1_mm,row.size_2_mm].every(value=>Number.isFinite(value)&&value>0&&value<=2000)&&
    [row.allowance_1_mm,row.allowance_2_mm].every(value=>Number.isFinite(value)&&value>=0&&value<=200)&&
    ((row.size_1_mm>=design.block.width+2*row.allowance_1_mm&&row.size_2_mm>=design.block.height+2*row.allowance_2_mm)||
     (row.size_2_mm>=design.block.width+2*row.allowance_2_mm&&row.size_1_mm>=design.block.height+2*row.allowance_1_mm)))
    .sort((a,b)=>(a.unit_system===design.project_context?-1:1)-(b.unit_system===design.project_context?-1:1)||a.size_1_mm-b.size_1_mm||a.size_2_mm-b.size_2_mm||a.id.localeCompare(b.id));
}

export function selectRawStock(design,stock){
  if(!stock){clearStock(design.block);return;}
  if(stock.material_id!==design.block.material_id)throw Error('Raw stock must belong to the selected engineering material.');
  const direct=stock.size_1_mm>=design.block.width+2*stock.allowance_1_mm&&stock.size_2_mm>=design.block.height+2*stock.allowance_2_mm;
  const y=direct?stock.size_1_mm:stock.size_2_mm,z=direct?stock.size_2_mm:stock.size_1_mm;
  const ay=direct?stock.allowance_1_mm:stock.allowance_2_mm,az=direct?stock.allowance_2_mm:stock.allowance_1_mm;
  if(y<design.block.width+2*ay||z<design.block.height+2*az)throw Error('Raw stock does not fit the finished block and source allowance.');
  Object.assign(design.block,{stock_id:stock.id,stock_dimensions:[design.block.length,y,z],
    machining_allowance:[0,ay,az],stock_excess:[0,(y-design.block.width)/2,(z-design.block.height)/2]});
}

export function setEnvelopeMaximum(design,axis,value){
  if(value!==null&&(!Number.isFinite(value)||value<=0||value>2000))throw Error('Maximum envelope dimensions must be between 0 and 2000 mm.');
  // 2000 mm is already the schema's maximum block size, so it adds no limit
  // on an omitted axis while preserving the existing three-number tuple.
  const maximum=[...(design.constraints.envelope_max||[2000,2000,2000])];
  maximum[axis]=value??2000;
  design.constraints.envelope_max=maximum.every(v=>v===2000)?null:maximum;
}

export const customPortDescription=(diameter,depth)=>`Custom Ø${Number(diameter)} × ${Number(depth)} mm`;
