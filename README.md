# psnSELF
<img width="1124" height="1144" alt="image" src="https://github.com/user-attachments/assets/3948c144-7c04-4611-9c47-9342c46be000" />


Self-hosted web dashboard for your PlayStation Network trophies.

A web-only fork of [psnTUI](https://github.com/TripShuti/psnTUI) — sync your trophy data and browse it from any browser.

## Features

- **Dashboard** — recent trophies, weekly activity heatmap, month-over-month comparison, play time overview, rarity distribution
- **Game list** — sortable table with trophy progress and play time; search and filter by name
- **Game detail** — full trophy list with friend comparison, play time breakdown (today/week/month)
- **Friends leaderboard** — compare progress with friends
- **Auto sync** — schedule periodic trophy sync from the UI
  > **Note:** Friend sync is manual-only, by design, for your safety
- **Manual play time** — set play time for games without PSN tracking

## Quick Start (Docker)

```bash
git clone https://github.com/TripShuti/psnself
cd psnself
docker compose up -d
```

Open [http://localhost:8420/auth](http://localhost:8420/auth), enter your NPSSO cookie, and you're done.

### Getting your NPSSO

1. Log into [my.playstation.com](https://my.playstation.com)
2. Visit `ca.account.sony.com/api/v1/ssocookie`
3. Copy the 64-character NPSSO value from the JSON response

## Manual Setup

```bash
pip install ".[web]"
python -m psnself.web
```

## CLI Sync (headless / cron)

```bash
pip install .
psnself --sync          # sync trophies
psnself --sync-friends   # sync friends leaderboard
psnself --sync-all       # both
```
## Configuration

All data is stored in `~/.config/psnself/`:
- `config.json` — NPSSO + online ID
- `schedule.json` — auto-sync intervals
- `trophies.db` — your trophy data

> **Note:** The container mounts your host's `/etc/localtime` so the daily
> auto-sync (23:00–00:00 window) runs at the correct local time. If you're
> on a platform where this mount doesn't work (e.g. some Docker Desktop
> setups), set `TZ=Your/Timezone` under `environment:` in
> `docker-compose.yml` instead — see the [list of tz database names](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones).

## Credits

Built on top of [psnTUI](https://github.com/TripShuti/psnTUI) by TripShuti.
