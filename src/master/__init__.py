#!/usr/bin/env python
# encoding: utf-8

"""
"""

from __future__ import absolute_import

import glob
import json
import logging
import netifaces
import os
import pymongo
import signal
import sys
import threading

import master.models
from master.models import *
from master.lib.mongo_oplog_watcher import OplogWatcher, OplogPrinter
from master.lib.amqp_man import AmqpManager
import master.watchers

logging.basicConfig(level=logging.DEBUG)

def _signal_handler(signum, frame):
	"""Shut down the running Master worker

	:signum: Signal number (e.g. signal.SIGINT, etc)
	:frame: Python frame (I think)
	:returns: None

	"""
	print("handling signal")
	Master.instance().stop()

def _install_sig_handlers():
	"""Install signal handlers
	"""
	print("installing signal handlers")
	signal.signal(signal.SIGINT, _signal_handler)
	signal.signal(signal.SIGTERM, _signal_handler)

class TalusDBWatcher(OplogWatcher):
	"""A class to watch the mongodb for changes"""

	def __init__(self, parent_log=None, *args, **kwargs):
		"""docstring for TalusDBWatcher constructor
		
		:db: database name, default to "talus"
		:collection: name of the collection to filter on, default to ``None``
		"""
		threading.Thread.__init__(self)
		OplogWatcher.__init__(self, *args, **kwargs)

		# { <mod_name>: [watchers], ... }
		self._watchers = {}

		if parent_log is None:
			self._log  = logging.getLogger("DB-WATCH")
		else:
			self._log = parent_log.getChild("DB-WATCH")
	
	def run(self):
		self._log.info("running")
		super(TalusDBWatcher, self).run()

		for collection,watchers in self._watchers.iteritems():
			for watcher in watchers:
				watcher.stop()
	
	def stop(self):
		"""Stop the database watcher
		:returns: TODO

		"""
		self._log.info("stopping")
		self._running.clear()
	
	def add_watcher(self, collection, watcher):
		self._watchers.setdefault(collection, []).append(watcher)
	
	def insert(self, ns, ts, id, obj, raw, **kwargs):
		"""Handle new insertions into the database

		:ns: TODO
		:ts: TODO
		:id: TODO
		:obj: TODO
		:raw: TODO
		:**kwargs: TODO
		:returns: TODO

		"""
		self._log.info("watched insert in {}: {}".format(ns, id))
		self._log.debug("received insert: {}".format(obj))

		if ns in self._watchers:
			for watcher in self._watchers[ns]:
				watcher.insert(id, obj)

	def update(self, ns, ts, id, mod, raw, **kwargs):
		"""Handle new updates in the database

		:ns: TODO
		:ts: TODO
		:id: TODO
		:mod: TODO
		:raw: TODO
		:**kwargs: TODO
		:returns: TODO

		"""
		self._log.info("update for {}:{}".format(ns, id))
		self._log.debug("modification: {}".format(mod))

		if ns in self._watchers:
			for watcher in self._watchers[ns]:
				watcher.update(id, mod)

	def delete(self, ns, ts, id, raw, **kwargs):
		"""Handle new deletions in the database

		:ns: TODO
		:ts: TODO
		:id: TODO
		:raw: TODO
		:**kwargs: TODO
		:returns: TODO

		"""
		self._log.info("watched delete in {}: {}".format(ns, id))

		if ns in self._watchers:
			for watcher in self._watchers[ns]:
				watcher.delete(id)

