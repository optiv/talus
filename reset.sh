#!/bin/sh

sudo stop talus_master
sudo stop talus_slave
sudo stop talus_web
sudo stop talus_amqp
sudo stop talus_db

echo sleeping for 10s
sleep 10

sudo kill -KILL $(ps aux | grep slave | grep -v grep | awk '{print $2}')
sudo kill -KILL $(ps aux | grep master | grep -v grep | awk '{print $2}')

sudo start talus_db
sudo start talus_amqp

echo sleeping for db to startup
sleep 20s

sudo start talus_web
sudo start talus_master
sudo start talus_slave

echo "should be good now..."

sleep 5
echo MASTER
echo MASTER
echo MASTER
echo MASTER
echo MASTER
sudo tail -n 30 /var/log/upstart/talus_master.conf

echo SLAVE
echo SLAVE
echo SLAVE
echo SLAVE
echo SLAVE
sudo tail -n 30 /var/log/upstart/talus_slave.conf
