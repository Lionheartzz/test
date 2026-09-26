export function createDrawingShell(){
  const $=id=>document.getElementById(id),header=document.querySelector('.drawing-header'),toolbar=document.querySelector('.drawing-toolbar');
  const backdrop=document.createElement('div');backdrop.className='drawing-backdrop';backdrop.hidden=true;document.body.append(backdrop);
  let openMenu=null,leftOpen=false,rightOpen=false,lastTrigger=null;
  const leftToggle=document.createElement('button'),rightToggle=document.createElement('button');
  leftToggle.type=rightToggle.type='button';leftToggle.id='drawing-tree-toggle';rightToggle.id='drawing-properties-toggle';
  leftToggle.textContent='Sheets';rightToggle.textContent='Properties';
  leftToggle.setAttribute('aria-controls','drawing-tree-panel');rightToggle.setAttribute('aria-controls','drawing-properties-panel');
  header.insertBefore(leftToggle,$('create'));header.insertBefore(rightToggle,$('create'));
  for(const id of ['save','pdf','cancel-job'])header.append($(id));
  $('save').classList.add('drawing-head-action');$('pdf').classList.add('drawing-head-action');$('cancel-job').classList.add('drawing-head-action');
  for(const divider of toolbar.querySelectorAll('.divider'))divider.remove();
  const groups=[
    ['Edit',['undo','redo']],
    ['Add annotation',['dimension','text','leader']],
    ['Insert',['view','table','schematic']],
    ['Document',['update','revision','release']],
  ];
  function closeMenu(returnFocus=false){
    if(!openMenu)return false;
    const {popup,trigger}=openMenu;popup.hidden=true;trigger.setAttribute('aria-expanded','false');openMenu=null;
    if(returnFocus)trigger.focus();return true;
  }
  for(const [label,ids] of groups){
    const host=document.createElement('div');host.className='drawing-menu-host';
    const trigger=document.createElement('button');trigger.type='button';trigger.textContent=label+' ▾';trigger.className='drawing-menu-trigger';trigger.setAttribute('aria-expanded','false');
    const popup=document.createElement('div');popup.className='drawing-menu-popup';popup.hidden=true;
    for(const id of ids)popup.append($(id));
    trigger.onclick=()=>{const wasOpen=openMenu?.trigger===trigger;closeMenu();if(wasOpen)return;popup.hidden=false;trigger.setAttribute('aria-expanded','true');openMenu={popup,trigger};};
    trigger.onkeydown=event=>{if(['ArrowDown','ArrowUp'].includes(event.key)){event.preventDefault();if(openMenu?.trigger!==trigger)trigger.click();const choices=[...popup.querySelectorAll('button:not(:disabled)')];choices[event.key==='ArrowDown'?0:choices.length-1]?.focus();}};
    popup.addEventListener('click',event=>{if(event.target.closest('button'))closeMenu();});
    popup.addEventListener('keydown',event=>{
      if(event.key==='Escape'){event.preventDefault();closeMenu(true);return;}
      const choices=[...popup.querySelectorAll('button:not(:disabled)')],index=choices.indexOf(document.activeElement);
      if(['ArrowDown','ArrowUp','Home','End'].includes(event.key)&&choices.length){event.preventDefault();choices[event.key==='Home'?0:event.key==='End'?choices.length-1:(index+(event.key==='ArrowDown'?1:-1)+choices.length)%choices.length].focus();}
    });
    host.append(trigger,popup);toolbar.append(host);
  }
  const statusExpand=document.createElement('button');statusExpand.id='drawing-message-expand';statusExpand.type='button';statusExpand.textContent='More';statusExpand.setAttribute('aria-label','Expand drawing status');statusExpand.setAttribute('aria-expanded','false');
  const statusbar=document.createElement('div'),message=$('message');statusbar.className='drawing-statusbar';message.replaceWith(statusbar);statusbar.append(message);
  statusbar.append(statusExpand);
  statusExpand.onclick=()=>{const expanded=document.body.classList.toggle('drawing-status-expanded');statusExpand.setAttribute('aria-expanded',String(expanded));statusExpand.textContent=expanded?'Less':'More';};
  const issues=$('issues'),checks=document.createElement('details');checks.className='drawing-checks';checks.open=false;
  const summary=document.createElement('summary');summary.textContent='Drawing checks';checks.append(summary);issues.replaceWith(checks);checks.append(issues);
  const observer=new MutationObserver(()=>{const count=issues.querySelectorAll('.issue').length;summary.textContent=`Drawing checks · ${count}`;if(issues.querySelector('.issue.error'))checks.open=true;});
  observer.observe(issues,{childList:true});
  document.querySelector('.drawing-tree').id='drawing-tree-panel';document.querySelector('.drawing-properties').id='drawing-properties-panel';
  function paint(){
    document.body.dataset.drawingLeftOpen=String(leftOpen);document.body.dataset.drawingRightOpen=String(rightOpen);
    backdrop.hidden=!(window.innerWidth<1024&&leftOpen||window.innerWidth<1280&&rightOpen);
    leftToggle.setAttribute('aria-expanded',String(leftOpen));rightToggle.setAttribute('aria-expanded',String(rightOpen));
  }
  leftToggle.onclick=()=>{leftOpen=!leftOpen;rightOpen=false;paint();};
  rightToggle.onclick=()=>{rightOpen=!rightOpen;leftOpen=false;paint();};
  backdrop.onclick=()=>{leftOpen=false;rightOpen=false;paint();};
  window.addEventListener('resize',()=>{if(window.innerWidth>=1024)leftOpen=false;if(window.innerWidth>=1280)rightOpen=false;paint();});
  document.addEventListener('click',event=>{
    if(openMenu&&!openMenu.trigger.parentElement.contains(event.target))closeMenu();
    const button=event.target.closest?.('button,a');if(button&&!button.closest('#modal'))lastTrigger=button;
  },true);
  document.addEventListener('keydown',event=>{
    if(event.key!=='Escape'||event.defaultPrevented||document.querySelector('dialog[open]'))return;
    if(closeMenu(true)){event.preventDefault();return;}
    if(leftOpen||rightOpen){leftOpen=false;rightOpen=false;paint();event.preventDefault();}
  });
  $('modal').addEventListener('close',()=>{
    let target=lastTrigger;
    if(target&&!target.getClientRects().length)target=target.closest('.drawing-menu-host')?.querySelector('.drawing-menu-trigger');
    if(target?.isConnected&&!target.disabled&&target.getClientRects().length)target.focus();
  });
  paint();return {closeMenu};
}
