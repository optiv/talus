#!/usr/bin/env python
# encoding: utf-8

import logging
import os
import sys

class ResultProcessorBase(object):
	"""A result processor. Each defined result processor will
	be asked if it can process new results"""

	def __init__(self):
		"""Init the result processor base
		"""
		self._log = logging.getLogger("ResultProc").getChild(self.__class__.__name__)
	
	def process(self, result):
		"""Process the result. Processing the result IS allowed to delete the
		result as part of the processing. Creating new models/other changes is
		also allowed/expected.

		:param mongoengine.Document result: The result to process
		"""
		raise NotImplemented("Inheriting classes must implement the process function")

	def can_process(self, result):
		"""A query function to determine if this result processor can process
		the result.

		:returns: True/False
		"""
		raise NotImplemented("Inheriting classes must implement the can_process function")
