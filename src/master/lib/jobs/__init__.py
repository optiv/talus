#!/usr/bin/env python
# encoding: utf-8

import json
import logging
import os
try:
    import Queue as Q  # ver. < 3.0
except ImportError:
	import queue as Q
PQ = Q.PriorityQueue
import threading
import time

from master import Master
from master.lib.amqp_man import AmqpManager
from master.models import *

logging.basicConfig(level=logging.DEBUG)

class JobHandler(object):
	"""A class to handle new jobs"""

	def __init__(self, job, queue_name):
		"""init the job handler
		
		:param mongoengine.Document job: A Job model
		:param str queue_name: The name of the queue this job will drip into
		"""
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
			job				= str(self.job.id),
			idx				= self.drip_count,
			image			= str(self.job.image.id),
			image_username	= self.job.image.username,
			image_password	= self.job.image.password,
			tool			= str(self.job.task.tool.name),
			params			= self.job.params,
			network			= self.job.network
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

		self._create_handlers_for_existing()

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
		self._job_handlers[str(job.id)] = handler

		with self._job_queue_lock:
			job_priority_queue = self._job_amqp_queues.setdefault(queue, PQ())
			job_priority_queue.put((job.priority, handler))
	
	def stop_job(self, job):
		"""This is intended to be called once a job has been completed
		(not cancelled, but completed)
		"""
		self._log.info("stopping job: {}".format(job.id))
		if str(job.id) not in self._job_handlers:
			self._log.warn("error, job {} not in job handlers".format(job.id))
			return

		with self._job_queue_lock:
			handler = self._job_handlers[str(job.id)]
			queue = self._job_amqp_queues[handler.queue_name]

			new_queue = []
			for priority,handler in queue.queue:
				if handler.job.id == job.id:
					continue
				new_queue.append((priority, handler))

			queue.queue = new_queue

		AmqpManager.instance().queue_msg(
			json.dumps(dict(
				type	= "cancel",
				job		= str(job.id)
			)),
			"",
			exchange=Master.AMQP_BROADCAST_XCHG
		)

		job.reload()
		job.status = {
			"name": "finished"
		}
		job.save()

		self._log.info("stopped job: {}".format(job.id))
	
	def cancel_job(self, job):
		"""Cancel the job ``job``

		:job: The job object to cancel
		:returns: None

		"""
		# TODO forcefully cancel the job (notify all slaves via amqp that
		# this job.id needs to be forcefully cancelled
		self._log.info("cancelling job: {}".format(job.id))
		if str(job.id) not in self._job_handlers:
			self._log.warn("error, job {} not in job handlers".format(job.id))
			return

		with self._job_queue_lock:
			handler = self._job_handlers[str(job.id)]
			queue = self._job_amqp_queues[handler.queue_name]

			new_queue = []
			for priority,info in queue.queue:
				if handler.job.id == job.id:
					continue
				new_queue.append((priority, handler))

			queue.queue = new_queue

		AmqpManager.instance().queue_msg(
			json.dumps(dict(
				type	= "cancel",
				job		= str(job.id)
			)),
			"",
			exchange=Master.AMQP_BROADCAST_XCHG
		)

		job.reload()
		job.status = {
			"name": "cancelled"
		}
		job.save()

		self._log.info("cancelled job: {}".format(job.id))

	# ---------------------------------------

	def _create_handlers_for_existing(self):
		self._log.info("creating job handlers for existing running jobs in the database")
		for job in Job.objects(status__name = "running"):
			self.run_job(job)
		
	# ---------------------------------------
	# job amqp related
	# ---------------------------------------

	def _on_job_status(self, channel, method, properties, body):
		"""Should be called when an AMQP_JOB_STATUS_QUEUE message is received - intended
		to be for job progress...  maybe more?
		"""
		self._log.info("received job status: {}".format(body))

		# just ack it immediately
		self._amqp_man.ack_method(method)

		data = json.loads(body)

		switch = dict(
			progress	= self._handle_job_progress,
			result		= self._handle_job_result,
		)

		if data["type"] not in switch:
			self._log.warn("unknown job status type! {}".format(data))
			return

		switch[data["type"]](data)

	def _handle_job_progress(self, data):
		"""Handling job progress
		"""
		self._log.debug("handling job progress: {}".format(data))

		Job.objects(id=data["job"]).update_one(inc__progress = data["amt"])

		if data["job"] not in self._job_handlers:
			self._log.warn("job {} not in current list of job handlers".format(data["job"]))
			return

		handler = self._job_handlers[data["job"]]
		job = handler.job
		job.reload()

		if job.progress >= job.limit:
			self._log.debug("job {} finished ({}/{})".format(job.id, job.progress, job.limit))
			self.stop_job(job)
	
	def _handle_job_result(self, data):
		"""Handling job result
		"""
		self._log.debug("handling job result: {}".format(data))

		if not isinstance(data["data"], dict):
			data["data"] = {"data": data["data"]}

		jobs = Job.objects(id=data["job"])
		if len(jobs) == 0:
			self._log.warn("received result for a non-existent job!")
		job = jobs[0]

		result = Result()
		result.job = job
		result.type = data["type"]
		result.tool	= data["tool"]
		result.data = data["data"]
		result.save()
	
	def _monitor_queues(self):
		"""Drip-feed the queue based on the current state of the job priority
		queue.
		"""
		with self._job_queue_lock:
			for queue_name,job_queue in self._job_amqp_queues.iteritems():
				if job_queue.qsize() == 0:
					time.sleep(0.5)
					continue
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
