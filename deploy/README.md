# CPET Platform — Oracle Cloud VM Deployment

## Prerequisites

- Ubuntu 22.04+ on Oracle Cloud (ARM or x86)
- DNS A record: `cpet.cyanluna.com` pointing to the VM public IP
- Ports 80 and 443 open in OCI security list / iptables

## 1. Install Nginx + Certbot

```bash
sudo apt update && sudo apt install -y nginx certbot python3-certbot-nginx
```

## 2. Deploy Nginx Config

```bash
sudo cp deploy/nginx/cpet.conf /etc/nginx/sites-available/cpet.conf
sudo ln -sf /etc/nginx/sites-available/cpet.conf /etc/nginx/sites-enabled/cpet.conf
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
```

## 3. SSL Certificate (Let's Encrypt)

```bash
sudo certbot --nginx -d cpet.cyanluna.com --non-interactive --agree-tos -m admin@cyanluna.com
```

Certbot auto-installs a systemd timer for renewal. Verify:

```bash
sudo systemctl list-timers | grep certbot
```

## 4. Create Runtime Directories

```bash
mkdir -p /home/ubuntu/cpet.db/data /home/ubuntu/cpet.db/published
```

Generated reports are published here and become accessible at:

```
https://cpet.cyanluna.com/report/<slug>/
```

## 5. FastAPI Systemd Service

Create `/etc/systemd/system/cpet-api.service`:

```ini
[Unit]
Description=CPET FastAPI
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/cpet.db
EnvironmentFile=/home/ubuntu/cpet.db/.env
ExecStart=/home/ubuntu/cpet.db/.venv/bin/python -m uvicorn server.main:app --host 127.0.0.1 --port 8100
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now cpet-api
```

## 6. Channel Webhook Systemd Service

Create `/etc/systemd/system/cpet-channel.service`:

```ini
[Unit]
Description=CPET Claude Channel Webhook
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/cpet.db/channel
EnvironmentFile=/home/ubuntu/cpet.db/.env
ExecStart=/home/ubuntu/.bun/bin/bun run webhook.ts
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now cpet-channel
```

## 7. Claude Code tmux Session

For interactive Claude Code sessions on the VM:

```bash
tmux new -s claude
cd /home/ubuntu/cpet.db
claude
# Detach: Ctrl-b d
# Reattach: tmux attach -t claude
```

## 8. Verify

```bash
# HTTP redirect
curl -I http://cpet.cyanluna.com

# HTTPS API
curl -s https://cpet.cyanluna.com/docs | head -5

# Channel health
curl -s http://127.0.0.1:8788/health
```

## 9. Maintenance

### Log locations

```bash
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
sudo journalctl -u cpet-api -f
sudo journalctl -u cpet-channel -f
```

### SSL auto-renewal

Certbot's systemd timer handles renewal automatically. Test manually:

```bash
sudo certbot renew --dry-run
```

### Nginx config changes

```bash
sudo nginx -t && sudo systemctl reload nginx
```
