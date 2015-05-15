#!/usr/bin/env python
# encoding: utf-8

from __future__ import absolute_import

import imp
import json
import logging
import os
import requests
import re
from requests.auth import HTTPBasicAuth
import select
import socket
import shutil
import struct
import sys
import threading
import time

DEV = len(sys.argv) > 1 and sys.argv[1] == "dev"

log_file = os.path.join(os.path.dirname(__file__), __file__.split(".")[0] + ".log")
if DEV:
	logging.basicConfig(level=logging.DEBUG)
else:
	logging.basicConfig(filename=log_file, level=logging.DEBUG)
logging.getLogger("requests").setLevel(logging.CRITICAL)

class HostComms(threading.Thread):
	def __init__(self, recv_callback, job_id, job_idx, tool, dev=False):
		super(HostComms, self).__init__()

		self._log = logging.getLogger("HostComms")
		self._dev = dev

		self._my_ip = socket.gethostbyname(socket.gethostname())
		self._host_ip = self._my_ip.rsplit(".", 1)[0] + ".1"
		self._host_port = 55555

		self._job_id = job_id
		self._job_idx = job_idx
		self._tool = tool

		self._running = threading.Event()
		self._running.clear()
		self._send_recv_lock = threading.Lock()

		self._recv_callback = recv_callback

		self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	
	def run(self):
		self._log.info("running")
		self._running.set()

		if not self._dev:
			self._sock.connect((self._host_ip, self._host_port))

		while self._running.is_set():
			if not self._dev:
				reads,_,_ = select.select([self._sock],[],[], 0.1)
				if len(reads) > 0:
					data = ""
					with self._send_recv_lock:
						while True:
							recvd = self._sock.recv(0x1000)
							if len(recvd) == 0:
								break
							data += recvd
					self._recv_callback(data)
			time.sleep(0.1)

		self._log.info("finished")
	
	def stop(self):
		self._log.info("stopping")
		self._running.clear()
	
	def send_msg(self, type, data):
		data = json.dumps({
			"job": self._job_id,
			"idx": self._job_idx,
			"tool": self._tool,
			"type": type,
			"data": data
		})
		data_len = struct.pack(">L", len(data))
		if not self._dev:
			try:
				with self._send_recv_lock:
					self._sock.send(data_len + data)
			except:
				# yes, just silently fail I think???
				pass

class TalusCodeImporter(object):
	"""This class will dynamically import tools and components from the
	talus git repository.
	
	This class *should* conform to "pep-302":https://www.python.org/dev/peps/pep-0302/
	"""

	def __init__(self, loc, username, password, parent_log=None):
		"""Create a new talus code importer that will fetch code from the specified
		``location``, using ``username`` and ``password``.

		:param str loc: The repo location (e.g. ``https://....`` or ``ssh://...``)
		:param str username: The username to fetch the code with
		:param str password: The password to fetch the code with
		"""
		if parent_log is None:
			parent_log = logging.getLogger("BOOT")
		self._log = parent_log.getChild("importer")

		self.loc = loc
		if self.loc.endswith("/"):
			self.loc = self.loc[:-1]

		self.username = username
		self.password = password

		self._code_dir = os.path.join(os.path.dirname(__file__), "TALUS_CODE")
		if not os.path.exists(self._code_dir):
			os.makedirs(self._code_dir)
		sys.path.insert(0, self._code_dir)

		self.cache = {}

		dir_check = lambda x: x.endswith("/")
		self.cache["tools"] = filter(dir_check, self._git_show("talus/tools")["items"])
		self.cache["components"] = filter(dir_check, self._git_show("talus/components")["items"])
		self.cache["lib"] = filter(dir_check, self._git_show("talus/lib")["items"])

		tools = []
	
	def find_module(self, abs_name, path=None):
		"""Normally, a finder object would return a loader that can load the module.
		In our case, we're going to be sneaky and just download the files and return
		``None`` and let the normal sys.path-type loading take place.

		This method is cleaner and less error prone

		:param str abs_name: The absolute name of the module to be imported
		"""
		# git ls-files for performance
		#git.ls_files(
		# Monkeys eat bananas and poop all day.
		if not abs_name.split(".")[0] == "talus":
			return None

		self.download_module(abs_name)

		# THIS IS IMPORTANT, YES WE WANT TO RETURN NONE!!!
		# THIS IS IMPORTANT, YES WE WANT TO RETURN NONE!!!
		# THIS IS IMPORTANT, YES WE WANT TO RETURN NONE!!!
		# THIS IS IMPORTANT, YES WE WANT TO RETURN NONE!!!
		# see the comment in the docstring
		return None
	
	def download_module(self, abs_name):
		"""Download the module found at ``abs_name`` from the talus git repository

		:param str abs_name: The absolute module name of the module to be downloaded
		"""
		path = abs_name.replace(".", "/")
		info = self._git_show(path)

		if info is None:
			info_test = self._git_show(path + ".py")
			if info_test is None:
				raise ImportError(abs_name)
			info = info_test

		self._log.info("loading module {} from git".format(abs_name))

		if info["type"] == "listing":
			return self._download_folder(abs_name, info)
		elif info["type"] == "file":
			return self._download_file(abs_name, info)

		return None
	
	def _download_folder(self, abs_name, info):
		"""Download the module (folder/__init__.py) from git. The module folder will
		only be recursively downloaded if it is a subfolder of the tools/components/lib
		folder.
		"""
		# if we're loading the root directory of a tool/component/library, recursively
		# download everything in git in that folder
		match = re.match(r'^talus\.(tools|components|lib)\.[a-zA-Z_0-9]+$', abs_name)
		recurse = (match is not None)

		self._download(info=info, recurse=recurse)
	
	def _download_file(self, abs_name, info):
		"""Download the single file from git
		"""
		path = os.path.join(self._code_dir, info["filename"])
		with open(path, "wb") as f:
			f.write(info["contents"])
	
	def _download(self, path=None, info=None, recurse=False):
		"""Download files/folders (maybe recursively) into ``self._code_dir``. If the path
		is a directory, the directory's immediate children will be downloaded. If ``recurse``
		is ``True``, then all children will downloaded recursively.

		:param str path: The talus-code-repo relative path to download
		:param dict info: The maybe-already-obtained info about the path
		:param bool recurse: If it should be recursively downloaded
		"""
		if path is None and info is None:
			raise Exception("WTF are you doing?? unexpected condition")

		if path is not None and info is None:
			info = self._git_show(path)

		base_path = os.path.join(self._code_dir, info["filename"])
		#self._log.info("downloading to {}".format(base_path))

		if info["type"] == "listing":
			if not os.path.exists(base_path):
				os.makedirs(base_path)

			for item in info["items"]:
				if item.endswith("/"):
					if recurse:
						self._download("{}/{}".format(info["filename"], item), recurse=recurse)
				else:
					self._download("{}/{}".format(info["filename"], item))

		elif info["type"] == "file":
			with open(base_path, "wb") as f:
				f.write(info["contents"])
	
	def _git_show(self, path, ref="HEAD"):
		"""Return the json object returned from the /code_cache on the web server

		:str param path: The talus-code-relative path to get information about (file or directory)
		:str param ref: The reference with which to lookup the code (can be a branch, commit, etc)
		"""
		res = requests.get(
			"/".join([self.loc, ref, path]),
			auth=HTTPBasicAuth(self.username, self.password)
		)

		if res.status_code // 100 != 2:
			return None

		return json.loads(res.text)

