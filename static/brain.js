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
      this.zoom=1;this.offsetX=0;this.offsetY=0;this.drag=null;
      this.reduced=window.matchMedia("(prefers-reduced-motion: reduce)");
      const n=1200,golden=Math.PI*(3-Math.sqrt(5));this.points=Array.from({length:n},(_,i)=>{const y=1-2*(i+.5)/n,r=Math.sqrt(1-y*y),theta=i*golden;return{x:Math.cos(theta)*r,y,z:Math.sin(theta)*r};});
      this.observer=new ResizeObserver(()=>this.fit());this.observer.observe(canvas);
      this.reduced.addEventListener("change",()=>this.draw());
      this.bindNavigation();
      this.makeControls();
      this.fit();
    }
    makeControls() {
      const bar=make("div","orb-zoom-controls");
      bar.setAttribute("role","group");
      bar.setAttribute("aria-label","연구 지도 배율");
      const button=(label,caption,onClick)=>{
        const node=make("button","",caption);
        node.type="button";node.title=label;
        node.setAttribute("aria-label",label);
        node.setAttribute("aria-controls",this.canvas.id);
        node.addEventListener("click",onClick);
        bar.append(node);
        return node;
      };
      this.zoomOut=button("지도 축소","−",()=>this.zoomTo(this.zoom/1.25));
      this.resetZoom=button("지도 배율과 위치 초기화","100%",()=>this.zoomTo(1));
      this.zoomIn=button("지도 확대","+",()=>this.zoomTo(this.zoom*1.25));
      this.canvas.after(bar);
      this.updateControls();
    }
    updateControls() {
      this.zoomOut.disabled=this.zoom<=1;
      this.zoomIn.disabled=this.zoom>=4;
      this.resetZoom.textContent=Math.round(this.zoom*100)+"%";
      this.resetZoom.setAttribute("aria-label",`현재 ${Math.round(this.zoom*100)}%. 지도 배율과 위치 초기화`);
      this.canvas.classList.toggle("zoomed",this.zoom>1);
    }
    zoomTo(requested,x=this.width/2,y=this.height/2) {
      const next=Math.min(4,Math.max(1,requested));
      if(next===this.zoom)return;
      const ratio=next/this.zoom;
      this.offsetX=(this.offsetX+this.width/2-x)*ratio+x-this.width/2;
      this.offsetY=(this.offsetY+this.height/2-y)*ratio+y-this.height/2;
      this.zoom=next;
      this.clampOffset();
      this.hover=null;this.canvas.style.cursor="";
      this.updateControls();this.draw();
    }
    clampOffset() {
      const limitX=this.width*(this.zoom-1)/2,limitY=this.height*(this.zoom-1)/2;
      this.offsetX=Math.max(-limitX,Math.min(limitX,this.offsetX));
      this.offsetY=Math.max(-limitY,Math.min(limitY,this.offsetY));
    }
    pointAt(event) {
      const rect=this.canvas.getBoundingClientRect();
      return {x:event.clientX-rect.left,y:event.clientY-rect.top};
    }
    hitAt(x,y) {
      let closest=null,dist=14*14;
      for(const hit of this.hits){
        const d=(hit.x-x)**2+(hit.y-y)**2;
        if(d<dist){closest=hit;dist=d;}
      }
      return closest;
    }
    bindNavigation() {
      const canvas=this.canvas;
      canvas.addEventListener("wheel",event=>{
        if(event.ctrlKey||event.metaKey||!event.deltaY)return;
        const unit=event.deltaMode===1?16:event.deltaMode===2?this.height:1;
        const delta=Math.max(-180,Math.min(180,event.deltaY*unit));
        const next=Math.min(4,Math.max(1,this.zoom*Math.exp(-delta*.002)));
        if(next===this.zoom)return;
        event.preventDefault();
        const {x,y}=this.pointAt(event);
        this.zoomTo(next,x,y);
      },{passive:false});
      // A click zooms the background or opens a record. A drag moves the magnified map.
      canvas.addEventListener("pointerdown",event=>{
        if(!event.isPrimary||event.button!==0)return;
        const {x,y}=this.pointAt(event);
        this.drag={id:event.pointerId,x,y,offsetX:this.offsetX,offsetY:this.offsetY,moved:false};
        if(this.zoom>1)canvas.setPointerCapture(event.pointerId);
      });
      canvas.addEventListener("pointermove",event=>{
        const {x,y}=this.pointAt(event),drag=this.drag;
        if(drag&&drag.id===event.pointerId){
          const dx=x-drag.x,dy=y-drag.y;
          if(Math.hypot(dx,dy)>5)drag.moved=true;
          if(drag.moved&&this.zoom>1){
            this.offsetX=drag.offsetX+dx;this.offsetY=drag.offsetY+dy;
            this.clampOffset();this.hover=null;canvas.style.cursor="grabbing";this.draw();
          }
          return;
        }
        this.hover=this.hitAt(x,y);
        canvas.style.cursor=this.hover?"pointer":"";
        if(this.reduced.matches||this.hover)this.draw();
      });
      canvas.addEventListener("pointerup",event=>{
        if(!this.drag||this.drag.id!==event.pointerId)return;
        const drag=this.drag;this.drag=null;canvas.style.cursor="";
        if(drag.moved)return;
        const {x,y}=this.pointAt(event);
        if(x<0||y<0||x>this.width||y>this.height)return;
        const hit=this.hitAt(x,y);
        if(hit)openItem(hit.item);
        else this.zoomTo(this.zoom<4?this.zoom*1.5:1,x,y);
      });
      canvas.addEventListener("pointercancel",()=>{this.drag=null;canvas.style.cursor="";});
      canvas.addEventListener("pointerleave",event=>{
        if(!canvas.hasPointerCapture(event.pointerId))this.drag=null;
        this.hover=null;canvas.style.cursor="";this.draw();
      });
    }
    fit(){const rect=this.canvas.getBoundingClientRect();if(rect.width<1||rect.height<1)return;this.width=rect.width;this.height=rect.height;const ratio=Math.min(2,window.devicePixelRatio||1);this.canvas.width=Math.round(this.width*ratio);this.canvas.height=Math.round(this.height*ratio);this.ctx.setTransform(ratio,0,0,ratio,0,0);this.draw();}
    setItems(items){this.items=items.slice(0,28);this.draw();}
    project(point,radius,cx,cy){const c=Math.cos(this.angle),s=Math.sin(this.angle),x=point.x*c+point.z*s,z=point.z*c-point.x*s,scale=1+z*.12;return{x:cx+x*radius*scale,y:cy+point.y*radius*scale,z};}
    drawLens(cx, cy, radius) {
      const ctx = this.ctx;
      ctx.save();
      ctx.translate(cx, cy);
      ctx.scale(radius, radius);
      const surface = ctx.createRadialGradient(-.35, -.55, .04, 0, 0, 1);
      surface.addColorStop(0, "rgba(227, 211, 175, .16)");
      surface.addColorStop(.28, "rgba(158, 139, 98, .075)");
      surface.addColorStop(.61, "rgba(65, 57, 40, .13)");
      surface.addColorStop(.88, "rgba(26, 23, 17, .35)");
      surface.addColorStop(1, "rgba(167, 145, 103, .13)");
      ctx.beginPath();
      ctx.arc(0, 0, 1, 0, Math.PI * 2);
      ctx.fillStyle = surface;
      ctx.fill();
      const edge = ctx.createLinearGradient(-.7, -.75, .7, .75);
      edge.addColorStop(0, "rgba(235, 221, 187, .46)");
      edge.addColorStop(.35, "rgba(171, 155, 118, .07)");
      edge.addColorStop(.68, "rgba(188, 166, 131, .10)");
      edge.addColorStop(1, "rgba(240, 167, 93, .37)");
      ctx.strokeStyle = edge;
      ctx.lineWidth = 1 / radius;
      ctx.stroke();
      const reflection = ctx.createLinearGradient(-1, -.8, .26, -.8);
      reflection.addColorStop(0, "rgba(239, 222, 184, 0)");
      reflection.addColorStop(.32, "rgba(239, 222, 184, .22)");
      reflection.addColorStop(1, "rgba(239, 222, 184, 0)");
      ctx.beginPath();
      ctx.arc(0, 0, .963, Math.PI * 1.07, Math.PI * 1.58);
      ctx.strokeStyle = reflection;
      ctx.lineWidth = .017;
      ctx.stroke();
      ctx.restore();
    }
    draw(){
      const {ctx,width:w,height:h}=this;if(!ctx||w<1||h<1||!this.canvas.getClientRects().length)return;
      this.clampOffset();
      ctx.clearRect(0,0,w,h);const cx=w/2+this.offsetX,cy=h*.5+this.offsetY,radius=Math.min(w*.36,h*.32)*this.zoom;
      this.drawLens(cx, cy, radius);
      ctx.save();ctx.translate(cx,cy);ctx.rotate(-.35);ctx.strokeStyle="rgba(195,168,110,.13)";ctx.lineWidth=1;ctx.beginPath();ctx.ellipse(0,0,radius*1.22,radius*.75,0,0,Math.PI*2);ctx.stroke();ctx.strokeStyle="rgba(240,167,93,.09)";ctx.beginPath();ctx.ellipse(0,0,radius*1.32,radius*1.12,.85,0,Math.PI*2);ctx.stroke();ctx.restore();
      const points=this.points.map(point=>this.project(point,radius,cx,cy)).sort((a,b)=>a.z-b.z);
      for (const p of points) {
        const front = (p.z + 1) / 2;
        const color = front > .7 ? "232,222,183" : "174,161,124";
        ctx.fillStyle = `rgba(${color},${.08 + front * .54})`;
        ctx.beginPath();
        ctx.arc(p.x, p.y, .55 + front * .72, 0, Math.PI * 2);
        ctx.fill();
      }
      for(let i=0;i<170;i++){const a=i*2.399963+this.angle*1.4,rr=radius*.32*Math.sqrt((i+.5)/170),x=cx+Math.cos(a)*rr,y=cy+Math.sin(a)*rr*.82;ctx.fillStyle=i%7===0?"rgba(255,128,49,.82)":"rgba(225,214,133,.65)";ctx.beginPath();ctx.arc(x,y,i%11===0?1.5:.8,0,Math.PI*2);ctx.fill();}
      this.hits=[];
      this.items.forEach((item,i)=>{const theta=i*2.399963+this.angle*.15,yy=1-2*(i+.5)/Math.max(this.items.length,1),rr=Math.sqrt(Math.max(0,1-yy*yy)),p=this.project({x:Math.cos(theta)*rr,y:yy*.85,z:Math.sin(theta)*rr},radius*1.05,cx,cy);const active=this.hover?.item.id===item.id&&this.hover?.item.type===item.type;ctx.strokeStyle="rgba(241,164,90,.16)";ctx.lineWidth=.65;ctx.beginPath();ctx.moveTo(cx,cy);ctx.lineTo(p.x,p.y);ctx.stroke();const color=item.type==="incomplete"?"#bca987":item.type==="sample"?"#a39a77":item.type==="chart"?"#d2d6a2":"#ff8c47";ctx.shadowColor=color;ctx.shadowBlur=active?20:10;ctx.fillStyle=color;ctx.beginPath();ctx.arc(p.x,p.y,active?4.8:3,0,Math.PI*2);ctx.fill();ctx.shadowBlur=0;ctx.strokeStyle=active?"rgba(255,206,142,.65)":"rgba(231,194,133,.25)";ctx.beginPath();ctx.arc(p.x,p.y,active?8:6,0,Math.PI*2);ctx.stroke();this.hits.push({...p,item});});
      if(this.hover){const hit=this.hits.find(p=>p.item.id===this.hover.item.id&&p.item.type===this.hover.item.type);if(hit){const label=(hit.item.title||types[hit.item.type]).slice(0,24);ctx.font="500 12px "+getComputedStyle(this.canvas).fontFamily;const labelWidth=Math.min(w-24,ctx.measureText(label).width+20),left=Math.max(8,Math.min(w-labelWidth-8,hit.x-labelWidth/2)),top=Math.max(8,hit.y-35);ctx.fillStyle="rgba(22,18,10,.94)";ctx.fillRect(left,top,labelWidth,24);ctx.strokeStyle="rgba(183,122,64,.7)";ctx.strokeRect(left,top,labelWidth,24);ctx.fillStyle="#e8e2d2";ctx.fillText(label,left+10,top+16);}}
    }
    tick(time){if(!this.hover&&!this.drag&&!this.reduced.matches&&!document.hidden&&this.canvas.getClientRects().length&&time-this.last>34){this.angle+=.002;this.last=time;this.draw();}}
  }
  const orbs=["research-orb","brain-orb"].map(id=>$(id)).filter(Boolean).map(canvas=>new ResearchOrb(canvas));
  function animate(time){orbs.forEach(orb=>orb.tick(time));requestAnimationFrame(animate);}requestAnimationFrame(animate);
  $("brain-search")?.addEventListener("input",event=>{state.query=event.target.value.trim();render();});
  for(const button of document.querySelectorAll("[data-brain-filter]"))button.addEventListener("click",()=>{state.filter=button.dataset.brainFilter;for(const other of document.querySelectorAll("[data-brain-filter]")){const selected=other===button;other.classList.toggle("selected",selected);other.setAttribute("aria-pressed",String(selected));}render();});
  $("brain-refresh")?.addEventListener("click",refresh);document.addEventListener("hyperpass:library-refresh",refresh);
  window.HyperpassBrain={refresh};render();refresh();
})();
