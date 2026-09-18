export function projectLibrary(ctx){
  const {$,element,action,api,post,openProject,isDirty,hasProject,onDeleted}=ctx;
  const home=element('section',null,'project-home');home.id='project-home';
  document.querySelector('.projectbar').before(home);
  let query='',archived=false;
  async function show(){
    document.body.classList.add('home');
    home.replaceChildren();
    const intro=element('div',null,'home-intro');intro.append(element('span','YOUR LOCAL ENGINEERING WORKSPACE','eyebrow'),element('h1','Manifold projects'),element('p','Start a new design or continue a saved project. Projects are saved on this computer. AI analysis sends selected documents and requirements to your configured provider.'));
    const controls=element('div',null,'action-row');intro.append(controls);
    action(controls,'New Manifold',()=>$('project-new').click());action(controls,'Import Project',()=>$('project-import').click());action(controls,'AI Design',()=>$('ai-design-open').click());
    if(hasProject())action(controls,'Return to current draft',()=>document.body.classList.remove('home'));
    const filters=element('div',null,'action-row'),search=element('input');search.placeholder='Search saved projects';search.setAttribute('aria-label','Search saved projects');search.value=query;filters.append(search);
    action(filters,archived?'Show active projects':'Show archived projects',()=>{archived=!archived;show();});
    const cards=element('div',null,'project-cards');home.append(intro,filters,cards);
    cards.append(element('p','Loading saved projects…','loading-state'));
    try{
      const rows=await api('/api/projects');
      const render=()=>{cards.replaceChildren();const visible=rows.filter(r=>r.archived===archived&&r.name.toLowerCase().includes(query.toLowerCase()));
        if(!visible.length)cards.append(element('p',archived?'No archived projects.':'No saved projects yet. Create a manifold or import a project to begin.','empty-projects'));
        for(const r of visible){const card=element('article',null,'library-card');card.dataset.projectId=r.id;cards.append(card);card.append(element('h2',r.name),element('p',`${r.status} · ${r.project_context||''} · ${r.features??0} features`),element('p',r.updated_at?'Saved '+new Date(r.updated_at).toLocaleString():r.error));
          const buttons=element('div',null,'action-row');card.append(buttons);
          if(!r.error){action(buttons,'Open',async()=>{if(isDirty()&&!confirm('Discard the current unsaved draft and open this project?'))return;try{await openProject(r.id);}catch(e){alert(e.message);}});
            action(buttons,'Drawings',()=>{if(isDirty()&&!confirm('Leave the unsaved manifold draft and open project drawings?'))return;location.href='/drawing.html?project='+r.id;});
            for(const [label,op]of [['Rename','rename'],['Duplicate','duplicate'],[r.archived?'Restore':'Archive',r.archived?'restore':'archive']])action(buttons,label,async()=>{let name;if(['rename','duplicate'].includes(op)){name=prompt('Project name',op==='duplicate'?r.name+' copy':r.name);if(!name?.trim())return;name=name.trim();}try{await post(`/api/projects/${r.id}/manage`,{expected_revision:r.revision,action:op,name:name||null});await show();}catch(e){alert(e.message);}});
            action(buttons,'Delete permanently',async()=>{const name=prompt(`Permanently delete “${r.name}” with its drawings and revision history? This cannot be undone. Shared PMC/MDTools records, assets and immutable build evidence are retained. Type the exact project name to confirm.`);if(name===null)return;if(name!==r.name){alert('Project name did not match. Nothing was deleted.');return;}try{await post(`/api/projects/${r.id}/delete`,{expected_revision:r.revision,confirm_name:name});onDeleted(r.id);await show();}catch(e){alert(e.message);}});
          }
        }
      };search.oninput=()=>{query=search.value;render();};render();
    }catch(e){cards.replaceChildren(element('p',e.message,'error'));}
  }
  $('projects-open').onclick=show;
  return {show};
}
