#!/bin/sh
# Run from the deployment repository checkout. Jenkins supplies these values.
set -eu

: "DEPLOYMENT_FILE:?Set DEPLOYMENT_FILE to the target deployment.yaml}"
: "NEW_IMAGE:?Set NEW_IMAGE to the pushed repository:tag}"
test -f "$DEPLOYMENT_FILE"
case "$NEW_IMAGE" in
    ''|*[!A-Za-z0-9._:/-]*) echo 'Invalid image reference.' >&2; exit 1 ;;
esac

# This manifest has one application container. Refuse an ambiguous update.
image_count="$(awk '/^[[:space:]]*image:/ { count++ } END { print count+0 }' "$DEPLOYMENT_FILE")"
if [ "$image_count" -ne 1 ]; then
    echo 'Expected exactly one container image in the deployment.' >&2
    exit 1
fi
sed -i -E "s|^([[:space:]]*)image:.*|\1image: $NEW_IMAGE|" "$DEPLOYMENT_FILE"
