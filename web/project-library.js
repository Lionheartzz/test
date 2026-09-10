export function projectLibrary(ctx){
  const {$,element,action,api,post,openProject,isDirty,hasProject}=ctx;
  const home=element('section',null,'project-home');home.id='project-home';
  document.querySelector('.projectbar').before(home);
  let query='',archived=false;
  async function show(){
    document.body.classList.add('home');
    home.replaceChildren();
    const intro=element('div',null,'home-intro');intro.append(element('span','YOUR LOCAL ENGINEERING WORKSPACE','eyebrow'),element('h1','Manifold projects'),element('p','Start a new design or continue a saved project. Work stays on this computer.'));
    const controls=element('div',null,'action-row');intro.append(controls);
    action(controls,'New Manifold',()=>$('project-new').click());action(controls,'Import Project',()=>$('project-import').click());
    if(hasProject())action(controls,'Return to current draft',()=>document.body.classList.remove('home'));
    const filters=element('div',null,'action-row'),search=element('input');search.placeholder='Search saved projects';search.setAttribute('aria-label','Search saved projects');search.value=query;filters.append(search);
    action(filters,archived?'Show active projects':'Show archived projects',()=>{archived=!archived;show();});
    const cards=element('div',null,'project-cards');home.append(intro,filters,cards);
    try{
      const rows=await api('/api/projects');
      const render=()=>{cards.replaceChildren();const visible=rows.filter(r=>r.archived===archived&&r.name.toLowerCase().includes(query.toLowerCase()));
        if(!visible.length)cards.append(element('p',archived?'No archived projects.':'No saved projects yet. Create a manifold or import a project to begin.','empty-projects'));
        for(const r of visible){const card=element('article',null,'library-card');card.dataset.projectId=r.id;cards.append(card);card.append(element('h2',r.name),element('p',`${r.status} · ${r.context||''} · ${r.features??0} features`),element('p',r.updated_at?'Saved '+new Date(r.updated_at).toLocaleString():r.error));
          const buttons=element('div',null,'action-row');card.append(buttons);
          if(!r.error){action(buttons,'Open',async()=>{if(isDirty()&&!confirm('Discard the current unsaved draft and open this project?'))return;try{await openProject(r.id);}catch(e){alert(e.message);}});
            for(const [label,op]of [['Rename','rename'],['Duplicate','duplicate'],[r.archived?'Restore':'Archive',r.archived?'restore':'archive']])action(buttons,label,async()=>{let name;if(['rename','duplicate'].includes(op)){name=prompt('Project name',op==='duplicate'?r.name+' copy':r.name);if(!name?.trim())return;name=name.trim();}try{await post(`/api/projects/${r.id}/manage`,{expected_revision:r.revision,action:op,name:name||null});await show();}catch(e){alert(e.message);}});
          }
        }
      };search.oninput=()=>{query=search.value;render();};render();
    }catch(e){cards.append(element('p',e.message));}
  }
  $('projects-open').onclick=show;
  return {show};
}
