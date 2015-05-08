#!/usr/bin/env python
# encoding: utf-8

import argparse
import cmd
import json
import os
import shlex
import sys
from tabulate import tabulate

from talus.cmds import TalusCmdBase
import talus.api
from talus.models import Task

class TaskCmd(TalusCmdBase):
	"""The Talus task command processor
	"""

	command_name = "task"

	def do_list(self, args):
		"""List all tasks in
		"""
		tasks = []
		headers = ["id", "name", "tool", "version"]
		for task in self._talus_client.task_iter():
			tasks.append([
				task.id,
				task.name,
				task.tool + " (" + task._fields["tool"].value["name"] + ")",
				task.version
			])
		print(tabulate(tasks, headers=headers))
	
	def do_info(self, args):
		"""List details about a task
		"""

	def do_create(self, args):
		"""Create a new task in Talus

		create -n NAME -t TOOL_ID_OR_NAME -p PARAMS -l LIMIT

		        -n,--name    The name of the new task (required, no default)
		        -t,--tool    The name or id of the tool to be run by the task (required, no default)
		       -l,--limit    The limit for the task. What the limit means is defined by how the tool
			                 reports progress. If the tool does not report progress, then the limit
							 means the number of total VMs to run.
		      -p,--params    The params of the task
		     -v,--version    The version the task should be pinned at, else the current HEAD (default=None)
		 -f,--params-file    The file that contains the params of the task

		Examples:
		---------

		To create a new task that uses the tool "BrowserFuzzer":

		    task create -n "IE Fuzzer" -t "BrowserFuzzer" -p "{...json params...}"

		To create a new task that also uses the "BrowserFuzzer" tool but reads in the params
		from a file:

		    task create -n "IE Fuzzer" -t "BrowserFuzzer" -f ie_fuzz_params.json
		"""
		parser = argparse.ArgumentParser()
		parser.add_argument("--name", "-n")
		parser.add_argument("--tool", "-t")
		parser.add_argument("--limit", "-l", default=1)
		parser.add_argument("--params", "-p", default=None)
		parser.add_argument("--version", "-v", default=None)
		parser.add_argument("--params-file", "-f", default=None)

		args = parser.parse_args(shlex.split(args))

		if args.params is None and args.params_file is None:
			sys.stderr.write("Error, params must be specified with either -p or -f")
			return

		if args.params_file is not None:
			if not os.path.exists(args.params_file):
				sys.stderr.write("ERROR, params file does not exist: '{}'".format(args.params_file))
				return

			with open(args.params_file, "r") as f:
				args.params = f.read()

		params = json.loads(args.params)

		task = self._talus_client.task_create(
			name			= args.name,
			params			= json.loads(args.params),
			tool_id			= args.tool,
			limit			= args.limit,
			version			= args.version
		)

		print("created")
	
	def do_delete(self, args):
		"""Delete an existing task

		task delete <TASK_ID_OR_NAME>
		"""
		args = shlex.split(args)
		self._talus_client.task_delete(args[0])
		print("deleted")
	
	def do_run(self, args):
		"""Run an existing task
		"""
		pass
	
	def do_clone(self, args):
		"""Clone an existing task
		"""
		pass