class TalusBootstrap(object):
	"""The main class that will bootstrap the job and get things running
	"""

	def __init__(self, config_path, dev=False):
		"""
		:param str config_path: The path to the config file containing json information about the job
		"""
		self._log = logging.getLogger("BOOT")

		if not os.path.exists(config_path):
			self._log.error("ERROR, config path {} not found!".format(config_path))
			exit(1)

		with open(config_path, "r") as f:
			self._config = json.loads(f.read())

		self._job_id = self._config["id"]
		self._idx = self._config["idx"]
		self._tool = self._config["tool"]
		self._params = self._config["params"]
		self._num_progresses = 0

		self.dev = dev
		self._host_comms = HostComms(self._on_host_msg_received, self._job_id, self._idx, self._tool, dev=dev)

	def run(self):
		self._log.debug("running bootstrap")

		self._host_comms.start()
		self._install_code_importer()

		talus_mod = __import__("talus", globals(), locals(), fromlist=["job"])
		job_mod = getattr(talus_mod, "job")
		Job = getattr(job_mod, "Job")

		try:
			job = Job(
				id					= self._job_id,
				idx					= self._idx,
				tool				= self._tool,
				params				= self._params,
				progress_callback	= self._on_progress,
				results_callback	= self._on_result,
			)
			job.run()
		except Exception as e:
			self._log.exception("Job had an error!")

		if self._num_progresses == 0:
			self._log.info("progress was never called, but job finished running, inc progress by 1")
			self._on_progress(1)

		self._host_comms.stop()
		self._log.debug("finished")

		self._host_comms.send_msg("finished", {})

		self._shutdown()
	
	def _shutdown(self):
		"""shutdown the vm"""
		os.system("shutdown -t 0 -r -f")
		os.system("shutdown now")
	
	def _on_host_msg_received(self, data):
		"""Handle the data received from the host

		:param str data: The raw data (probably in json format)
		"""
		self._log.info("received a message from the host: {}".format(data))
		data = json.loads(data)
	
	def _on_progress(self, num):
		"""Increment the progress count for this job by ``num``

		:param int num: The number to increment the progress count of this job by
		"""
		self._num_progresses += num
		self._log.debug("progress incrementing by {}".format(num))
		self._host_comms.send_msg("progress", num)
	
	def _on_result(self, result_data):
		"""Append this to the results for this job

		:param object result_data: Any python object to be stored with this job's results (str, dict, a number, etc)
		"""
		self._log.debug("sending result")
		self._host_comms.send_msg("result", result_data)
	
	def _install_code_importer(self):
		"""Install the sys.meta_path finder/loader to automatically load modules from
		the talus git repo.
		"""
		self._log.debug("installing talus code importer")
		code = self._config["code"]
		self._code_importer = TalusCodeImporter(
			code["loc"],
			code["username"],
			code["password"],
			parent_log = self._log
		)
		sys.meta_path = [ self._code_importer ]

def main(dev=False):
	config_path = os.path.join(os.path.dirname(__file__), "config.json")
	bootstrap = TalusBootstrap(config_path, dev=dev)
	bootstrap.run()

if __name__ == "__main__":
	dev = False
	if len(sys.argv) > 1 and sys.argv[1] == "dev":
		dev = True

	main(dev=dev)
