FROM ubuntu:18.04
MAINTAINER "Alaska Satellite Facility"

ENTRYPOINT ["apachectl", "-DFOREGROUND"]

RUN apt-get update
RUN apt-get install -y apache2 libssl-dev libapache2-mod-wsgi apache2-dev python3 python3-pip

COPY requirements.txt /tmp/requirements.txt
RUN pip3 install -r /tmp/requirements.txt

COPY urs /tmp/urs
RUN cd /tmp/urs && apxs -i -c -n mod_auth_urs mod_auth_urs.c mod_auth_urs_cfg.c mod_auth_urs_session.c mod_auth_urs_ssl.c mod_auth_urs_http.c mod_auth_urs_json.c mod_auth_urs_crypto.c

RUN a2enmod rewrite
RUN a2enmod ssl

RUN mkdir -p /var/tmp/urs/session
RUN chgrp -R www-data /var/tmp/urs
RUN chown -R www-data /var/tmp/urs

COPY src /var/www/

COPY conf/apache2.conf /etc/apache2/apache2.conf
