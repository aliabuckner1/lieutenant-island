import json,urllib.request,urllib.parse,csv,datetime as dt,bisect,math,statistics as st,sys

ROAD_FT_MLLW = 9.92           # measured from the road 2026-09-15 (data/road_measurements.csv); lidar had said 10.40
ROAD_UNCERT  = 0.50
RATIO        = 1.05           # Wellfleet / Boston height ratio (NOAA subordinate offset)
# surge model: resid_ft = c0 + c1*(mb-1015) + c2*u + c3*v + c4*spd*v + c5*(yr-2020)
C = [0.5221, -0.0321, -0.0272, -0.0068, -0.0006, 0.0308]
UA = {"User-Agent":"lieutenant-island-tides (https://github.com/aliabuckner1/lieutenant-island)"}
def j(url, hdr=None):
    r=urllib.request.Request(url, headers=hdr or {})
    for a in range(4):
        try:
            with urllib.request.urlopen(r,timeout=90) as f: return json.load(f)
        except Exception as e:
            if a==3: print("FAIL",url[:90],e,file=sys.stderr); return {}
            import time; time.sleep(2*(a+1))
P=lambda s: dt.datetime.strptime(s,"%Y-%m-%d %H:%M")
now=dt.datetime.now()

# ---------- 1. astronomical curve (precomputed, verified to 0.002 ft) ----------
curve=[(P(r["t"]),float(r["ft_mllw"])) for r in csv.DictReader(open("data/wellfleet_curve_6min.csv"))]
day0=now.replace(hour=0,minute=0,second=0,microsecond=0)
curve=[c for c in curve if c[0]>=day0]
ct=[c[0] for c in curve]
print("curve pts:",len(curve),curve[0][0],"->",curve[-1][0],file=sys.stderr)

# ---------- 2. live residual at Boston (obs - pred, right now) ----------
B="https://api.tidesandcurrents.noaa.gov/api/prod/datagetter?"
q=dict(station="8443970",datum="MLLW",units="english",time_zone="lst_ldt",format="json",application="lt_island")
obs=j(B+urllib.parse.urlencode({**q,"product":"water_level","date":"latest"}))
prd=j(B+urllib.parse.urlencode({**q,"product":"predictions","date":"latest"}))
pm={x["t"]:float(x["v"]) for x in prd.get("predictions",[])}
live=[(P(x["t"]),float(x["v"])-pm[x["t"]]) for x in obs.get("data",[]) if x["t"] in pm and x["v"]]
live_resid = st.mean([v for _,v in live[-10:]]) if live else None
print("live Boston residual:",round(live_resid,3) if live_resid is not None else None,file=sys.stderr)

# ---------- 3. forecast wind (NWS) + pressure (Open-Meteo) ----------
def nws_series(key):
    g=j("https://api.weather.gov/gridpoints/BOX/111,86", UA).get("properties",{}).get(key)
    out=[]
    if not g: return out
    for v in g["values"]:
        t0,dur=v["validTime"].split("/")
        t0=dt.datetime.fromisoformat(t0).astimezone().replace(tzinfo=None)
        h=1
        m=dur.replace("P","").replace("T","")
        if "D" in m: h=int(m.split("D")[0])*24
        elif "H" in m: h=int(m.split("H")[0])
        for k in range(max(h,1)): out.append((t0+dt.timedelta(hours=k), v["value"]))
    return out
ws={t:v*0.539957 for t,v in nws_series("windSpeed") if v is not None}      # km/h -> kt
wd={t:v for t,v in nws_series("windDirection") if v is not None}
om=j("https://api.open-meteo.com/v1/forecast?latitude=41.8937&longitude=-70.0034"
     "&hourly=surface_pressure,pressure_msl&forecast_days=8&timezone=America%2FNew_York")
mb={}
for t,v in zip(om.get("hourly",{}).get("time",[]), om.get("hourly",{}).get("pressure_msl",[])):
    if v is not None: mb[dt.datetime.fromisoformat(t)]=v
