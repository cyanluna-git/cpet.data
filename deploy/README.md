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

## 4. Create Published Directory

```bash
mkdir -p /home/ubuntu/cpet.db/published
```

Place static HTML reports here. They become accessible at:

```
https://cpet.cyanluna.com/report/<filename>.html
```

## 5. FastAPI Systemd Service

Create `/etc/systemd/system/cpet-api.service`:

```ini
[Unit]
Description=CPET FastAPI
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/cpet.db/backend
ExecStart=/home/ubuntu/cpet.db/backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8100
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now cpet-api
```

## 6. Claude Code tmux Session

For interactive Claude Code sessions on the VM:

```bash
tmux new -s claude
cd /home/ubuntu/cpet.db
claude
# Detach: Ctrl-b d
# Reattach: tmux attach -t claude
```

## 7. Verify

```bash
# HTTP redirect
curl -I http://cpet.cyanluna.com

# HTTPS API
curl -s https://cpet.cyanluna.com/docs | head -5

# Static report
curl -I https://cpet.cyanluna.com/report/
```

## 8. Maintenance

### Log locations

```bash
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
sudo journalctl -u cpet-api -f
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
