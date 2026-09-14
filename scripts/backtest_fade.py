"""Backtest: should the wind/pressure forecast fade with lead time, and is the 6 h / 18 h gauge handoff right?

Replays every Boston high tide from Jan 2024 (when Open-Meteo's archive of past forecasts starts) through
Jul 2026, using the forecast that was available 0-7 days ahead, and scores each approach against what the
gauge actually measured. Weights fitted from the data are 2-fold cross-validated by alternating months.

Inputs (data/): boston_high_tides.csv, boston_met.csv, ndbc_44013_wind.csv,
                backtest/openmeteo_prev_runs_{2024,2025,2026}.json, backtest/boston_hourly_2024_2026.csv
Errors are at Boston scale in inches (Wellfleet is x1.05, which doesn't change any ranking).
Run from the project folder:  python3 scripts/backtest_fade.py | tee data/backtest/results.txt
"""
import csv, json, math, pathlib, datetime as dt
from zoneinfo import ZoneInfo

D = pathlib.Path(__file__).resolve().parent.parent/'data'
C = [0.5221, -0.0321, -0.0272, -0.0068, -0.0006, 0.0308]   # the site's surge model
RATIO, ROAD, TYP = 1.05, 10.40, 0.58
HOUR = dt.timedelta(hours=1)
def P(s): return dt.datetime.strptime(s[:16].replace('T', ' '), '%Y-%m-%d %H:%M')

def pieces(p, s, d, year):
    """baseline (sea-level offset), pressure and wind parts of the surge model, ft at Boston"""
    u, v = -s*math.sin(math.radians(d)), -s*math.cos(math.radians(d))
    return C[0] + C[5]*(year-2020), C[1]*(p-1015), C[2]*u + C[3]*v + C[4]*s*v

def rmse(e): return 12*math.sqrt(sum(x*x for x in e)/len(e))
def bias(e): return 12*sum(e)/len(e)
def fold(t): return t['t'].month % 2
def lsq(rows):
    """least-squares weights (1 or 2 predictors, no intercept) for rows of (target, [x...])"""
    k = len(rows[0][1])
    A = [[sum(x[i]*x[j] for _, x in rows) for j in range(k)] for i in range(k)]
    b = [sum(tg*x[i] for tg, x in rows) for i in range(k)]
    if k == 1: return [b[0]/A[0][0]]
    det = A[0][0]*A[1][1] - A[0][1]*A[1][0]
    return [(b[0]*A[1][1] - b[1]*A[0][1])/det, (A[0][0]*b[1] - A[1][0]*b[0])/det]
def fade(d): return 1.0 if d <= 3 else max(0.0, (7-d)/4)   # the proposal: 100% to day 3, 0% by day 7

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
    if r['t'] < '2024-01-01' or not r['pressure_mb']: continue
    k = P(r['t']).replace(minute=0)
    sum_p[k] = sum_p.get(k, 0) + float(r['pressure_mb']); n_p[k] = n_p.get(k, 0) + 1
obs_p = {k: v/n_p[k] for k, v in sum_p.items()}
ET, UTC = ZoneInfo('America/New_York'), dt.timezone.utc
obs_w = {}
for r in csv.DictReader(open(D/'ndbc_44013_wind.csv')):
    if r['t_utc'] < '2023-12-31': continue
    try: s, d = float(r['wind_kt']), float(r['wind_dir_deg'])
    except ValueError: continue
    k = P(r['t_utc']).replace(tzinfo=UTC).astimezone(ET).replace(tzinfo=None, minute=0)
    obs_w.setdefault(k, (s, d))

# ---- the tides ----
tides = []
for r in csv.DictReader(open(D/'boston_high_tides.csv')):
    if r['pred_time'] < '2024-01-01': continue
    t = P(r['pred_time'])
    tides.append(dict(t=t, hr=t.replace(minute=0), year=t.year, pred=float(r['pred_ft']),
                      obs=float(r['obs_ft']), y=float(r['resid_ft'])))
print(f"{len(tides)} Boston high tides, {tides[0]['t']:%Y-%m-%d} to {tides[-1]['t']:%Y-%m-%d}\n")

