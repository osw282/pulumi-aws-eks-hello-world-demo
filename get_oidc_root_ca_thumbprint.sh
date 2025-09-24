#!/bin/bash

# This script is copied and modified from
# https://gist.github.com/riccardomc/a3891356b09516ab3f3b79a12e9b13e1
# Thanks to riccardomc for the script
set -e

if [ ! -z "$DEBUG" ] ; then
    set -x
fi

REGIONS="us-east-2
    us-east-1 
    us-west-1
    us-west-2
    ap-east-1
    ap-northeast-2
    ap-southeast-1
    ap-southeast-2
    ap-northeast-1
    eu-central-1
    eu-west-1
    eu-west-2
    eu-west-3
    eu-north-1
    me-south-1
    sa-east-1"

for REGION in $REGIONS ; do
    JWKS_URI="oidc.eks.${REGION}.amazonaws.com"

    # Extract all certificates in separate files
    # https://unix.stackexchange.com/questions/368123/how-to-extract-the-root-ca-and-subordinate-ca-from-a-certificate-chain-in-linux
    TEMP=$(mktemp -d -t oidc-eks-XXXX)
    openssl s_client -servername $JWKS_URI -showcerts -connect $JWKS_URI:443 < /dev/null 2>/dev/null | awk -v dir="$TEMP" '/-----BEGIN CERTIFICATE-----/,/-----END CERTIFICATE-----/{ if(/BEGIN/){a++}; out=dir"/cert00"a".crt"; print >out }'

    # Assume last found certificate in chain is the ROOT_CA
    ROOT_CA=$(ls -1 $TEMP/* | tail -1)

    # Extract SHA-1 fingerprint in desired format (no header, no colons)
    # AWS OIDC providers require SHA-1 thumbprints (40 characters)
    THUMBPRINT=$(openssl x509 -fingerprint -sha1 -noout -in $ROOT_CA | sed 's/^.*=//' | sed 's/://g')
    printf '{"%s": "%s"}\n' $REGION $THUMBPRINT
    rm -rf $TEMP
done