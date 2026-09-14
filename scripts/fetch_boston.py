import json, urllib.request, time, csv, sys
BASE="https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
def get(**kw):
    kw.setdefault("station","8443970"); kw.setdefault("time_zone","lst_ldt")
    kw.setdefault("units","english"); kw.setdefault("format","json"); kw.setdefault("application","lt_island_tides")
    url=BASE+"?"+urllib.parse.urlencode(kw)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=60) as r: return json.load(r)
        except Exception as e:
            if attempt==3: print("FAIL",kw.get("begin_date"),kw.get("product"),e,file=sys.stderr); return {}
            time.sleep(2*(attempt+1))

rows=[]
for yr in range(2005,2027):
    b,e=f"{yr}0101",f"{yr}1231"
    obs=get(product="high_low", datum="MLLW", begin_date=b, end_date=e)
    prd=get(product="predictions", datum="MLLW", interval="hilo", begin_date=b, end_date=e)
    o={}
    for d in obs.get("data",[]):
        ty=d.get("ty","").strip()
        if ty in ("HH","H "):  # observed higher-high / high
            o.setdefault(d["t"][:10],[]).append((d["t"], float(d["v"]), ty))
    p=[d for d in prd.get("predictions",[]) if d.get("type")=="H"]
    # match each predicted high to nearest observed high within 90 min
    import datetime as dt
    obs_all=sorted([(dt.datetime.strptime(t,"%Y-%m-%d %H:%M"),v) for lst in o.values() for t,v,_ in lst])
    import bisect
    times=[x[0] for x in obs_all]
    n=0
    for d in p:
        pt=dt.datetime.strptime(d["t"],"%Y-%m-%d %H:%M"); pv=float(d["v"])
        i=bisect.bisect_left(times,pt); best=None
        for j in (i-1,i,i+1):
            if 0<=j<len(obs_all):
                dm=abs((obs_all[j][0]-pt).total_seconds())/60
                if dm<=90 and (best is None or dm<best[0]): best=(dm,obs_all[j][1],obs_all[j][0])
        if best:
            rows.append({"pred_time":d["t"],"pred_ft":pv,"obs_ft":best[1],
                         "resid_ft":round(best[1]-pv,3),"lag_min":round((best[2]-pt).total_seconds()/60)})
            n+=1
    print(f"{yr}: {n} matched high tides", file=sys.stderr)

with open("/Users/aliabuckner/Apollo/lieutenant-island/data/boston_high_tides.csv","w",newline="") as f:
    w=csv.DictWriter(f,fieldnames=["pred_time","pred_ft","obs_ft","resid_ft","lag_min"]); w.writeheader(); w.writerows(rows)
print("TOTAL",len(rows))
