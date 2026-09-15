"""Backtest: should the site average the wind and pressure forecast over the hours before high tide?

The surge model was fitted on weather averaged over the hours leading up to each high tide (pressure over the 6 hours
up to it, wind over the 9 hours up to it; the rows saved in data/model.pkl reproduce those windows), but the site
plugs in the forecast for the single hour of the tide. This replays the same 2024-26 tides as backtest_fade.py both
ways, using the forecasts that were available 0-7 days ahead, and scores them against the gauge. Nothing is refitted,
and every way is scored on the same tides.

Inputs (data/): boston_high_tides.csv, boston_met.csv, ndbc_44013_wind.csv, backtest/openmeteo_prev_runs_{2024,2025,2026}.json
Errors are at Boston scale in inches (Wellfleet is x1.05, which doesn't change any ranking).
Run from the project folder:  python3 scripts/backtest_weather_window.py | tee data/backtest/weather_window.txt
"""
import csv, json, math, pathlib, datetime as dt
from zoneinfo import ZoneInfo

D = pathlib.Path(__file__).resolve().parent.parent/'data'
C = [0.5221, -0.0321, -0.0272, -0.0068, -0.0006, 0.0308]   # the site's surge model
RATIO, ROAD = 1.05, 10.40
HOUR = dt.timedelta(hours=1)
def P(s): return dt.datetime.strptime(s[:16].replace('T', ' '), '%Y-%m-%d %H:%M')
def rmse(e): return 12*math.sqrt(sum(x*x for x in e)/len(e))

def surge(p, u, v, s, year):
    """the site's surge model, ft at Boston"""
    return C[0] + C[1]*(p-1015) + C[2]*u + C[3]*v + C[4]*s*v + C[5]*(year-2020)

# ways to read the weather for a tide: (label, hours of pressure, hours of wind), each counted back from the tide's hour
WAYS = [('tide hour', 1, 1), ('3h/3h', 3, 3), ('6h/9h', 6, 9)]

def reading(get_p, get_w, h, n_p, n_w):
    """mean pressure over the n_p hours up to h, and mean wind (u, v, speed) over the n_w hours up to h"""
    ps = [get_p(h - k*HOUR) for k in range(n_p)]
    ws = [get_w(h - k*HOUR) for k in range(n_w)]
    if None in ps or None in ws: return None
    u = sum(-s*math.sin(math.radians(d)) for s, d in ws)/n_w
    v = sum(-s*math.cos(math.radians(d)) for s, d in ws)/n_w
    return sum(ps)/n_p, u, v, sum(s for s, _ in ws)/n_w

# ---- archived forecasts: wx[local hour][days ahead] = (pressure mb, wind kt, wind from deg) ----
wx = {}
for y in (2024, 2025, 2026):
    h = json.load(open(D/f'backtest/openmeteo_prev_runs_{y}.json'))['hourly']
    for i, t in enumerate(h['time']):
        rec = {}
        for d in range(8):
            suf = '' if d == 0 else f'_previous_day{d}'
            vals = (h['pressure_msl'+suf][i], h['wind_speed_10m'+suf][i], h['wind_direction_10m'+suf][i])
            if None not in vals: rec[d] = vals
        wx[P(t)] = rec

# ---- observed weather, for a "perfect forecast" reference: Boston pressure + NDBC 44013 buoy wind ----
sum_p, n_p = {}, {}
for r in csv.DictReader(open(D/'boston_met.csv')):
    if r['t'] < '2023-12-31' or not r['pressure_mb']: continue
    k = P(r['t']).replace(minute=0)
    sum_p[k] = sum_p.get(k, 0) + float(r['pressure_mb']); n_p[k] = n_p.get(k, 0) + 1
obs_p = {k: v/n_p[k] for k, v in sum_p.items()}
ET, UTC = ZoneInfo('America/New_York'), dt.timezone.utc
obs_w = {}
for r in csv.DictReader(open(D/'ndbc_44013_wind.csv')):
    if r['t_utc'] < '2023-12-30': continue
    try: s, d = float(r['wind_kt']), float(r['wind_dir_deg'])
    except ValueError: continue
    k = P(r['t_utc']).replace(tzinfo=UTC).astimezone(ET).replace(tzinfo=None, minute=0)
    obs_w.setdefault(k, (s, d))

