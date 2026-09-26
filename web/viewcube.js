import {VIEW_DIRECTIONS,CORNER_VIEWS,viewDirection} from './viewer-navigation.js';

const LABELS={top:'Top',bottom:'Bottom',front:'Front',back:'Back',left:'Left',right:'Right',iso:'Isometric'};
function label(key){
  if(LABELS[key])return LABELS[key];
  const match=/^corner-([rl])([fb])([td])$/.exec(key);
  return match?`${match[1]==='r'?'Right':'Left'} ${match[2]==='f'?'front':'back'} ${match[3]==='t'?'top':'bottom'}`:key;
}

export function createViewCube(container,onView,getState){
  const root=document.createElement('div');root.className='viewcube';root.setAttribute('aria-label','ViewCube navigation');
  const trigger=document.createElement('button');trigger.type='button';trigger.className='viewcube-trigger';trigger.title='ViewCube directions';trigger.setAttribute('aria-expanded','false');trigger.setAttribute('aria-label','Open ViewCube directions');
  const icon=document.createElement('span');icon.className='viewcube-glyph';icon.setAttribute('aria-hidden','true');
  for(const side of ['top','front','right']){const face=document.createElement('span');face.className='viewcube-glyph-'+side;face.textContent=side[0].toUpperCase();icon.append(face);}
  trigger.append(icon);
  const menu=document.createElement('div');menu.className='viewcube-menu';menu.hidden=true;
  const heading=document.createElement('div');heading.className='viewcube-heading';heading.textContent='STANDARD VIEWS';menu.append(heading);
  const buttons=new Map();
  for(const key of Object.keys(VIEW_DIRECTIONS)){
    const button=document.createElement('button');button.type='button';button.textContent=label(key);button.setAttribute('aria-label',`${label(key)} view`);button.dataset.view=key;
    button.onclick=()=>{onView(key);close();};menu.append(button);buttons.set(key,button);
  }
  const corners=document.createElement('div');corners.className='viewcube-heading';corners.textContent='CORNER VIEWS';menu.append(corners);
  for(const key of Object.keys(CORNER_VIEWS)){
    const button=document.createElement('button');button.type='button';button.textContent=label(key);button.setAttribute('aria-label',`${label(key)} corner view`);button.dataset.view=key;
    button.onclick=()=>{onView(key);close();};menu.append(button);buttons.set(key,button);
  }
  function close(returnFocus=false){menu.hidden=true;trigger.setAttribute('aria-expanded','false');if(returnFocus)trigger.focus();}
  trigger.onclick=()=>{const opening=menu.hidden;menu.hidden=!opening;trigger.setAttribute('aria-expanded',String(opening));if(opening)menu.querySelector('button')?.focus();};
  menu.addEventListener('keydown',event=>{if(event.key==='Escape'){event.preventDefault();close(true);}else if(['ArrowDown','ArrowUp'].includes(event.key)){event.preventDefault();const list=[...buttons.values()],i=list.indexOf(document.activeElement);list[(i+(event.key==='ArrowDown'?1:-1)+list.length)%list.length].focus();}});
  document.addEventListener('pointerdown',event=>{if(!root.contains(event.target))close();});
  root.append(trigger,menu);container.append(root);
  function sync(){const state=getState();root.dataset.projection=state?.projection||'perspective';for(const [key,button]of buttons)button.setAttribute('aria-current',String(!!state?.direction&&viewDirection(key).dot({x:state.direction[0],y:state.direction[1],z:state.direction[2]})>.99999));}
  sync();return {sync,close,root};
}
