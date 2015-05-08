"""
The `serf` module is responsible for creating, cloning, stopping, and starting
serfs (VM, docker container, etc - a runtime environment in which a task is to
be run).
"""

class Serfdom(object):
	"""Manages serfs"""

	def __init__(self, arg):
		"""docstring for Serfdom constructor"""
		super(Serfdom, self).__init__()
		self.arg = arg

	def testing(self):
		pass
