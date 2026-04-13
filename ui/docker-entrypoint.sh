#!/bin/sh
set -eu

: "${SRE_UI_API_UPSTREAM:=http://sre-agent:8000}"
export SRE_UI_API_UPSTREAM

envsubst '$SRE_UI_API_UPSTREAM' \
  < /etc/nginx/templates/default.conf.template \
  > /etc/nginx/conf.d/default.conf

exec /docker-entrypoint.sh "$@"
