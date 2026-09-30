"""Is Wellfleet Harbor's tide curve the same shape as Boston's?

USGS ran a gauge on the harbor side of the Chequessett Neck Road dike (site 011058798) from Sep 2017 to Aug 2022, one
reading every 5 minutes. For every high tide in that record, this takes Boston's OBSERVED curve, stretches it the way
the site does (NOAA's predicted Wellfleet/Boston durations in time, their heights in height), anchors it on the harbor's
observed high, and asks: how long before the high was the water X ft below it, and how long after? Actual minus stretched.

The gauge's lows are not used as anchors: it sits in a channel that can't drain fully, so its lows come 72 min after
Boston's and its range reads 7% smaller, which would distort anything anchored on them.

Run from the project folder:  python3 scripts/wellfleet_shape.py | tee data/wellfleet_shape/results.txt
Downloads the raw records into data/wellfleet_shape/ on the first run (about 45 MB, not committed).
"""
import csv, json, pathlib, datetime as dt, statistics as st, bisect, time, urllib.request
D = pathlib.Path(__file__).resolve().parent.parent/'data'/'wellfleet_shape'
D.mkdir(parents=True, exist_ok=True)
# 1. USGS harbor-side stage, 5-min, one file per water year
for y in range(2017, 2023):
    f = D/f'usgs_{y}.rdb'
    if f.exists(): continue
    url = f"https://waterservices.usgs.gov/nwis/iv/?sites=011058798&format=rdb&parameterCd=00065&startDT={y}-01-01&endDT={y}-12-31"
    req = urllib.request.Request(url, headers={'User-Agent': 'lieutenant-island-tides'})
    for tries in range(3):
        try:
            data = urllib.request.urlopen(req, timeout=120).read(); break
        except Exception as e:
            print('retry', y, e); time.sleep(5)
    f.write_bytes(data); print('usgs', y, len(data))
# 2. Boston observed water level, 6-min, MLLW, 31-day chunks
out = D/'boston_obs.csv'
if not out.exists():
    rows = []
    d = dt.date(2017, 9, 1)
    while d < dt.date(2022, 9, 1):
        e = min(d + dt.timedelta(days=30), dt.date(2022, 9, 1))
        url = ("https://api.tidesandcurrents.noaa.gov/api/prod/datagetter?station=8443970&product=water_level&datum=MLLW&units=english"
               f"&time_zone=lst_ldt&format=json&application=lieutenant_island_crossing&begin_date={d:%Y%m%d}&end_date={e:%Y%m%d}")
        for tries in range(3):
            try:
                j = json.load(urllib.request.urlopen(url, timeout=60)); break
            except Exception as ex:
                print('retry', d, ex); time.sleep(5)
        for x in j.get('data', []):
            if x['v']: rows.append(f"{x['t']},{x['v']}")
        print('boston', d, len(j.get('data', [])))
        d = e + dt.timedelta(days=1)
    out.write_text("t,v\n" + "\n".join(rows) + "\n")

P = lambda s: dt.datetime.strptime(s[:16], '%Y-%m-%d %H:%M')
# harbor side of the dike: column 218558_00065
W = []
for f in sorted(D.glob('usgs_*.rdb')):
    for line in f.read_text().splitlines():
        if not line.startswith('USGS'): continue
        c = line.split('\t')
        if len(c) >= 7 and c[6] not in ('', 'Ice', 'Eqp'):
            try: W.append((P(c[2]), float(c[6])))
            except ValueError: pass
B = [(P(r['t']), float(r['v'])) for r in csv.DictReader(open(D/'boston_obs.csv'))]
W.sort(); B.sort()
print(f"harbor gauge: {len(W)} readings {W[0][0]:%Y-%m-%d} to {W[-1][0]:%Y-%m-%d}; Boston: {len(B)} readings")

def extremes(S, step):
    """highs and lows: the max/min within ±3 h, with a complete record around it"""
    t = [x[0] for x in S]; v = [x[1] for x in S]; out = []
    n = int(3*60/step)
    for i in range(n, len(S)-n):
        if (t[i+n]-t[i-n]) > dt.timedelta(minutes=step*2*n*1.1): continue   # gap in the record
        seg = v[i-n:i+n+1]
        if v[i] == max(seg) and seg.index(v[i]) == n: out.append(('H', t[i], v[i]))
        elif v[i] == min(seg) and seg.index(v[i]) == n: out.append(('L', t[i], v[i]))
    # keep alternation, drop duplicates closer than 6 h
    clean = []
    for e in out:
        if clean and clean[-1][0] == e[0]:
            if (e[0] == 'H') == (e[2] > clean[-1][2]): clean[-1] = e
        else: clean.append(e)
    return clean
WE, BE = extremes(W, 5), extremes(B, 6)
def nearest(E, kind, t, tol=dt.timedelta(hours=2)):
    c = [e for e in E if e[0] == kind and abs(e[1]-t) <= tol]
    return min(c, key=lambda e: abs(e[1]-t)) if c else None
