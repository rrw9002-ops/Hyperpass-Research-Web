"use strict";
(() => {
  const colors = {
    orange:"#ff9800", yellow:"#fdd835", red:"#f23645", green:"#4caf50", lime:"#00e676",
    teal:"#00897b", aqua:"#00bcd4", blue:"#2962ff", navy:"#311b92", purple:"#9c27b0",
    fuchsia:"#e040fb", maroon:"#880e4f", olive:"#808000", silver:"#b2b5be", gray:"#787b86",
    black:"#363a45", white:"#ffffff"
  };
  const defaultColors = ["#ffad62", "#85d8c2", "#c2adeb", "#90bdf5"];
  const priceFields = ["open", "high", "low", "close", "hl2", "hlc3", "ohlc4"];
  const methods = ["sma", "ema", "highest", "lowest"];
  const pivotCode = `//@version=6
indicator("Hyperpass · 1Y Pivot Highs", overlay = true, max_lines_count = 500)
pivotBars = input.int(5, "고점 좌우 확인 봉", minval = 1, maxval = 100)
lookbackDays = input.int(365, "조회 일수", minval = 1, maxval = 3650)
lineColor = input.color(color.orange, "추세선 색")
cutoff = last_bar_time - lookbackDays * 86400000
highPoint = ta.pivothigh(high, pivotBars, pivotBars)
pivotTime = time[pivotBars]
var int previousTime = na
var float previousHigh = na

if barstate.isconfirmed and not na(highPoint) and pivotTime >= cutoff
    if not na(previousTime) and previousTime >= cutoff
        line.new(previousTime, previousHigh, pivotTime, highPoint, xloc = xloc.bar_time, color = lineColor, width = 2)
    previousTime := pivotTime
    previousHigh := highPoint

if barstate.islast
    for segment in line.all
        if line.get_x1(segment) < cutoff
            line.delete(segment)
`;
  const pivotName = "최근 1년 고점 추세선";

  function colorValue(value) {
    if (/^#[0-9a-f]{6}(?:[0-9a-f]{2})?$/i.test(value)) return value;
    if (/^color\.[a-z]+$/.test(value) && Object.hasOwn(colors, value.slice(6))) return colors[value.slice(6)];
    throw Error("색을 color.orange 같은 기본 색 또는 6자리 HEX로 지정하세요.");
  }
  function cleanLine(line) {
    return line.replace(/"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|\/\/.*/g, part => part.startsWith("//") ? "" : part).trimEnd();
  }
  function integer(value, min, max) {
    if (!Number.isInteger(value) || value < min || value > max) throw Error(min + "에서 " + max + " 사이의 정수를 입력하세요.");
    return value;
  }
  function literalString(value) {
    if (/^"(?:\\.|[^"\\])*"$|^'(?:\\.|[^'\\])*'$/.test(value)) return value.slice(1,-1).replace(/\\(["'\\])/g,"$1");
    throw Error("제목을 따옴표로 묶어 주세요.");
  }

  // Recognize only the supplied drawing program, including its control-flow indentation.
  // Never infer what different Pine code would draw from its name or a matching keyword.
  function readPivot(source) {
    const reference = pivotCode.split("\n").map(cleanLine).filter(line => line.trim());
    const lines = source.split("\n").map(cleanLine).filter(line => line.trim());
    if (lines.length !== reference.length) return null;
    const edits = [
      [1, /pivotBars = input.int\((\d+),/, "5"],
      [2, /lookbackDays = input.int\((\d+),/, "365"],
      [3, /lineColor = input.color\((color\.[a-z]+|#[0-9a-fA-F]{6}),/, "color.orange"]
    ];
    const values = [];
    for (const [index, pattern, original] of edits) {
      const match = lines[index].match(pattern);
      if (!match) return null;
      values.push(match[1]);
      lines[index] = lines[index].replace(pattern, text => text.replace(match[1], original));
    }
    if (lines.some((line,index) => line !== reference[index])) return null;
    return {type:"pivot", title:pivotName, radius:integer(Number(values[0]),1,100),
      days:integer(Number(values[1]),1,3650), color:colorValue(values[2])};
  }

  // Split a function's arguments at top-level commas, retaining nested indicator calls and quoted titles.
  function parseCall(text) {
    const matched = /^([A-Za-z_][\w.]*)\((.*)\)$/.exec(text);
    if (!matched) throw Error("이 함수나 수식은 앱 안에서 계산할 수 없습니다.");
    const args = [], named = new Map();
    const value = matched[2];
    let depth=0, start=0, quote="";
    for (let i=0; i<=value.length; i++) {
      const char=value[i];
      if (quote) {
        if (char === "\\") i++;
        else if (char === quote) quote="";
      } else if (char === '"' || char === "'") quote=char;
      else if (char === "(") depth++;
      else if (char === ")") depth--;
      else if ((!depth && char === ",") || i === value.length) {
        const part=value.slice(start,i).trim(), key=/^([a-z_]\w*)\s*=\s*(.+)$/.exec(part);
        if (!part) throw Error("함수 인수를 확인하세요.");
        if (key) {
          if (named.has(key[1])) throw Error("중복된 함수 옵션입니다.");
          named.set(key[1],key[2]);
        } else {
          if (named.size) throw Error("이름이 있는 인수 뒤에 위치 인수를 쓸 수 없습니다.");
          args.push(part);
        }
        start=i+1;
      }
      if (depth<0 || depth>10) throw Error("함수 중첩 범위를 확인하세요.");
    }
    if (depth || quote) throw Error("괄호와 따옴표가 닫혔는지 확인하세요.");
    return {name:matched[1],args,named};
  }
  function options(call, keys) {
    if (call.args.length > keys.length) throw Error("앱 차트에서 지원하지 않는 추가 인수가 있습니다.");
    const values = new Map(call.args.map((arg,i) => [keys[i],arg]));
    for (const [key,value] of call.named) {
      if (!keys.includes(key) || values.has(key)) throw Error("지원하지 않거나 중복된 옵션입니다 · " + key);
      values.set(key,value);
    }
    return values;
  }

  function compile(source) {
    if (typeof source !== "string" || !source.trim() || source.length > 64000) throw Error("64 KB 이내의 Pine 지표 코드를 입력하세요.");
    const pivot = readPivot(source.replace(/\r\n?/g,"\n"));
    if (pivot) return pivot;
    const fields = new Map(priceFields.map(field=>[field,{field}]));
    const periods = new Map(), plots = [];
    let title="", expressions=0;
    function length(value) {
      return integer(periods.has(value) ? periods.get(value) : /^\d+$/.test(value) ? Number(value) : NaN,1,2000);
    }
    function expression(value) {
      if (++expressions>80) throw Error("앱 차트에서는 한 지표에 80개 이하의 계산식을 사용할 수 있습니다.");
      if (fields.has(value)) return fields.get(value);
      const call = parseCall(value);
      if (!call.name.startsWith("ta.") || !methods.includes(call.name.slice(3))) throw Error("앱 차트에서 지원하지 않는 수식입니다 · "+call.name);
      const params=options(call,["source","length"]);
      return {method:call.name.slice(3), input:expression(params.get("source")), length:length(params.get("length"))};
    }
    for (const [index,raw] of source.split(/\r?\n/).entries()) {
      const line=cleanLine(raw);
      if (!line.trim()) continue;
      try {
        if (line!==line.trimStart()) throw Error("조건문과 반복문은 Desktop에서 실행하세요.");
        if (line.startsWith("indicator(")) {
          if (title) throw Error("indicator()는 한 번만 선언하세요.");
          const decl=options(parseCall(line),["title","shorttitle","overlay"]);
          title=literalString(decl.get("title"));
          if (decl.has("shorttitle")) literalString(decl.get("shorttitle"));
          if (decl.get("overlay")!=="true") throw Error("현재 종목의 가격 축에 표시하려면 overlay=true가 필요합니다.");
        } else if (line.startsWith("plot(")) {
          if (plots.length >= 4) throw Error("가격 차트에는 한 지표당 선 4개까지 표시할 수 있습니다.");
          const params=options(parseCall(line),["series","title","color","linewidth"]);
          plots.push({input:expression(params.get("series")),
            label:params.has("title")?literalString(params.get("title")):params.get("series"),
            color:params.has("color")?colorValue(params.get("color")):defaultColors[plots.length],
            width:params.has("linewidth")?integer(Number(params.get("linewidth")),1,4):2});
        } else {
          const assigned=/^(?:(?:int|float)\s+)?([A-Za-z_]\w*)\s*=\s*(.+)$/.exec(line);
          if (!assigned) throw Error("앱 차트에서 지원하지 않는 명령입니다.");
          const [,name,rhs]=assigned;
          if (fields.has(name) || periods.has(name)) throw Error("이미 선언한 변수입니다 · "+name);
          if (rhs.startsWith("input.int(")) {
            const params=options(parseCall(rhs),["defval","title","minval","maxval","step"]);
            if (params.has("title")) literalString(params.get("title"));
            const len=length(params.get("defval"));
            for (const key of ["minval","maxval","step"]) if (params.has(key) && !/^-?\d+$/.test(params.get(key))) throw Error("기간 옵션에는 정수를 사용하세요.");
            if (len<Number(params.get("minval")??1) || len>Number(params.get("maxval")??2000) || Number(params.get("step")??1)<1) throw Error("기본 기간과 입력 범위를 확인하세요.");
            periods.set(name,len);
          } else if (/^\d+$/.test(rhs)) periods.set(name,length(rhs));
          else fields.set(name,expression(rhs));
        }
      } catch(error) { throw Error((index+1)+"행 · "+error.message); }
    }
    if (!title || !plots.length) throw Error("overlay=true인 indicator()와 plot()이 필요합니다.");
    return {type:"plots",title,plots};
  }

  function fieldValue(bar, field) {
    if (field==="hl2") return (bar.high+bar.low)/2;
    if (field==="hlc3") return (bar.high+bar.low+bar.close)/3;
    if (field==="ohlc4") return (bar.open+bar.high+bar.low+bar.close)/4;
    return bar[field];
  }
  function rolling(input, method, period) {
    const out=Array(input.length).fill(null);
    let sum=0, average=null, seen=0;
    const deque=[];
    let front=0;
    for (let i=0;i<input.length;i++) {
      const value=input[i];
      if (!Number.isFinite(value)) continue;
      seen++;
      if (method==="ema") {
        average=average===null?value:average+(value-average)*2/(period+1); out[i]=average;
      } else if (method==="sma") {
        sum+=value;
        if (i>=period && Number.isFinite(input[i-period])) sum-=input[i-period];
        if (seen>=period) out[i]=sum/period;
      } else {
        while (front<deque.length && deque[front]<=i-period) front++;
        while (front<deque.length && (method==="highest" ? input[deque.at(-1)]<=value : input[deque.at(-1)]>=value)) deque.pop();
        deque.push(i);
        if (seen>=period) out[i]=input[deque[front]];
      }
    }
    return out;
  }
  function timeframeSeconds(timeframe) {
    if (/^\d+$/.test(timeframe)) return Number(timeframe)*60;
    if (/^(?:1)?(?:D|d)$/.test(timeframe)) return 25*3600;
    if (/^(?:1)?(?:W|wk)$/.test(timeframe)) return 8*86400;
    if (/^(?:1)?(?:M|mo)$/.test(timeframe)) return 32*86400;
    return Infinity;
  }
  function calculate(plan, bars, timeframe, nowSeconds=Date.now()/1000) {
    if (!bars.length) throw Error("표시할 가격 봉이 없습니다.");
    if (plan.type==="plots") {
      const cache=new Map();
      function values(spec) {
        if (!cache.has(spec)) cache.set(spec, spec.field ? bars.map(b=>fieldValue(b,spec.field)) : rolling(values(spec.input),spec.method,spec.length));
        return cache.get(spec);
      }
      const lines=plan.plots.map(plot=>({...plot, values:values(plot.input)}));
      return {lines, points:[], message:lines.map(line=>line.label).join(" · ")+(lines.every(line=>line.values.every(v=>!Number.isFinite(v)))?" · 계산에 필요한 봉이 부족합니다.":"")};
    }
    const {radius,days,color}=plan, last=bars.at(-1).time, cutoff=last-days*86400;
    const points=[], values=Array(bars.length).fill(null);
    // Providers do not supply barstate.isconfirmed. A later observed bar proves closure;
    // a recent last bar is conservatively omitted as a confirmation bar until the next refresh.
    const lastConfirmed=last+timeframeSeconds(timeframe)<=nowSeconds?bars.length-1:bars.length-2;
    for (let i=radius;i+radius<=lastConfirmed;i++) {
      if (bars[i].time<cutoff) continue;
      const high=bars[i].high;
      let pivot=true;
      // A plateau belongs to the rightmost tied high, matching Pine's pivot ordering.
      for (let step=1;step<=radius;step++) if (bars[i-step].high>high || bars[i+step].high>=high) {pivot=false;break;}
      if (!pivot) continue;
      points.push({index:i,high,confirmedAt:i+radius});
    }
    const displayed=points.slice(-501);
    displayed.forEach((point,index)=>{
      const previous=displayed[index-1];
      values[point.index]=point.high;
      if(previous) for(let j=previous.index+1;j<point.index;j++) values[j]=previous.high+(point.high-previous.high)*(j-previous.index)/(point.index-previous.index);
    });
    let message="최근 "+days+"일 · 확인 고점 "+points.length+"개 · 연결선 "+Math.max(0,displayed.length-1)+"개 · "+radius+"봉 뒤 확정된 고점을 사후 연결";
    if (points.length<2) message+=" · 선을 그릴 고점이 아직 두 개 미만입니다.";
    else message+=" · 고점에 마우스를 올리면 확정 봉을 확인할 수 있습니다.";
    if (bars[0].time>cutoff) message+=" · 조회한 이력만 사용";
    return {lines:[{label:"고점 사후 연결값",values,color,width:2}],points:displayed,message};
  }
  window.HyperpassLocalIndicators=Object.freeze({compile,calculate,example:{name:pivotName,code:pivotCode}});
})();
