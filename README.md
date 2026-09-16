# Lt. Island Tides

**When is the road to Lieutenant Island (Wellfleet, MA) underwater?**
Live at **https://aliabuckner1.github.io/lieutenant-island/**. The short link **https://ltisland.netlify.app** forwards there.

Residents of Lieutenant Island use printed tide calendars, built from NOAA's predictions for Wellfleet, to know when the road on
and off the island will be flooded. Those predictions have grown less reliable. They're pinned to 1983–2001 sea level, and the
sea at Boston is about 6½ inches higher now. They leave out wind and air pressure. And Wellfleet has no tide gauge of its own,
so its numbers are Boston's, scaled and shifted. Today 94% of high tides come in above the prediction, by about 8 inches on
average.

This site corrects for that. It adds today's sea level and a weather model (National Weather Service wind, Open-Meteo pressure)
built from more than 3,000 past high tides, leans on NOAA's live Boston tide gauge for the next day or so, and compares the
result with the road's height from USGS airborne lidar. Islanders can also report what they see at the road. Reports are
recorded in a Google Sheet and can help pin down the road's real height and check the forecast against what actually happens at
Wellfleet, so the model can be improved over time.

## How well it works

Replaying about 900 high tides from 2024–26 with the weather forecasts available at the time, against what Boston's tide gauge
measured:

| Forecast | Typical error |
|---|---|
| NOAA's prediction (what the calendars use) | about 9 in |
| This site, a day ahead | about 4 in |
| This site, a week ahead | about 5 in |

## How it works

The page runs entirely in the browser. On every load it fetches NOAA tide predictions, the live Boston tide gauge, the NWS wind
forecast and Open-Meteo pressure, then compares the result with the road's low point: 9.9 ft above MLLW, measured from the road on 15 Sep 2026
(nine tape-measure depths through one tide, `data/road_measurements.csv`). It had been 10.4 ft from lidar, good to about ±6 in.
No server and no build step.

## What's where

| Folder | What it is |
|---|---|
| `apps-script/` | The Google Apps Script that receives road reports and adds each one to a Google Sheet. Setup steps are at the top of the file. |
| `site/` | **The live site.** `index.html`, `tide-data.js` (data fetching and the forecast model), `base.css`. Edit these directly. |
| `design-options/` | Design history: the mockups the current layout was chosen from. Not deployed. |
| `scripts/` | Python analysis: tide and weather history, the road profile, and `backtest_fade.py`, which replays 2024–26 tides to check the forecast. |
| `data/` | Downloaded data and results (see `data/backtest/results.txt`). |
| `archive/` | Earlier versions of the live page. |
| `*.html` (top level) | The original one-page analysis and the September field card for logging when water reaches the road. |

## Deploying

GitHub Actions publishes the `site/` folder to GitHub Pages on every push to `main` that changes it
(`.github/workflows/pages.yml`). It can also be run by hand from the Actions tab.

## Rerunning the forecast check

```
python3 scripts/fetch_backtest_data.py
python3 scripts/backtest_fade.py | tee data/backtest/results.txt
```
