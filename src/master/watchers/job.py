#!/usr/bin/env python
# encoding: utf-8

import bson
import os
import sys
import uuid

import master.models
from master.lib.jobs import JobManager
from master.watchers import WatcherBase
from master.lib.amqp_man import AmqpManager

class JobWatcher(WatcherBase):
	collection = "talus.job"

	def __init__(self, *args, **kwargs):
		WatcherBase.__init__(self, *args, **kwargs)

		self._job_man = JobManager()
		# this needs to be continuously running
		self._job_man.start()

		for job in master.models.Job.objects(status__name__in=["run", "stop", "cancel"]):
			self._handle_status(job.id, job=job)
	
	def stop(self):
		"""Stop the JobWatcher"""
		self._job_man.stop()

	def insert(self, id_, obj):
		self._log.debug("handling insert")

		self._handle_status(id_, obj)

	def update(self, id, mod):
		self._log.debug("handling update")

		self._handle_status(id, mod)
	
	def delete(self, id):
		self._log.debug("handling delete")

		#self._handle_status(id)

	# -----------------------

	def _handle_status(self, id_, obj=None, job=None):
		switch = {
			"run"		: self._handle_run,
			"stop"		: self._handle_stop,
			"cancel"	: self._handle_cancel,
		}

		if job is None:
			jobs = master.models.Job.objects(id=id_)
			if len(jobs) == 0:
				return
			job = jobs[0]

		if job.status["name"] in switch:
			switch[job.status["name"]](id_, job)
	
	def _handle_run(self, id_, job):
		"""Handle running a job
		"""
		self._log.info("handling job runnage")

		if job.image.status["name"] != "ready":
			self._log.warn("Image is not in a ready state! cannot run the job yet, cancelling")
			job.status = {"name": "cancelled", "desc": "image not ready"}
			job.save()
			return

		self._job_man.run_job(job)

		job.status = {
			"name": "running"
		}
		job.save()

	def _handle_stop(self, id_, job):
		"""Handle stopping a job - to be used only for internal purposes. Not
		really intended for a user to be able to set this.
		"""
		self._log.info("handling job cancellation")

		job.status = {
			"name": "stopping"
		}
		job.save()

		self._job_man.stop_job(job)
	
	def _handle_cancel(self, id_, job):
		"""Handle cancelling a job
		"""
		self._log.info("handling job cancellation")

		job.status = {
			"name": "cancelling"
		}
		job.save()

		self._job_man.cancel_job(job)
