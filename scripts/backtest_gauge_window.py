"""Would averaging the tide gauge over a longer window predict upcoming tides better?

The site holds the gauge's recent reading (observed minus predicted) constant into the future and mixes it with the
weather forecast (70% gauge now, sliding to 0% at 3 days). It currently averages the last hour. Readings taken near low
tide are noisier, which is the likely cause of the dip 15-18 hours out, so this compares longer averaging windows.

Uses the same 2024-26 tides and archived forecasts as backtest_fade.py.
Run from the project folder:  python3 scripts/backtest_gauge_window.py | tee data/backtest/gauge_window.txt
"""
import csv, json, math, pathlib, datetime as dt

D = pathlib.Path(__file__).resolve().parent.parent/'data'
C = [0.5221, -0.0321, -0.0272, -0.0068, -0.0006, 0.0308]
HOUR = dt.timedelta(hours=1)
def P(s): return dt.datetime.strptime(s[:16].replace('T', ' '), '%Y-%m-%d %H:%M')
def model(p, s, d, year):
    u, v = -s*math.sin(math.radians(d)), -s*math.cos(math.radians(d))
    return C[0] + C[5]*(year-2020) + C[1]*(p-1015) + C[2]*u + C[3]*v + C[4]*s*v
def rmse(e): return 12*math.sqrt(sum(x*x for x in e)/len(e))
def site_g(h): return max(0.0, 0.7*(1 - h/72))

wx = {}
for y in (2024, 2025, 2026):
    h = json.load(open(D/f'backtest/openmeteo_prev_runs_{y}.json'))['hourly']
    for i, t in enumerate(h['time']):
        rec = {}
        for d in range(4):
            suf = '' if d == 0 else f'_previous_day{d}'
            vals = (h['pressure_msl'+suf][i], h['wind_speed_10m'+suf][i], h['wind_direction_10m'+suf][i])
            if None not in vals: rec[d] = vals
        wx[P(t)] = rec
resid = {P(r['t']): float(r['obs_ft']) - float(r['pred_ft'])
         for r in csv.DictReader(open(D/'backtest/boston_hourly_2024_2026.csv')) if r['obs_ft'] and r['pred_ft']}
tides = [dict(hr=P(r['pred_time']).replace(minute=0), year=int(r['pred_time'][:4]), y=float(r['resid_ft']))
         for r in csv.DictReader(open(D/'boston_high_tides.csv')) if r['pred_time'] >= '2024-01-01']

# how many hours of readings, ending "now", the gauge estimate averages
WINDOWS = {'last hour (site now)': 2, 'last 6 h': 7, 'last tide cycle (~12.4 h)': 13, 'last 2 cycles (~25 h)': 26}
HRS = [1, 3, 6, 9, 12, 15, 18, 24, 36, 48, 60]

print(f"{len(tides)} Boston high tides, 2024-26. Typical error (RMSE, inches) at each number of hours before the tide.\n")
for label, use in (('GAUGE ALONE', lambda g, h, m: g), ('SITE MIX (gauge + forecast)', lambda g, h, m: site_g(h)*g + (1 - site_g(h))*m)):
    print(label)
    print(f"{'window':<28}" + ''.join(f"{str(h)+' h':>7}" for h in HRS) + f"{'avg':>7}{'avg <=24h':>11}")
    for name, n in WINDOWS.items():
        per = {}
        for h in HRS:
            lead, errs = (0 if h < 24 else h//24), []
            for T in tides:
                vals = [resid.get(T['hr'] - (h + k)*HOUR) for k in range(n)]
                f = wx.get(T['hr'], {}).get(lead)
                if None in vals or not f: continue
                errs.append(T['y'] - use(sum(vals)/n, h, model(*f, T['year'])))
            per[h] = rmse(errs)
        short = [per[h] for h in HRS if h <= 24]
        print(f"{name:<28}" + ''.join(f"{per[h]:7.2f}" for h in HRS) + f"{sum(per.values())/len(per):7.2f}{sum(short)/len(short):11.2f}")
    print()
