import json, math, urllib.request, csv, concurrent.futures as cf, sys
d=json.load(open("data/li_road.json"))
W={e["id"]:e["geometry"] for e in d["elements"] if "geometry" in e}
# chain from the mainland end (NW) onto the island
order=[9342317, 9342139, 172993477, 172993476, 9342264]
pts=[]
for wid in order:
    g=W[wid]
    if pts and abs(g[0]['lat']-pts[-1][0])>1e-6: g=g[::-1]
    for p in g:
        if not pts or (abs(p['lat']-pts[-1][0])>1e-7 or abs(p['lon']-pts[-1][1])>1e-7):
            pts.append((p['lat'],p['lon']))
def m(a,b):
    return math.hypot((b[0]-a[0])*111320,(b[1]-a[1])*111320*math.cos(math.radians(41.9)))
# densify to ~8 m
dense=[pts[0]]; 
for i in range(len(pts)-1):
    a,b=pts[i],pts[i+1]; L=m(a,b); n=max(1,int(L//8))
    for k in range(1,n+1): dense.append((a[0]+(b[0]-a[0])*k/n, a[1]+(b[1]-a[1])*k/n))
# only the first 1100 m (mainland -> onto the island)
cum=[0]
for i in range(1,len(dense)): cum.append(cum[-1]+m(dense[i-1],dense[i]))
dense=[p for p,c in zip(dense,cum) if c<=1100]; cum=[c for c in cum if c<=1100]
print("points:",len(dense),"span m:",round(cum[-1]),file=sys.stderr)
def elev(i):
    lat,lon=dense[i]
    u=f"https://epqs.nationalmap.gov/v1/json?x={lon}&y={lat}&units=Feet&wkid=4326&includeDate=true"
    for a in range(4):
        try:
            r=json.load(urllib.request.urlopen(u,timeout=45))
            v=r.get("value")
            return i, (None if v in (None,"","-1000000") else float(v))
        except Exception:
            pass
    return i, None
res={}
with cf.ThreadPoolExecutor(max_workers=6) as ex:
    for i,v in ex.map(elev, range(len(dense))): res[i]=v
with open("data/road_profile.csv","w",newline="") as f:
    w=csv.writer(f); w.writerow(["dist_m","lat","lon","elev_ft_navd88"])
    for i,(p,c) in enumerate(zip(dense,cum)): w.writerow([round(c,1),round(p[0],6),round(p[1],6),res.get(i)])
ok=[v for v in res.values() if v is not None]
print(f"got {len(ok)}/{len(dense)} elevations", file=sys.stderr)
