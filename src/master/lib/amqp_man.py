#!/usr/bin/env python
# encoding: utf-8

import logging
import os
import threading
import time
import pika

pika_logger = logging.getLogger('pika')
pika_logger.setLevel(logging.CRITICAL)

class AmqpQueueHandler(threading.Thread):
	daemon = True

	def __init__(self, callback, queue_name, channel, lock, no_ack, running):
		super(AmqpQueueHandler, self).__init__()

		self.lock = lock
		self.channel = channel
		self.queue_name = queue_name
		self.callback = callback
		self.no_ack = no_ack
		self._running = running

		self._log = logging.getLogger("AmqpMan").getChild(self.queue_name)
	
	def run(self):
		self._running.set()
		self._log.debug("monitoring")

		while self._running.is_set():
			with self.lock:
				method, props, body = self.channel.basic_get(
					self.queue_name,
					no_ack=self.no_ack
				)
			if method is None:
				time.sleep(0.1)
				continue
			self._log.debug("recieved message")
			self.callback(self.channel, method, props, body)

		self._log.debug("finished")
	
	def stop(self):
		self._log.debug("stopping")
		self._running.clear()

class AmqpManager(threading.Thread):
	"""A class to manage jobs (starting/stopping/cancelling/etc)"""

	daemon = True

	AMQP_JOB_QUEUE = "jobs"
	AMQP_JOB_RESULT_QUEUE = "job_results"

	_INSTANCE = None
	@classmethod
	def instance(cls, host=None):
		if cls._INSTANCE is None:
			cls._INSTANCE = cls(host)
		return cls._INSTANCE

	def __init__(self, host=None):
		"""init the job manager
		"""
		super(AmqpManager, self).__init__()

		if host is None and "TALUS_AMQP_PORT_5672_TCP" in os.environ:
			host = os.environ["TALUS_AMQP_PORT_5672_TCP"].replace("tcp://", "")
		self._amqp_host = host

		self._amqp_conn = None
		self._amqp_channel = None

		self._running = threading.Event()
		self._amqp_connected = threading.Event()
		self._amqp_consume_thread = None
		self._log = logging.getLogger("AmqpMan")

		self._cached_exchange_declares = []
		self._cached_bind_queues = []
		self._cached_queue_declares = []
		self._cached_queue_consumes = []

		self._queue_props = {}
		self._queue_handlers = {}

		self._amqp_lock = threading.Lock()
		self._handlers_lock = threading.Lock()
	
	def do_start(self):
		if self._running.is_set():
			return
		self.start()
	
	def run(self):
		"""Run the job manager. Only one of these should ever be running at a time
		:returns: TODO

		"""
		self._log.info("running")
		self._running.set()

		self._amqp_connect()

		for exchange_name, type in self._cached_exchange_declares:
			self.declare_exchange(exchange_name, type)
		for queue_name, props in self._cached_queue_declares:
			self.declare_queue(queue_name, **props)
		for exchange_name, queue in self._cached_bind_queues:
			self.bind_queue(exchange_name, queue)
		for queue_name, callback, no_ack in self._cached_queue_consumes:
			self.consume_queue(queue_name, callback, no_ack=no_ack)

		self._amqp_ioloop()

		self._log.info("finished")
	
	def stop(self):
		"""Stop the job manager
		:returns: TODO

		"""
		self._log.info("stopping")
		if self._amqp_channel is not None:
			try:
				self._amqp_channel.stop_consuming()
			except RuntimeError as e:
				pass
			try:
				self._amqp_conn.close()
			except RuntimeError as e:
				pass
		self._running.clear()
		
	def get_message_count(self, queue_name, **props):
		""" Get the size of the amqp queue ``queue_name``. Note that the ``props``
		kwargs must match the declaration properties of the queue. Getting the
		queue size is done by redeclaring the queue with the same properties, with
		the additional ``passive=True`` property set.

		:queue_name: The name of the queue
		"""
		if len(props) is None and queue_name in self._queue_props:
			props = self._queue_props[queue_name]

		with self._amqp_lock:
			method = self._amqp_channel.queue_declare(queue_name, passive=True, **props)
		res = method.method.message_count
		return res
	
	def declare_exchange(self, name, type):
		"""Declare an exchange named ``name`` and of type ``type``
		"""
		self._log.info("declaring exchange {}, type {}".format(name, type))
		if self._amqp_channel is None:
			self._cached_exchange_declares.append((name, type))
		else:
			self._amqp_channel.exchange_declare(
				exchange=name,
				type=type
			)
	
	def bind_queue(self, exchange, queue):
		"""Bind the queue ``queue`` to the exchange ``exchange``
		"""
		self._log.info("binding queue {!r} to exchange {!r}".format(queue, exchange))
		if self._amqp_channel is None:
			self._cached_bind_queues.append((exchange, queue))
		else:
			self._amqp_channel.queue_bind( exchange=exchange,
				queue=queue
			)
	
	def declare_queue(self, queue_name, **props):
		"""Declare the queue ``queue_name`` with properties defined in
		``**props`` kwargs. Popular properties to set:

		* durable
		* exclusive
		* auto_delete
		"""
		self._log.info("declaring queue {}".format(queue_name))

		self._queue_props[queue_name] = props
		if self._amqp_channel is None:
			self._cached_queue_declares.append((queue_name, props))
		else:
			self._amqp_channel.queue_declare(
				queue_name,
				**props
			)
	
	def consume_queue(self, queue_name, callback, no_ack=False):
		"""Consume from the queue ``queue_name`` with callback ``callback``
		"""
		self._log.info("will consume from queue {}".format(queue_name))

		if self._amqp_channel is None:
			self._cached_queue_consumes.append((queue_name, callback, no_ack))
		else:
			with self._handlers_lock:
				handler = AmqpQueueHandler(
					callback,
					queue_name,
					self._amqp_channel,
					self._amqp_lock,
					no_ack,
					self._running
				)
				self._queue_handlers[queue_name] = handler
				handler.start()
	
	def wait_for_ready(self, timeout=2**31):
		"""Wait until the AMQP manager is connected and ready to go
		"""
		self._log.info("waiting until connected")
		self._amqp_connected.wait(timeout)
		# stupid, not sure if neccessary
		time.sleep(3)
		self._log.info("connected!")
	
	def queue_msg(self, msg, queue_name, **props):
		"""Queue the message ``msg`` in  the queue ``queue_name``

		:param str msg: The message to send (str or unicode)
		:param str queue_name: The queue to put the message in
		:param dict **props: Any additional props (exchange, etc)
		"""
		default_props = dict(
			exchange	= ""
		)
		default_props.update(props)
		with self._amqp_lock:
			self._amqp_channel.basic_publish(
				routing_key=queue_name,
				body=msg,
				**default_props
			)
	
	def ack_method(self, method):
		"""basic_ack the method

		:method: The method to ack
		"""
		with self._amqp_lock:
			self._amqp_channel.basic_ack(delivery_tag=method.delivery_tag)
	
	# ---------------------------------------
	# amqp related
	# ---------------------------------------
	
	def _amqp_ioloop(self):
		"""
		"""
		while self._running.is_set():
			time.sleep(0.1)

	def _amqp_connect(self):
		"""
		"""
		self._log.info("connecting to amqp: {}".format(self._amqp_host))
		self._amqp_conn = pika.BlockingConnection(pika.URLParameters("amqp://guest:guest@" + self._amqp_host))
		self._amqp_channel = self._amqp_conn.channel()

		self._amqp_connected.set()
	
	def _job_queue(self, channel, method, properties, body):
		"""Called when an AMQP message is received
		"""
		print("received {}".format(body))
