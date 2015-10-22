#!/usr/bin/env python
# encoding: utf-8

import logging
from talus import TalusCodeBase

class Component(TalusCodeBase):
	"""This is the baseclass for all Components"""

	def __init__(self, parent_log=None, **kwargs):
		"""Initialize the component """
		if parent_log is not None:
			TalusCodeBase.__init__(self, **kwargs)
			self.log = parent_log.getChild(self.__class__.__name__)

		else:
			TalusCodeBase.__init__(self)
			self.log = logging.getLogger("RUNLOCAL").getChild(self.__class__.__name__)
			# everything else at this point should be the normal args, so init them
			self.init(**kwargs)

		if len(self.log.handlers) == 0:
			logging.basicConfig(level=logging.DEBUG)