# ---- the tides ----
tides = []
for r in csv.DictReader(open(D/'boston_high_tides.csv')):
    if r['pred_time'] < '2024-01-01': continue
    t = P(r['pred_time'])
    tides.append(dict(t=t, hr=t.replace(minute=0), year=t.year, pred=float(r['pred_ft']), obs=float(r['obs_ft']), y=float(r['resid_ft'])))

def score(get_p, get_w):
    """RMSE on all tides, RMSE on big surges, and % of near-the-road tides called wrong, for each way"""
    rows = []
    for T_ in tides:
        rs = [reading(get_p, get_w, T_['hr'], a, b) for _, a, b in WAYS]
        if None not in rs: rows.append((T_, rs))
    out = dict(n=len(rows), rmse=[], n_big=0, big=[], n_near=0, wrong=[])
    big = [r for r in rows if r[0]['y'] > 1.0]
    near = [r for r in rows if abs(RATIO*r[0]['obs'] - ROAD) <= 1.0]
    out['n_big'], out['n_near'] = len(big), len(near)
    for i in range(len(WAYS)):
        out['rmse'].append(rmse([T_['y'] - surge(*rs[i], T_['year']) for T_, rs in rows]))
        out['big'].append(rmse([T_['y'] - surge(*rs[i], T_['year']) for T_, rs in big]))
        out['wrong'].append(100*sum((RATIO*(T_['pred'] + surge(*rs[i], T_['year'])) > ROAD) != (RATIO*T_['obs'] > ROAD)
                                    for T_, rs in near)/len(near))
    return out

labels = ' '.join(f'{w[0]:>10}' for w in WAYS)
print(f"{len(tides)} Boston high tides, {tides[0]['t']:%Y-%m-%d} to {tides[-1]['t']:%Y-%m-%d}")
print("ways: tide hour = the forecast for the hour of high tide (the site now); 3h/3h = pressure and wind averaged over the")
print("      3 hours up to it; 6h/9h = pressure over 6 hours and wind over 9 hours up to it (how the model was fitted)\n")
print("1. FORECAST WEATHER, BY DAYS AHEAD (weather model only, no live gauge)")
print(f"{'days':>4} {'n':>5}   RMSE all tides, in:{labels}   {'n':>3}  big surges (>12 in):{labels}   {'n':>3}  % flood calls wrong:{labels}")
res = {}
for d in range(8):
    def fp(h, d=d): f = wx.get(h, {}).get(d); return f[0] if f else None
    def fw(h, d=d): f = wx.get(h, {}).get(d); return (f[1], f[2]) if f else None
    s = res[d] = score(fp, fw)
    print(f"{d:>4} {s['n']:>5}   {'':>18}" + ''.join(f"{x:11.2f}" for x in s['rmse']) +
          f"   {s['n_big']:>3}  {'':>19}" + ''.join(f"{x:11.2f}" for x in s['big']) +
          f"   {s['n_near']:>3}  {'':>19}" + ''.join(f"{x:11.1f}" for x in s['wrong']))
avg = [sum(res[d]['rmse'][i] for d in range(8))/8 for i in range(len(WAYS))]
print("   average RMSE over days 0-7:" + ''.join(f"  {WAYS[i][0]} {avg[i]:.2f}" for i in range(len(WAYS))))

print("\n2. REFERENCE: OBSERVED WEATHER (Boston pressure + buoy wind) instead of a forecast, so only the timing differs")
o = score(obs_p.get, obs_w.get)
print(f"   n={o['n']}: RMSE" + ''.join(f"  {WAYS[i][0]} {o['rmse'][i]:.2f}" for i in range(len(WAYS))) +
      f"   | big surges n={o['n_big']}:" + ''.join(f"  {WAYS[i][0]} {o['big'][i]:.2f}" for i in range(len(WAYS))) +
      f"   | flood calls wrong n={o['n_near']}:" + ''.join(f"  {WAYS[i][0]} {o['wrong'][i]:.1f}%" for i in range(len(WAYS))))
