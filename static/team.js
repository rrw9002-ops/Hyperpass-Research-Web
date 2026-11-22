"use strict";
(() => {
  const host = document.getElementById("workspace-team");
  if (!host) return;
  const $ = id => document.getElementById(id);
  const state = {documents:[], current:null, original:"", busy:false, ready:false, pendingPath:null};
  host.innerHTML = `<div class="workspace-heading"><div><span class="eyebrow">YOUR TEAM / YOUR METHODS</span><h1>팀의 관점과 분석 방법을 다듬으세요.</h1><p>GitHub의 역할과 분석 방법을 출발점으로, 수업과 연구 목적에 맞게 수정할 수 있습니다.</p></div><button id="team-refresh" class="button ghost compact" type="button">파일 목록 새로고침 ↻</button></div>
    <div class="workspace-note"><span>↗</span><p>역할의 지침과 스킬(분석 방법)은 글 파일입니다. 여기서 고치고 저장하면 <strong>다음 분석부터 바로 적용</strong>됩니다. 같은 파일을 <code>team/</code> 폴더에서 편집기로 직접 고쳐도 됩니다. 진행 중인 분석에는 시작할 때의 지침이 유지됩니다.</p></div>
    <div class="team-editor-layout"><aside class="panel team-document-panel"><div class="panel-heading"><div><span class="section-kicker">01 / TEAM DOCUMENTS</span><h2>역할과 분석 방법</h2></div></div><div class="team-search"><label class="sr-only" for="team-search">팀 파일 검색</label><input id="team-search" type="search" placeholder="역할·분석 방법 찾기"></div><nav id="team-document-list" aria-label="편집할 팀 문서"></nav><details class="team-location"><summary>직접 편집할 폴더</summary><p id="team-directory">팀 파일 위치를 불러오는 중입니다.</p><p>팀 배정·근거 채택·독립 검토의 기본 구조는 유지합니다. 이 화면에서는 기존 역할의 지침과 분석 방법을 수정합니다.</p></details></aside>
    <section class="panel team-writing-panel" aria-labelledby="team-editor-title"><div class="panel-heading"><div><span class="section-kicker">02 / INSTRUCTIONS & METHODS</span><h2 id="team-editor-title">편집할 문서를 선택하세요.</h2><code id="team-document-path"></code></div><span id="team-edit-status" class="workspace-state">준비 중</span></div><div class="team-writing-body"><label class="sr-only" for="team-content">팀 문서 내용</label><textarea id="team-content" rows="24" spellcheck="false" disabled placeholder="왼쪽에서 역할 지침이나 분석 방법을 선택하세요."></textarea><div class="team-save-bar"><p id="team-revision">원본과 수정 이력을 구분해 보관합니다.</p><div><button id="team-reload" type="button" class="button ghost" disabled>저장된 내용 다시 읽기</button><button id="team-save" type="button" class="button primary" disabled>변경 내용 저장 ↗</button></div></div><p id="team-feedback" class="feedback" aria-live="polite"></p></div></section></div>
    <dialog id="team-unsaved-dialog" aria-labelledby="team-unsaved-title"><h2 id="team-unsaved-title">저장하지 않은 변경이 있습니다.</h2><p class="dialog-description">현재 입력을 유지하거나, 변경을 버리고 저장된 문서를 열 수 있습니다.</p><div class="workspace-actions"><button id="team-keep-editing" type="button" class="button primary">계속 편집</button><button id="team-discard" type="button" class="button ghost">변경 버리고 열기</button></div></dialog>`;
  const dirty = () => Boolean(state.current) && $("team-content").value !== state.original;
  const feedback = (message, isError=false) => {$("team-feedback").textContent=message;$("team-feedback").classList.toggle("error-text",isError);};
  const make = (tag,cls,text) => {const node=document.createElement(tag);if(cls)node.className=cls;if(text!==undefined)node.textContent=String(text);return node;};
  function sync() {
    const changed=dirty();
    $("team-save").disabled=state.busy||!changed;
    $("team-reload").disabled=state.busy||!state.current;
    $("team-refresh").disabled=state.busy;
    $("team-content").disabled=state.busy||!state.current;
    $("team-edit-status").textContent=state.busy?"처리 중":!state.current?"문서 선택":changed?"저장하지 않음":"저장된 내용";
    $("team-edit-status").classList.toggle("changed",changed);
    for(const button of $("team-document-list").querySelectorAll("button"))button.disabled=state.busy;
  }
  function renderList() {
    const list=$("team-document-list"),query=$("team-search").value.trim().toLowerCase();
    list.replaceChildren();
    const groupOrder={common:0,instruction:0,instructions:0,role:1,roles:1,skill:2,skills:2,method:2,methods:2,reference:3};
    const documents=state.documents.filter(item=>[item.title,item.path,item.kind,item.summary].join(" ").toLowerCase().includes(query)).sort((a,b)=>(groupOrder[a.kind]??4)-(groupOrder[b.kind]??4));
    if(!documents.length){list.append(make("p","team-empty",state.ready?"일치하는 문서가 없습니다.":"팀 문서를 불러오고 있습니다."));return;}
    const labels={role:"역할 지침",roles:"역할 지침",skill:"분석 방법",skills:"분석 방법",method:"분석 방법",methods:"분석 방법",reference:"공통 분석 기준",common:"공통 규칙",instruction:"운영 지침",instructions:"운영 지침"};
    let previous="";
    for(const item of documents){
      const group=labels[item.kind]||"팀 문서";
      if(group!==previous){list.append(make("span","team-list-group",group));previous=group;}
      const button=make("button","team-document"),active=item.path===state.current?.path;
      button.type="button";button.classList.toggle("selected",active);button.setAttribute("aria-current",active?"true":"false");
      button.append(make("strong","",item.title||item.path),make("small","",item.summary||item.path));
      button.addEventListener("click",()=>requestOpen(item.path));list.append(button);
    }
    sync();
  }
  function requestOpen(path) {
    if(state.busy)return;
    if(dirty()){state.pendingPath=path;$("team-unsaved-dialog").showModal();return;}
    openDocument(path);
  }
  async function openDocument(path) {
    if(state.busy)return;
    state.busy=true;feedback("문서를 불러오고 있습니다.");sync();
    try{
      const document=await window.HyperpassApp.api("/api/team/document?path="+encodeURIComponent(path));
      if(typeof document.content!=="string"||typeof document.revision!=="string")throw new Error("문서 응답을 읽지 못했습니다.");
      state.current=document;state.original=document.content;$("team-content").value=document.content;
      $("team-editor-title").textContent=document.title||state.documents.find(item=>item.path===path)?.title||path;
      $("team-document-path").textContent="team/"+document.path.replace(/^team\//,"");
      const modified=document.modified_at||document.updated_at;$("team-revision").textContent=modified?"마지막 저장: "+new Date(modified).toLocaleString("ko-KR"):"저장하면 다음 분석부터 사용합니다.";
      feedback("저장된 문서를 읽었습니다. 수정한 뒤 저장해 주세요.");
    }catch(error){feedback(error.message,true);}
    finally{state.busy=false;renderList();sync();}
  }
  async function refresh() {
    if(state.busy)return;
    state.busy=true;sync();
    try{
      const data=await window.HyperpassApp.api("/api/team");
      if(!Array.isArray(data.documents))throw new Error("팀 문서 목록을 읽지 못했습니다.");
      state.documents=data.documents.filter(item=>item&&typeof item.path==="string");state.ready=true;
      $("team-directory").textContent=data.team_dir||"앱의 team/ 폴더";
      renderList();feedback(dirty()?"파일 목록을 새로 읽었습니다. 편집 중인 입력은 유지했습니다.":"팀 문서를 선택하면 내용을 편집할 수 있습니다.");
    }catch(error){feedback(error.message,true);}
    finally{state.busy=false;sync();}
    if(!state.current&&state.documents.length)await openDocument(state.documents[0].path);
  }
  async function save() {
    if(state.busy||!dirty())return;
    const content=$("team-content").value,path=state.current.path,revision=state.current.revision;
    state.busy=true;feedback("변경 내용을 저장하고 있습니다.");sync();
    try{
      const document=await window.HyperpassApp.api("/api/team/document",{method:"POST",body:{path,content,expected_revision:revision}});
      if(typeof document.revision!=="string")throw new Error("저장 응답을 확인하지 못했습니다. 입력은 유지했습니다. 저장된 내용을 다시 읽어 확인하세요.");
      state.current={...state.current,...document,path};state.original=typeof document.content==="string"?document.content:content;
      $("team-content").value=state.original;$("team-revision").textContent="마지막 저장: "+new Date(document.modified_at||document.updated_at||Date.now()).toLocaleString("ko-KR");
      const item=state.documents.find(item=>item.path===path);if(item)Object.assign(item,document);
      feedback("저장했습니다. 다음에 시작하는 분석부터 적용됩니다. 진행 중인 분석의 지침은 바뀌지 않습니다.");
    }catch(error){feedback(error.message+" 입력한 내용은 그대로 유지했습니다.",true);}
    finally{state.busy=false;renderList();sync();}
  }
  $("team-content").addEventListener("input",()=>{sync();feedback(dirty()?"아직 저장하지 않은 변경입니다.":"");});
  $("team-search").addEventListener("input",renderList);$("team-refresh").addEventListener("click",refresh);$("team-save").addEventListener("click",save);
  $("team-reload").addEventListener("click",()=>{if(state.current)requestOpen(state.current.path);});
  $("team-keep-editing").addEventListener("click",()=>{$("team-unsaved-dialog").close();state.pendingPath=null;});
  $("team-discard").addEventListener("click",()=>{const path=state.pendingPath;$("team-unsaved-dialog").close();state.pendingPath=null;if(path)openDocument(path);});
  window.addEventListener("beforeunload",event=>{if(dirty()){event.preventDefault();event.returnValue="";}});
  host.addEventListener("keydown",event=>{if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==="s"){event.preventDefault();save();}});
  const loadWhenVisible=()=>{if(!host.hidden&&!state.ready&&!state.busy)refresh();};
  new MutationObserver(loadWhenVisible).observe(host,{attributes:true,attributeFilter:["hidden"]});
  document.addEventListener("hyperpass:workspace-change",loadWhenVisible);
  window.HyperpassTeam={refresh,hasUnsavedChanges:dirty};renderList();sync();loadWhenVisible();
})();
