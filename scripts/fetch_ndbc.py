import urllib.request,gzip,io,csv,sys
rows=[]
for yr in range(2015,2026):
    u=f"https://www.ndbc.noaa.gov/view_text_file.php?filename=44013h{yr}.txt.gz&dir=data/historical/stdmet/"
    try:
        raw=urllib.request.urlopen(u,timeout=120).read()
        txt=raw.decode("utf-8","ignore")
        n=0
        for line in txt.splitlines():
            if line.startswith("#"): continue
            f=line.split()
            if len(f)<8: continue
            try:
                Y,M,D,h,m=int(f[0]),int(f[1]),int(f[2]),int(f[3]),int(f[4])
                wd,ws=float(f[5]),float(f[6])
            except: continue
            if wd>=999 or ws>=99: continue
            rows.append([f"{Y}-{M:02d}-{D:02d} {h:02d}:{m:02d}",wd,round(ws*1.94384,1)])  # m/s -> kt
            n+=1
        print(yr,n,file=sys.stderr)
    except Exception as e: print(yr,"FAIL",e,file=sys.stderr)
with open("data/ndbc_44013_wind.csv","w",newline="") as f:
    w=csv.writer(f); w.writerow(["t_utc","wind_dir_deg","wind_kt"]); w.writerows(rows)
print("total",len(rows))
