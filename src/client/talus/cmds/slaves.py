#!/usr/bin/env python
# encoding: utf-8

import argparse
import arrow
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
		headers = ["id", "hostname", "ip", "max_vms", "running_vms"]
		values = []
		for slave in self._talus_client.slave_iter():
			values.append([
				slave.id,
				slave.hostname,
				slave.ip,
				slave.max_vms,
				slave.running_vms
			])
		print(tabulate(values, headers=headers))
	
	def do_info(self, args):
		"""List information about a slave

		talus slave info ID_OR_HOSTNAME_OR_IP

		"""
		search_item = shlex.split(args)[0]
		slave = Slave.find_one(self._talus_host, id=search_item)
		if slave is None:
			slave = Slave.find_one(self._talus_host, hostname=search_item)
			if slave is None:
				slave = Slave.find_one(self._talus_host, ip=search_item)
				if slave is None:
					raise talus.errors.TalusApiError("Could not locate slave by id/hostname/ip {!r}".format(search_item))

		vm_headers = ["tool", "vnc", "running since", "job", "job idx"]
		vm_vals = []
		for vm in slave.vms:
			vm_vals.append([
				vm["tool"],
				vm["vnc_port"],
				arrow.get(vm["start_time"]).humanize(),
				vm["job"],
				vm["idx"]
			])

		if len(slave.vms) == 0:
			vm_infos = ""
		else:
			vm_infos = "\n\n" + "\n".join("    {}".format(x) for x in tabulate(vm_vals, headers=vm_headers).split("\n"))

		print("""
ID: {id}
UUID: {uuid}
Hostname: {hostname}
IP Addr: {ip}
Jobs Run: {jobs_run}
Max VMs: {max_vms}
Running VMs: {running_vms}{vm_infos}
		""".format(
			id			= slave.id,
			uuid		= slave.uuid,
			hostname	= slave.hostname,
			ip			= slave.ip,
			jobs_run	= slave.total_jobs_run,
			max_vms		= slave.max_vms,
			running_vms	= slave.running_vms,
			vm_infos	= vm_infos
		))
