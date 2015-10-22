#!/usr/bin/env python 
# encoding: utf-8

# force all imports to be absolute import paths!
from __future__ import absolute_import

import json
import os
import sys
import tempfile

class MockJob(object):
	def __init__(self):
		self.files_dir = os.path.join(os.getcwd(), "TALUS_RUNLOCAL_FILESET")
		if not os.path.exists(self.files_dir):
			os.makedirs(self.files_dir)
		self.file_counter = 0

	def add_file(self, contents, filename=None, content_type="application/octet-stream", **metadata):
		local_filename = self._get_next_filename()
		with open(local_filename, "wb") as f:
			f.write(contents)

		metadata.update(dict(
			filename		= filename,
			content_type	= content_type,
		))
		with open(local_filename + ".json", "wb") as f:
			f.write(json.dumps(metadata, indent=4, separators=(",", ": ")))

		return local_filename
		
	def _get_next_filename(self):
		while True:
			new_file = os.path.join(self.files_dir, "file_" + str(self.file_counter))
			if not os.path.exists(new_file):
				return new_file
			self.file_counter += 1

class TalusCodeBase(object):
	"""The base class for Talus Tools and Components"""

	def __init__(self, job=None):
		"""TODO: to be defined1. """
		if job is None:
			job = MockJob()

		self.job = job
	
	def run(self, arg1):
		"""The main function that will be run

		:arg1: TODO
		:returns: TODO

		"""
		pass
	
	def add_file(self, contents, content_type="application/octet-stream", filename=None, **metadata):
		return self.job.add_file(
			contents		= contents,
			filename		= filename,
			content_type	= content_type,
			**metadata
		)
