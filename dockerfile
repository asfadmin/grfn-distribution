FROM ubuntu:16.04
MAINTAINER "Alaska Satellite Facility"

ENTRYPOINT ["apachectl", "-DFOREGROUND"]

RUN apt-get update
RUN apt-get install -y apache2 libssl-dev libapache2-mod-wsgi apache2-dev python python-pip

COPY requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

COPY urs /tmp/urs
RUN cd /tmp/urs && apxs -i -c -n mod_auth_urs mod_auth_urs.c mod_auth_urs_cfg.c mod_auth_urs_session.c mod_auth_urs_ssl.c mod_auth_urs_http.c mod_auth_urs_json.c mod_auth_urs_crypto.c

RUN a2enmod rewrite
RUN mkdir -p /var/tmp/urs/session

COPY src /var/www/

COPY conf/door_config.yaml /var/www/door/door_config.yaml
COPY conf/apache.conf /etc/apache2/apache2.conf
