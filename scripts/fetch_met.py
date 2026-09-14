import json,urllib.request,urllib.parse,csv,time,sys
BASE="https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
def get(**kw):
    kw.setdefault("station","8443970"); kw.setdefault("time_zone","lst_ldt")
    kw.setdefault("units","english"); kw.setdefault("format","json"); kw.setdefault("application","lt_island")
    u=BASE+"?"+urllib.parse.urlencode(kw)
    for a in range(4):
        try:
            with urllib.request.urlopen(u,timeout=90) as r: return json.load(r)
        except Exception as e:
            if a==3: print("FAIL",kw,e,file=sys.stderr); return {}
            time.sleep(2*(a+1))
out={}
for yr in range(2015,2027):
    for mth in range(1,13):
        b=f"{yr}{mth:02d}01"
        e=f"{yr}{mth:02d}31" if mth in (1,3,5,7,8,10,12) else (f"{yr}{mth:02d}30" if mth!=2 else f"{yr}0228")
        if yr==2026 and mth>9: break
        w=get(product="wind",begin_date=b,end_date=e)
        p=get(product="air_pressure",begin_date=b,end_date=e)
        for d in w.get("data",[]):
            out.setdefault(d["t"],{}).update({"ws":d.get("s"),"wdir":d.get("d")})
        for d in p.get("data",[]):
            out.setdefault(d["t"],{})["mb"]=d.get("v")
    print(yr,len(out),file=sys.stderr)
with open("data/boston_met.csv","w",newline="") as f:
    w=csv.writer(f); w.writerow(["t","wind_kt","wind_dir_deg","pressure_mb"])
    for t in sorted(out):
        r=out[t]; w.writerow([t,r.get("ws"),r.get("wdir"),r.get("mb")])
print("rows",len(out))
