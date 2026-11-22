'use strict';
(function(){
  document.getElementById('print').addEventListener('click',()=>window.print());
  const status=document.getElementById('copy-status');let timer;
  for(const button of document.querySelectorAll('.copy')){
    button.addEventListener('click',async()=>{
      const code=button.closest('.example').querySelector('pre code');
      try{await navigator.clipboard.writeText(code.textContent);status.textContent='복사했습니다. AI 대화창이나 터미널에 붙여넣으세요.'}
      catch{const range=document.createRange();range.selectNodeContents(code);const selection=window.getSelection();selection.removeAllRanges();selection.addRange(range);status.textContent='선택했습니다. Windows는 Ctrl+C, Mac은 ⌘C로 복사하세요.'}
      clearTimeout(timer);timer=setTimeout(()=>{status.textContent=''},4000);
    });
  }
})();
