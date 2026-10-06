import {libraryBrowser} from './library-browser.js';
import {engineeringText} from './engineering-labels.js';

export const libraryCategories=[
  ['cavities','Cavities','Cavity machining definitions, interfaces and engineering data.',true,true],
  ['cartridges','Cartridges','Valve identities, technical properties and compatible cavities.',true,false],
  ['external-ports','External Ports','Hydraulic port definitions, threads, sealing and machining data.',true,true],
  ['threads','Threads','Thread designations, standards and machining reference data.',true,true],
  ['materials','Materials & Stock','Engineering materials, properties and available stock sizes.',true,false],
  ['tooling','Tooling','Drills, flat-bottom drills, spotface cutters and tooling data.',true,true],
  ['closures','Closures & Plugs','Closure and plug products, interfaces and engineering data.',true,true],
  ['modifiers','Machining Modifiers','O-ring grooves, counterbores, undercuts and machining data.',true,true],
  ['seals','Seals & O-rings','Seal sizes, materials, fluids and backup-ring information.',false,true],
  ['fittings','Fittings & Adapters','Fitting products, connections and engineering dimensions.',false,true],
  ['fasteners','Fasteners & Mounting','Bolts, mounting hardware, sizes and assembly information.',false,true],
  ['fluids','Hydraulic Fluids','Fluid types, properties and compatibility information.',false,true],
  ['surface-treatments','Surface Treatments','Coatings, material applicability and finish specifications.',false,true],
  ['standards','Standards','Standard designations, editions and engineering applicability.',false,true],
  ['cross-references','Cross References','Explicit product and designation relationships.',false,true],
  ['inspection','Inspection & QA','Inspection methods, test requirements and acceptance criteria.',false,true],
  ['manufacturing','Manufacturing & DFM','Manufacturing guidance and process requirements.',false,true],
  ['documentation','Production Documentation','Drawing callouts and manufacturing document requirements.',false,true],
  ['commercial','Commercial & Cost','Dated supplier prices, quantities and lead-time information.',false,true],
  ['suppliers','Manufacturers & Suppliers','Product families, availability and supplier information.',false,true],
];

export function engineeringGroups(ctx,parent,data){
  const {element}=ctx;
  for(const group of data.groups||[]){
    const section=element('section',null,'library-engineering-data');section.append(element('h3',group.title));
    for(const row of group.fields||[])section.append(element('p',row.label+': '+row.value));
    if(!group.fields?.length)section.append(element('p','Additional engineering values not available.'));
    parent.append(section);
  }
}

// Search/page/scroll persist independently from the executable Definitions tab.
export function libraryKnowledgeUI(ctx,{show,back,onInvalidate,isCurrent,scrollContainer,labels,descriptions}){
  const {element,field,action,api}=ctx,content=ctx.$('workflow-content'),states={};
  const state=category=>states[category]??={q:'',status:'',offset:0,limit:40,scroll:0};
  async function detail(category,key,options){
    const saved=state(category);saved.scroll=scrollContainer()?.scrollTop||0;
    const token=onInvalidate();show('Engineering Library / '+labels[category]);
    action(content,'Back to '+labels[category],()=>back(category,{...options,libraryMode:'knowledge'}));
    const box=element('section',null,'library-card');content.append(box);box.append(element('p','Loading engineering data…'));
    try{
      const row=await api('/api/engineering-library/knowledge/'+encodeURIComponent(key));if(!isCurrent(token))return;
      box.replaceChildren(element('h3',row.name));
      if(row.family)box.append(element('p',row.family));box.append(element('p',row.status,'property-note'));
      engineeringGroups(ctx,box,row);
    }catch{if(isCurrent(token))box.replaceChildren(element('p','Engineering data could not be loaded.'));}
  }
  async function browse(category,options){
    const saved=state(category),token=onInvalidate();show('Engineering Library / '+labels[category]);
    const shell=libraryBrowser(ctx,content,{description:descriptions[category],back:()=>back('home'),readOnly:true});
    let request=0,timer;
    const load=async()=>{
      const ticket=++request;
      try{
        const page=await api('/api/engineering-library/knowledge?'+new URLSearchParams({category,q:saved.q,status:saved.status,offset:saved.offset,limit:saved.limit}));
        if(!isCurrent(token)||ticket!==request)return;
        shell.count.textContent=page.total.toLocaleString()+' records';
        const hasFamily=page.items.some(row=>row.family),hasData=page.items.some(row=>row.key_data);
        const columns=['Name',...(hasFamily?['Type / Family']:[]),...(hasData?['Key engineering data']:[]),'Status'];
        shell.rows(columns,page.items,(row,buttons)=>{
          action(buttons,'View',()=>detail(category,row.key,options));return [row.name,...(hasFamily?[row.family]:[]),...(hasData?[row.key_data]:[]),row.status];
        });
        shell.paging(saved.offset,page.total,saved.limit,offset=>{saved.offset=offset;saved.scroll=0;return load();});
        const node=scrollContainer();if(node)node.scrollTop=saved.scroll;
      }catch{if(isCurrent(token)&&ticket===request)shell.failure('Engineering data could not be loaded.',load);}
    };
    const update=(key,value)=>{saved[key]=value;saved.offset=0;saved.scroll=0;clearTimeout(timer);timer=setTimeout(load,160);};
    const search=field(shell.filters,'Search',saved.q,value=>update('q',value));search.oninput=()=>update('q',search.value);
    field(shell.filters,'Status',saved.status,value=>update('status',value),{'':'All records',VERIFIED:'Verified',PARTIAL:'Partial data'});
    await load();
  }
  return {browse,remember:category=>{state(category).scroll=scrollContainer()?.scrollTop||0;}};
}
