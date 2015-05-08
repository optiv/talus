#!/usr/bin/env python
# encoding: utf-8

"""
Docstring for the VM module
"""

class VM(object):
	"""The VM class exposes functionality to manage VMs:
	* image format conversion
	* etc"""

	def __init__(self, libvirt_info):
		"""Initialize the VM class (is this really needed?)"""
		super(VM, self).__init__()
		self.libvirt_info = libvirt_info
