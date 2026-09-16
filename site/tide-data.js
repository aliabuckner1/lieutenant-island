/* Lieutenant Island crossing — shared live data layer for the design options.
   Extracted from site/index.html (tested against the Python pipeline). */
(function(){
"use strict";
/* the road's low point, measured from the road on 2026-09-15: nine tape-measure depths through one tide, each implying
   9.83–9.97 ft (data/road_measurements.csv). It replaces 10.40 ft, which came from lidar and was only good to ±6 in. */
var ROAD=9.92, RATIO=1.05, TYP=0.58, DAYS=8, NEAR=0.5;  /* near miss = peak within 6 in of the road */
/* a closure peaking under QUIET_IN inches is a puddle at the low point rather than a crossing to avoid, so it's shown
   quietly; one lasting BRIEF_MIN minutes or less just says "briefly", since its start and end are within our timing error */
var QUIET_IN=2, BRIEF_MIN=15;
var C=[0.5221,-0.0321,-0.0272,-0.0068,-0.0006,0.0308];
var TZ="America/New_York", LAT=41.8937, LON=-70.0034;
var NOAA="https://api.tidesandcurrents.noaa.gov/api/prod/datagetter";
var MIN=60000, HOUR=3600000, DAY=86400000;
var STATES=[
 {color:"#0ca30c", lab:"Clear", cls:"clear"},
 {color:"#fab219", lab:"Shallow · under 6 in", cls:"shallow"},
 {color:"#ec835a", lab:"Deep · 6–15 in", cls:"deep"},
 {color:"#d03b3b", lab:"Impassable · 15 in +", cls:"shut"}
];
function stateFor(inches){ if(inches<=0)return STATES[0]; if(inches<=6)return STATES[1];
  if(inches<=15)return STATES[2]; return STATES[3]; }

/* ---- time ----
   Every timestamp is Wellfleet wall-clock time (America/New_York), held as a UTC millisecond
   count and read back with getUTC*, so the page works the same in any time zone. */
var ETFMT=new Intl.DateTimeFormat("en-US",{timeZone:TZ,year:"numeric",month:"2-digit",day:"2-digit",
  hour:"2-digit",minute:"2-digit",second:"2-digit",hourCycle:"h23"});
function toWall(instant){var o={};ETFMT.formatToParts(instant).forEach(function(x){o[x.type]=x.value;});
  return Date.UTC(+o.year,+o.month-1,+o.day,(+o.hour)%24,+o.minute,+o.second);}
function nowW(){return toWall(new Date());}
function parseWall(s){var a=s.split(/[-T: ]/);return Date.UTC(+a[0],+a[1]-1,+a[2],+(a[3]||0),+(a[4]||0));}
function D(ms){return new Date(ms);}
function dayStart(ms){return ms-ms%DAY;}
function minOfDay(ms){return Math.round((ms-dayStart(ms))/MIN);}
function ymd(ms){var d=D(ms);return d.getUTCFullYear()+("0"+(d.getUTCMonth()+1)).slice(-2)+("0"+d.getUTCDate()).slice(-2);}
function hourKey(ms){return Math.floor(ms/HOUR);}
function fmtT(ms){var d=D(ms),h=d.getUTCHours(),m=d.getUTCMinutes(),ap=h<12?"am":"pm";h=h%12||12;
  return h+":"+(m<10?"0":"")+m+ap;}
function fmtD(ms,opt){var o={timeZone:"UTC"};for(var k in opt)o[k]=opt[k];return D(ms).toLocaleDateString("en-US",o);}
function fmtDur(mins){var t=Math.round(mins),h=Math.floor(t/60),m=t%60;
  return ((h?h+"h ":"")+(m||!h?m+"m":"")).trim();}
function depthTxt(i){return i<1?"<1 in":Math.round(i)+" in";}
function shortBy(n){var i=(ROAD-n.lvl)*12;return i<1?"<1 in":Math.round(i)+" in";}

/* ---- fetching ---- */
function getJSON(url,timeout){
  var ctl=typeof AbortController!=="undefined"?new AbortController():null;
  var to=ctl?setTimeout(function(){ctl.abort();},timeout||20000):null;
  var opt={cache:"no-store"};if(ctl)opt.signal=ctl.signal;
  return fetch(url,opt).then(function(r){
    if(!r.ok)throw new Error("HTTP "+r.status+" from "+url.split("?")[0]);return r.json();
  }).finally(function(){if(to)clearTimeout(to);});
}
function noaa(p){
  var q={datum:"MLLW",units:"english",time_zone:"lst_ldt",format:"json",application:"lieutenant_island_crossing"};
  for(var k in p)q[k]=p[k];
  return getJSON(NOAA+"?"+new URLSearchParams(q).toString()).then(function(j){
    if(j&&j.error)throw new Error(j.error.message||"NOAA error");return j;});
}
function load(){
  var now=nowW(),d0=dayStart(now),b=ymd(d0-DAY),e=ymd(d0+(DAYS+1)*DAY);
  return Promise.allSettled([
    noaa({station:"8443970",product:"predictions",interval:"6",begin_date:b,end_date:e}),
    noaa({station:"8443970",product:"predictions",interval:"hilo",begin_date:b,end_date:e}),
    noaa({station:"8446613",product:"predictions",interval:"hilo",begin_date:b,end_date:e}),
    noaa({station:"8443970",product:"water_level",date:"recent"}),
    getJSON("https://api.weather.gov/gridpoints/BOX/111,86",25000),
    getJSON("https://api.open-meteo.com/v1/forecast?latitude="+LAT+"&longitude="+LON+
      "&hourly=pressure_msl&past_days=1&forecast_days=10&timezone=America%2FNew_York")
  ]).then(function(r){
    r.forEach(function(x,i){if(x.status==="rejected")console.warn("source "+i+" failed:",x.reason);});
    return build(r,nowW());
  });
}
function ok(x){return x.status==="fulfilled"?x.value:null;}
function tideFail(){var e=new Error("tide data unavailable");e.kind="tide";return e;}

function build(r,now){
  var bos6J=ok(r[0]),bhlJ=ok(r[1]),whlJ=ok(r[2]);
  if(!bos6J||!bhlJ||!whlJ||!bos6J.predictions||!bhlJ.predictions||!whlJ.predictions)throw tideFail();
  var d0=dayStart(now);

  /* 1. astronomical curve: Boston's 6-minute prediction, time-warped onto Wellfleet's official hi/lo */
  var bos6=bos6J.predictions.map(function(p){return {ms:parseWall(p.t),v:+p.v};});
  function ext(j){return j.predictions.map(function(p){return {ms:parseWall(p.t),v:+p.v,ty:p.type};});}
  var bhl=ext(bhlJ),whl=ext(whlJ),pairs=[];
  bhl.forEach(function(x){var best=null;
    whl.forEach(function(y){if(y.ty!==x.ty)return;var dm=Math.abs(y.ms-x.ms)/MIN;
      if(dm<=75&&(!best||dm<best.dm))best={dm:dm,y:y};});
    if(best)pairs.push([x,best.y]);});
  var warped=[],k=0;
  bos6.forEach(function(s){
    while(k+1<pairs.length&&pairs[k+1][0].ms<=s.ms)k++;
    if(k+1>=pairs.length||pairs[k][0].ms>s.ms)return;
    var b1=pairs[k][0],w1=pairs[k][1],b2=pairs[k+1][0],w2=pairs[k+1][1];
    if(b2.ms<=b1.ms||Math.abs(b2.v-b1.v)<1e-9)return;
    var f=(s.ms-b1.ms)/(b2.ms-b1.ms);
    warped.push({ms:w1.ms+f*(w2.ms-w1.ms),v:w1.v+(s.v-b1.v)*(w2.v-w1.v)/(b2.v-b1.v)});
  });
  warped.sort(function(a,c){return a.ms-c.ms;});
  function astroAt(ms){
    if(!warped.length||ms<warped[0].ms||ms>warped[warped.length-1].ms)return null;
    var lo=0,hi=warped.length-1;
    while(hi-lo>1){var mid=(lo+hi)>>1;if(warped[mid].ms<=ms)lo=mid;else hi=mid;}
    var a=warped[lo],c=warped[hi];if(c.ms===a.ms)return a.v;
    return a.v+(ms-a.ms)/(c.ms-a.ms)*(c.v-a.v);
  }

  /* 2. surge right now: Boston gauge minus Boston prediction, averaged over the last hour */
  var pm={};bos6J.predictions.forEach(function(p){pm[p.t]=+p.v;});
  var live=null,gaugeAt=null,obsJ=ok(r[3]);
  if(obsJ&&obsJ.data){
    var obs=obsJ.data.filter(function(x){return x.v!==""&&x.v!=null&&pm[x.t]!=null;})
      .map(function(x){return {ms:parseWall(x.t),r:+x.v-pm[x.t]};});
    if(obs.length&&now-obs[obs.length-1].ms<3*HOUR){
      var last=obs.slice(-10);
      live=last.reduce(function(a,c){return a+c.r;},0)/last.length;
      gaugeAt=obs[obs.length-1].ms;
    }
  }

  /* 3. forecast wind (NWS) and pressure (Open-Meteo), keyed by hour */
  var ws={},wd={},mb={},nws=ok(r[4]),om=ok(r[5]);
  function durH(s){var q=/^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?)?$/.exec(s||"");
    return q?Math.max(1,(+(q[1]||0))*24+(+(q[2]||0))+Math.ceil((+(q[3]||0))/60)):1;}
  function expand(o,mul,out){if(!o||!o.values)return;
    o.values.forEach(function(v){if(v.value==null)return;
      var p=v.validTime.split("/"),st=toWall(new Date(p[0]));
      for(var i=0,n=durH(p[1]);i<n;i++)out[hourKey(st+i*HOUR)]=v.value*mul;});}
  if(nws&&nws.properties){var pr=nws.properties,uom=(pr.windSpeed&&pr.windSpeed.uom)||"";
    expand(pr.windSpeed,/km_h/.test(uom)?0.539957:/m_s/.test(uom)?1.943844:1,ws);
    expand(pr.windDirection,1,wd);}
  if(om&&om.hourly&&om.hourly.time){om.hourly.time.forEach(function(t,i){
    var v=om.hourly.pressure_msl[i];if(v!=null)mb[hourKey(parseWall(t))]=v;});}
  /* the last hour with both wind and pressure, so tides past the end of the forecast can say so */
  function lastKey(o){var k=Object.keys(o);return k.length?Math.max.apply(null,k):-Infinity;}
  var wxEnd=Math.min(lastKey(ws),lastKey(wd),lastKey(mb));
  /* the model was fitted on the weather leading up to high tide: pressure averaged over the 6 hours up to it, wind over
     the 9 hours up to it. Averaging the forecast the same way beat using the single hour at every range 0–7 days ahead
     (scripts/backtest_weather_window.py). Hours before the forecast starts are skipped. */
  var P_HOURS=6,W_HOURS=9;
  function wxAt(ms){var h=hourKey(ms);
    if(ws[h]==null||wd[h]==null||mb[h]==null)return null;
    var p=0,np=0,u=0,v=0,s=0,nw=0;
    for(var k=0;k<W_HOURS;k++){var sk=ws[h-k],dk=wd[h-k];
      if(k<P_HOURS&&mb[h-k]!=null){p+=mb[h-k];np++;}
      if(sk!=null&&dk!=null){u-=sk*Math.sin(dk*Math.PI/180);v-=sk*Math.cos(dk*Math.PI/180);s+=sk;nw++;}}
    u/=nw;v/=nw;s/=nw;
    return {p:p/np,u:u,v:v,s:s,dir:(Math.atan2(-u,-v)*180/Math.PI+360)%360};}
  function surgeAt(ms){var w=wxAt(ms);
    if(!w)return null;
    return C[0]+C[1]*(w.p-1015)+C[2]*w.u+C[3]*w.v+C[4]*w.s*w.v+C[5]*(D(ms).getUTCFullYear()-2020);}

  /* 4. blend: the live gauge's share of the surge (g) starts at 70% now and slides to nothing 3 days out; the rest
     comes from the weather model, or a typical amount for hours the forecast doesn't cover. Chosen by replaying
     2024–26 tides against archived forecasts (scripts/backtest_fade.py) */
  var GAUGE_NOW=0.7,GAUGE_HOURS=72;
  function blendAt(t){
    var hrs=Math.max(0,(t-now)/HOUR),mod=surgeAt(t),g=live==null?0:Math.max(0,GAUGE_NOW*(1-hrs/GAUGE_HOURS));
    return {res:(g?g*live:0)+(1-g)*(mod!=null?mod:TYP),g:g,mod:mod};
  }
  /* what's behind the surge at one moment, split into pieces (feet at Wellfleet) that add up to it */
  function explain(ms){
    var b=blendAt(ms),h=hourKey(ms),w=wxAt(ms),g=b.g,m=(1-g)*RATIO,parts=[];
    if(g>0)parts.push({k:"gauge",ft:g*live*RATIO});
    if(b.mod==null)parts.push({k:"typical",ft:m*TYP});
    else{
      parts.push({k:"base",ft:m*(C[0]+C[5]*(D(ms).getUTCFullYear()-2020))});
      parts.push({k:"pressure",ft:m*C[1]*(w.p-1015)});
      parts.push({k:"wind",ft:m*(C[2]*w.u+C[3]*w.v+C[4]*w.s*w.v)});}
    return {ms:ms,surge:b.res*RATIO,g:g,model:b.mod!=null,beyond:isFinite(wxEnd)&&h>wxEnd,parts:parts,
      wind:w?w.s:null,dir:w?w.dir:null,mb:w?w.p:null,
      liveFt:live==null?null:live*RATIO,gaugeAt:gaugeAt};
  }
  var raw=[],series=[];
  for(var t=d0;t<d0+DAYS*DAY;t+=6*MIN){
    var a=astroAt(t);if(a!=null)raw.push({ms:t,astro:a,res:blendAt(t).res});
  }
  /* the weather part changes in hourly steps, and drops to the typical amount where the forecast ends; averaging it over
     an hour either side turns those steps into ramps, so a step can't split one closure into two */
  raw.forEach(function(p,i){
    var sum=0,n=0;
    for(var j=Math.max(0,i-10);j<=Math.min(raw.length-1,i+10);j++)if(Math.abs(raw[j].ms-p.ms)<=HOUR){sum+=raw[j].res;n++;}
    var res=sum/n,lvl=p.astro+res*RATIO;
    series.push({ms:p.ms,astro:p.astro,surge:res*RATIO,lvl:lvl,inch:(lvl-ROAD)*12});
  });
  if(!series.length)throw tideFail();
  var closures=[],cur=null;
  series.forEach(function(p){
    if(p.lvl>ROAD){if(!cur)cur={s:p.ms,e:p.ms,pk:p.lvl,pkMs:p.ms};else{cur.e=p.ms;if(p.lvl>cur.pk){cur.pk=p.lvl;cur.pkMs=p.ms;}}}
    else if(cur){closures.push(cur);cur=null;}});
  if(cur)closures.push(cur);
  /* near misses: at each astronomical high water, take the highest water within an hour either side;
     if it stays under the road but comes within NEAR of it, flag it */
  var near=[];
  for(var i=1;i<series.length-1;i++){
    var hp=series[i];
    if(!(hp.astro>series[i-1].astro&&hp.astro>=series[i+1].astro))continue;
    var pk=hp;
    for(var j=Math.max(0,i-10);j<=Math.min(series.length-1,i+10);j++)if(series[j].lvl>pk.lvl)pk=series[j];
    if(pk.lvl<=ROAD&&pk.lvl>ROAD-NEAR)near.push(pk);
  }
  var days={},order=[];
  series.forEach(function(p){var dk=dayStart(p.ms);if(!days[dk]){days[dk]=[];order.push(dk);}days[dk].push(p);});
  /* NOAA's official Wellfleet high waters (the tide-chart times and heights) */
  var highs=whl.filter(function(x){return x.ty==="H"&&x.ms>=d0-DAY&&x.ms<d0+DAYS*DAY;}).map(function(x){return {ms:x.ms,v:x.v};});
  return {now:now,series:series,closures:closures,near:near,highs:highs,days:days,order:order,live:live,gaugeAt:gaugeAt,explain:explain,
    windOK:Object.keys(ws).length>0,pressOK:Object.keys(mb).length>0};
}


/* ---- shared helpers for the design options ---- */
function interp(S,ms){
  if(ms<=S[0].ms)return S[0];if(ms>=S[S.length-1].ms)return S[S.length-1];
  var lo=0,hi=S.length-1;
  while(hi-lo>1){var mid=(lo+hi)>>1;if(S[mid].ms<=ms)lo=mid;else hi=mid;}
  var a=S[lo],b=S[hi],w=(ms-a.ms)/(b.ms-a.ms);
  return {ms:ms,lvl:a.lvl+w*(b.lvl-a.lvl),inch:a.inch+w*(b.inch-a.inch)};
}
function closureAt(M,ms){for(var i=0;i<M.closures.length;i++){var c=M.closures[i];if(ms>=c.s&&ms<=c.e)return c;}return null;}
/* where things stand right now: wet or dry, when that next changes, and the closure that's next */
function statusNow(M){
  var n=nowW(),S=M.series,cur=interp(S,n),wet=cur.inch>0,change=null,next=null,i;
  for(i=0;i<S.length;i++){if(S[i].ms<=n)continue;if((S[i].inch>0)!==wet){change=S[i].ms;break;}}
  /* the next closure worth naming up top: a shallow puddle at the low point isn't one */
  if(!wet)for(i=0;i<M.closures.length;i++)if(M.closures[i].s>n&&(M.closures[i].pk-ROAD)*12>=QUIET_IN){next=M.closures[i];break;}
  return {now:n,inch:cur.inch,lvl:cur.lvl,wet:wet,state:stateFor(cur.inch),change:change,
    closure:wet?closureAt(M,n):null,next:next};
}
/* the dry stretches between closures, across the whole forecast */
function openWindows(M){
  var S=M.series,out=[],cursor=S[0].ms,last=S[S.length-1].ms;
  M.closures.forEach(function(c){if(c.s>cursor)out.push({s:cursor,e:c.s});cursor=Math.max(cursor,c.e);});
  if(cursor<last)out.push({s:cursor,e:last});
  return out;
}
function dayName(k,n){var d=Math.round((dayStart(k)-dayStart(n))/DAY);
  return d===0?"Today":d===1?"Tomorrow":fmtD(k,{weekday:"long"});}
/* "12:12am tonight", "3:18pm tomorrow", "Tuesday 4:06pm" */
function whenTxt(ms,n){
  var d=Math.round((dayStart(ms)-dayStart(n))/DAY),h=D(ms).getUTCHours(),t=fmtT(ms);
  if(d===0)return t+(h>=17?" tonight":" today");
  if(d===1&&h<5)return t+" tonight";
  if(d===1)return t+" tomorrow";
  return fmtD(ms,{weekday:"long"})+" "+t;
}
function longDur(mins){var t=Math.round(mins);if(t<1440)return fmtDur(t);
  var d=Math.floor(t/1440),h=Math.round((t-d*1440)/60);if(h===24){d++;h=0;}return d+"d"+(h?" "+h+"h":"");}
function inchesOver(c){return (c.pk-ROAD)*12;}
/* four fixed parts of the day, used the same way in every design */
var SLOTS=[{n:"Overnight",s:0,sub:"12–6am"},{n:"Morning",s:6,sub:"6am–noon"},{n:"Afternoon",s:12,sub:"noon–6pm"},{n:"Evening",s:18,sub:"6pm–12am"}];
function slotOf(ms){return Math.floor(D(ms).getUTCHours()/6);}
/* "Afternoon", "Morning → afternoon", "Evening → overnight" */
function slotLabel(M,c){
  var carryIn=c.s===M.series[0].ms,a=carryIn?0:slotOf(c.s);
  if(dayStart(c.e)>dayStart(c.s))return SLOTS[a].n+" → overnight";
  var b=slotOf(c.e);return a===b?SLOTS[a].n:SLOTS[a].n+" → "+SLOTS[b].n.toLowerCase();
}
/* "1:06–3:54pm", or "11:06pm–2:12am" when the half of the day changes */
function rangeTxt(s,e){var a=fmtT(s),b=fmtT(e);
  return (a.slice(-2)===b.slice(-2)&&e-s<12*HOUR)?a.slice(0,-2)+"–"+b:a+"–"+b;}
/* what's still ahead on a given day: closures that start that day and haven't ended, plus close calls */
function upcomingForDay(M,k,n){
  var items=[];
  M.closures.forEach(function(c){if(dayStart(c.s)===k&&c.e>=n)items.push({ms:c.s,c:c});});
  M.near.forEach(function(x){if(dayStart(x.ms)===k&&x.ms>=n)items.push({ms:x.ms,x:x});});
  return items.sort(function(a,b){return a.ms-b.ms;});
}
function slotInfo(M,k,b){
  var a=k+SLOTS[b].s*HOUR,z=a+6*HOUR,over=M.closures.filter(function(c){return c.s<z&&c.e>=a;});
  return {a:a,z:z,over:over,starts:over.filter(function(c){return c.s>=a;}),
    near:M.near.filter(function(x){return x.ms>=a&&x.ms<z;}),
    worst:over.reduce(function(m,c){return Math.max(m,inchesOver(c));},0)};
}
function slotIndex(M,c){return c.s===M.series[0].ms?0:slotOf(c.s);}
/* line icons for the four parts of the day: moon, sunrise, sun, sunset. Add ?icons=off to the URL to hide them. */
var ICON_PATHS=[
  '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>',
  '<path d="M17 18a5 5 0 0 0-10 0M12 2v7M4.22 10.22l1.42 1.42M1 18h2M21 18h2M18.36 11.64l1.42-1.42M23 22H1M8 6l4-4 4 4"/>',
  '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/>',
  '<path d="M17 18a5 5 0 0 0-10 0M12 9V2M4.22 10.22l1.42 1.42M1 18h2M21 18h2M18.36 11.64l1.42-1.42M23 22H1M16 5l-4 4-4-4"/>'
];
var ICONS=!/[?&]icons=off/.test(location.search);
function slotIcon(b){return ICONS?'<svg class="ic" viewBox="0 0 24 24" aria-hidden="true">'+ICON_PATHS[b]+"</svg>":"";}
/* a quiet line of the day's high tides — tide-chart times and heights, for the boat */
function highsHTML(M,k,n){
  var hs=M.highs.filter(function(h){return dayStart(h.ms)===k&&h.ms>=n-30*MIN;});
  if(!hs.length)return "";
  return '<span class="hilab"><svg class="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M2 15c2 0 2-2 4-2s2 2 4 2 2-2 4-2 2 2 4 2 2-2 4-2M2 21c2 0 2-2 4-2s2 2 4 2 2-2 4-2 2 2 4 2 2-2 4-2M12 3v6M9 6l3-3 3 3"/></svg>'+
    "High tide"+(hs.length>1?"s":"")+"</span>"+
    hs.map(function(h){return "<span><b>"+fmtT(h.ms)+"</b> "+h.v.toFixed(1)+" ft</span>";}).join("");
}
function partOfDay(ms){var x=D(ms).getUTCHours();
  return x<5?"overnight":x<12?"morning":x<17?"afternoon":x<21?"evening":"night";}
/* a quiet one-line "right now" — planning ahead is the main job, so this stays small */
/* right now as a badge (a check when clear, waves when underwater), so it doesn't look like the depth colours */
var CHECK_IC='<svg class="ic" style="color:var(--clear)" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M8 12.5l2.7 2.7L16 9.8"/></svg>';
function wavesIc(color){return '<svg class="ic" style="color:'+color+'" viewBox="0 0 24 24" aria-hidden="true"><path d="M2 9c2 0 2-2 4-2s2 2 4 2 2-2 4-2 2 2 4 2 2-2 4-2M2 15c2 0 2-2 4-2s2 2 4 2 2-2 4-2 2 2 4 2 2-2 4-2"/></svg>';}
function statusLineHTML(M){
  var s=statusNow(M),n=s.now;
  /* name the next real closure, not the next time the water touches the low point: s.next already skips puddles */
  if(!s.wet)return '<span class="badge" style="background:var(--clear-bg)">'+CHECK_IC+'Clear right now</span>'+
    '<span>'+(s.next?"next closure "+whenTxt(s.next.s,n):"no closures this week")+"</span>";
  return '<span class="badge" style="background:var(--'+s.state.cls+'-bg)">'+wavesIc(s.state.color)+'Underwater right now</span>'+
    (s.change?"<span>reopens "+whenTxt(s.change,n)+"</span>":"");
}
function freshHTML(M,note){
  var bits=["Live · updated "+fmtT(M.now)];
  if(M.live==null)bits.push('<span class="warn">tide gauge unavailable</span>');
  var miss=[!M.windOK&&"wind",!M.pressOK&&"pressure"].filter(Boolean).join(" and ");
  if(miss)bits.push('<span class="warn">'+miss+" forecast unavailable — typical surge assumed</span>");
  if(note)bits.push('<span class="warn">'+note+"</span>");
  bits.push("depths are estimates — give yourself margin");
  return bits.join(" · ");
}
function errorHTML(err){
  return err&&err.kind==="tide"
    ?"<b>Couldn’t reach NOAA’s tide service.</b> Check your connection and reload — NOAA also drops out briefly now and then."
    :"<b>Something went wrong loading the forecast.</b> Reload to try again.";
}
/* fetch now, every 10 minutes while open, and whenever the page comes back after 5+ minutes away */
function run(o){
  var M=null,last=0,busy=false;
  function refresh(){if(busy)return;busy=true;
    load().then(function(m){M=m;last=Date.now();o.render(m);window.__crossing=m;})
      .catch(function(e){console.error(e);o.error(e,M);}).finally(function(){busy=false;});}
  refresh();
  setInterval(refresh,10*MIN);
  if(o.tick)setInterval(function(){if(M)o.tick(M);},30000);
  window.addEventListener("pageshow",function(e){if(e.persisted&&Date.now()-last>5*MIN)refresh();});
  document.addEventListener("visibilitychange",function(){if(!document.hidden&&Date.now()-last>5*MIN)refresh();});
}
window.Tides={load:load,run:run,ROAD:ROAD,NEAR:NEAR,QUIET_IN:QUIET_IN,BRIEF_MIN:BRIEF_MIN,MIN:MIN,HOUR:HOUR,DAY:DAY,STATES:STATES,stateFor:stateFor,
  nowW:nowW,parseWall:parseWall,dayStart:dayStart,minOfDay:minOfDay,fmtT:fmtT,fmtD:fmtD,fmtDur:fmtDur,longDur:longDur,
  depthTxt:depthTxt,shortBy:shortBy,interp:interp,closureAt:closureAt,statusNow:statusNow,
  openWindows:openWindows,dayName:dayName,whenTxt:whenTxt,inchesOver:inchesOver,partOfDay:partOfDay,statusLineHTML:statusLineHTML,SLOTS:SLOTS,slotOf:slotOf,slotIndex:slotIndex,slotIcon:slotIcon,highsHTML:highsHTML,slotLabel:slotLabel,rangeTxt:rangeTxt,upcomingForDay:upcomingForDay,slotInfo:slotInfo,freshHTML:freshHTML,errorHTML:errorHTML};
})();
