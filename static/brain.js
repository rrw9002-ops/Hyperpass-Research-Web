"use strict";
(() => {
  const $ = id => document.getElementById(id);
  const state = {items:[],filter:"all",query:"",loading:null,ready:false};
  const types = {report:"완료 보고서",chart:"차트 연구",tradingview:"TradingView 백테스트",incomplete:"미완료 기록",sample:"고정 샘플"};
  const make = (tag,cls,text) => { const node=document.createElement(tag); if(cls)node.className=cls; if(text!==undefined)node.textContent=String(text); return node; };
  const dateLabel = value => {const date=new Date(value);return Number.isNaN(+date)?"":date.toLocaleString("ko-KR",{year:"2-digit",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit"});};
  function openItem(item) {
    const app=window.HyperpassApp;
    if(!app){$("brain-feedback").textContent="작업 공간 연결을 준비하고 있습니다. 잠시 후 다시 눌러 주세요.";return;}
    const action=item.type==="chart"?app.openChart:item.type==="tradingview"?async id=>{app.selectWorkspace('tradingview');await window.HyperpassTradingView?.open(id);}:app.openRun;
    if(typeof action!=="function"){$("brain-feedback").textContent="이 기록을 여는 기능이 아직 준비되지 않았습니다.";return;}
    Promise.resolve(action(item.id)).catch(()=>{$("brain-feedback").textContent="기록을 열지 못했습니다. 앱 연결을 확인해 주세요.";});
  }
  async function useMemory(item,button) {
    if(item.type!=="report")return;
    const action=window.HyperpassApp?.useMemory;
    if(typeof action!=="function"){$("brain-feedback").textContent="이전 판단 연결 기능을 준비하고 있습니다. 잠시 후 다시 눌러 주세요.";return;}
    button.disabled=true;$("brain-feedback").textContent="";
    try{await action(item.id);}
    catch{$("brain-feedback").textContent="이전 판단으로 연결하지 못했습니다. 앱 연결을 확인하고 다시 시도해 주세요.";}
    finally{button.disabled=false;}
  }
  function render() {
    const list=$("brain-records"); if(!list)return; list.replaceChildren();
    const query=state.query.toLocaleLowerCase();
    const shown=state.items.filter(item=>(state.filter==="all"||item.type===state.filter||(state.filter==="chart"&&item.type==="tradingview"))&&(!query||[item.title,item.summary,item.category,item.target_role].join(" ").toLocaleLowerCase().includes(query)));
    if(!shown.length){list.append(make("p","brain-empty",state.ready?(state.items.length?"검색 조건에 맞는 기록이 없습니다.":"아직 저장된 연구가 없습니다.\n리서치나 차트 연구를 시작하면 여기에 쌓입니다."):"저장된 연구를 불러오고 있습니다."));return;}
    for(const item of shown){
      const card=make("button","brain-record");card.type="button";card.setAttribute("aria-label",`${types[item.type]} 열기: ${item.title}`);
      const meta=make("div","brain-record-meta");meta.append(make("span","brain-record-type",types[item.type]),make("time","",dateLabel(item.created_at)));card.append(meta,make("strong","",item.title||"제목 없는 연구"));
      if(item.summary)card.append(make("p","",item.summary));
      card.addEventListener("click",()=>openItem(item));
      if(item.type==="report"){
        const entry=make("article","brain-record-entry"),actions=make("div","brain-record-actions");
        const memoryButton=make("button","text-button","이전 판단으로 사용 ↗");memoryButton.type="button";
        memoryButton.setAttribute("aria-label",`이전 판단으로 사용: ${item.title}`);
        memoryButton.title="현재 근거와 구분할 참고 기억으로 연결합니다.";
        memoryButton.addEventListener("click",()=>useMemory(item,memoryButton));
        actions.append(make("span","","현재 근거와 구분해 참고"),memoryButton);entry.append(card,actions);list.append(entry);
      }else list.append(card);
    }
  }
  async function refresh() {
    if(state.loading)return state.loading;
    state.loading=(async()=>{
      try{
        const response=await fetch("/api/library",{credentials:"same-origin",cache:"no-store",headers:{Accept:"application/json"}});
        if(!response.ok)throw new Error("library unavailable");
        const data=await response.json();if(!Array.isArray(data.items)||!data.counts)throw new Error("invalid library");
        state.items=data.items.filter(item=>item&&Object.hasOwn(types,item.type)&&typeof item.id==="string"&&typeof item.title==="string").slice(0,500);state.ready=true;
        for(const node of document.querySelectorAll("[data-brain-count]")){const value=data.counts[node.dataset.brainCount];node.textContent=Number.isFinite(value)&&value>=0?Number(value).toLocaleString("ko-KR"):"—";}
        $("brain-feedback").textContent="";render();orbs.forEach(orb=>orb.setItems(state.items));
      }catch{
        $("brain-feedback").textContent="기록을 불러오지 못했습니다. 앱이 실행 중인지 확인하고 새로고침해 주세요.";
        if(!state.ready){for(const node of document.querySelectorAll("[data-brain-count]"))node.textContent="—";$("brain-records").replaceChildren();}
      }finally{state.loading=null;}
    })();return state.loading;
  }
  class ResearchOrb {
    constructor(canvas){
      this.canvas=canvas;this.ctx=canvas.getContext("2d");this.width=0;this.height=0;this.items=[];this.hits=[];this.hover=null;this.angle=0;this.last=0;
      this.reduced=window.matchMedia("(prefers-reduced-motion: reduce)");
      const n=1200,golden=Math.PI*(3-Math.sqrt(5));this.points=Array.from({length:n},(_,i)=>{const y=1-2*(i+.5)/n,r=Math.sqrt(1-y*y),theta=i*golden;return{x:Math.cos(theta)*r,y,z:Math.sin(theta)*r};});
      this.observer=new ResizeObserver(()=>this.fit());this.observer.observe(canvas);
      this.reduced.addEventListener("change",()=>this.draw());
      canvas.addEventListener("pointermove",event=>{const rect=canvas.getBoundingClientRect(),x=event.clientX-rect.left,y=event.clientY-rect.top;this.hover=this.hits.find(hit=>(hit.x-x)**2+(hit.y-y)**2<144)||null;canvas.style.cursor=this.hover?"pointer":"default";if(this.reduced.matches)this.draw();});
      canvas.addEventListener("pointerleave",()=>{this.hover=null;canvas.style.cursor="default";if(this.reduced.matches)this.draw();});
      canvas.addEventListener("click",event=>{const rect=canvas.getBoundingClientRect(),x=event.clientX-rect.left,y=event.clientY-rect.top;const hit=this.hits.find(point=>(point.x-x)**2+(point.y-y)**2<144);if(hit)openItem(hit.item);});
      this.fit();
    }
    fit(){const rect=this.canvas.getBoundingClientRect();if(rect.width<1||rect.height<1)return;this.width=rect.width;this.height=rect.height;const ratio=Math.min(2,window.devicePixelRatio||1);this.canvas.width=Math.round(this.width*ratio);this.canvas.height=Math.round(this.height*ratio);this.ctx.setTransform(ratio,0,0,ratio,0,0);this.draw();}
    setItems(items){this.items=items.slice(0,28);this.draw();}
    project(point,radius,cx,cy){const c=Math.cos(this.angle),s=Math.sin(this.angle),x=point.x*c+point.z*s,z=point.z*c-point.x*s,scale=1+z*.12;return{x:cx+x*radius*scale,y:cy+point.y*radius*scale,z};}
    draw(){
      const {ctx,width:w,height:h}=this;if(!ctx||w<1||h<1||!this.canvas.getClientRects().length)return;
      ctx.clearRect(0,0,w,h);const cx=w/2,cy=h*.5,radius=Math.min(w*.36,h*.32);
      const haze=ctx.createRadialGradient(cx,cy,3,cx,cy,radius*1.2);haze.addColorStop(0,"rgba(233,206,118,.12)");haze.addColorStop(.35,"rgba(176,133,45,.04)");haze.addColorStop(1,"rgba(0,0,0,0)");ctx.fillStyle=haze;ctx.fillRect(0,0,w,h);
      ctx.save();ctx.translate(cx,cy);ctx.rotate(-.35);ctx.strokeStyle="rgba(195,168,110,.10)";ctx.lineWidth=1;ctx.beginPath();ctx.ellipse(0,0,radius*1.22,radius*.75,0,0,Math.PI*2);ctx.stroke();ctx.strokeStyle="rgba(240,167,93,.07)";ctx.beginPath();ctx.ellipse(0,0,radius*1.32,radius*1.12,.85,0,Math.PI*2);ctx.stroke();ctx.restore();
      const points=this.points.map(point=>this.project(point,radius,cx,cy)).sort((a,b)=>a.z-b.z);
      for(const p of points){const front=(p.z+1)/2,core=1-Math.min(1,Math.hypot(p.x-cx,p.y-cy)/radius);ctx.fillStyle=`rgba(${front>.7?232:174},${front>.7?222:161},${front>.7?183:124},${.08+front*.51+core*.12})`;const size=.55+front*.72;ctx.beginPath();ctx.arc(p.x,p.y,size,0,Math.PI*2);ctx.fill();}
      for(let i=0;i<170;i++){const a=i*2.399963+this.angle*1.4,rr=radius*.32*Math.sqrt((i+.5)/170),x=cx+Math.cos(a)*rr,y=cy+Math.sin(a)*rr*.82;ctx.fillStyle=i%7===0?"rgba(255,128,49,.82)":"rgba(225,214,133,.65)";ctx.beginPath();ctx.arc(x,y,i%11===0?1.5:.8,0,Math.PI*2);ctx.fill();}
      this.hits=[];
      this.items.forEach((item,i)=>{const theta=i*2.399963+this.angle*.15,yy=1-2*(i+.5)/Math.max(this.items.length,1),rr=Math.sqrt(Math.max(0,1-yy*yy)),p=this.project({x:Math.cos(theta)*rr,y:yy*.85,z:Math.sin(theta)*rr},radius*1.05,cx,cy);const active=this.hover?.item.id===item.id&&this.hover?.item.type===item.type;ctx.strokeStyle="rgba(241,164,90,.16)";ctx.lineWidth=.65;ctx.beginPath();ctx.moveTo(cx,cy);ctx.lineTo(p.x,p.y);ctx.stroke();const color=item.type==="incomplete"?"#bca987":item.type==="sample"?"#a39a77":item.type==="chart"?"#d2d6a2":"#ff8c47";ctx.shadowColor=color;ctx.shadowBlur=active?20:10;ctx.fillStyle=color;ctx.beginPath();ctx.arc(p.x,p.y,active?4.8:3,0,Math.PI*2);ctx.fill();ctx.shadowBlur=0;ctx.strokeStyle=active?"rgba(255,206,142,.65)":"rgba(231,194,133,.25)";ctx.beginPath();ctx.arc(p.x,p.y,active?8:6,0,Math.PI*2);ctx.stroke();this.hits.push({...p,item});});
      if(this.hover){const hit=this.hits.find(p=>p.item.id===this.hover.item.id&&p.item.type===this.hover.item.type);if(hit){const label=(hit.item.title||types[hit.item.type]).slice(0,24);ctx.font="10px Segoe UI, sans-serif";const labelWidth=Math.min(w-24,ctx.measureText(label).width+20),left=Math.max(8,Math.min(w-labelWidth-8,hit.x-labelWidth/2)),top=Math.max(8,hit.y-35);ctx.fillStyle="rgba(22,18,10,.94)";ctx.fillRect(left,top,labelWidth,24);ctx.strokeStyle="rgba(183,122,64,.7)";ctx.strokeRect(left,top,labelWidth,24);ctx.fillStyle="#e8e2d2";ctx.fillText(label,left+10,top+16);}}
    }
    tick(time){if(!this.reduced.matches&&!document.hidden&&this.canvas.getClientRects().length&&time-this.last>34){this.angle+=.002;this.last=time;this.draw();}}
  }
  const orbs=["research-orb","brain-orb"].map(id=>$(id)).filter(Boolean).map(canvas=>new ResearchOrb(canvas));
  function animate(time){orbs.forEach(orb=>orb.tick(time));requestAnimationFrame(animate);}requestAnimationFrame(animate);
  $("brain-search")?.addEventListener("input",event=>{state.query=event.target.value.trim();render();});
  for(const button of document.querySelectorAll("[data-brain-filter]"))button.addEventListener("click",()=>{state.filter=button.dataset.brainFilter;for(const other of document.querySelectorAll("[data-brain-filter]")){const selected=other===button;other.classList.toggle("selected",selected);other.setAttribute("aria-pressed",String(selected));}render();});
  $("brain-refresh")?.addEventListener("click",refresh);document.addEventListener("hyperpass:library-refresh",refresh);
  window.HyperpassBrain={refresh};render();refresh();
})();
