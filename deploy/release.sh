#!/usr/bin/env bash
# Ship the committed code (never the working tree) to the server, then close SSH again.
# The locked exam scripts are left out, so the public server physically cannot serve them.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"
export AWS_PROFILE="${AWS_PROFILE:-pehchaan}" AWS_REGION="${AWS_REGION:-us-west-2}" AWS_PAGER=""
STATE_DIR="$HOME/.pehchaan"
# shellcheck disable=SC1091
source "$STATE_DIR/deploy.env"
KEY_FILE="$STATE_DIR/deploy-key.pem"
MY_IP="$(curl -fsS https://checkip.amazonaws.com | tr -d '[:space:]')/32"
SSH=(ssh -i "$KEY_FILE" -o StrictHostKeyChecking=accept-new -o "UserKnownHostsFile=$STATE_DIR/known_hosts" -o ConnectTimeout=8
     "ubuntu@$PUBLIC_IP")

close_ssh() {
  aws ec2 revoke-security-group-ingress --group-id "$SG_ID" --protocol tcp --port 22 --cidr "$MY_IP" >/dev/null 2>&1 || true
}
trap close_ssh EXIT
aws ec2 authorize-security-group-ingress --group-id "$SG_ID" --protocol tcp --port 22 --cidr "$MY_IP" >/dev/null 2>&1 || true

for _ in $(seq 1 40); do "${SSH[@]}" true 2>/dev/null && break; sleep 3; done

"${SSH[@]}" 'sudo rm -rf /tmp/pehchaan-release && mkdir -p /tmp/pehchaan-release'
git archive --format=tar HEAD -- . ':(exclude)data/bench/test_scripts.jsonl' ':(exclude)data/bench/test_scripts.sha256' \
  ':(exclude)tests' ':(exclude)docs' | "${SSH[@]}" 'tar -x -C /tmp/pehchaan-release'
"${SSH[@]}" "sudo bash /tmp/pehchaan-release/deploy/remote_setup.sh '$HOST'"
echo "released $(git rev-parse --short HEAD) to https://$HOST"
