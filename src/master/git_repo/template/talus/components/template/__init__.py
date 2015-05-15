#!/usr/bin/env python
# encoding: utf-8

import os
import sys

from talus.components import Component

class Template(Component):
	"""This is a description for the Template component, which has
	one method
	"""

	def init(self, prefix):
		"""Initialize the Template component with a ``prefix``

		:param str prefix: The prefix to be used in the ``add_objects`` function
		"""
		# -----------
		# A few notes
		# -----------
		# * Components can accept other components as arguments (with :param Component(Name) argname:)
		#
		# * Components have a logger at self._log. See the python logging module for
		#   details. (basically, call debug(), info(), warn(), error(), methods
		#   on it to log data)
		#
		# * Components do not have a progress() or result() method
		#
		# * Inheritance works with talus components - e.g. a parameter's type is
		#   Component(ISomething), any component that subclasses ISomething
		#   will be able to be used.
		#
		# GOOD LUCK!

		self.prefix = prefix
	
	def add_objects(self, obj1, obj2):
		"""Add the two objects together (as strings), prepending our prefix
		"""
		return self.prefix + str(obj1) + str(obj2)
