import './save-feedback.css';

const duration=2700;
let toast=null,toastTimer=null;
function dismissToast(){clearTimeout(toastTimer);if(toast)toast.hidden=true;}
function showToast(message){
  if(!toast){
    toast=document.createElement('div');toast.className='save-toast';
    toast.setAttribute('role','status');toast.setAttribute('aria-live','polite');toast.setAttribute('aria-atomic','true');
    document.body.append(toast);
  }
  clearTimeout(toastTimer);toast.hidden=false;toast.textContent=message;
  toastTimer=setTimeout(()=>{toast.hidden=true;},duration);
}

export function createSaveFeedback(button,message){
  const normalLabel=button.textContent;let resetTimer=null;
  return {
    async run(save){
      clearTimeout(resetTimer);dismissToast();button.textContent='Saving…';
      try{
        const result=await save();
        button.textContent='Saved ✓';showToast(message);
        resetTimer=setTimeout(()=>{button.textContent=normalLabel;},duration);
        return result;
      }catch(error){button.textContent=normalLabel;throw error;}
    }
  };
}
