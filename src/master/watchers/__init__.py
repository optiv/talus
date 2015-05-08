import glob
import os
import sys

class WatcherBase(object):
	def __init__(self, parent_log):
		self._log = parent_log.getChild(self.__class__.__name__)
	
	def stop(self):
		pass
