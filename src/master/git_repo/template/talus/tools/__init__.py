#!/usr/bin/env python
# encoding: utf-8

from talus import TalusCodeBase

class Tool(TalusCodeBase):

	"""When a task is run in Talus, this code will be the first
	user-controlled code"""

	def __init__(self, idx, progress_cb, results_cb, parent_log):
		"""TODO: to be defined1. """
		TalusCodeBase.__init__(self)

		self._progress_cb = progress_cb
		self._results_cb = results_cb
		self._log = parent_log.getChild(self.__class__.__name__)
	
	def progress(self, num=1):
		self._progress_cb(num)
	
	def results(self, data):
		self._results_cb(data)
	
	def run(self, arg1):
		"""TODO: Docstring for run.

		:arg1: TODO
		:returns: TODO

		"""
		raise NotImplemented
