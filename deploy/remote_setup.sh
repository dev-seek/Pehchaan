#!/usr/bin/env bash
# Runs ON the server as root, from deploy/release.sh. Installs the release in /tmp/pehchaan-release and restarts the app.
# Secrets are never handled here: they live only in /etc/pehchaan/secrets.env (root, mode 600).
set -euo pipefail

HOST="$1"
RELEASE=/tmp/pehchaan-release
BASE=/opt/pehchaan
export DEBIAN_FRONTEND=noninteractive

if ! command -v caddy >/dev/null || ! command -v ffmpeg >/dev/null || ! [ -x /usr/bin/python3 ] || ! dpkg -s python3-venv >/dev/null 2>&1; then
  apt-get update -qq
  apt-get install -y -qq python3-venv ffmpeg caddy >/dev/null
fi
id pehchaan >/dev/null 2>&1 || useradd --system --home-dir "$BASE" --shell /usr/sbin/nologin pehchaan
install -d -m 755 "$BASE"
install -d -m 750 -o pehchaan -g pehchaan "$BASE/state"
install -d -m 700 /etc/pehchaan
[ -f /etc/pehchaan/secrets.env ] || install -m 600 /dev/null /etc/pehchaan/secrets.env

[ -d "$BASE/venv" ] || python3 -m venv "$BASE/venv"
"$BASE/venv/bin/pip" install -q --disable-pip-version-check -r "$RELEASE/requirements.txt"

rm -rf "$BASE/app.new"
cp -a "$RELEASE" "$BASE/app.new"
ln -s "$BASE/state" "$BASE/app.new/.cache"
chown -R root:root "$BASE/app.new"
chmod -R go-w "$BASE/app.new"
rm -rf "$BASE/app.old"
[ -d "$BASE/app" ] && mv "$BASE/app" "$BASE/app.old"
mv "$BASE/app.new" "$BASE/app"

install -m 644 "$BASE/app/deploy/pehchaan.service" /etc/systemd/system/pehchaan.service
sed "s/__HOST__/$HOST/" "$BASE/app/deploy/Caddyfile" > /etc/caddy/Caddyfile
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1
systemctl daemon-reload
systemctl enable --now caddy >/dev/null 2>&1
systemctl reload caddy
systemctl enable pehchaan >/dev/null 2>&1
systemctl restart pehchaan

for _ in $(seq 1 40); do
  curl -fsS -o /dev/null http://127.0.0.1:8000/api/health && { rm -rf "$RELEASE"; echo "app is up"; exit 0; }
  sleep 0.5
done
journalctl -u pehchaan -n 25 --no-pager | cut -c1-160
exit 1
