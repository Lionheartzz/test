// Owned by the viewer: parameter frames update editable features while retaining
// automatic references until a fresh resolved frame (or project reset) replaces them.
export function createReferenceState(){
  let features=[];
  return {
    reset(value=[]){features=value.map(f=>({...f}));},
    load(kind,value){
      const old=features;
      features=value.map(f=>({...f}));
      if(kind==='parameter-preview')features.push(...old.filter(f=>f.route_net&&!features.some(x=>x.id===f.id)));
      return features;
    },
    get features(){return features;}
  };
}
