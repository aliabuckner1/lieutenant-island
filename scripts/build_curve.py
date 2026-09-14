import json,urllib.request,urllib.parse,csv,time,sys,datetime as dt,bisect
B="https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
def get(**kw):
    kw.setdefault("time_zone","lst_ldt"); kw.setdefault("units","english"); kw.setdefault("format","json")
    kw.setdefault("application","lt_island"); kw.setdefault("datum","MLLW")
    u=B+"?"+urllib.parse.urlencode(kw)
    for a in range(5):
        try:
            with urllib.request.urlopen(u,timeout=120) as r: return json.load(r)
        except Exception as e:
            if a==4: print("FAIL",kw.get("begin_date"),kw.get("station"),e,file=sys.stderr); return {}
            time.sleep(3*(a+1))
P=lambda s: dt.datetime.strptime(s,"%Y-%m-%d %H:%M")
start=dt.date(2026,9,1)
months=[]
for k in range(14):
    b=(start.replace(day=1)+dt.timedelta(days=31*k)).replace(day=1)
    months.append((b,(b+dt.timedelta(days=32)).replace(day=1)-dt.timedelta(days=1)))
bos6=[]; boshl=[]; welhl=[]
for b,e in months:
    bb,ee=b.strftime("%Y%m%d"),e.strftime("%Y%m%d")
    d=get(product="predictions",station="8443970",interval="6",begin_date=bb,end_date=ee)
    bos6+= [(P(x["t"]),float(x["v"])) for x in d.get("predictions",[])]
    d=get(product="predictions",station="8443970",interval="hilo",begin_date=bb,end_date=ee)
    boshl+=[(P(x["t"]),float(x["v"]),x["type"]) for x in d.get("predictions",[])]
    d=get(product="predictions",station="8446613",interval="hilo",begin_date=bb,end_date=ee)
    welhl+=[(P(x["t"]),float(x["v"]),x["type"]) for x in d.get("predictions",[])]
    print(b,len(bos6),len(boshl),len(welhl),file=sys.stderr)
bos6=sorted(set(bos6)); boshl=sorted(set(boshl)); welhl=sorted(set(welhl))
# align extremum series by NEAREST TIME + matching type (robust across year boundaries)
wl_by_type={"H":[],"L":[]}
for t,h,ty in welhl: wl_by_type[ty].append((t,h))
for k in wl_by_type: wl_by_type[k].sort()
pairs=[]
for tb,hb,ty in boshl:
    lst=wl_by_type[ty]; tt=[x[0] for x in lst]
    i=bisect.bisect_left(tt, tb)
    best=None
    for j in (i-1,i,i+1):
        if 0<=j<len(lst):
            dm=abs((lst[j][0]-tb).total_seconds())/60
            if dm<=75 and (best is None or dm<best[0]): best=(dm,lst[j])
    if best: pairs.append(((tb,hb,ty),(best[1][0],best[1][1],ty)))
print("aligned extrema:",len(pairs),"of",len(boshl),file=sys.stderr)
bt=[p[0][0] for p in pairs]
out=[]
for t,h in bos6:
    i=bisect.bisect_right(bt,t)-1
    if i<0 or i+1>=len(pairs): continue
    (tb1,hb1,_),(tw1,hw1,_)=pairs[i]; (tb2,hb2,_),(tw2,hw2,_)=pairs[i+1]
    if tb2<=tb1 or abs(hb2-hb1)<1e-9: continue
    f=(t-tb1).total_seconds()/(tb2-tb1).total_seconds()
    tw=tw1+dt.timedelta(seconds=f*(tw2-tw1).total_seconds())
    hw=hw1+(h-hb1)*(hw2-hw1)/(hb2-hb1)
    out.append((tw,hw))
out.sort()
# resample to a clean 6-min grid
g0=out[0][0].replace(second=0,microsecond=0); g0-=dt.timedelta(minutes=g0.minute%6)
grid=[]; ts=[x[0] for x in out]
t=g0
while t<=out[-1][0]:
    j=bisect.bisect_left(ts,t)
    if j==0: v=out[0][1]
    elif j>=len(out): v=out[-1][1]
    else:
        a,b_=out[j-1],out[j]
        w=(t-a[0]).total_seconds()/max((b_[0]-a[0]).total_seconds(),1)
        v=a[1]+w*(b_[1]-a[1])
    grid.append((t.strftime("%Y-%m-%d %H:%M"),round(v,3))); t+=dt.timedelta(minutes=6)
with open("data/wellfleet_curve_6min.csv","w",newline="") as f:
    w=csv.writer(f); w.writerow(["t","ft_mllw"]); w.writerows(grid)
print("grid rows",len(grid),grid[0],grid[-1])
# verify against official Wellfleet hi/lo
gm={k:v for k,v in grid}
err=[]
for tw,hw,ty in welhl:
    k=tw.replace(minute=tw.minute-tw.minute%6).strftime("%Y-%m-%d %H:%M")
    if k in gm: err.append(abs(gm[k]-hw))
if err:
    err.sort(); print(f"VERIFY vs official Wellfleet hi/lo: n={len(err)} mean|err|={sum(err)/len(err):.3f} ft  p95={err[int(.95*len(err))]:.3f} ft  max={err[-1]:.3f} ft")
