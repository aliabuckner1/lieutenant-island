"""Does NOAA's Gulf of Maine model (GoMOFS) forecast the Boston surge better than nothing?

GoMOFS is a physics model (ROMS) run by NOAA four times a day with a 72 h horizon; its station file includes
Boston Harbor (station index 6, 3.5 km from the tide gauge). CO-OPS's data server keeps about a month of runs,
so this scores every high tide in that window: the model's surge (its water level minus NOAA's astronomical
prediction, with the datum offset removed) against the surge the gauge actually recorded, using the 00Z run
from the day before each tide (so leads of roughly 12-36 h). Baselines: the tide chart alone, the chart plus
the site's fixed typical amount, and persistence (the surge seen at the same tide 24 h earlier).

Errors are at Boston scale in inches. Run from the project folder:
  python3 scripts/backtest_gomofs.py | tee data/backtest/gomofs.txt
"""
import urllib.request, urllib.parse, urllib.error, re, json, math, statistics, datetime as dt, sys

UA = {"User-Agent": "Mozilla/5.0 (Macintosh) AppleWebKit/537.36 Chrome/128 Safari/537.36"}
TDS = "https://opendap.co-ops.nos.noaa.gov/thredds"
API = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter?station=8443970&units=english&format=json&application=lieutenant_island"
STATION, TYP_IN = 6, 0.58*12
def get(u, t=240): return urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=t).read().decode("latin-1")
def nums(s, name):
    """values only: drop the [i][j] index labels the server prefixes on each line"""
    on = False; out = []
    for l in s.splitlines():
        if l.strip().startswith(name): on = True; continue
        if on and re.match(r"^[A-Za-z_-]", l.strip()): on = False
        if on: out += [float(x) for x in re.findall(r"-?\d+\.?\d*(?:[eE][-+]?\d+)?", re.sub(r"\[\d+\]", "", l))]
    return out

# ---- which days are on the server ----
days = []
for y_m in re.findall(r'href="(\d\d)/catalog.html"', get(f"{TDS}/catalog/NOAA/GOMOFS/MODELS/2026/catalog.html")):
    for d in re.findall(r'href="(\d\d)/catalog.html"', get(f"{TDS}/catalog/NOAA/GOMOFS/MODELS/2026/{y_m}/catalog.html")):
        days.append(dt.date(2026, int(y_m), int(d)))
days = sorted(set(days))
print(f"GoMOFS runs on the server: {days[0]} to {days[-1]} ({len(days)} days)")

# ---- NOAA: datum offset, 6-min predictions and observations over the window (GMT), in 31-day chunks ----
dat = json.loads(get("https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations/8443970/datums.json"))["datums"]
D = {x["name"]: float(x["value"]) for x in dat}; MSL = D["MSL"] - D["MLLW"]
print(f"Boston MSL is {MSL:.2f} ft above MLLW (model water level is relative to MSL)")
pred, obs = {}, {}
a = days[0]
while a <= days[-1] + dt.timedelta(days=3):
    b = min(a + dt.timedelta(days=30), days[-1] + dt.timedelta(days=3))
    span = f"&datum=MLLW&time_zone=gmt&begin_date={a:%Y%m%d}&end_date={b:%Y%m%d}"
    for p in json.loads(get(API + "&product=predictions&interval=6" + span))["predictions"]: pred[p["t"]] = float(p["v"])
    for o in json.loads(get(API + "&product=water_level" + span))["data"]:
        if o["v"]: obs[o["t"]] = float(o["v"])
    a = b + dt.timedelta(days=1)
keys = sorted(pred)
highs = [k for i, k in enumerate(keys[1:-1], 1) if pred[k] > pred[keys[i-1]] and pred[k] >= pred[keys[i+1]] and pred[k] > 7]
def resid(k): return (obs[k] - pred[k])*12 if k in obs else None

