#!/usr/bin/env python
# encoding: utf-8

import bson
import datetime
import glob
import os
import sys
import time
import uuid

import master.models
from master.watchers import WatcherBase
from master.lib.amqp_man import AmqpManager
from master import Master
from master.watchers.result_processors import ResultProcessorBase

class ResultWatcher(WatcherBase):
	collection = "talus.result"

	def __init__(self, *args, **kwargs):
		WatcherBase.__init__(self, *args, **kwargs)

		self._processors = []

		for filename in glob.glob(os.path.join(os.path.dirname(__file__), "result_processors", "*.py")):
			filename_ = os.path.basename(filename)
			if filename_ == "__init__.py":
				continue
			mod_name = filename_.replace(".py", "")
			mod = __import__(
				"master.watchers.result_processors.{}".format(mod_name),
				globals(),
				locals()
			)
			for item_name in dir(mod):
				item = getattr(mod, item_name)
				# we only care about classes
				if type(item) is not type:
					continue
				if issubclass(item, ResultProcessorBase):
					self._processors.append(item())

	def insert(self, id_, obj):
		self._log.debug("handling insert")

		results = master.models.Result.objects(id=id_)
		if len(results) == 0:
			self._log.warn("WTF? couldn't find Result object that was just inserted")
			return

		result = results[0]
		# propagate tags from the job object (user, etc)
		result.tags = result.job.tags
		# save the _real_ current time so it's not dependent on the VM's time
		result.created = datetime.datetime.utcnow()
		result.save()

		for processor in self._processors:
			try:
				can_process = processor.can_process(result)
			except NotImplemented as e:
				self._log.error("Result processor class '{}' does not implement the can_process function!".format(processor.__class__.__name__))
				continue

			if can_process:
				processor.process(result)

				try:
					result.reload()
				except Exception as e:
					self._log.info("error reloading result document, probably deleted?? TODO verify this is OK", exc_info=True)
					# if it's been deleted, then just return, as no other processors should be able to process it
					return

	def update(self, id, mod):
		pass
	
	def delete(self, id):
		pass
