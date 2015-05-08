#!/usr/bin/env python
# encoding: utf-8

import json
import logging
import netifaces
import os
import pika
import pymongo
import sh
import signal
import socket
import sys
import threading
import twisted
from twisted.internet import protocol, reactor, endpoints
import time
import uuid

from slave.amqp_man import AmqpManager
from slave.vm import VMHandler,ImageManager
import slave.models

logging.basicConfig(level=logging.DEBUG)

logging.getLogger("sh").setLevel(logging.INFO)
logging.getLogger("sh.stream_bufferer").setLevel(logging.INFO)
logging.getLogger("sh.command").setLevel(logging.INFO)
logging.getLogger("sh.command.process").setLevel(logging.INFO)
logging.getLogger("sh.command.process.stream_writer").setLevel(logging.INFO)
logging.getLogger("sh.config.process").setLevel(logging.INFO)

def _signal_handler(signum, frame):
	"""Shut down the running Master worker

	:signum: Signal number (e.g. signal.SIGINT, etc)
	:frame: Python frame (I think)
	:returns: None

	"""
	print("handling signal")
	Slave.instance().stop()

def _install_sig_handlers():
	"""Install signal handlers
	"""
	print("installing signal handlers")
	signal.signal(signal.SIGINT, _signal_handler)
	signal.signal(signal.SIGTERM, _signal_handler)

class GuestComms(object):
	"""Communicates with the guest hosts as they start running"""
	def dataReceived(self, data):
		data = json.loads(data)
		res = Slave.instance().handle_guest_comms(data)
		self.transport.write(res)

class GuestCommsFactory(protocol.Factory):
	def buildProtocol(self, addr):
		return GuestComms()

