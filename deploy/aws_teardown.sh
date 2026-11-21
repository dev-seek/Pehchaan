#!/usr/bin/env bash
# Remove everything deploy/aws_create.sh made, and nothing else. It lists the targets and asks before deleting.
set -euo pipefail

export AWS_PROFILE="${AWS_PROFILE:-pehchaan}" AWS_REGION="${AWS_REGION:-us-west-2}" AWS_PAGER=""
# shellcheck disable=SC1091
source "$HOME/.pehchaan/deploy.env"
echo "Will delete: instance $INSTANCE_ID, Elastic IP $PUBLIC_IP, security group $SG_ID, key pair pehchaan-deploy"
read -r -p "Type DELETE to continue: " answer
[ "$answer" = "DELETE" ] || { echo "Nothing was deleted."; exit 1; }

aws ec2 terminate-instances --instance-ids "$INSTANCE_ID" >/dev/null
aws ec2 wait instance-terminated --instance-ids "$INSTANCE_ID"
aws ec2 release-address --allocation-id "$ALLOC_ID"
aws ec2 delete-security-group --group-id "$SG_ID"
aws ec2 delete-key-pair --key-name pehchaan-deploy
echo "Deleted."
