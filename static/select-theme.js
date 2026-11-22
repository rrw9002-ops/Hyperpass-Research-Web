'use strict';
(function(){
  if(CSS.supports('appearance','base-select')||!matchMedia('(pointer:fine)').matches||matchMedia('(forced-colors:active)').matches)return;
  let field,menu,rows,active,typed='',typedAt=0;
  function close(){if(!menu)return;menu.remove();field.removeAttribute('aria-expanded');field.removeAttribute('aria-controls');field.removeAttribute('aria-activedescendant');menu=null;field=null;typed=''}
  function move(index){if(!rows[index]||rows[index].getAttribute('aria-disabled')==='true')return;rows[active]?.removeAttribute('data-focus');active=index;rows[index].setAttribute('data-focus','');field.setAttribute('aria-activedescendant',rows[index].id);rows[index].scrollIntoView({block:'nearest'})}
  function commit(){if(!menu)return;const sel=field,i=active;if(i>=0&&rows[i].getAttribute('aria-disabled')!=='true'&&sel.selectedIndex!==i){sel.selectedIndex=i;sel.dispatchEvent(new Event('input',{bubbles:true}));sel.dispatchEvent(new Event('change',{bubbles:true}))}close()}
  function allowed(el){return el instanceof HTMLSelectElement&&!el.multiple&&!el.hasAttribute('size')&&!el.disabled&&el.options.length}
  function open(sel){
    close();field=sel;menu=document.createElement('div');menu.className='hp-select-list';menu.id='hp-select-picker';menu.setAttribute('role','listbox');field.setAttribute('aria-expanded','true');field.setAttribute('aria-controls',menu.id);
    const host=field.closest('dialog[open]')||document.body;host.append(menu);const box=field.getBoundingClientRect();Object.assign(menu.style,{width:box.width+'px',left:box.left+'px',font:getComputedStyle(field).font});
    let previous=null;active=-1;
    rows=Array.from(sel.options,(o,i)=>{if(o.parentElement instanceof HTMLOptGroupElement&&previous!==o.parentElement){previous=o.parentElement;const label=document.createElement('small');label.textContent=previous.label;menu.append(label)}const r=document.createElement('div');r.id='hp-select-option-'+i;r.textContent=o.label;r.setAttribute('role','option');r.setAttribute('aria-selected',String(i===sel.selectedIndex));r.setAttribute('aria-disabled',String(o.disabled||Boolean(o.closest('optgroup:disabled'))));r.hidden=o.hidden;r.onpointermove=()=>{if(i!==active)move(i)};r.onmousedown=e=>e.preventDefault();r.onclick=()=>{move(i);if(active===i)commit()};menu.append(r);return r});
    const below=innerHeight-box.bottom,above=box.top,up=below<160&&above>below;
    menu.style.maxHeight=Math.min(340,Math.max(60,(up?above:below)-7))+'px';if(up)menu.style.bottom=(innerHeight-box.top)+'px';else menu.style.top=box.bottom+'px';
    sel.focus();move(sel.selectedIndex);
  }
  document.addEventListener('pointerdown',e=>{if(menu?.contains(e.target))return;const el=e.target;if(!allowed(el)){close();return}e.preventDefault();if(el===field)close();else open(el)},true);
  document.addEventListener('keydown',e=>{
    if(!menu){if(allowed(e.target)&&['Enter',' ','ArrowDown','ArrowUp','F4'].includes(e.key)){e.preventDefault();open(e.target)}return}
    if(e.key==='Tab'){close();return}e.preventDefault();if(e.key==='Escape'||e.key==='F4'){close();return}if(e.key==='Enter'||e.key===' '){commit();return}
    const valid=rows.map((r,i)=>r.hidden||r.getAttribute('aria-disabled')==='true'?-1:i).filter(i=>i>=0);if(!valid.length)return;
    const idx=valid.indexOf(active),delta={ArrowDown:1,ArrowUp:-1,PageDown:8,PageUp:-8}[e.key];
    if(delta)move(valid[Math.max(0,Math.min(valid.length-1,idx+delta))]);else if(e.key==='Home')move(valid[0]);else if(e.key==='End')move(valid.at(-1));
    else if(e.key.length===1){typed=(performance.now()-typedAt<850?typed:'')+e.key.toLocaleLowerCase();typedAt=performance.now();const found=valid.find(i=>rows[i].textContent.toLocaleLowerCase().startsWith(typed));if(found!=null)move(found)}
  },true);
  document.addEventListener('focusin',e=>{if(menu&&e.target!==field&&!menu.contains(e.target))close()});document.addEventListener('scroll',e=>{if(menu&&!menu.contains(e.target))close()},true);window.addEventListener('resize',close);
})();