def series_between(S, t0, t1):
    ts = [x[0] for x in S]
    i, j = bisect.bisect_left(ts, t0), bisect.bisect_right(ts, t1)
    return S[i:j]
def cross(seg, level, rising):
    """first time the segment passes `level` (rising) or last time it drops through it (falling)"""
    idx = range(len(seg)-1) if rising else range(len(seg)-2, -1, -1)
    for i in idx:
        (t0, v0), (t1, v1) = seg[i], seg[i+1]
        if (v0 < level <= v1) if rising else (v0 >= level > v1):
            f = (level-v0)/(v1-v0); return t0 + (t1-t0)*f
    return None

def hilo(station, y):
    f = D/f'hilo_{station}_{y}.json'
    if not f.exists():
        url = ("https://api.tidesandcurrents.noaa.gov/api/prod/datagetter?product=predictions&interval=hilo&datum=MLLW&units=english"
               f"&time_zone=lst_ldt&format=json&application=lieutenant_island_crossing&station={station}&begin_date={y}0101&end_date={y}1231")
        f.write_bytes(urllib.request.urlopen(url, timeout=60).read()); time.sleep(1)
    return [(x['type'], P(x['t']), float(x['v'])) for x in json.loads(f.read_text())['predictions']]
BP, WP = [], []
for y in range(2017, 2023): BP += hilo('8443970', y); WP += hilo('8446613', y)
print(f"NOAA predicted Wellfleet high after Boston: median {st.median([(nearest(WP,'H',e[1],dt.timedelta(hours=1.5))[1]-e[1]).total_seconds()/60 for e in BP[:2000] if e[0]=='H' and nearest(WP,'H',e[1],dt.timedelta(hours=1.5))]):.0f} min; "
      f"low: {st.median([(nearest(WP,'L',e[1],dt.timedelta(hours=1.5))[1]-e[1]).total_seconds()/60 for e in BP[:2000] if e[0]=='L' and nearest(WP,'L',e[1],dt.timedelta(hours=1.5))]):.0f} min")

LEVELS = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
def minutes_to(seg, t_high, v_high, drop, after):
    """minutes from the high until the water is `drop` ft below it (after=True), or from that point up to the high"""
    lvl = v_high - drop
    if after:
        for i in range(len(seg)-1):
            if seg[i][0] < t_high: continue
            (t0, v0), (t1, v1) = seg[i], seg[i+1]
            if v0 >= lvl > v1: return ((t0 + (t1-t0)*((lvl-v0)/(v1-v0))) - t_high).total_seconds()/60
    else:
        for i in range(len(seg)-2, -1, -1):
            if seg[i+1][0] > t_high: continue
            (t0, v0), (t1, v1) = seg[i], seg[i+1]
            if v0 < lvl <= v1: return (t_high - (t0 + (t1-t0)*((lvl-v0)/(v1-v0)))).total_seconds()/60
    return None
res = {}   # (bucket, side, L) -> list of (actual - site) minutes
n = 0
for k in range(1, len(WE)-1):
    if WE[k][0] != 'H': continue
    wh = WE[k]; bh = nearest(BE, 'H', wh[1])
    if not bh: continue
    # the site's stretch for this tide: NOAA predicted durations, Wellfleet / Boston, each limb
    bph = nearest(BP, 'H', bh[1], dt.timedelta(hours=1)); wph = nearest(WP, 'H', wh[1], dt.timedelta(hours=1.5))
    if not (bph and wph): continue
    bpl0 = max([e for e in BP if e[0]=='L' and e[1] < bph[1]], key=lambda e: e[1], default=None)
    bpl1 = min([e for e in BP if e[0]=='L' and e[1] > bph[1]], key=lambda e: e[1], default=None)
    wpl0 = max([e for e in WP if e[0]=='L' and e[1] < wph[1]], key=lambda e: e[1], default=None)
    wpl1 = min([e for e in WP if e[0]=='L' and e[1] > wph[1]], key=lambda e: e[1], default=None)
    if not (bpl0 and bpl1 and wpl0 and wpl1): continue
    stretch = {'rise': (wph[1]-wpl0[1])/(bph[1]-bpl0[1]), 'fall': (wpl1[1]-wph[1])/(bpl1[1]-bph[1])}
    hscale = {'rise': (wph[2]-wpl0[2])/(bph[2]-bpl0[2]), 'fall': (wph[2]-wpl1[2])/(bph[2]-bpl1[2])}
    wseg = series_between(W, wh[1]-dt.timedelta(hours=6), wh[1]+dt.timedelta(hours=6))
    bseg = series_between(B, bh[1]-dt.timedelta(hours=6), bh[1]+dt.timedelta(hours=6))
    if len(wseg) < 120 or len(bseg) < 100: continue
    n += 1
    bucket = 'floods the road (Boston high >= 10.5 ft)' if bh[2] >= 10.5 else 'close (9.5-10.5)' if bh[2] >= 9.5 else 'stays dry (< 9.5)'
    for L in LEVELS:
        for side, after in (('rise', False), ('fall', True)):
            ta = minutes_to(wseg, wh[1], wh[2], L, after)
            tb = minutes_to(bseg, bh[1], bh[2], L/hscale[side], after)   # Boston, at the equivalent drop
            if ta is None or tb is None: continue
            site = tb*stretch[side]
            for b in (bucket, 'all tides'): res.setdefault((b, side, L), []).append(ta-site)
