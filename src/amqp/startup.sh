#!/bin/bash

mkdir -p /talus/logs/rabbitmq
chown rabbitmq:rabbitmq /talus/logs/rabbitmq

mkdir -p /talus/data/rabbitmq
chown rabbitmq:rabbitmq /talus/data/rabbitmq

rabbitmq-server 2>&1 >> /talus/logs/rabbitmq/output.log
