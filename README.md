# WhatsApp Automation Campaign Manager

Web-based WhatsApp automation system for bulk messaging, campaign tracking, session management, and contact import using Flask, Playwright, and PostgreSQL.

## What It Does

- Manages multiple persistent WhatsApp Web sessions
- Sends messages to contacts or groups
- Supports text, captions, and media attachments
- Tracks sent and failed messages by campaign
- Imports contacts from `.csv` and `.xlsx`
- Stores reusable campaign messages in the database
- Provides campaign monitoring, automation actions, and live status views
- Persists configuration values in `data/saved_configurations.txt`

## Main Features

- WhatsApp session storage with reusable Playwright profile folders
- Open logged-in sessions in visible browser windows
- Start sending with one or more logged-in sessions
- Randomized delays for:
  - message send
  - attachment send
  - click timing
  - search-result click timing
  - batch start timing
- Humanized automation behavior for clicks and typing
- Automation actions after send, such as:
  - open groups and scroll
  - check group members
  - open WhatsApp profile
  - open WhatsApp settings
  - scroll opened chat
  - open number info
- Campaign naming and campaign ID tracking
- Campaign reuse and failed-number reuse
- Monitoring panels for:
  - live campaign progress
  - automation actions
  - stored campaigns
  - WhatsApp sessions

## Tech Stack

- Python
- Flask
- Playwright
- PostgreSQL
- HTML / CSS / vanilla JavaScript
- Docker / Docker Compose

## Important Folders and Files

- `main.py` - Flask app entry point and Playwright automation flow
- `core/` - shared modules: group scraping (`main_scrapper.py`), DB export (`group_db_exporter.py`), recovery worker, phone validation
- `panels/` - server-rendered panel helpers and JSON APIs
- `templates/index.html` - main UI
- `data/` - runtime state: `saved_configurations.txt`, `profile_numbers_sequence.txt`, `session.txt`, `result.txt`, `auth.json`
- `db/` - `postgres_tables.sql` schema plus local dumps
- `dev/` - debugging and scratch scripts (not used by the app)
- `docs/` - architecture notes
- `archive/` - old bundles
- `playwright_profile/` - base Playwright user data directory
- `playwright_profiles/` - stored WhatsApp session profiles
- `send_uploads/` - uploaded media/files for sending

## Data Stored

The app uses PostgreSQL tables for campaign and contact workflows, including:

- `sms_sent`
- `sms_not_sent`
- `all_contacts`
- SMS message records used by the Campaign Messages selector

## Quick Start

### Option 1: Docker Compose

Recommended when you want PostgreSQL and the app together.

```bash
docker compose up -d --build
```

Then open:

```text
http://localhost:5000
```

## Local Run

1. Install Python dependencies:

```bash
pip install -r requirements.txt
```

2. Install Playwright browser:

```bash
playwright install chromium
```

3. Make sure PostgreSQL is available and your app environment is configured.

4. Start the app:

```bash
python main.py
```

5. Open:

```text
http://localhost:5000
```

## Basic Workflow

1. Open the app
2. Add or reuse WhatsApp session profiles
3. Log in to WhatsApp Web
4. Upload contacts or load them from DB
5. Select campaign messages
6. Optionally select media
7. Configure delays and random ranges
8. Start sending
9. Monitor campaign progress and actions

## Session Persistence

WhatsApp sessions are stored in Playwright profile directories, so they usually remain logged in across restarts unless WhatsApp logs them out.

To keep sessions long-term:

- do not delete `playwright_profile/` or `playwright_profiles/`
- do not remove a session unless you want it deleted
- back up the profile folders regularly

## Viewing the Automation Windows After Deployment

The bot always launches Chromium **headed** (`PLAYWRIGHT_HEADLESS=false`), so the WhatsApp windows exist on every deployment. How you see them depends on where it runs:

| Deployment | How to watch |
|---|---|
| `python main.py` on a Windows/Linux VM | Windows open on the VM desktop. Connect with RDP (or the VM console) to watch them. |
| Docker, default `xvfb` mode | Chromium runs on a virtual display inside the container and `x11vnc` shares it. Connect any VNC viewer (RealVNC, TightVNC, TigerVNC) to `<server-ip>:5900`. |
| Docker with `docker-compose.vm-display.yml` | Linux desktop VM only: windows open on the VM's own X display. |

For Docker VNC viewing:

1. Set a password in `.env`: `VNC_PASSWORD=your-secret` (never expose port 5900 without one; prefer a firewall rule or SSH tunnel: `ssh -L 5900:localhost:5900 user@server`).
2. `docker compose up -d --build`
3. Open a VNC viewer to `<server-ip>:5900` (or `localhost:5900` through the tunnel). You can scan QR codes and watch every campaign window live. Several viewers can connect at once.

Env knobs: `VNC_ENABLED` (true/false), `VNC_PORT` (host port), `XVFB_SCREEN` (virtual screen size, default `1440x900x24`).

## Notes

- Visible automation windows appear on the machine where Playwright is running
- If the app is hosted on a VM, the browser windows open on that VM desktop session
- Browser-only remote users can use the web UI, but native Playwright windows still belong to the host machine/session

## Recommended Backup Items

- `playwright_profile/`
- `playwright_profiles/`
- `data/saved_configurations.txt`
- `data/profile_numbers_sequence.txt`

## Project Status

This repository is actively customized for operational WhatsApp campaign workflows, including session reuse, DB-backed campaign history, upload/import tools, and humanized automation behavior.

```
whatsapp
├─ main.py                      Flask app + automation (entry point)
├─ core/
│  ├─ main_scrapper.py          WhatsApp group scraping
│  ├─ group_db_exporter.py      scraped contacts -> PostgreSQL
│  ├─ recovery_worker.py        scrape recovery + session snapshots
│  └─ phone_validation.py
├─ panels/                      UI panel helpers / JSON APIs
├─ templates/
│  └─ index.html
├─ data/                        runtime state (config, profile sequence, session log)
├─ db/                          postgres_tables.sql + local dumps
├─ dev/                         debugging scripts
├─ docs/                        architecture.md
├─ archive/                     old bundles
├─ send_uploads/                uploaded media (runtime)
├─ playwright_profiles/         WhatsApp session profiles (runtime, never commit)
├─ Dockerfile
├─ docker-compose.yml
├─ docker-compose.vm-display.yml
├─ docker-entrypoint.sh
├─ requirements.txt
└─ README.md
```