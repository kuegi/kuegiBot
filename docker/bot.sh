#!/bin/sh

PUID=${PUID:-911}
PGID=${PGID:-911}

groupmod -o -g "$PGID" abc
usermod -o -u "$PUID" abc

chown -R abc:abc /app
chown -R abc:abc /var/www
chown -R abc:abc /settings
chown -R abc:abc /logs

sudo -u abc lighttpd -f /lighttpd.conf
sudo -u abc /venv/bin/python3 -u /app/cryptobot.py /settings/settings.json
