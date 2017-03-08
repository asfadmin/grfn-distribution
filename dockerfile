FROM ubuntu:16.04
MAINTAINER "Alaska Satellite Facility"

ENTRYPOINT ["/usr/sbin/apache2", "-DFOREGROUND"]

RUN apt-get update
RUN apt-get install -y apache2 libssl-dev libapache2-mod-wsgi apache2-dev

COPY requirements.txt /tmp/
RUN pip install -r /tmp/requirements.txt

COPY urs /tmp/
RUN cd /tmp/urs && apxs -i -c -n mod_auth_urs mod_auth_urs.c mod_auth_urs_cfg.c mod_auth_urs_session.c mod_auth_urs_ssl.c mod_auth_urs_http.c mod_auth_urs_json.c mod_auth_urs_crypto.c

COPY src/door /var/www/
COPY src/html /var/www/

COPY conf/door_config.yaml /var/www/door/
COPY conf/apache.conf /etc/apache2/

RUN a2enmod rewrite

RUN mkdir -p /var/tmp/urs/session

