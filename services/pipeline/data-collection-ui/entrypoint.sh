#!/usr/bin/env sh

# If a .env file exists in /tmp, source it
if [ -f /tmp/.env ]; then
    set -a
    . /tmp/.env
    set +a
fi

exec npm run start
