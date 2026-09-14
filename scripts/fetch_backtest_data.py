"""Download what scripts/backtest_fade.py needs into data/backtest/:
- Open-Meteo Previous Runs API: archived pressure and wind forecasts made 0-7 days ahead (archive starts Jan 2024)
- NOAA CO-OPS Boston (8443970): hourly observed water level and hourly predictions
Run from the project folder:  python3 scripts/fetch_backtest_data.py
"""
import csv, json, time, pathlib, urllib.request, datetime as dt

OUT = pathlib.Path(__file__).resolve().parent.parent/'data'/'backtest'
OUT.mkdir(parents=True, exist_ok=True)
LAT, LON = 41.8937, -70.0034
today = dt.date.today()
years = range(2024, today.year + 1)

def get(url, timeout=240):
    for a in range(4):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r: return json.load(r)
        except Exception as e:
            if a == 3: raise
            time.sleep(2*(a + 1))

# ---- archived forecasts, one file per year ----
base_vars = ('pressure_msl', 'wind_speed_10m', 'wind_direction_10m')
hourly = list(base_vars) + [f'{v}_previous_day{d}' for d in range(1, 8) for v in base_vars]
for y in years:
    end = min(dt.date(y, 12, 31), today - dt.timedelta(days=1))
    j = get(f'https://previous-runs-api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}'
            f'&hourly={",".join(hourly)}&wind_speed_unit=kn&timezone=America%2FNew_York'
            f'&start_date={y}-01-01&end_date={end}')
    (OUT/f'openmeteo_prev_runs_{y}.json').write_text(json.dumps(j))
    print('Open-Meteo', y, len(j['hourly']['time']), 'hours')
    time.sleep(2)

# ---- Boston hourly observed + predicted (NOAA allows a year per request) ----
NOAA = ('https://api.tidesandcurrents.noaa.gov/api/prod/datagetter?station=8443970&datum=MLLW&units=english'
        '&time_zone=lst_ldt&format=json&application=lieutenant_island_crossing')
rows = {}
for y in years:
    b, e = f'{y}0101', (f'{y}1231' if y < today.year else today.strftime('%Y%m%d'))
    for prod, extra, key in (('hourly_height', '', 'obs'), ('predictions', '&interval=h', 'pred')):
        j = get(f'{NOAA}&product={prod}{extra}&begin_date={b}&end_date={e}', timeout=180)
        data = j.get('data') or j.get('predictions') or []
        for d in data:
            if d.get('v') not in ('', None): rows.setdefault(d['t'], {})[key] = float(d['v'])
        print('NOAA', y, prod, len(data), 'rows')
with open(OUT/'boston_hourly_2024_2026.csv', 'w', newline='') as f:
    w = csv.writer(f); w.writerow(['t', 'obs_ft', 'pred_ft'])
    for t in sorted(rows): w.writerow([t, rows[t].get('obs', ''), rows[t].get('pred', '')])
print('wrote', len(rows), 'hours')
