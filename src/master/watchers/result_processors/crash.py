#!/usr/bin/env python
# encoding: utf-8

import os
import sys

import master.watchers.result_processors as processors
from master.models import *

class CrashProcessor(processors.ResultProcessorBase):
	"""A simple crash processor
	"""

	def can_process(self, result):
		"""Return True/False if the result is a crash result
		"""
		self._log.info("result type: {!r}".format(result.type))
		return result.type == "crash"
	
	def process(self, result):
		"""Process the crash result

		:param mongoengine.Document result: The result to process
		"""
		self._log.info("processing crash")

		# fill this in later
		if Result.objects(data__hash_major=result.data["hash_major"], data__hash_minor=result.data["hash_minor"]).count() > 50:
			self._log.debug("removing unneeded crash result ({}:{} hash)".format(result.data["hash_major"], result.data["hash_minor"]))
			result.delete()
