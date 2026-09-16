"""Backtest: would a richer surge model beat the site's, scored on forecasts it never saw?

Each candidate form is fitted on tides through 2023 (observed pressure and wind, averaged over the 6 h / 9 h up to
high tide, from data/model.pkl), then scored on every 2024-26 tide using the archived forecast that was available
0-7 days ahead, averaged the same way the site does. So the numbers are out-of-sample in time AND use real
forecasts rather than observed weather. Weather model only, no live gauge (as in backtest_fade.py section 1).

Candidates: the site's form; + an annual sea-level cycle; + wind-squared terms; both.
Also checks the annual cycle is stable by fitting it on 2015-19 and 2020-23 separately.

Inputs (data/): model.pkl, boston_high_tides.csv, backtest/openmeteo_prev_runs_{2024,2025,2026}.json
Errors are at Boston scale in inches (Wellfleet is x1.05, which doesn't change any ranking).
Run from the project folder:  python3 scripts/backtest_model_form.py | tee data/backtest/model_form.txt
"""
import csv, json, math, pathlib, pickle, datetime as dt

D = pathlib.Path(__file__).resolve().parent.parent/'data'
HOUR = dt.timedelta(hours=1)
P_HOURS, W_HOURS = 6, 9
def P(s): return dt.datetime.strptime(s[:16].replace('T', ' '), '%Y-%m-%d %H:%M')
def rmse(e): return 12*math.sqrt(sum(x*x for x in e)/len(e))
def bias(e): return 12*sum(e)/len(e)

# ---- model forms: feature vectors from (pressure mb, u, v, speed kt, time) ----
def feats(kind, p, u, v, s, t):
    ang = 2*math.pi*t.timetuple().tm_yday/365.25
    x = [1, p-1015, u, v, s*v, t.year-2020]
    if kind in ('season', 'both'): x += [math.sin(ang), math.cos(ang)]
    if kind in ('wind2', 'both'):  x += [s*u, s*s]
    return x
KINDS = [('site', 'site form'), ('season', '+ annual cycle'), ('wind2', '+ wind squared'), ('both', '+ both')]

def lsq(X, y):
    k = len(X[0]); A = [[sum(x[i]*x[j] for x in X) for j in range(k)] for i in range(k)]
    b = [sum(yy*x[i] for x, yy in zip(X, y)) for i in range(k)]
    for i in range(k):
        piv = max(range(i, k), key=lambda r: abs(A[r][i])); A[i], A[piv] = A[piv], A[i]; b[i], b[piv] = b[piv], b[i]
        for r in range(i+1, k):
            f = A[r][i]/A[i][i]; b[r] -= f*b[i]
            for c in range(i, k): A[r][c] -= f*A[i][c]
    w = [0]*k
    for i in range(k-1, -1, -1): w[i] = (b[i]-sum(A[i][c]*w[c] for c in range(i+1, k)))/A[i][i]
    return w

# ---- fit on observed weather through 2023 ----
C_SITE, rows = pickle.load(open(D/'model.pkl', 'rb'))
rows = [r for r in rows if all(k in r for k in ('p', 'u', 'v', 'spd', 'resid', 't'))]
train = [r for r in rows if r['t'].year <= 2023]
W = {}
for kind, _ in KINDS:
    W[kind] = lsq([feats(kind, r['p'], r['u'], r['v'], r['spd'], r['t']) for r in train], [r['resid'] for r in train])
print(f"fitted on {len(train)} tides {train[0]['t']:%Y-%m} to {train[-1]['t']:%Y-%m} (observed weather)")

# the annual cycle, era by era
print("\nANNUAL CYCLE BY ERA (should agree if it's real)")
for lo, hi in ((2015, 2019), (2020, 2023), (2015, 2023)):
    sub = [r for r in train if lo <= r['t'].year <= hi]
    w = lsq([feats('season', r['p'], r['u'], r['v'], r['spd'], r['t']) for r in sub], [r['resid'] for r in sub])
    amp = 12*math.hypot(w[6], w[7]); peak = (math.atan2(w[6], w[7]) % (2*math.pi))/(2*math.pi)*365.25
    print(f"   {lo}-{hi} (n={len(sub)}): amplitude ±{amp:.1f} in, peak around {(dt.date(2021,1,1)+dt.timedelta(days=peak)):%b %d}")

# ---- archived forecasts: wx[local hour][days ahead] = (pressure, wind kt, wind from deg) ----
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

def reading(h, d):
    """forecast d days ahead, averaged the way the site does: pressure over 6 h up to h, wind over 9 h"""
    ps, ws = [], []
    for k in range(W_HOURS):
        f = wx.get(h - k*HOUR, {}).get(d)
        if f is None: return None
        if k < P_HOURS: ps.append(f[0])
        ws.append((f[1], f[2]))
    u = sum(-s*math.sin(math.radians(dg)) for s, dg in ws)/W_HOURS
    v = sum(-s*math.cos(math.radians(dg)) for s, dg in ws)/W_HOURS
    return sum(ps)/P_HOURS, u, v, sum(s for s, _ in ws)/W_HOURS

# ---- the tides ----
tides = []
for r in csv.DictReader(open(D/'boston_high_tides.csv')):
    if r['pred_time'] < '2024-01-01': continue
    t = P(r['pred_time'])
    tides.append(dict(t=t, hr=t.replace(minute=0), y=float(r['resid_ft'])))

def pred(kind, w, rd, t): return sum(a*b for a, b in zip(w, feats(kind, rd[0], rd[1], rd[2], rd[3], t)))
print(f"\n{len(tides)} Boston high tides 2024-26 scored with the FORECAST available N days ahead (RMSE in inches; bias in brackets)")
head = f"{'days':>4} {'n':>4}  {'shipped':>14}" + ''.join(f"{lab:>17}" for _, lab in KINDS)
print(head)
avg = {k: [] for k, _ in KINDS}; avg['shipped'] = []
fall = {k: [] for k, _ in KINDS}
for d in range(8):
    rows_d = [(T_, reading(T_['hr'], d)) for T_ in tides]
    rows_d = [(T_, rd) for T_, rd in rows_d if rd is not None]
    e_ship = [T_['y'] - pred('site', C_SITE, rd, T_['t']) for T_, rd in rows_d]
    line = f"{d:>4} {len(rows_d):>4}  {rmse(e_ship):6.2f} ({bias(e_ship):+4.1f})"
    avg['shipped'].append(rmse(e_ship))
    for kind, _ in KINDS:
        e = [T_['y'] - pred(kind, W[kind], rd, T_['t']) for T_, rd in rows_d]
        line += f"  {rmse(e):6.2f} ({bias(e):+4.1f})"
        avg[kind].append(rmse(e))
        fall[kind] += [x for x, (T_, _) in zip(e, rows_d) if T_['t'].month in (9, 10, 11) and d == 1] if d == 1 else []
    print(line)
print("   average over days 0-7:  shipped %.2f" % (sum(avg['shipped'])/8) + ''.join(f"   {lab} {sum(avg[k])/8:.2f}" for k, lab in KINDS))
print("\n   Sep-Nov tides only, 1 day ahead (the road's season):" + ''.join(f"   {lab} {rmse(fall[k]):.2f} ({bias(fall[k]):+.1f})" for k, lab in KINDS if fall[k]))
print("\ncoefficients (ft):")
for kind, lab in KINDS: print(f"   {lab:<16}", [round(x, 4) for x in W[kind]])
