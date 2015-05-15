#!/usr/bin/env python
# encoding: utf-8

from talus import TalusCodeBase

class Component(TalusCodeBase):
	"""This is the baseclass for all Components"""

	def __init__(self, parent_log):
		"""Initialize the component """
		TalusCodeBase.__init__(self)

		self.log = parent_log.getChild(self.__class__.__name__)
