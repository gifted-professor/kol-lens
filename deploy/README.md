# Deploy Notes

This directory contains the minimum deployment assets for the `deploy-phase7-checkpoint` branch.

Files:

- `gunicorn.conf.py` — gunicorn runtime config, bound to `127.0.0.1:5001` by default
- `nginx/kol-lens.conf` — Nginx site config serving `frontend/dist` and proxying `/api/` to gunicorn
- `systemd/kol-lens.service` — systemd unit for running gunicorn as a long-lived service

Expected server layout:

- repo checkout: `/srv/kol-lens`
- frontend build output: `/srv/kol-lens/frontend/dist`
- backend virtualenv: `/srv/kol-lens/backend/.venv`
- app env file: `/srv/kol-lens/.env.local`

Frontend API contract after this hardening:

- browser calls same-origin `/api/...`
- local preview images also stay same-origin
- Nginx proxies `/api/` to `127.0.0.1:5001`
- browser no longer needs direct access to port `5001`

Server deployment commands:

```bash
sudo useradd --system --create-home --home-dir /srv/kol-lens --shell /usr/sbin/nologin kol || true
sudo mkdir -p /srv/kol-lens
sudo chown -R "$USER":"$USER" /srv/kol-lens
git clone <repo-url> /srv/kol-lens
cd /srv/kol-lens
git fetch origin
git checkout deploy-phase7-checkpoint
git pull --ff-only origin deploy-phase7-checkpoint
python3 -m venv backend/.venv
backend/.venv/bin/pip install --upgrade pip
backend/.venv/bin/pip install -r backend/requirements.txt
cp .env.example .env.local
cd frontend
npm ci
npm run build
cd /srv/kol-lens
sudo chown -R kol:kol /srv/kol-lens
```

Install system service and Nginx config:

```bash
cd /srv/kol-lens
sudo cp deploy/systemd/kol-lens.service /etc/systemd/system/kol-lens.service
sudo cp deploy/nginx/kol-lens.conf /etc/nginx/sites-available/kol-lens.conf
sudo ln -sf /etc/nginx/sites-available/kol-lens.conf /etc/nginx/sites-enabled/kol-lens.conf
sudo rm -f /etc/nginx/sites-enabled/default
sudo systemctl daemon-reload
sudo systemctl enable --now kol-lens.service
sudo nginx -t
sudo systemctl reload nginx
```

Useful checks:

```bash
systemctl status kol-lens --no-pager
curl -I http://127.0.0.1:5001/api/health
curl -I http://127.0.0.1/api/health
journalctl -u kol-lens -n 100 --no-pager
```
