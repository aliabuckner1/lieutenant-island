import json,urllib.request,urllib.parse,csv,time,sys,datetime as dt
B="https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
def get(**kw):
    kw.setdefault("station","8446613"); kw.setdefault("time_zone","lst_ldt"); kw.setdefault("units","english")
    kw.setdefault("format","json"); kw.setdefault("application","lt_island"); kw.setdefault("datum","MLLW")
    u=B+"?"+urllib.parse.urlencode(kw)
    for a in range(4):
        try:
            with urllib.request.urlopen(u,timeout=90) as r: return json.load(r)
        except Exception as e:
            if a==3: print("FAIL",kw.get("begin_date"),e,file=sys.stderr); return {}
            time.sleep(2*(a+1))
rows=[]
start=dt.date(2026,9,1)
for k in range(13):     # 13 months of 6-minute predictions
    b=(start+dt.timedelta(days=31*k)).replace(day=1)
    e=(b+dt.timedelta(days=32)).replace(day=1)-dt.timedelta(days=1)
    d=get(product="predictions",interval="6",begin_date=b.strftime("%Y%m%d"),end_date=e.strftime("%Y%m%d"))
    n=0
    for x in d.get("predictions",[]): rows.append((x["t"],float(x["v"]))); n+=1
    print(b,n,file=sys.stderr)
rows=sorted(set(rows))
with open("data/wellfleet_pred_6min.csv","w",newline="") as f:
    w=csv.writer(f); w.writerow(["t","ft_mllw"]); w.writerows(rows)
print("rows",len(rows),rows[0],rows[-1])
