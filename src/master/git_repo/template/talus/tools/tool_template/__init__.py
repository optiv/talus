#!/usr/bin/env python
# encoding: utf-8

import os
import sys
import time

from talus.tools import Tool

class ToolTemplate(Tool):
	"""This is a description for the Template Tool
	"""

	def run(self, arg1, arg2, comp1, iters):
		"""Run the Template tool with a few args and a component

		:param str arg1: The first argument (a string)
		:param str arg2: The second argument (a string)
		:param int iters: The number of times to report progress
		:param Component(ComponentTemplate) comp1: The third argument (an instantiated Template component)
		"""
		# -----------
		# A few notes
		# -----------
		# * Tools have a logger at self.log. See the python logging module for
		#   details. (basically, call debug(), info(), warn(), error(), methods
		#   on it to log data)
		#
		# * Tools have a progress(amt=1) method that progress can be reported with.
		#   If progress() is never manually called, it will be called once after the
		#   tool has run.
		#
		# * Tools have result(data) method that can be used to save a job's results
		#
		# * Inheritance works with talus components - e.g. a parameter's type is
		#   Component(ISomething), any component that subclasses ISomething
		#   will be able to be used.
		#
		# * The tool's index into the Job is found at ``self.idx``
		#
		# GOOD LUCK!

		self.log.debug("starting Template tool, idx: {}".format(self.idx))

		added = comp1.add_objects(arg1, arg2)

		for x in range(iters):
			self.progress(1)
			time.sleep(5)

		# add a file to the default result filelist for this job
		file_id = self.add_file(
			"FILE CONTENTS",
			content_type="application/json",
			filename="this_was_the_filename.json"
		)

		self.result("result_type", {
			"result_data1": file_id,
			"result_data2": added
		})
