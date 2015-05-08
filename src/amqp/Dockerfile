# sudo build -t talus_amqp .

FROM ubuntu:14.04

RUN apt-get update
RUN apt-get install -y rabbitmq-server python-librabbitmq

# /logs needs to be mounted as a volume
ENV RABBITMQ_LOG_BASE /talus/logs/rabbitmq
ENV RABBITMQ_MNESIA_BASE /talus/data/rabbitmq

# rabbitmq port
EXPOSE 5672

ADD startup.sh /startup.sh

CMD []
ENTRYPOINT ["/startup.sh"]
