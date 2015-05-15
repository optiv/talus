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
		return result.type == "crash"
	
	def process(self, result):
		"""Process the crash result

		:param mongoengine.Document result: The result to process
		"""
		self._log.info("processing crash")

		# fill this in later
