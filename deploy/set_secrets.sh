#!/usr/bin/env bash
# Put the demo passcode and (unless --passcode-only) the OpenAI key on the server, then restart the app.
# Values travel over SSH on stdin and land in a root-only file. They are never printed or written to the repository.
# The passcode is kept in ~/.pehchaan/demo_passcode so you can hand it to judges.
set -euo pipefail
set +x

cd "$(git rev-parse --show-toplevel)"
export AWS_PROFILE="${AWS_PROFILE:-pehchaan}" AWS_REGION="${AWS_REGION:-us-west-2}" AWS_PAGER=""
STATE_DIR="$HOME/.pehchaan"
# shellcheck disable=SC1091
source "$STATE_DIR/deploy.env"
PASS_FILE="$STATE_DIR/demo_passcode"
umask 077
[ -s "$PASS_FILE" ] || openssl rand -hex 9 > "$PASS_FILE"

KEY=""
if [ "${1:-}" != "--passcode-only" ]; then
  KEY="${OPENAI_API_KEY:-}"
  if [ -z "$KEY" ] && [ -f .env ]; then
    KEY="$(sed -n 's/^[[:space:]]*OPENAI_API_KEY[[:space:]]*=[[:space:]]*//p' .env | tail -1 | tr -d "\"'[:space:]")"
  fi
  [ -n "$KEY" ] || { echo "No OPENAI_API_KEY found in your shell or .env. Nothing was changed."; exit 1; }
fi

MY_IP="$(curl -fsS https://checkip.amazonaws.com | tr -d '[:space:]')/32"
SSH=(ssh -i "$STATE_DIR/deploy-key.pem" -o StrictHostKeyChecking=accept-new -o "UserKnownHostsFile=$STATE_DIR/known_hosts"
     -o ConnectTimeout=8 "ubuntu@$PUBLIC_IP")
close_ssh() {
  aws ec2 revoke-security-group-ingress --group-id "$SG_ID" --protocol tcp --port 22 --cidr "$MY_IP" >/dev/null 2>&1 || true
}
trap close_ssh EXIT
aws ec2 authorize-security-group-ingress --group-id "$SG_ID" --protocol tcp --port 22 --cidr "$MY_IP" >/dev/null 2>&1 || true
for _ in $(seq 1 20); do "${SSH[@]}" true 2>/dev/null && break; sleep 2; done

{
  printf 'DEMO_PASSCODE=%s\n' "$(cat "$PASS_FILE")"
  [ -z "$KEY" ] || printf 'OPENAI_API_KEY=%s\n' "$KEY"
} | "${SSH[@]}" 'sudo bash -c '"'"'
  umask 077; new=$(mktemp); cat > "$new"
  grep -q "^OPENAI_API_KEY=" "$new" || grep "^OPENAI_API_KEY=" /etc/pehchaan/secrets.env >> "$new" || true
  install -m 600 -o root -g root "$new" /etc/pehchaan/secrets.env; rm -f "$new"
  systemctl restart pehchaan
'"'"''
unset KEY
for _ in $(seq 1 30); do curl -fsS -o /dev/null "https://$HOST/health" && break; sleep 1; done
echo "Secrets are on the server. Passcode file: $PASS_FILE"
[ "${1:-}" = "--passcode-only" ] || node deploy/verify_live.mjs "https://$HOST"
