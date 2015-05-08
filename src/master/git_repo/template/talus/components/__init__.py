#!/usr/bin/env python
# encoding: utf-8

from talus import TalusCodeBase

class Component(TalusCodeBase):

	"""This is the baseclass for all Components"""

	def __init__(self):
		"""Initialize the component """
		TalusCodeBase.__init__(self)

	def run(self):
		"""Run the component
		:returns: TODO

		"""
		raise NotImplemented
