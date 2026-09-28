// The authoritative route check owns the CAD lane. Keep its request and the
// transient preview lifecycle in one flight, including failure and stale exits.
export function createRouteRefineFlight({snapshot,isCurrent,cancelPreview,submit,setEditing,apply,settle,reportError}){
  let pending=false;
  return {
    get pending(){return pending;},
    async run(input){
      if(pending)return false;
      let guard=snapshot(input.id);
      pending=true;
      try{
        setEditing(false);
        await cancelPreview();
        if(!isCurrent(guard))return false;
        const result=await submit(input);
        if(!isCurrent(guard))return false;
        apply(result,input);
        guard=snapshot(input.id);
        return true;
      }catch(error){
        if(isCurrent(guard))reportError(error);
        return false;
      }finally{
        pending=false;
        setEditing(true);
        settle();
      }
    }
  };
}
