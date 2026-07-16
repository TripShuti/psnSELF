# psnSELF

Self-hosted web dashboard for your PlayStation Network trophies.

A web-only fork of [psnTUI](https://github.com/TripShuti/psnTUI) — sync your trophy data and browse it from any browser.

## Features

- **Dashboard** — recent trophies, weekly activity heatmap, month-over-month comparison, play time overview, rarity distribution
- **Game list** — sortable table with trophy progress and play time; search and filter by name
- **Game detail** — full trophy list with friend comparison, play time breakdown (today/week/month)
- **Friends leaderboard** — compare progress with friends
- **Auto sync** — schedule periodic trophy and friends sync from the UI
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

## Credits

Built on top of [psnTUI](https://github.com/TripShuti/psnTUI) by TripShuti.
