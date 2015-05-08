#!/usr/bin/env python
# encoding: utf-8

import bson
import os
import sys
import uuid

import master.models
from master.lib.jobs import JobManager
from master.watchers import WatcherBase

class JobWatcher(WatcherBase):
	collection = "talus.job"

	def __init__(self, *args, **kwargs):
		WatcherBase.__init__(self, *args, **kwargs)

		self._job_man = JobManager()
		# this needs to be continuously running
		self._job_man.start()

		for job in master.models.Job.objects(status__name__in=["run", "stop"]):
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

		self._job_man.run_job(job)

		job.status = {
			"name": "running"
		}
		job.save()
	
	def _handle_cancel(self, id_, job):
		"""Handle cancelling a job
		"""
		self._log.info("handling job cancellation")

		self._job_man.cancel_job(job)

		job.status = {
			"name": "cancelling"
		}
		job.save()