# ================= 1. weather forecast by days ahead =================
print("1. TYPICAL ERROR BY DAYS AHEAD (RMSE, inches; lower is better)")
print("   chart  = NOAA tide chart alone            +7in  = chart + the site's fixed typical amount")
print("   offset = chart + sea-level offset only     full  = offset + weather at full strength (the site now)")
print("   fade   = proposal: weather 100% to day 3, 0% by day 7")
print("   best w = best single weather weight;  best p/w = separate pressure and wind weights (cross-validated)")
print(f"{'days':>4} {'n':>5} {'chart':>6} {'+7in':>6} {'offset':>7} {'full':>6} {'fade':>6}   {'best w':>13}   {'best p/w':>20}")
store = {}
for d in range(8):
    rows = []
    for T_ in tides:
        f = wx.get(T_['hr'], {}).get(d)
        if f: rows.append((T_,) + pieces(*f, T_['year']))
    def err(fn): return [T_['y'] - fn(b, p_, w_) for T_, b, p_, w_ in rows]
    e_full = err(lambda b, p_, w_: b + p_ + w_)
    e_w, e_pw, ws, pws = [], [], [], []
    for k in (0, 1):
        train = [r for r in rows if fold(r[0]) != k]; test = [r for r in rows if fold(r[0]) == k]
        w1 = lsq([(T_['y'] - b, [p_ + w_]) for T_, b, p_, w_ in train])[0]
        w2 = lsq([(T_['y'] - b, [p_, w_]) for T_, b, p_, w_ in train])
        ws.append(w1); pws.append(w2)
        e_w += [T_['y'] - (b + w1*(p_ + w_)) for T_, b, p_, w_ in test]
        e_pw += [T_['y'] - (b + w2[0]*p_ + w2[1]*w_) for T_, b, p_, w_ in test]
    W, PW = sum(ws)/2, [(pws[0][0] + pws[1][0])/2, (pws[0][1] + pws[1][1])/2]
    store[d] = dict(rows=rows, PW=PW)
    print(f"{d:>4} {len(rows):>5} {rmse(err(lambda b, p_, w_: 0.0)):6.2f} {rmse(err(lambda b, p_, w_: TYP)):6.2f} "
          f"{rmse(err(lambda b, p_, w_: b)):7.2f} {rmse(e_full):6.2f} {rmse(err(lambda b, p_, w_: b + fade(d)*(p_ + w_))):6.2f}   "
          f"{rmse(e_w):6.2f} (w {W:4.2f})   {rmse(e_pw):6.2f} (p {PW[0]:4.2f} w {PW[1]:4.2f})")
    if d == 1:
        b1 = (bias(err(lambda b, p_, w_: 0.0)), bias(err(lambda b, p_, w_: b)), bias(e_full))
e_obs = []
for T_ in tides:
    p, w = obs_p.get(T_['hr']), obs_w.get(T_['hr'])
    if p is not None and w is not None:
        b, p_, w_ = pieces(p, w[0], w[1], T_['year']); e_obs.append(T_['y'] - (b + p_ + w_))
print(f"   (days 0 = the same-day forecast run)")
print(f"   average miss at day 1 (actual minus forecast): chart {b1[0]:+.1f} in, offset {b1[1]:+.1f} in, full {b1[2]:+.1f} in")
print(f"   reference, OBSERVED pressure + buoy wind instead of a forecast (2024-25, n={len(e_obs)}): {rmse(e_obs):.2f} in")

# ================= 2. big surges =================
print("\n2. BIG SURGES ONLY (water came in more than 12 in above the chart): RMSE, inches, and average shortfall")
print(f"{'days':>4} {'n':>4} {'chart':>6} {'offset':>7} {'full':>6} {'fade':>6} {'best p/w':>9}   shortfall full / fade")
for d in range(8):
    S = [r for r in store[d]['rows'] if r[0]['y'] > 1.0]
    PW = store[d]['PW']
    def e(fn): return [T_['y'] - fn(b, p_, w_) for T_, b, p_, w_ in S]
    ef, efd = e(lambda b, p_, w_: b + p_ + w_), e(lambda b, p_, w_: b + fade(d)*(p_ + w_))
    print(f"{d:>4} {len(S):>4} {rmse(e(lambda b, p_, w_: 0.0)):6.2f} {rmse(e(lambda b, p_, w_: b)):7.2f} {rmse(ef):6.2f} {rmse(efd):6.2f} "
          f"{rmse(e(lambda b, p_, w_: b + PW[0]*p_ + PW[1]*w_)):9.2f}   {bias(ef):+6.1f} / {bias(efd):+6.1f}")