print(f"\n{n} highs compared. Minutes from the moment the water is X ft below the high up to the high (rise), and from the high\n"
      "down to X ft below it (fall): ACTUAL at the harbor gauge minus the SITE's stretched-Boston shape. Positive = the real water\n"
      "takes longer (rising: reaches the road later; falling: leaves it later). Negative on the fall = leaves the road EARLIER.")
for b in ['all tides', 'floods the road (Boston high >= 10.5 ft)', 'close (9.5-10.5)', 'stays dry (< 9.5)']:
    print(f"\n  {b}  (n={len(res.get((b,'rise',1.5),[]))})")
    print(f"  {'ft below high':>14} {'rise: median':>13} {'middle half':>14} {'fall: median':>13} {'middle half':>14}")
    for L in LEVELS:
        r, f = res.get((b,'rise',L),[]), res.get((b,'fall',L),[])
        if len(r) < 5: continue
        qr, qf = st.quantiles(r, n=4), st.quantiles(f, n=4)
        print(f"  {L:>14.1f} {st.median(r):>+13.1f} {qr[0]:>+6.0f} to {qr[2]:<+5.0f} {st.median(f):>+13.1f} {qf[0]:>+6.0f} to {qf[2]:<+5.0f}")

# the same, by year and season, for road-flooding tides at 1.5 ft below the high
res2 = {}
for k in range(1, len(WE)-1):
    if WE[k][0] != 'H': continue
    wh = WE[k]; bh = nearest(BE, 'H', wh[1])
    if not bh or bh[2] < 10.5: continue
    bph = nearest(BP, 'H', bh[1], dt.timedelta(hours=1)); wph = nearest(WP, 'H', wh[1], dt.timedelta(hours=1.5))
    if not (bph and wph): continue
    bpl0 = max([e for e in BP if e[0]=='L' and e[1] < bph[1]], key=lambda e: e[1], default=None)
    bpl1 = min([e for e in BP if e[0]=='L' and e[1] > bph[1]], key=lambda e: e[1], default=None)
    wpl0 = max([e for e in WP if e[0]=='L' and e[1] < wph[1]], key=lambda e: e[1], default=None)
    wpl1 = min([e for e in WP if e[0]=='L' and e[1] > wph[1]], key=lambda e: e[1], default=None)
    if not (bpl0 and bpl1 and wpl0 and wpl1): continue
    stretch = {'rise': (wph[1]-wpl0[1])/(bph[1]-bpl0[1]), 'fall': (wpl1[1]-wph[1])/(bpl1[1]-bph[1])}
    hscale = {'rise': (wph[2]-wpl0[2])/(bph[2]-bpl0[2]), 'fall': (wph[2]-wpl1[2])/(bph[2]-bpl1[2])}
    wseg = series_between(W, wh[1]-dt.timedelta(hours=6), wh[1]+dt.timedelta(hours=6))
    bseg = series_between(B, bh[1]-dt.timedelta(hours=6), bh[1]+dt.timedelta(hours=6))
    if len(wseg) < 120 or len(bseg) < 100: continue
    season = ('winter' if bh[1].month in (12,1,2) else 'spring' if bh[1].month in (3,4,5) else 'summer' if bh[1].month in (6,7,8) else 'autumn')
    for side, after in (('rise', False), ('fall', True)):
        ta = minutes_to(wseg, wh[1], wh[2], 1.5, after); tb = minutes_to(bseg, bh[1], bh[2], 1.5/hscale[side], after)
        if ta is None or tb is None: continue
        for b in (str(bh[1].year), season): res2.setdefault((b, side), []).append(ta-tb*stretch[side])
print("\nRoad-flooding tides, 1.5 ft below the high, actual minus site, minutes (rise / fall), by year and season")
for b in ['2017','2018','2019','2020','2021','2022','winter','spring','summer','autumn']:
    r, f = res2.get((b,'rise'),[]), res2.get((b,'fall'),[])
    if r: print(f"  {b:>7}: rise {st.median(r):+5.1f}   fall {st.median(f):+5.1f}   (n={len(r)})")
print("\nThe site (site/tide-data.js, SHAPE_FALL) nudges the stretched curve 8 min earlier on the fall at 2 ft below the high, scaled by\nthe square root of the distance below the high. The rise is left alone: depths measured at the road fit the unshifted curve\n(data/road_measurements.csv, 2026-09-30).")
