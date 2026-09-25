const STORAGE_KEY = 'pmc:studio-layout:v1';
const DEFAULTS = {left:260,right:360,drawer:240,leftCollapsed:false,rightCollapsed:false};
const clamp = (value,min,max) => Math.min(max,Math.max(min,value));

export function createStudioShell({$}) {
  const workspace=document.querySelector('.workspace');
  const app=$('app');
  let stored={};
  try { stored=JSON.parse(localStorage.getItem(STORAGE_KEY)||'{}')||{}; } catch {}
  let layout={
    left:clamp(Number(stored.left)||DEFAULTS.left,220,360),
    right:clamp(Number(stored.right)||DEFAULTS.right,300,480),
    drawer:clamp(Number(stored.drawer)||DEFAULTS.drawer,160,Math.max(160,window.innerHeight*.45)),
    leftCollapsed:!!stored.leftCollapsed,
    rightCollapsed:!!stored.rightCollapsed,
  };
  let busy=false,leftOpen=false,rightOpen=false,validationOpen=false,openMenu=null;
  document.addEventListener('click',event=>{
    if(busy&&event.target.closest('button')){
      event.preventDefault();
      event.stopImmediatePropagation();
    }
  },true);
  const backdrop=document.createElement('div');
  backdrop.className='panel-backdrop';
  backdrop.hidden=true;
  app.append(backdrop);
  const save=()=>{try {localStorage.setItem(STORAGE_KEY,JSON.stringify(layout));} catch {}};
  function viewportWidth(){return window.innerWidth;}
  function paint(){
    workspace.style.setProperty('--left-width',layout.left+'px');
    workspace.style.setProperty('--right-width',layout.right+'px');
    document.querySelector('.validation-panel').style.setProperty('--drawer-height',Math.min(layout.drawer,window.innerHeight*.45)+'px');
    workspace.dataset.leftCollapsed=String(layout.leftCollapsed);
    workspace.dataset.rightCollapsed=String(layout.rightCollapsed);
    workspace.dataset.leftOpen=String(leftOpen);
    workspace.dataset.rightOpen=String(rightOpen);
    backdrop.hidden=!(viewportWidth()<1024&&leftOpen||viewportWidth()<1280&&rightOpen);
    $('left-restore').hidden=viewportWidth()>=1024&&!layout.leftCollapsed;
    $('right-restore').hidden=viewportWidth()>=1280&&!layout.rightCollapsed;
    $('left-split').setAttribute('aria-valuenow',String(layout.left));
    $('right-split').setAttribute('aria-valuenow',String(layout.right));
    $('validation-split').setAttribute('aria-valuenow',String(layout.drawer));
    $('validation-body').hidden=!validationOpen;
    $('validation-toggle').setAttribute('aria-expanded',String(validationOpen));
    document.querySelector('.validation-panel').dataset.open=String(validationOpen);
  }
  function closeMenus(restoreFocus=false){
    if(!openMenu)return;
    const trigger=openMenu.querySelector('.menu-trigger');
    openMenu.querySelector('.menu-popover').hidden=true;
    trigger.setAttribute('aria-expanded','false');
    openMenu=null;
    if(restoreFocus)trigger.focus();
  }
  function toggleMenu(host,focusFirst=false){
    if(busy)return;
    const wasOpen=openMenu===host;
    closeMenus();
    if(wasOpen)return;
    openMenu=host;
    host.querySelector('.menu-popover').hidden=false;
    host.querySelector('.menu-trigger').setAttribute('aria-expanded','true');
    if(focusFirst)host.querySelector('.menu-popover button:not(:disabled)')?.focus();
  }
  for(const host of document.querySelectorAll('.menu-host')){
    const trigger=host.querySelector('.menu-trigger'),popup=host.querySelector('.menu-popover');
    trigger.addEventListener('click',()=>toggleMenu(host));
    trigger.addEventListener('keydown',event=>{
      if(event.key==='ArrowDown'||event.key==='ArrowUp'){
        event.preventDefault();toggleMenu(host,true);
        if(event.key==='ArrowUp')popup.querySelector('button:last-of-type')?.focus();
      }
    });
    popup.addEventListener('click',event=>{
      if(event.target.closest('button'))closeMenus();
    });
    popup.addEventListener('keydown',event=>{
      if(event.key==='Escape'){event.preventDefault();closeMenus(true);return;}
      const buttons=[...popup.querySelectorAll('button:not(:disabled)')];
      const index=buttons.indexOf(document.activeElement);
      if(['ArrowDown','ArrowUp','Home','End'].includes(event.key)&&buttons.length){
        event.preventDefault();
        buttons[event.key==='Home'?0:event.key==='End'?buttons.length-1:(index+(event.key==='ArrowDown'?1:-1)+buttons.length)%buttons.length].focus();
      }
    });
  }
  document.addEventListener('pointerdown',event=>{if(openMenu&&!openMenu.contains(event.target))closeMenus();});
  document.addEventListener('keydown',event=>{if(event.key==='Escape'&&openMenu){event.preventDefault();closeMenus(true);}});
  $('add-cavity').addEventListener('click',()=>{if(!busy)$('library-open').click();});

  function togglePanel(side){
    if(busy)return;
    const width=viewportWidth();
    if(side==='left'&&width<1024){leftOpen=!leftOpen;rightOpen=false;}
    else if(side==='right'&&width<1280){rightOpen=!rightOpen;leftOpen=false;}
    else {layout[side+'Collapsed']=!layout[side+'Collapsed'];save();}
    closeMenus();paint();
  }
  $('left-toggle').onclick=()=>togglePanel('left');
  $('left-restore').onclick=()=>togglePanel('left');
  $('right-toggle').onclick=()=>togglePanel('right');
  $('right-restore').onclick=()=>togglePanel('right');
  backdrop.onclick=()=>{leftOpen=false;rightOpen=false;paint();};
  window.addEventListener('resize',()=>{if(viewportWidth()>=1024)leftOpen=false;if(viewportWidth()>=1280)rightOpen=false;paint();});
  $('reset-layout').onclick=()=>{
    if(busy)return;
    layout={...DEFAULTS};leftOpen=false;rightOpen=false;validationOpen=false;
    try{localStorage.removeItem(STORAGE_KEY);}catch{}
    paint();
  };

  function resizeOnPointer(element,key,min,max,sign){
    element.addEventListener('pointerdown',event=>{
      if(busy||event.button!==0||key==='drawer'&&!validationOpen||key==='left'&&viewportWidth()<1024||key==='right'&&viewportWidth()<1280)return;
      const start=key==='drawer'?event.clientY:event.clientX,initial=layout[key];
      element.setPointerCapture(event.pointerId);
      const move=e=>{layout[key]=clamp(initial+(key==='drawer'?start-e.clientY:(e.clientX-start)*sign),min,key==='drawer'?Math.min(max,Math.max(min,window.innerHeight*.45)):max);paint();};
      const stop=()=>{element.removeEventListener('pointermove',move);element.removeEventListener('pointerup',stop);element.removeEventListener('pointercancel',stop);save();};
      element.addEventListener('pointermove',move);
      element.addEventListener('pointerup',stop);
      element.addEventListener('pointercancel',stop);
    });
    element.addEventListener('keydown',event=>{
      if(busy||!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key))return;
      event.preventDefault();
      const delta=event.key==='ArrowRight'||event.key==='ArrowUp'?10:-10;
      layout[key]=clamp(layout[key]+(key==='drawer'?delta:delta*sign),min,key==='drawer'?Math.min(max,Math.max(min,window.innerHeight*.45)):max);
      paint();save();
    });
  }
  resizeOnPointer($('left-split'),'left',220,360,1);
  resizeOnPointer($('right-split'),'right',300,480,-1);
  resizeOnPointer($('validation-split'),'drawer',160,600,1);
  for(const [id,min,max]of [['left-split',220,360],['right-split',300,480],['validation-split',160,600]]){
    $(id).setAttribute('aria-valuemin',String(min));
    $(id).setAttribute('aria-valuemax',String(max));
  }
  $('validation-toggle').onclick=()=>{validationOpen=!validationOpen;paint();};
  $('notice-expand').onclick=()=>{
    const expanded=document.querySelector('.status-strip').classList.toggle('expanded');
    $('notice-expand').setAttribute('aria-expanded',String(expanded));
    $('notice-expand').setAttribute('aria-label',expanded?'Collapse status message':'Expand status message');
  };
  $('compact-mode').onchange=event=>$(event.target.value+'-mode').click();
  paint();
  return {
    setBusy(value){busy=!!value;if(busy){closeMenus();leftOpen=false;rightOpen=false;paint();}},
    validationCompleted(result){if((result?.counts?.FAIL||0)+(result?.counts?.WARNING||0)>0){validationOpen=true;paint();}},
    syncMode(mode){$('compact-mode').value=mode;},
    closeMenus,
  };
}
