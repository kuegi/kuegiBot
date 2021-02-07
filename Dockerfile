FROM python:alpine as build-env

# set the working directory in the container
WORKDIR /code

RUN apk add --no-cache build-base linux-headers wget

RUN python3 -m venv /venv

# copy the dependencies file to the working directory
COPY requirements.txt .
COPY Binance_Futures_python ./Binance_Futures_python

# install dependencies
RUN /venv/bin/pip install -r requirements.txt

RUN cd Binance_Futures_python && /venv/bin/python3 setup.py install


FROM python:alpine

EXPOSE 8282

RUN apk add --no-cache bash shadow lighttpd sudo

RUN  echo "**** create abc user ****" && \
 groupmod -g 1000 users && \
 useradd -u 911 -U -d /app -s /bin/false abc && \
 usermod -G users abc

COPY --from=build-env /venv /venv
# copy the content of the local src directory to the working directory
COPY ./docker /
COPY . /app
COPY ./history_crawler.py /app/
COPY ./dashboard /var/www

VOLUME /settings
VOLUME /logs

# command to run on container start
CMD [ "/bot.sh" ]
