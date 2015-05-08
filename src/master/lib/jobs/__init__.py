#!/usr/bin/env python
# encoding: utf-8

import json
import logging
import os
try:
    import Queue as Q  # ver. < 3.0
except ImportError:
	import queue as Q
import threading
import time

from master.lib.amqp_man import AmqpManager

logging.basicConfig(level=logging.DEBUG)

class JobHandler(object):
	"""A class to handle new jobs"""

	def __init__(self, job, queue_name):
		"""init the job handler"""
		self.job = job
		self.drip_count = 0
		self.queue_name = queue_name
	
	def drip(self, drip_size):
		"""Return items to be inserted into the queue. The ``drip_size`` is the total
		number in this drip. The amount yielded should be determined by the priority
		and the drip_size.

		:num: The number of items to return
		"""
		priority = self.job.priority
		num = int(round(drip_size * priority / 100.0))
		for x in range(num):
			yield self.drop()

	def drop(self):
		self.drip_count += 1
		return json.dumps(dict(
			job		= str(self.job.id),
			idx		= self.drip_count,
			image	= str(self.job.image.id),
			tool	= str(self.job.task.tool.name),
			params	= self.job.params
		))

class JobManager(threading.Thread):
	"""A class to manage jobs (starting/stopping/cancelling/etc)"""

	AMQP_JOB_QUEUE = "jobs"
	AMQP_JOB_STATUS_QUEUE = "job_status"
	AMQP_JOB_PROPS = dict(
		durable		= True,
		auto_delete	= False,
		exclusive	= False,
	)

	def __init__(self, drip_size=10):
		"""init the job manager
		
		:drip_size: The number of jobs to be added to the queue at once"""
		super(JobManager, self).__init__()

		self._drip_size = drip_size

		self._running = threading.Event()
		self._job_queue_lock = threading.Lock()

		self._amqp_man = AmqpManager.instance()

		self._log = logging.getLogger("JobMan")
		
		# each job can potentially specify their own queue, this
		# will be a dict of Q.PriorityQueue()s
		self._job_amqp_queues = {}
		# dict of {<jobid>: JobHandler}
		self._job_handlers = {}
	
	def run(self):
		"""Run the job manager. Only one of these should ever be running at a time
		:returns: TODO

		"""
		self._log.info("running")
		self._running.set()

		self._amqp_man.declare_queue(self.AMQP_JOB_QUEUE, **self.AMQP_JOB_PROPS)
		self._amqp_man.declare_queue(self.AMQP_JOB_STATUS_QUEUE, **self.AMQP_JOB_PROPS)
		self._amqp_man.consume_queue(self.AMQP_JOB_STATUS_QUEUE, self._on_job_status)
		self._amqp_man.do_start()
		self._amqp_man.wait_for_ready()

		self._log.info("beginning main loop")

		while self._running.is_set():
			self._monitor_queues()
			time.sleep(0.2)

		self._log.info("finished")
	
	def stop(self):
		"""Stop the job manager
		:returns: TODO

		"""
		self._log.info("stopping")
		self._running.clear()
	
	def run_job(self, job):
		"""TODO: Docstring for run_job.

		:job: TODO
		:returns: TODO
		"""
		self._log.info("running job: {}".format(job.id))

		job.priority = self._safe_priority(job.priority)
		job.save()

		queue = job.queue
		if queue is None or queue == "":
			queue = self.AMQP_JOB_QUEUE

		handler = JobHandler(job, queue)
		self._job_handlers[job.id] = handler

		with self._job_queue_lock:
			job_priority_queue = self._job_amqp_queues.setdefault(queue, Q.PriorityQueue())
			job_priority_queue.put((job.priority, handler))
	
	def stop_job(self, job):
		"""This is intended to be called once a job has been completed
		(not cancelled, but completed)
		"""
		self._log.info("stopping job: {}".format(job.id))
		if job.id not in self._job_handlers:
			self._log.warn("error, job {} not in job handlers".format(job.id))
			return

		with self._job_queue_lock:
			handler = self._job_handlers[job.id]
			queue = self._job_amqp_queues[handler.queue_name]

			for idx,handler in enumerate(queue.queue):
				if handler.job.id == job.id:
					del queue.queue[idx]
					break

		self._log.info("stopped job: {}")
	
	def cancel_job(self, job):
		"""TODO: Docstring for stop_job.

		:job: TODO
		:returns: TODO

		"""
		# TODO forcefully cancel the job (notify all slaves via amqp that
		# this job.id needs to be forcefully cancelled
		self._log.info("stopping job: {}".format(job.id))
		if job.id not in self._job_handlers:
			self._log.warn("error, job {} not in job handlers".format(job.id))
			return

		with self._job_queue_lock:
			handler = self._job_handlers[job.id]
			queue = self._job_amqp_queues[handler.queue_name]

			for idx,handler in enumerate(queue.queue):
				if handler.job.id == job.id:
					del queue.queue[idx]
					break

		self._log.info("stopped job: {}")
		
	# ---------------------------------------
	# job amqp related
	# ---------------------------------------

	def _on_job_status(self, channel, method, properties, body):
		"""Should be called when an AMQP_JOB_STATUS_QUEUE message is received - intended
		to be for job progress...  maybe more?
		"""
		print("received job status: {}".format(body))
	
	def _monitor_queues(self):
		"""Drip-feed the queue based on the current state of the job priority
		queue.
		"""
		with self._job_queue_lock:
			for queue_name,job_queue in self._job_amqp_queues.iteritems():
				num_msgs = self._amqp_man.get_message_count(queue_name)
				if num_msgs < self._drip_size:
					self._log.debug("queue has {}/{} messages, dripping some more".format(num_msgs, self._drip_size))
					self._do_drip(queue_name, job_queue)
	
	def _safe_priority(self, priority):
		res = priority
		if not isinstance(res, int):
			res = 50

		if res < 0:
			res = 0

		elif res > 100:
			res = 100

		return res
	
	def _do_drip(self, queue_name, job_queue):
		"""Drip more items into the job queue

		:queue_name: The name of the queue to add more job items into
		:job_queue: The job queue to work
		:returns: None
		"""
		for priority,job in job_queue.queue:
			for drop in job.drip(self._drip_size):
				self._amqp_man.queue_msg(drop, queue_name)
