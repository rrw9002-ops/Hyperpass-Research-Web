"use strict";
(() => {
  const fields = new Map();
  const get = id => document.getElementById(id);
  const qualified = /^[A-Z0-9_]+:[A-Z0-9.^=_!-]+$/;

  async function resolve(query, target="any") {
    if (!query || !String(query).trim()) throw new Error("종목명 또는 티커를 입력하세요.");
    return window.HyperpassApp.api("/api/symbols/resolve?" + new URLSearchParams({q:String(query).trim(), target}));
  }

  function attach(id, prefix) {
    const input=get(id), matches=get(prefix + "-matches"), status=get(prefix + "-status");
    if (!input || !matches || !status || fields.has(id)) return;
    let timer, request=0, composing=false, selectedItem=null;
    function choose(item) {
      if (input.disabled) return;
      ++request;
      clearTimeout(timer);
      selectedItem=item;
      input.value=item.name;
      status.textContent="선택한 종목 · " + item.id;
      matches.replaceChildren();
      input.focus();
    }
    async function search(query, version) {
      try {
        const data=await window.HyperpassApp.api("/api/tradingview/symbols?q=" + encodeURIComponent(query));
        if(version !== request || input.value.trim() !== query) return;
        for(const item of data.results || []) {
          const button=document.createElement("button");
          button.type="button";
          button.className="button ghost compact";
          button.textContent=item.name + " · " + item.id;
          button.addEventListener("click",()=>choose(item));
          matches.append(button);
        }
        status.textContent=matches.children.length ? "이름 또는 티커로 바로 조회하거나 목록에서 종목을 선택하세요." : (data.notice || "일치하는 이름을 찾지 못했습니다. 거래소 티커도 입력할 수 있습니다.");
      } catch(error) {if(version === request) status.textContent=error.message;}
    }
    function update() {
      selectedItem=null;
      clearTimeout(timer);
      const version=++request, query=input.value.trim();
      matches.replaceChildren();
      status.textContent="";
      if(composing || !query) return;
      if(qualified.test(query.toUpperCase())) {status.textContent=query.toUpperCase(); return;}
      status.textContent="종목 검색 중…";
      timer=setTimeout(()=>search(query,version),280);
    }
    input.addEventListener("input",update);
    input.addEventListener("compositionstart",()=>{composing=true;update();});
    input.addEventListener("compositionend",()=>{composing=false;update();});
    input.addEventListener("keydown",event=>{
      if(event.isComposing) return;
      if(event.key==="ArrowDown" && matches.firstChild){event.preventDefault();matches.firstChild.focus();}
      if(event.key==="Escape"){++request;clearTimeout(timer);matches.replaceChildren();status.textContent="";}
    });
    fields.set(id,async target=>{
      const text=input.value.trim(), item=selectedItem && text===selectedItem.name ? selectedItem : null;
      const result=await resolve(item ? item.id : text,target);
      if(input.value.trim()!==text) throw new Error("종목이 변경되었습니다. 다시 조회하세요.");
      ++request;
      clearTimeout(timer);
      matches.replaceChildren();
      status.textContent=(item?.name || result.name) + " · " + (target==="yahoo" ? result.yahoo : result.id || result.yahoo);
      return result;
    });
  }
  async function field(id,target) {
    const bound=fields.get(id);
    return bound ? bound(target) : resolve(get(id)?.value,target);
  }
  window.HyperpassSymbols={resolve,field,attach,selected:async()=>(await field("tv-symbol","tradingview")).id};
  document.addEventListener("DOMContentLoaded",()=>{
    attach("tv-symbol","tv-symbol");
    attach("chart-symbol","chart-symbol");
    attach("symbol","research-symbol");
  },{once:true});
})();