print(f"forecast: wind {len(ws)}h, dir {len(wd)}h, pressure {len(mb)}h",file=sys.stderr)

def surge_at(t):
    """modelled residual (ft, Boston) at time t"""
    hh=t.replace(minute=0,second=0,microsecond=0)
    s=ws.get(hh); d=wd.get(hh); p=mb.get(hh)
    if s is None or d is None or p is None: return None
    u=-s*math.sin(math.radians(d)); v=-s*math.cos(math.radians(d))
    return C[0]+C[1]*(p-1015)+C[2]*u+C[3]*v+C[4]*s*v+C[5]*(t.year-2020)

# blend: live residual dominates for the first 6 h, model takes over after 18 h
def resid_at(t):
    m=surge_at(t)
    hrs=(t-now).total_seconds()/3600
    if live_resid is None: return m if m is not None else 0.58
    if m is None: return live_resid if hrs<12 else 0.58
    if hrs<=6: w=1.0
    elif hrs>=18: w=0.0
    else: w=(18-hrs)/12
    return w*live_resid+(1-w)*m

# ---------- 4. build the water-level series & closure windows ----------
FCAST_DAYS=8
series=[]
for t,h in curve:
    if t>=day0+dt.timedelta(days=FCAST_DAYS): break
    r=resid_at(t)
    series.append({"t":t.strftime("%Y-%m-%dT%H:%M"),
                   "astro":round(h,2), "lvl":round(h+r*RATIO,2), "surge":round(r*RATIO,2)})
def find_windows(pts,key,thr):
    out=[];cur=None
    for p in pts:
        wet=p[key]>thr
        if wet and cur is None: cur={"start":p["t"],"end":p["t"],"peak":p[key]}
        elif wet: cur["end"]=p["t"]; cur["peak"]=max(cur["peak"],p[key])
        elif cur: out.append(cur); cur=None
    if cur: out.append(cur)
    for w in out: w["peak"]=round(w["peak"],2); w["over_in"]=round((w["peak"]-thr)*12)
    return out
closures=find_windows(series,"lvl",ROAD_FT_MLLW)

# 12-month astronomical outlook (typical surge baked in, for planning only)
TYP=0.62
long=[]
cur=None
for t,h in curve:
    if t>now+dt.timedelta(days=370): break
    lv=h+TYP
    if lv>ROAD_FT_MLLW:
        if cur is None: cur={"start":t,"end":t,"peak":lv}
        else: cur["end"]=t; cur["peak"]=max(cur["peak"],lv)
    elif cur:
        long.append({"start":cur["start"].strftime("%Y-%m-%dT%H:%M"),"end":cur["end"].strftime("%Y-%m-%dT%H:%M"),
                     "peak":round(cur["peak"],2),"over_in":round((cur["peak"]-ROAD_FT_MLLW)*12)}); cur=None
payload={
 "generated": now.strftime("%Y-%m-%dT%H:%M"),
 "road_ft_mllw": ROAD_FT_MLLW, "road_uncert_ft": ROAD_UNCERT,
 "live_resid_boston_ft": round(live_resid,2) if live_resid is not None else None,
 "forecast_days": FCAST_DAYS,
 "series": series, "closures": closures, "outlook": long,
 "model": {"r2":0.576,"sd_ft":0.311,"coefs":C,"ratio":RATIO},
}
json.dump(payload,open("data/payload.json","w"))
print(f"\nseries {len(series)} pts | closures next {FCAST_DAYS}d: {len(closures)} | 12-mo outlook: {len(long)}")
for c in closures[:8]:
    a,b=P(c['start'].replace('T',' ')),P(c['end'].replace('T',' '))
    print(f"  {a:%a %b %d  %H:%M}-{b:%H:%M}  ({(b-a).seconds//60+6:3d} min)  peak {c['peak']:.2f} ft = {c['over_in']:2d} in over road")
