#!/bin/sh

PUID=${PUID:-911}
PGID=${PGID:-911}

groupmod -o -g "$PGID" abc
usermod -o -u "$PUID" abc


chown -R abc:abc /history

sudo -u abc /venv/bin/python3 -u /app/history_crawler.py $1 $2
