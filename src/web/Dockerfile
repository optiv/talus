# sudo docker build -t talus_web .

FROM ubuntu:14.04
MAINTAINER Optiv Research <research@accuvant.com>

# Update package list and upgrade
RUN apt-get update && \
    apt-get -y -q upgrade

# Install dependencies from apt
RUN apt-get install --no-install-recommends -q -y \
		apache2 \
		libapache2-mod-wsgi \
		python python-pip \
		python-dev \
		build-essential \
		git \
	&& apt-get purge -y --auto-remove python-dev build-essential \
	&& apt-get clean \
	&& rm -rf /tmp/* /var/tmp/* /var/lib/apt/lists/*

ADD startup.sh /startup.sh

ADD apache/000-default.conf /etc/apache2/sites-enabled/000-default.conf
ADD ./app /web
RUN pip install -r /web/requirements/production.txt
RUN cd /web \
	&& NO_CONNECT=1 python manage.py collectstatic --noinput

# Clean up
RUN apt-get purge -y --auto-remove \
        python-dev build-essential && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

CMD []
ENTRYPOINT ["/startup.sh"]
