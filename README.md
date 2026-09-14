# Lieutenant Island causeway crossing

When is the causeway road to Lieutenant Island (Wellfleet, MA) under water? Live at **https://ltisland.netlify.app**.

The page runs entirely in the browser. On every load it fetches NOAA tide predictions, the live Boston tide gauge,
the NWS wind forecast and Open-Meteo pressure, works out how much extra water they add to the tide chart, and compares
the result with the road's low point: 10.4 ft above MLLW, from airborne lidar, known to about ±6 in. No server, no
build step.

## What's where

| Folder | What it is |
|---|---|
| `site/` | **The live site.** `index.html`, `tide-data.js` (data fetching and the forecast model), `base.css`. Edit these directly. |
| `design-options/` | Design history: the mockups the current layout was chosen from. Not deployed. |
| `scripts/` | Python analysis: tide and weather history, the road profile, and `backtest_fade.py`, which replays 2024–26 tides to check the forecast. |
| `data/` | Downloaded data and results (see `data/backtest/results.txt`). |
| `archive/` | Earlier versions of the live page. |
| `*.html` (top level) | The original one-page analysis and the September field card for logging when water reaches the road. |

## Deploying

Netlify publishes the `site/` folder. With the repo linked in Netlify, every push to `main` goes live and every pull
request gets a preview link.

## Rerunning the forecast check

```
python3 scripts/fetch_backtest_data.py
python3 scripts/backtest_fade.py | tee data/backtest/results.txt
```
