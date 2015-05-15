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

class ResultCmd(TalusCmdBase):
	"""The talus result command processor
	"""

	command_name = "result"

	def do_list(self, args):
		"""List results in talus for a specific job. Fields to be searched for must
		be turned into parameter format (E.g. ``--search-item "some value"`` format would search
		for a result with the field ``search_item`` equaling ``some value``).

		result list --search-item "search value" [--search-item2 "search value2" ...]
		"""
		parts = shlex.split(args)

		search = {}
		key = None
		for item in parts:
			if key is None:
				if not item.startswith("--"):
					raise talus.errors("args must be alternating search item/value pairs!")
				item = item[2:].replace("-", "_")
				key = item
			elif key is not None:
				search[key] = item
				key = None
				print("searching for {} = {}".format(key, item))

		print(tabulate(self._talus_client.result_iter(**search), headers=Result.headers()))
			
