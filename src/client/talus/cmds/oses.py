#!/usr/bin/env python
# encoding: utf-8

import argparse
import cmd
import os
import shlex
import sys
from tabulate import tabulate

from talus.cmds import TalusCmdBase
import talus.api
import talus.errors
from talus.models import *

class OsCmd(TalusCmdBase):
	"""The Talus code command processor
	"""

	command_name = "os"
	
	def do_list(self, args):
		"""List all operating system models defined in Talus
		"""
		print(tabulate(self._talus_client.os_iter(), headers=OS.headers()))

	def do_create(self, args):
		"""Create a new operating system model in Talus

		create -n NAME [--type TYPE] [-t TAG1,TAG2,..] [-v VERSION]

		   -n,--name    The name of the new OS model (required, no default)
		   -t,--type    The type of the OS mdoel (default: "windows")
		   -a,--arch	The architecture of the OS (default: "x64")
		-v,--version    The version of the new OS model (default: "")

		Examples:

		To create a new operating system model for an x64 Windows 7 OS:

		    os create -n "Windows 7 x64" -t windows -v 7 -a x64
		"""
		parser = argparse.ArgumentParser()
		parser.add_argument("--name", "-n")
		parser.add_argument("--type", "-t", default="windows")
		parser.add_argument("--version", "-v", default="")
		parser.add_argument("--arch", "-a", default="x64")

		args = parser.parse_args(shlex.split(args))

		new_os = OS(self._talus_host)
		new_os.name = args.name
		new_os.type = args.type
		new_os.version = args.version
		new_os.arch = args.arch

		try:
			new_os.save()
			print("created")
		except talus.errors.TalusApiError as e:
			sys.stderr.write("Error saving OS: {}\n".format(e.message))
	
	def do_delete(self, args):
		"""Delete an operating system model in Talus

		os delete <OS_ID_OR_NAME>
		"""
		args = shlex.split(args)
		self._talus_client.os_delete(args[0])
		print("deleted")
