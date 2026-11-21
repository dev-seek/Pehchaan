#!/usr/bin/env bash
# Create the one small server Pehchaan runs on. Safe to run again: it reuses whatever already exists.
# Everything is tagged Project=pehchaan, so it can be listed and removed with deploy/aws_teardown.sh.
# State (ids, host name, SSH key) stays in ~/.pehchaan, outside the repository.
set -euo pipefail

export AWS_PROFILE="${AWS_PROFILE:-pehchaan}" AWS_REGION="${AWS_REGION:-us-west-2}" AWS_PAGER=""
STATE_DIR="$HOME/.pehchaan"
KEY_FILE="$STATE_DIR/deploy-key.pem"
KEY_NAME="pehchaan-deploy"
SG_NAME="pehchaan-web"
INSTANCE_TYPE="${INSTANCE_TYPE:-t3.small}"
TAGS='{Key=Project,Value=pehchaan},{Key=Name,Value=pehchaan-web}'

umask 077
mkdir -p "$STATE_DIR"

if ! aws ec2 describe-key-pairs --key-names "$KEY_NAME" >/dev/null 2>&1; then
  aws ec2 create-key-pair --key-name "$KEY_NAME" --key-type ed25519 \
    --tag-specifications "ResourceType=key-pair,Tags=[$TAGS]" --query KeyMaterial --output text > "$KEY_FILE"
  chmod 600 "$KEY_FILE"
fi

VPC_ID=$(aws ec2 describe-vpcs --filters Name=is-default,Values=true --query 'Vpcs[0].VpcId' --output text)
SG_ID=$(aws ec2 describe-security-groups --filters "Name=group-name,Values=$SG_NAME" "Name=vpc-id,Values=$VPC_ID" \
  --query 'SecurityGroups[0].GroupId' --output text)
if [ "$SG_ID" = "None" ]; then
  SG_ID=$(aws ec2 create-security-group --group-name "$SG_NAME" --description "Pehchaan public web, HTTP and HTTPS only" \
    --vpc-id "$VPC_ID" --tag-specifications "ResourceType=security-group,Tags=[$TAGS]" --query GroupId --output text)
  for port in 80 443; do
    aws ec2 authorize-security-group-ingress --group-id "$SG_ID" --protocol tcp --port "$port" --cidr 0.0.0.0/0 >/dev/null
  done
fi

INSTANCE_ID=$(aws ec2 describe-instances \
  --filters Name=tag:Project,Values=pehchaan Name=instance-state-name,Values=pending,running,stopped \
  --query 'Reservations[0].Instances[0].InstanceId' --output text)
if [ "$INSTANCE_ID" = "None" ]; then
  AMI=$(aws ssm get-parameter --name /aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id \
    --query Parameter.Value --output text)
  INSTANCE_ID=$(aws ec2 run-instances --image-id "$AMI" --instance-type "$INSTANCE_TYPE" --count 1 \
    --key-name "$KEY_NAME" --security-group-ids "$SG_ID" \
    --metadata-options HttpTokens=required,HttpPutResponseHopLimit=1,HttpEndpoint=enabled \
    --block-device-mappings 'DeviceName=/dev/sda1,Ebs={VolumeSize=20,VolumeType=gp3,Encrypted=true,DeleteOnTermination=true}' \
    --tag-specifications "ResourceType=instance,Tags=[$TAGS]" "ResourceType=volume,Tags=[$TAGS]" \
    --query 'Instances[0].InstanceId' --output text)
fi
aws ec2 wait instance-running --instance-ids "$INSTANCE_ID"

ALLOC_ID=$(aws ec2 describe-addresses --filters Name=tag:Project,Values=pehchaan --query 'Addresses[0].AllocationId' --output text)
if [ "$ALLOC_ID" = "None" ]; then
  ALLOC_ID=$(aws ec2 allocate-address --domain vpc \
    --tag-specifications "ResourceType=elastic-ip,Tags=[$TAGS]" --query AllocationId --output text)
fi
aws ec2 associate-address --instance-id "$INSTANCE_ID" --allocation-id "$ALLOC_ID" --allow-reassociation >/dev/null
PUBLIC_IP=$(aws ec2 describe-addresses --allocation-ids "$ALLOC_ID" --query 'Addresses[0].PublicIp' --output text)
HOST="${PUBLIC_IP//./-}.sslip.io"

cat > "$STATE_DIR/deploy.env" <<EOF
INSTANCE_ID=$INSTANCE_ID
SG_ID=$SG_ID
ALLOC_ID=$ALLOC_ID
PUBLIC_IP=$PUBLIC_IP
HOST=$HOST
EOF
echo "server ready: https://$HOST"
