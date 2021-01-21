Setup 
=====

Build the docker image
----------------------
```
docker build -t kuegibot .
```


Define the docker containers         
----------------------------
The easiest way to setup the container is by using docker-compose.

### Volumes

- /settings - the path to your defaults.json and settings.json 
- /logs - the bot logoutput if defined
- /history - output of the history crawler

### Environment variables
- PUID - current user id
- PGID - current group id 


```yaml

version: '3.4'
services:
  kuegibot:
    image: kuegibot
    container_name: kuegibot
    restart: always
    ports:
      - 8282:8282
    volumes:
      - ./data/kuegibot/settings:/settings
      - ./data/kuegibot/logs:/logs
    environment:
      - PUID=1000
      - PGID=1000


  kuegibot_history:
    image: kuegibot
    container_name: kuegibot_history
    command: /history.sh bybit
    restart: "no"
    volumes:
      - ./data/kuegibot/history:/history
    environment:
      - PUID=1000
      - PGID=1000
```

Start them
----------
```
docker-compose up -d kuegibot
docker-compose up -d kuegibot_history
```

After that, the dashboard is available at http://<yourip>:8282