class Slave(object):
	"""The slave handler"""

	AMQP_JOB_QUEUE = "jobs"
	AMQP_JOB_STATUS_QUEUE = "job_status"
	AMQP_JOB_PROPS = dict(
		durable		= True,
		auto_delete = False,
		exclusive	= False
	)

	AMQP_SLAVE_QUEUE = "slaves"
	AMQP_SLAVE_STATUS_QUEUE = "slave_status"
	AMQP_SLAVE_PROPS = dict(
		durable		= True,
		auto_delete = False,
		exclusive	= False
	)

	_INSTANCE = None
	@classmethod
	def instance(cls, amqp_host=None, max_vms=None):
		if cls._INSTANCE is None:
			cls._INSTANCE = cls(amqp_host, max_vms)
		return cls._INSTANCE

	def __init__(self, amqp_host, max_vms):
		"""Init the slave"""
		self._max_vms_lock = threading.Semaphore(max_vms)

		self._amqp_host = amqp_host
		self._log = logging.getLogger("Slave")

		self._running = threading.Event()
		self._slave_config_received = threading.Event()

		self._amqp_man = AmqpManager.instance(self._amqp_host)
		self._image_man = ImageManager.instance()

		self._uuid = str(uuid.uuid4())
		self._ip = netifaces.ifaddresses('eth0')[2][0]['addr']
		self._hostname = socket.gethostname()

		# these will be set by the config amqp message
		# see the _handle_config method
		self._db_host = None
		self._code_loc = None

		self._already_consuming = False

		self._handlers = []
		self._total_jobs_run = 0

	def run(self):
		self._running.set()
		self._log.info("running")

		self._amqp_man.declare_queue(self.AMQP_JOB_QUEUE, **self.AMQP_JOB_PROPS)
		self._amqp_man.declare_queue(self.AMQP_JOB_STATUS_QUEUE, **self.AMQP_JOB_PROPS)

		self._amqp_man.declare_queue(self.AMQP_SLAVE_QUEUE, **self.AMQP_SLAVE_PROPS)
		self._amqp_man.declare_queue(self.AMQP_SLAVE_STATUS_QUEUE, **self.AMQP_SLAVE_PROPS)
		self._amqp_man.declare_queue(self.AMQP_SLAVE_QUEUE + "_" + self._uuid, **self.AMQP_SLAVE_PROPS)
		self._amqp_man.do_start()
		self._amqp_man.wait_for_ready()

		self._amqp_man.queue_msg(
			json.dumps(dict(
				type		= "new",
				uuid		= self._uuid,
				ip			= self._ip,
				hostname	= self._hostname
			)),
			self.AMQP_SLAVE_STATUS_QUEUE
		)

		self._amqp_man.consume_queue(self.AMQP_SLAVE_QUEUE, self._on_slave_all_received)
		self._amqp_man.consume_queue(self.AMQP_SLAVE_QUEUE + "_" + self._uuid, self._on_slave_me_received)

		self._log.info("waiting for slave config to be received")

		while self._running.is_set():
			time.sleep(0.2)

		self._log.info("finished")
	
	def stop(self):
		"""
		Stop the slave
		"""
		self._log.info("stopping!")
		self._amqp_man.stop()
		self._running.clear()

		for handler in self._handlers:
			handler.stop()
	
	# -----------------------
	# guest comms
	# -----------------------

	def handle_guest_comms(self, data):
		if "type" not in data:
			self._log.warn("type not found in guest comms data: {}".format(data))
			return "{}"

		if "mac" not in data:
			self._log.warn("guest comms did not define a mac address")
			return "{}"

		handler = self._handler_macs[data["mac"]]
		return handler.handle_comms(data)
	
	# -----------------------
	# amqp stuff
	# -----------------------

	def _on_job_received(self, channel, method, properties, body):
		"""
		"""
		self._log.info("received job from queue: {}".format(body))
		self._amqp_man.ack_method(method)

		data = json.loads(body)

		self._max_vms_lock.acquire()

		handler = VMHandler(
			job			= data["job"],
			idx			= data["idx"],
			image		= data["image"],
			tool		= data["tool"],
			params		= data["params"],
			code_loc	= self._code_loc,
			on_finished	= self._on_vm_handler_finished
		)

		self._handlers.append(handler)
		handler.start()

		self._update_status()
	
	def _on_vm_handler_finished(self, handler):
		"""
		Handle a finished VM handler
		"""
		self._log.debug("The VM handler {} for job {} has finished".format(handler, handler.job))
		del self._handlers[self._handlers.index(handler)]
		self._max_vms_lock.release()

		self._total_jobs_run += 1
		self._update_status()
	
	def _on_slave_all_received(self, channel, method, properties, body):
		"""
		"""
		self._log.info("received slave all msg from queue: {}".format(body))

		data = json.loads(body)

		self._amqp_man.ack_method(method)

	def _on_slave_me_received(self, channel, method, properties, body):
		"""
		"""
		self._log.info("received slave me msg from queue: {}".format(body))

		data = json.loads(body)

		switch = dict(
			config	= self._handle_config
		)

		if "type" not in data or data["type"] not in switch:
			self._log.debug("malformed data received on me slave queue: {}".format(body))
		else:
			switch[data["type"]](data)
		self._amqp_man.ack_method(method)
	
	def _handle_config(self, data):
		self._log.info("handling config: {}".format(data))

		if "db" in data:
			self._log.info("connecting to mongodb at {}".format(data["db"]))
			self._db_host = data["db"]
			slave.models.do_connect(self._db_host)

		if "code" in data:
			self._log.info("setting code location to {}".format(data["code"]))
			self._code_loc = data["code"]

		if "image_url" in data:
			self._log.info("setting image url to {}".format(data["image_url"]))
			self._image_url = data["image_url"]
			self._image_man.instance().image_url = self._image_url

		if not self._already_consuming:
			self._amqp_man.consume_queue(self.AMQP_JOB_QUEUE, self._on_job_received)
			self._already_consuming = True
	
	# -----------------------

	def _update_status(self):
		self._amqp_man.queue_msg(
			json.dumps(dict(
				type			= "status",
				uuid			= self._uuid,
				running_vms		= len(self._handlers),
				total_jobs_run	= self._total_jobs_run
			)),
			self.AMQP_SLAVE_STATUS_QUEUE
		)

def main(amqp_host, max_vms):
	#_install_sig_handlers()

	endpoints.serverFromString(reactor, "tcp:55555").listen(GuestCommsFactory())

	slave = Slave.instance(amqp_host, max_vms)
	reactor.callWhenRunning(slave.run)
	reactor.addSystemEventTrigger("during", "shutdown", Slave.instance().stop)
	reactor.run()

if __name__ == "__main__":
	if len(sys.argv) < 3:
		sys.stderr.write("USAGE: {} <AMQP_HOST> <MAX_VMS>\n")
		exit(1)

	main(sys.argv[1], sys.argv[2])
