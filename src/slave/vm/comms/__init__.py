#!/usr/bin/env python
# encoding: utf-8

import base64
import logging
import paramiko
import time
import winrm

logging.basicConfig(level=logging.DEBUG)

VM_TYPE_LINUX = 0
VM_TYPE_WINDOWS = 1

class VMComms(object):
	sep = "/"

	@classmethod
	def get_comms(self, vm_type):
		"""Get an appropriate VMComms implementation for the vm type

		:param str vm_type: either ``VM_TYPE_LINUX`` or ``VM_TYPE_WINDOWS``
		:returns: An appropriate VMComms instance
		"""
		switch = {
			VM_TYPE_LINUX: SSHComms,
			VM_TYPE_WINDOWS: WinrmComms
		}

		if vm_type not in switch:
			return None

		return switch[vm_type]()

	def __init__(self):
		self._log = logging.getLogger(self.__class__.__name__)
	
	def tmp_loc(self):
		raise NotImplemented("Inheriting classes must implement the tmp_loc function")
	
	def connect(self, ip, username, password):
		raise NotImplemented("Inheriting classes must implement the connect function")

	def run_cmd(self, background=False, *cmd):
		raise NotImplemented("Inheriting classes must implement the run_cmd function")

	def run_script(self, script):
		raise NotImplemented("Inheriting classes must implement the run_script function")
	
	def put_file(self, location, contents):
		raise NotImplemented("Inheriting classes must implement the put_file function")

class WinrmComms(VMComms):
	sep = "\\"

	def connect(self, ip, username, password):
		self._log.debug("connecting to VM at {}".format(ip))
		self._sess = winrm.Session(ip, (username, password))

		# loop until we can successfully 
		while True:
			time.sleep(0.1)
			try:
				r = self._sess.run_cmd("echo", ["blah"])
				if "blah" in r.std_out:
					break
			except:
				pass

		self._log.info("connected to VM at {}!".format(ip))
	
	def tmp_loc(self):
		return '$([System.Environment]::ExpandEnvironmentVariables("%TEMP%"))'
	
	def run_cmd(self, background, *cmd):
		if background:
			cmd = ["start", "cmd", "/k", '"{}"'.format(" ".join('"' + x + '"' for x in cmd))]

		r = self._sess.run_cmd(cmd[0], cmd[1:])
		return r.std_out
	
	def run_script(self, script, background=False):
		if background:
			return self._run_script_background(script)
		else:
			r = self._sess.run_ps(script)
			return r.std_out
	
	def _run_script_background(self, script):
		"""Run the script in the background (do not block)
		"""
		base64_script = base64.b64encode(script.encode("utf_16_le"))
		cmd = "powershell -encodedcommand %s" % base64_script
		shell_id = self._sess.protocol.open_shell()
		command_id = self._sess.protocol.run_command(shell_id, cmd, [])

		return (shell_id, command_id)
	
	def put_file(self, location, contents):
		# max is supposed to be 2047 characters
		step = 1500
		for i in range(0, len(contents), step):
			self._do_put_file(location, contents[i:i+step])
	
	def _do_put_file(self, location, contents):
		# adapted/copied from https://github.com/diyan/pywinrm/issues/18
		ps_script = """
$filePath = "{location}"
$s = @"
{b64_contents}
"@
$data = [System.Convert]::FromBase64String($s)
add-content -value $data -encoding byte -path $filePath
		""".format(
			location		= location,
			b64_contents	= base64.b64encode(contents)
		)

		r = self._sess.run_ps(ps_script)
		if r.status_code == 1:
			self._log.warn(r.std_err)
			return None

		return r.std_out

class SSHComms(VMComms):
	pass
