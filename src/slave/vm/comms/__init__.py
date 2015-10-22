#!/usr/bin/env python
# encoding: utf-8

import base64
import logging
import paramiko
import pipes
import random
import scp
import tempfile
import time
import winrm

logging.basicConfig(level=logging.DEBUG)

logging.getLogger("paramiko").setLevel(logging.INFO)

class VMComms(object):
	sep = "/"

	@classmethod
	def get_comms(self, vm_type, parent_log):
		"""Get an appropriate VMComms implementation for the vm type

		:param str vm_type: expecting values like "windows", or "linux"
		:returns: An appropriate VMComms instance
		"""
		if "window" in vm_type.lower():
			return WinrmComms(parent_log)

		return SSHComms(parent_log)

	def __init__(self, parent_log):
		self._log = parent_log.getChild(self.__class__.__name__)
	
	def tmp_loc(self):
		raise NotImplemented("Inheriting classes must implement the tmp_loc function")
	
	def connect(self, ip, username, password, keep_going_event):
		raise NotImplemented("Inheriting classes must implement the connect function")

	def run_cmd(self, background=False, *cmd):
		raise NotImplemented("Inheriting classes must implement the run_cmd function")

	def run_script(self, script):
		raise NotImplemented("Inheriting classes must implement the run_script function")
	
	def put_file(self, location, contents):
		raise NotImplemented("Inheriting classes must implement the put_file function")
	
	def close(self):
		pass

class WinrmComms(VMComms):
	sep = "\\"

	def connect(self, ip, username, password, keep_going_event):
		self._log.debug("connecting to VM at {}".format(ip))
		self._sess = winrm.Session(ip, (username, password))

		count = 0
		e = None

		# loop until we can successfully 
		while keep_going_event.is_set():
			count += 1
#			if count == 20:
#				self._log.warn("COULD NOT CONNECT TO VM: {}".format(e))
#				return False

			try:
				# NOTE this is _sess.run_cmd, NOT! self.run_cmd
				r = self._sess.run_cmd("echo", ["blah"])
				if "blah" in r.std_out:
					break
			except Exception as e:
				self._log.error("could not connect: {}".format(e))
				pass

			# keep vm handlers from doing everything at exactly the same time
			time.sleep(0.5)

		self._log.info("connected to VM at {}!".format(ip))

		return True
	
	def close(self):
		pass
	
	def tmp_loc(self):
		return '$([System.Environment]::ExpandEnvironmentVariables("%TEMP%"))'
	
	def run_cmd(self, background=False, *cmd):
		if background:
			cmd = ["start", "cmd", "/k", '"{}"'.format(" ".join('"' + x + '"' for x in cmd))]

		try:
			r = self._sess.run_cmd(cmd[0], cmd[1:])
		except:
			return None
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
		try:
			step = 1500
			for i in range(0, len(contents), step):
				self._do_put_file(location, contents[i:i+step])

			return True
		except:
			return False
	
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
	def tmp_loc(self):
		return "/tmp"
	
	def connect(self, ip, username, password, keep_going_event):
		count = 0
		e = None

		while keep_going_event.is_set():
			count += 1
#			if count == 20:
#				self._log.warn("COULD NOT CONNECT TO VM: {}".format(e))
#				return False

			try:
				self._ssh = paramiko.SSHClient()
				self._ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
				try:
					self._ssh.connect(ip, username=username, password=password)
				except Exception as e:
					continue

				output = self.run_cmd(False, "echo", "blah")
				if "blah" in output:
					break
			except:
				pass

			time.sleep(0.5)

		self._scp = scp.SCPClient(self._ssh.get_transport())
		self._log.info("connected to VM at {}!".format(ip))

		return True
	
	def close(self):
		try:
			self._ssh.close()
		except:
			pass
	
	def run_cmd(self, background=False, *cmd):
		cmd = list(cmd)

		cmd = [pipes.quote(x) for x in cmd]
		if background:
			cmd.append("&")

		try:
			stdin,stdout,stderr = self._ssh.exec_command(" ".join(cmd))
			return "".join(stdout.readlines()) + "".join(stderr.readlines())
		except:
			return None
	
	def run_script(self, script, background=False):
		tmp_script_name = "/tmp/{}".format(str(random.random()))

		cmd = ["bash", tmp_script_name]
		if background:
			cmd.append("&")

		self.put_file(tmp_script_name, script)

		return self.run_cmd(background=background, *cmd)
	
	def put_file(self, location, contents):
		tmp = tempfile.NamedTemporaryFile()
		tmp.write(contents)

		# the full contents won't be written to disk if we don't
		# flush it
		tmp.flush()

		try:
			self._scp.put(tmp.name, location)
			return True
		except:
			return False
		finally:
			tmp.close()
