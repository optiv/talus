#!/usr/bin/env python
# encoding: utf-8

import json
import logging
import os
import sys
from talus import TalusCodeBase

class Tool(TalusCodeBase):

	"""When a task is run in Talus, this code will be the first
	user-controlled code"""

	def __init__(self, idx=None, progress_cb=None, results_cb=None, parent_log=None, **kwargs):
		"""TODO: to be defined1. """
		self.idx = idx
		if parent_log is not None:
			# TODO maybe we should explicitly set a flag that says it's being run
			# with the bootstrap... talus.BOOTSTRAP_RUNNING = True?? dunno
			TalusCodeBase.__init__(self, **kwargs)
			self.log = parent_log.getChild(self.__class__.__name__)

		else:
			TalusCodeBase.__init__(self)
			self.log = logging.getLogger("RUNLOCAL").getChild(self.__class__.__name__)

			self._total_progress = 0
			self._file_counter = 0
			self._results_dir = os.path.join(os.getcwd(), "TALUS_RESULTS")
			if not os.path.exists(self._results_dir):
				os.makedirs(self._results_dir)

		if len(self.log.handlers) == 0:
			logging.basicConfig(level=logging.DEBUG)

		self._progress_cb = progress_cb
		self._results_cb = results_cb
	
	def progress(self, num=1):
		if self._progress_cb is not None:
			self._progress_cb(num)
		else:
			self._total_progress += num
			self.log.info("progress: {} ({} total)".format(num, self._total_progress))
	
	def result(self, result_type, data):
		if self._results_cb is not None:
			self._results_cb(result_type, data)
		else:
			self.log.info("result ({}): {}".format(result_type, str(data)[:60] + " ..."))
			result_file = self._get_next_filename()
			with open(result_file, "wb") as f:
				f.write(json.dumps({
					"type": result_type,
					"data": data,
				}, indent=4, separators=(",", ": ")))
		
	def _get_next_filename(self):
		while True:
			new_file = os.path.join(self._results_dir, "result_" + str(self._file_counter))
			if not os.path.exists(new_file):
				return new_file
			self._file_counter += 1
	
	def run(self, arg1):
		"""TODO: Docstring for run.

		:arg1: TODO
		:returns: TODO

		"""
		raise NotImplemented