# ================= 3. does the road flood? =================
print("\n3. DOES THE ROAD FLOOD AT THIS TIDE? (Wellfleet = Boston x 1.05; tides whose actual peak was within 12 in of the road)")
print(f"{'days':>4} {'n':>4}   % called wrong:  {'chart':>6} {'offset':>7} {'full':>6} {'fade':>6} {'best p/w':>9}")
for d in range(8):
    S = [r for r in store[d]['rows'] if abs(RATIO*r[0]['obs'] - ROAD) <= 1.0]
    PW = store[d]['PW']
    def wrong(fn):
        return 100*sum((RATIO*(T_['pred'] + fn(b, p_, w_)) > ROAD) != (RATIO*T_['obs'] > ROAD) for T_, b, p_, w_ in S)/len(S)
    print(f"{d:>4} {len(S):>4}   {'':>16} {wrong(lambda b, p_, w_: 0.0):6.1f} {wrong(lambda b, p_, w_: b):7.1f} "
          f"{wrong(lambda b, p_, w_: b + p_ + w_):6.1f} {wrong(lambda b, p_, w_: b + fade(d)*(p_ + w_)):6.1f} "
          f"{wrong(lambda b, p_, w_: b + PW[0]*p_ + PW[1]*w_):9.1f}")

# ================= 4. live gauge window =================
hourly = {}
for r in csv.DictReader(open(D/'backtest/boston_hourly_2024_2026.csv')):
    if r['obs_ft'] and r['pred_ft']: hourly[P(r['t'])] = float(r['obs_ft']) - float(r['pred_ft'])
def old_g(h): return 1.0 if h <= 6 else 0.0 if h >= 18 else (18 - h)/12   # before 2026-09-14
def new_g(h): return max(0.0, 0.7*(1 - h/72))                              # now: 70% sliding to 0 at 3 days
print("\n4. LIVE BOSTON GAUGE vs WEATHER FORECAST, BY HOURS BEFORE THE TIDE: RMSE, inches")
print("   gauge = assume the reading an hour before 'now' holds; forecast = offset + weather (same-day run under 24 h);")
print("   old = previous mix (all gauge to 6 h, all forecast from 18 h); new = 70% gauge sliding to 0 at 3 days;")
print("   best = best mix at that hour (cross-validated)")
print(f"{'hours':>5} {'n':>5} {'gauge':>6} {'forecast':>9} {'old':>6} {'new':>6}   {'best mix':>18}")
avg = {'old': [], 'new': []}
for h in (1, 3, 6, 9, 12, 15, 18, 24, 36, 48, 60, 72):
    lead, rows = (0 if h < 24 else h//24), []
    for T_ in tides:
        g0, g1 = hourly.get(T_['hr'] - h*HOUR), hourly.get(T_['hr'] - (h + 1)*HOUR)
        f = wx.get(T_['hr'], {}).get(lead)
        if g0 is None or g1 is None or not f: continue
        rows.append((T_, (g0 + g1)/2, sum(pieces(*f, T_['year']))))
    e_b, As = [], []
    for k in (0, 1):
        train = [r for r in rows if fold(r[0]) != k]; test = [r for r in rows if fold(r[0]) == k]
        a = min(1.0, max(0.0, lsq([(T_['y'] - m, [g - m]) for T_, g, m in train])[0])); As.append(a)
        e_b += [T_['y'] - (a*g + (1 - a)*m) for T_, g, m in test]
    e_old = rmse([T_['y'] - (old_g(h)*g + (1 - old_g(h))*m) for T_, g, m in rows])
    e_new = rmse([T_['y'] - (new_g(h)*g + (1 - new_g(h))*m) for T_, g, m in rows])
    avg['old'].append(e_old); avg['new'].append(e_new)
    print(f"{h:>5} {len(rows):>5} {rmse([T_['y'] - g for T_, g, m in rows]):6.2f} {rmse([T_['y'] - m for T_, g, m in rows]):9.2f} "
          f"{e_old:6.2f} {e_new:6.2f}   {rmse(e_b):6.2f} (gauge {sum(As)/2:4.0%})")
print(f"   average over these hours: old {sum(avg['old'])/len(avg['old']):.2f} in, new {sum(avg['new'])/len(avg['new']):.2f} in")

# ================= 5. input check =================
pp = [(wx[k][0][0], v) for k, v in obs_p.items() if 0 in wx.get(k, {})]
pw = [(wx[k][0][1], v[0]) for k, v in obs_w.items() if 0 in wx.get(k, {})]
print("\n5. INPUT CHECK: same-day Open-Meteo forecast vs observed")
print(f"   pressure: forecast minus Boston observed averages {sum(a - b for a, b in pp)/len(pp):+.1f} mb (n={len(pp)})")
print(f"   wind speed: forecast averages {sum(a for a, _ in pw)/len(pw):.1f} kt vs buoy {sum(b for _, b in pw)/len(pw):.1f} kt (n={len(pw)})")
