#!/usr/bin/env python
# encoding: utf-8

import argparse
import cmd
import os
import shlex
import sys
from tabulate import tabulate
import textwrap

from talus.cmds import TalusCmdBase
import talus.api
import talus.errors
from talus.models import *

class SlaveCmd(TalusCmdBase):
	"""The Talus slave command processor
	"""

	command_name = "slave"

	def do_list(self, args):
		"""List existing slaves connected to Talus.

		slave list

		"""
		print(tabulate(self._talus_client.slave_iter(), headers=Slave.headers()))
