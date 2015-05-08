#!/bin/bash

mkdir -p /talus/logs/mongodb || true
mkdir -p /talus/data/mongodb || true

(sleep 10 ; echo 'cfg={"_id" :"rs0", "version": 1, "members": [{"_id": 0, "host": "talus_db:27017"}]}; rs.initiate(cfg) ; rs.reconfig(cfg, {force:true}) ; rs.slaveOk();' | mongo) &

mongod \
	--logpath /talus/logs/mongodb/mongodb.log \
	--dbpath /talus/data/mongodb \
	--replSet rs0