class Master(object):
	"""The master class watches the database for changes, queues and handles amqp messages,
	and handles VM image conversions"""

	AMQP_BROADCAST_XCHG = "broadcast"
	AMQP_SLAVE_QUEUE = "slaves"
	AMQP_SLAVE_STATUS_QUEUE = "slave_status"

	# -------------------------
	# class methods
	# -------------------------

	_instance = None

	@classmethod
	def instance(cls):
		"""Return the singleton instance of the Master class
		:returns: TODO

		"""
		if cls._instance is None:
			cls._instance = cls()
		return cls._instance

	def __init__(self):
		"""docstring for Master constructor"""
		super(Master, self).__init__()

		self._log = logging.getLogger(self.__class__.__name__)

		# this will be set when the docker container is linked to talus_db
		self._db_conn_info = os.environ["TALUS_DB_PORT_27017_TCP"].replace("tcp://", "")

		self._running = threading.Event()
		self._watcher = None
		self._amqp_man = AmqpManager.instance()
		
		# TODO need a better way than just eth0
		self._ip = netifaces.ifaddresses('eth0')[2][0]['addr']

		self._log.info("ready")

	# -------------------------
	# public functions
	# -------------------------
	
	def run(self):
		"""Run the master daemon
		:returns: TODO

		"""
		self._log.info("running")
		self._running.set()
		self._start_watcher()
		self._log.info("started watcher")

		self._amqp_man.do_start()
		self._amqp_listen_for_slaves()

		# stupid GIL
		while self._watcher.is_alive():
			self._watcher.join(2**32)

		self._shutdown_singletons()

		self._log.info("done running")

	def stop(self):
		"""Stop the master service from running
		:returns: TODO

		"""
		self._log.info("stopping")
		self._running.clear()
		self._watcher.stop()
	
	def handle_signal(self, sig, frame):
		"""TODO: Docstring for handle_signal.

		:sig: TODO
		:frame: TODO
		:returns: TODO

		"""
		self.stop()
	
	# -------------------------
	# private functions
	# -------------------------

	def _amqp_listen_for_slaves(self):
		"""Setup amqp queues to listen/respond to slaves
		"""
		self._amqp_man.declare_exchange(
			self.AMQP_BROADCAST_XCHG,
			"fanout"
		)
		self._amqp_man.declare_queue(self.AMQP_SLAVE_QUEUE,
			durable		= True,
			auto_delete	= False,
			exclusive	= False
		)
		self._amqp_man.declare_queue(self.AMQP_SLAVE_STATUS_QUEUE,
			durable		= True,
			auto_delete	= False,
			exclusive	= False
		)
		self._amqp_man.consume_queue(self.AMQP_SLAVE_STATUS_QUEUE, self._on_slave_status)
	
	def _on_slave_status(self, channel, method, props, body):
		"""Slaves will respond to commands/queries via this queue. Slaves
		will also send an initial connection message via this queue
		in order to get configuration details and report basic stats
		"""
		self._amqp_man.ack_method(method)

		data = json.loads(body)
		switch = dict(
			new			= self._handle_slave_new,
			status		= self._handle_slave_status,
			heartbeat	= self._handle_slave_heartbeat,
		)

		if "type" not in data or data["type"] not in switch:
			self._log.warn("recieved slave data is in the wrong format")
		else:
			switch[data["type"]](data)
	
	def _handle_slave_status(self, data):
		"""Handle slave status messages"""
		if "uuid" not in data:
			self._log.warn("got a slave status message that does not include a uuid")
			self._log.debug(data)
			return

		uuid = data["uuid"]
		self._log.info("got slave status update message")

		slaves = Slave.objects(uuid=uuid)
		if len(slaves) == 0:
			self._log.warn("got a slave status message that does not specify its uuid!")
			return

		slave = slaves[0]
		if "running_vms" in data:
			slave.running_vms = data["running_vms"]

		if "total_jobs_run" in data:
			slave.total_jobs_run = data["total_jobs_run"]

		if "vms" in data:
			slave.vms = data["vms"]

		slave.save()
	
	def _handle_slave_new(self, data):
		"""Handle new slave messages"""
		self._log.info("handling new slave message: {}".format(data))

		# these must be unique
		Slave.objects(
			#ip=data["ip"],
			hostname=data["hostname"]
		).delete()

		slave = Slave()
		slave.ip = data["ip"]
		slave.hostname = data["hostname"]
		slave.uuid = data["uuid"]
		slave.save()

		self._amqp_man.queue_msg(
			json.dumps(dict(
				type		= "config",
				db			= self._ip,
				code		= dict(
					loc		= "http://{}/code_cache".format(self._ip),

					# TODO put these in a config file
					username	= "talus_job",
					password	= "Monkeys eat bananas and poop all day."
				),
				image_url	= "http://{}/images/".format(self._ip)
			)),
			self.AMQP_SLAVE_QUEUE + "_" + slave.uuid
		)
	
	def _handle_slave_heartbeat(self, data):
		"""Handle slave heartbeats"""
		self._log.info("handling slave heartbeat: {}".format(data))

	def _shutdown_singletons(self):
		self._log.info("shutting down singletons")
		AmqpManager.instance().stop()

	def _start_watcher(self):
		"""Create and start the DB watcher
		:returns: TODO

		"""
		self._watcher = TalusDBWatcher(
			parent_log	= self._log,
			connection	= pymongo.MongoClient(self._db_conn_info.split(":")[0], 27017)
		)
		self._watcher.start()

		# import all of the DB watchers defined in master/watchers/
		for filename in glob.glob(os.path.join(os.path.dirname(__file__), "watchers", "*.py")):
			if os.path.basename(filename) == "__init__.py":
				continue

			mod_name = os.path.basename(filename).replace(".py", "")
			mod_base = __import__("master.watchers", globals(), locals(), fromlist=[mod_name])
			mod = getattr(mod_base, mod_name)
			
			for name in dir(mod):
				item = getattr(mod, name)
				if type(item) is not type:
					continue
				if item != master.watchers.WatcherBase and issubclass(item, master.watchers.WatcherBase):
					watcher = getattr(mod, name)(self._log)
					self._watcher.add_watcher(watcher.collection, watcher)
	
def main():
	_install_sig_handlers()

	master.models.do_connect()

	m = Master.instance()
	m.run()

if __name__ == "__main__":
	main()
