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

class JobCmd(TalusCmdBase):
	"""The Talus job command processor
	"""

	command_name = "job"

	def do_list(self, args):
		"""List existing jobs in Talus.

		job list

		"""
		headers = ["id", "name", "status", "priority", "progress", "image"]
		fields = []
		for job in self._talus_client.job_iter():
			fields.append([
				str(job.id),
				job.name,
				job.status["name"],
				job.priority,
				"{:0.2f}% ({}/{})".format(
					job.progress / float(job.limit) * 100,
					job.progress,
					job.limit
				),
				job._fields["image"]["name"]
			])
		print(tabulate(fields, headers=headers))
	
	def do_create(self, args):
		"""Create a new job in Talus

		job create TASK_NAME_OR_ID -i IMAGE [-n NAME] [-p PARAMS] [-q QUEUE] [--priority (0-100)]

		       -n,--name    The name of the job (defaults to name of the task + timestamp)
		      --priority    The priority for the job (0-100, defaults to 50)
			  -q,--queue    The queue the job should be inserted into (default: jobs)
			  -i,--image    The image the job should run in (name or id)
		      -l,--limit    The limit for the task. What the limit means is defined by how the tool
			                reports progress. If the tool does not report progress, then the limit
			                means the number of total VMs to run.
		     -p,--params    Params for the task (defaults to the default params of the task)
		-f,--params-file    The file that contains the params of the job

		Examples:

		To run the task "CalcFuzzer" while only updating the ``chars`` parameter:

		    job create "CalcFuzzer" -p '{"chars": "013579+-()/*"}'
		"""
		parser = argparse.ArgumentParser()
		parser.add_argument("task_name_or_id")
		parser.add_argument("--name", "-n", default=None)
		parser.add_argument("--priority", default=50)
		parser.add_argument("--limit", "-l", default=None)
		parser.add_argument("--image", "-i")
		parser.add_argument("--queue", "-q", default="jobs")
		parser.add_argument("--params", "-p", default=None)
		parser.add_argument("--params-file", "-f", default=None)

		args = parser.parse_args(shlex.split(args))

		params = args.params
		if args.params_file is not None:
			if not os.path.exists(args.params_file):
				raise errors.TalusApiError("params file does not exist: {}".format(args.params_file))
			with open(args.params_file, "r") as f:
				params = f.read()

		if params is not None:
			try:
				params = json.loads(params)
			except Exception as e:
				raise errors.TalusApiError("params are not in json format: " + e.message)

		self._talus_client.job_create(
			task_name_or_id	= args.task_name_or_id,
			name			= args.name,
			image			= args.image,
			params			= params,
			priority		= args.priority,
			limit			= args.limit,
			queue			= args.queue
		)

		print("created")
