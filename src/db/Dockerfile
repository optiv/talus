# sudo docker build -t talus_db .

FROM ubuntu:14.04

RUN apt-get update
RUN apt-get upgrade -y

RUN apt-key adv --keyserver hkp://keyserver.ubuntu.com:80 --recv 7F0CEB10
RUN echo "deb http://repo.mongodb.org/apt/ubuntu "$(lsb_release -sc)"/mongodb-org/3.0 multiverse" | tee /etc/apt/sources.list.d/mongodb-org-3.0.list
RUN apt-get update
RUN apt-get install -y mongodb-org mongodb-org-server mongodb-org-shell mongodb-org-mongos mongodb-org-tools

EXPOSE 27017

ADD startup.sh /startup.sh

CMD []
ENTRYPOINT ["/startup.sh"]