# ---- one 00Z run per day: model surge at each high tide 12-36 h after the run ----
rows = []   # (high-tide time, lead h, observed surge in, model surge in)
for d in days:
    f = f"{TDS}/dodsC/NOAA/GOMOFS/MODELS/{d:%Y/%m/%d}/gomofs.t00z.{d:%Y%m%d}.stations.forecast.nc"
    try:
        z = [v for v in nums(get(f + ".ascii?" + urllib.parse.quote(f"zeta[0:1:720][{STATION}:1:{STATION}]", safe=",:")), "zeta") if v < 1e30]
        t = [v for v in nums(get(f + ".ascii?" + urllib.parse.quote("ocean_time[0:1:720]", safe=",:")), "ocean_time") if v > 1e8]
    except Exception as e:
        print(f"   {d}: no run ({str(e)[:60]})", file=sys.stderr); continue
    series = [(dt.datetime(2016, 1, 1) + dt.timedelta(seconds=s), zv*3.28084 + MSL) for s, zv in zip(t, z)]
    run0 = dt.datetime(d.year, d.month, d.day)
    for k in highs:
        kt = dt.datetime.strptime(k, "%Y-%m-%d %H:%M"); lead = (kt - run0).total_seconds()/3600
        if not (12 <= lead <= 36) or resid(k) is None: continue
        # the model's tide runs 6-18 min ahead of NOAA's, so compare peak height to peak height, not level at a fixed time
        win = [v for ts, v in series if abs((ts - kt).total_seconds()) <= 3600]
        if len(win) < 15: continue
        rows.append((k, lead, resid(k), (max(win) - pred[k])*12))
    print(f"   {d}: {sum(1 for r in rows if r[0][:10] > str(d))} tides so far", file=sys.stderr)
print(f"\n{len(rows)} high tides scored, leads 12-36 h, {rows[0][0][:10]} to {rows[-1][0][:10]}")

def rmse(e): return math.sqrt(sum(x*x for x in e)/len(e))
o = [r[2] for r in rows]; m = [r[3] for r in rows]
bias = statistics.mean(x - y for x, y in zip(m, o))
print(f"observed surge over the window: mean {statistics.mean(o):+.1f} in, sd {statistics.pstdev(o):.1f} in")
print(f"GoMOFS surge minus observed:    mean {bias:+.1f} in  (a constant offset; removed below)")
print("\nTYPICAL ERROR AT HIGH TIDE (RMSE, inches)")
print(f"   tide chart alone                       {rmse(o):.2f}")
print(f"   chart + fixed typical amount ({TYP_IN:.0f} in)   {rmse([x - TYP_IN for x in o]):.2f}")
print(f"   chart + this window's own mean        {rmse([x - statistics.mean(o) for x in o]):.2f}   (unfair: uses hindsight)")
# high tides drift ~50 min a day, so "the same tide yesterday" is the nearest high to 24 h 50 min earlier
prev, HT = {}, {h: dt.datetime.strptime(h, "%Y-%m-%d %H:%M") for h in highs}
for k in highs:
    target = HT[k] - dt.timedelta(hours=24, minutes=50)
    cands = [h for h in highs if abs((HT[h] - target).total_seconds()) <= 7200 and resid(h) is not None]
    prev[k] = resid(min(cands, key=lambda h: abs((HT[h] - target).total_seconds()))) if cands else None
pe = [r[2] - prev[r[0]] for r in rows if prev.get(r[0]) is not None]
print(f"   persistence (same tide 24 h earlier)   {rmse(pe):.2f}   (n={len(pe)})")
print(f"   GoMOFS, offset removed                 {rmse([y - x + bias for x, y in zip(m, o)]):.2f}")
mo, mm = statistics.mean(o), statistics.mean(m)
corr = sum((a-mo)*(b-mm) for a, b in zip(o, m)) / math.sqrt(sum((a-mo)**2 for a in o) * sum((b-mm)**2 for b in m))
print(f"\ncorrelation between GoMOFS surge and observed surge, tide to tide: {corr:.2f}")
big = [(r, ) for r in rows if abs(r[2]) >= 6]
if big: print(f"tides with |observed surge| >= 6 in (n={len(big)}): GoMOFS error {rmse([r[2] - r[3] + bias for (r,) in big]):.2f} vs chart+typical {rmse([r[2] - TYP_IN for (r,) in big]):.2f}")
