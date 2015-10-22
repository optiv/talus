#!/usr/bin/env python
# encoding: utf-8

from __future__ import absolute_import

import base64
import imp
import json
import logging
import os
import marshal
import pip
import pip.req
import requests
import re
from requests.auth import HTTPBasicAuth
import select
import site
import socket
import shutil
import struct
import subprocess
import sys
import threading
import time
import traceback

class FriendlyJSONEncoder(json.JSONEncoder):
	def default(self, o):
		# I don't want to have to import bson here, since that's installed
		# via a top-level requirements.txt with pymongo. We'll just check the
		# class name instead (HACK)
		if o.__class__.__name__ == "ObjectId":
			return str(o)
		else:
			return super(self.__class__, self).default(o)

ORIG_ARGS = sys.argv

# clear out any existing handlers
logging.getLogger().handlers = []

logging.getLogger("urllib3").setLevel(logging.WARN)

DEV = len(sys.argv) > 1 and sys.argv[1] == "dev"

log_file = os.path.join(os.path.dirname(__file__), __file__.split(".")[0] + ".log")
if DEV:
	logging.basicConfig(level=logging.DEBUG)
else:
	logging.basicConfig(filename=log_file, level=logging.DEBUG)
logging.getLogger("requests").setLevel(logging.CRITICAL)

stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(name)s:%(levelname)s: %(message)s')
stream_handler.setFormatter(formatter)
logging.getLogger().addHandler(stream_handler)

class LogAccumulator(logging.Handler):
	def __init__(self):
		super(self.__class__, self).__init__()
		self.records = []
	
	def emit(self, record):
		self.records.append(record)
	
	def get_records(self):
		formatter = logging.Formatter('%(asctime)s %(levelname)s:%(name)s:%(message)s')
		res = []
		for record in self.records:
			res.append(formatter.format(record))
		return res

class HostComms(threading.Thread):
	def __init__(self, recv_callback, job_id, job_idx, tool, dev=False):
		super(HostComms, self).__init__()

		self._log = logging.getLogger("HostComms")
		self._dev = dev

		while True:
			self._my_ip = socket.gethostbyname(socket.gethostname())
			if self._my_ip.startswith("127.0"):
				p = subprocess.Popen(["ifconfig", "eth0"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
				stdout,stderr = p.communicate()
				for line in stdout.split("\n"):
					if "inet addr:" in line:
						match = re.match(r'^\s*inet addr:(\d+\.\d+\.\d+\.\d+).*$', line)
						self._my_ip = match.group(1)
						break

			if not self._my_ip.startswith("192.168.123."):
				self._log.debug("we don't have an ip address yet (currently '{}')".format(self._my_ip))
				time.sleep(0.2)
				continue

			break

		self._log.debug("we have an ip! {}".format(self._my_ip))

		self._host_ip = self._my_ip.rsplit(".", 1)[0] + ".1"
		self._host_port = 55555

		self._job_id = job_id
		self._job_idx = job_idx
		self._tool = tool

		self._running = threading.Event()
		self._running.clear()
		self._connected = threading.Event()
		self._connected.clear()

		self._send_recv_lock = threading.Lock()

		self._recv_callback = recv_callback

		self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	
	def run(self):
		self._log.info("running")
		self._running.set()

		if not self._dev:
			self._sock.connect((self._host_ip, self._host_port))

		self._connected.set()

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
			},

			# use this so that users don't run into errors with ObjectIds not being
			# able to be encodable. If using bson.json_util.dumps was strictly used
			# everywhere, could just use that dumps method, but it's not, and I'd rather
			# keep it simple for now
			cls=FriendlyJSONEncoder
		)

		self._connected.wait(2**31)

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
		self.pypi_loc = loc.replace("/code_cache", "/pypi/")
		if self.loc.endswith("/"):
			self.loc = self.loc[:-1]

		self.username = username
		self.password = password

		self._code_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), "TALUS_CODE")
		if not os.path.exists(self._code_dir):
			os.makedirs(self._code_dir)
		sys.path.insert(0, self._code_dir)

		self._pypi_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), "TALUS_PYPI")
		if not os.path.exists(self._pypi_dir):
			os.makedirs(self._pypi_dir)
			os.makedirs(os.path.join(self._pypi_dir, "simple"))

		# since we will be installing code via "pip install --user ...", make
		# sure the user site is on our path
		if not os.path.exists(site.USER_SITE):
			os.makedirs(site.USER_SITE)
		sys.path.insert(0, site.USER_SITE)

		self.cache = {}

		self.cache["git"] = {"__items__":set(["talus/"]), "talus/":{"__items__": set()}}

		dir_check = lambda x: x.endswith("/")
		pypi_items = self._git_show("talus/pypi/simple")["items"]
		self.cache["pypi"] = dict(map(lambda x: (x.replace("/", ""), True), filter(dir_check, pypi_items)))
	
	def find_module(self, abs_name, path=None):
		"""Normally, a finder object would return a loader that can load the module.
		In our case, we're going to be sneaky and just download the files and return
		``None`` and let the normal sys.path-type loading take place.

		This method is cleaner and less error prone

		:param str abs_name: The absolute name of the module to be imported
		"""
		package_name = abs_name.split(".")[0]

		last_name = abs_name.split(".")[-1]
		if last_name in sys.modules:
			return None

		try:
			# means it can already be imported, no work to be done here
			imp.find_module(abs_name)

			# THIS IS IMPORTANT, YES WE WANT TO RETURN NONE!!!
			# THIS IS IMPORTANT, YES WE WANT TO RETURN NONE!!!
			# THIS IS IMPORTANT, YES WE WANT TO RETURN NONE!!!
			# THIS IS IMPORTANT, YES WE WANT TO RETURN NONE!!!
			# see the comment in the docstring
			return None
		except ImportError as e:
			pass

		if package_name == "talus" and self._module_in_git(abs_name):
			self.download_module(abs_name)
			# THIS IS IMPORTANT, YES WE WANT TO RETURN NONE!!!
			# THIS IS IMPORTANT, YES WE WANT TO RETURN NONE!!!
			# THIS IS IMPORTANT, YES WE WANT TO RETURN NONE!!!
			# THIS IS IMPORTANT, YES WE WANT TO RETURN NONE!!!
			# see the comment in the docstring
			return None

		# we NEED to have the 2nd check here or else it will keep downloading
		# the same package over and over
		if package_name in self.cache["pypi"] and package_name not in sys.modules:
			self.install_package(package_name)
			# just in case sys.argv got mucked with somehow/somewhere
			#os.execvp("python", [__file__] + ORIG_ARGS)
			#os.execvp("python", ORIG_ARGS)

		# THIS IS IMPORTANT, YES WE WANT TO RETURN NONE!!!
		# THIS IS IMPORTANT, YES WE WANT TO RETURN NONE!!!
		# THIS IS IMPORTANT, YES WE WANT TO RETURN NONE!!!
		# THIS IS IMPORTANT, YES WE WANT TO RETURN NONE!!!
		# see the comment in the docstring
		return None
# 	
# 	def load_module(self, abs_name, *args):
# 		if abs_name in sys.modules:
# 			mod = sys.modules[abs_name]
# 		else:
# 			mod = sys.modules.setdefault(abs_name, imp.new_module(abs_name))
# 
# 		fp, pathname, desc = imp.find_module(abs_name)
# 
# 		actual_path = pathname
# 		if not actual_path.endswith(".py") and not actual_path.endswith(".pyc"):
# 			actual_path = os.path.join(actual_path, "__init__.py")
# 
# 		mod.__file__ = actual_path
# 		mod.__name__ = abs_name
# 		mod.__path__ = pathname
# 		mod.__loader__ = self
# 		mod.__package__ = ".".join(abs_name.split(".")[:-1])
# 
# 		if actual_path.endswith("__init__.py") or actual_path.endswith("__init__.pyc"):
# 			mod.__path__ = [ pathname ]
# 
# 		data = open(actual_path, "rb").read()
# 		if actual_path.endswith(".pyc"):
# 			code = marshal.loads(data[8:])
# 		else:
# 			code = compile(data, actual_path, "exec")
# 
# 		exec code in mod.__dict__
# 
# 		return mod
	
	def download_module(self, abs_name):
		"""Download the module found at ``abs_name`` from the talus git repository

		:param str abs_name: The absolute module name of the module to be downloaded
		"""
		self._log.info("downloading module {}".format(abs_name))

		path = abs_name.replace(".", "/")
		info = self._git_show(path)

		if info is None:
			info_test = self._git_show(path + ".py")
			if info_test is None:
				raise ImportError(abs_name)
			info = info_test

		self._log.info("loading module {} from git".format(abs_name))

		if info["type"] == "listing":
			return self._download_folder(abs_name, info, self._code_dir)
		elif info["type"] == "file":
			return self._download_file(abs_name, info, self._code_dir)

		return None
	
	def _download_folder(self, abs_name, info, dest):
		"""Download the module (folder/__init__.py) from git. The module folder will
		only be recursively downloaded if it is a subfolder of the tools/components/lib
		folder.
		"""
		# if we're loading the root directory of a tool/component/library, recursively
		# download everything in git in that folder
		match = re.match(r'^talus\.(tools|components|lib)\.[a-zA-Z_0-9]+$', abs_name)
		recurse = (match is not None)

		self._download(dest, info=info, recurse=recurse)
	
	def install_requirements(self, rel_path):
		self._log.info("installing requirements {}".format(rel_path))
		full_path = os.path.join(self._code_dir, rel_path)

#		# from pip
#		for item in pip.req.parse_requirements(full_path, "somesessionid"):
#			if isinstance(item, pip.req.InstallRequirement):
#				self._log.info("downloading package {}".format(item.name))
#				self._download(self._pypi_dir, path="talus/pypi/simple/{}".format(item.name), recurse=True)

		try:
			pip.main([
				"install",
				"--user",
				# grab only the hostname from the pypi_loc
				"--trusted-host", re.match(r'^.*://([^/]+)/.*$', self.pypi_loc).group(1),
				"-i",
					self.pypi_loc,
					#"file://{}".format(os.path.abspath(os.path.join(self._pypi_dir, "talus", "pypi", "simple")).replace("\\", "/")),
				"-r",
					full_path
			])
		except SystemExit as e:
			self._log.error("Could not install package. Sorry :^(")
	
	def install_package(self, package_name):
		self._log.info("downloading package {} to local python index".format(package_name))
		pinfo = self.cache["pypi"][package_name]

		# folder structure:
		# pypi/
		#  |--pymongo/
		#		|--index.html
		#		|--pymongo-0.3.0.tar.gz
		#
		self._download(self._pypi_dir, path="talus/pypi/simple/{}".format(package_name), recurse=True)

		self._log.info("installing package {} from local python index".format(package_name))
		pip.main([
			"install",
			"--user",
			"-i",
				self.pypi_loc,
			package_name
		])
	
	def _download_file(self, abs_name, info, dest):
		"""Download the single file from git
		"""
		self._log.debug("downloading file: {}".format(info["filename"]))

		path = os.path.join(dest, info["filename"])
		with open(path, "wb") as f:
			f.write(base64.b64decode(info["contents"]))
	
	def _download(self, dest, path=None, info=None, recurse=False):
		"""Download files/folders (maybe recursively) into ``self._code_dir``. If the path
		is a directory, the directory's immediate children will be downloaded. If ``recurse``
		is ``True``, then all children will downloaded recursively.

		:param str dest: The root path that the relative path should be added to
		:param str path: The talus-code-repo relative path to download
		:param dict info: The maybe-already-obtained info about the path
		:param bool recurse: If it should be recursively downloaded
		"""
		if path is None and info is None:
			raise Exception("WTF are you doing?? unexpected condition")

		if path is not None and info is None:
			info = self._git_show(path)

		if info is None:
			raise Exception("Error! could not get information from code cache about {!r}".format(path))

		self._log.debug("downloading file: {}".format(info["filename"]))

		base_path = os.path.join(dest, info["filename"])

		if info["type"] == "listing":
			if not os.path.exists(base_path):
				os.makedirs(base_path)

			for item in info["items"]:
				if item.endswith("/"):
					if recurse:
						self._download(dest, "{}/{}".format(info["filename"], item), recurse=recurse)
				else:
					self._download(dest, "{}/{}".format(info["filename"], item))

		elif info["type"] == "file":
			with open(base_path, "wb") as f:
				f.write(base64.b64decode(info["contents"]))
			if os.path.basename(info["filename"]) == "requirements.txt" and \
					re.match(r'^(talus|talus/tools/[a-zA-Z_0-9]+|talus/components/[a-zA-Z_0-9]+)', os.path.dirname(info["filename"])) is not None:
				self.install_requirements(base_path)
	
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

		res = json.loads(res.text)

		# cache existence info about all directories shown!
		if path != "talus/pypi/simple" and res["type"] == "listing":
			self._add_to_cache(path, items=res["items"])

		return res
	
	def _add_to_cache(self, path, items=None):
		cache = root = self.cache["git"]

		parts = path.split("/")
		for part in parts:
			cache = cache.setdefault(part + "/", {"__items__": set()})

		for item in items:
			cache["__items__"].add(item)
	
	def _module_in_git(self, modname):
		parts = modname.split(".")

		cache = self.cache["git"]

		for part in parts[:-1]:
			items = cache["__items__"]
			if part + "/"  not in items:
				return False

			cache = cache[part + "/"]

		last_part = parts[-1]
		items = cache["__items__"]

		# e.g. talus.fileset
		if last_part + ".py" in items:
			return True

		# e.g. talus.tools
		if last_part + "/" in items:
			return True

		return False

class TalusBootstrap(object):
	"""The main class that will bootstrap the job and get things running
	"""

	def __init__(self, config_path, dev=False):
		"""
		:param str config_path: The path to the config file containing json information about the job
		"""
		self._log = logging.getLogger("BOOT")
		self._log_accumulator = LogAccumulator()
		# add this to the root logger so it will capture EVERYTHING
		logging.getLogger().addHandler(self._log_accumulator)

		if not os.path.exists(config_path):
			self._log.error("ERROR, config path {} not found!".format(config_path))
			logging.shutdown()
			exit(1)

		with open(config_path, "r") as f:
			self._config = json.loads(f.read())

		self._job_id = self._config["id"]
		self._idx = self._config["idx"]
		self._tool = self._config["tool"]
		self._params = self._config["params"]
		self._fileset = self._config["fileset"]
		self._db_host = self._config["db_host"]
		self._debug = self._config["debug"]
		self._num_progresses = 0

		self.dev = dev
		self._host_comms = HostComms(self._on_host_msg_received, self._job_id, self._idx, self._tool, dev=dev)
	
	def sys_except_hook(self, type_, value, traceback):
		formatted = traceback.format_exception(type_, value, traceback)

		self._log.exception("there was an exception!")
		self._log.error(formatted)
		try:
			self._host_comms.send_msg("error", {
				"message": str(value),
				"backtrace": formatted,
				"logs": self._log_accumulator.get_records()
			})
		except:
			pass
		logging.shutdown()

	def run(self):
		self._log.debug("running bootstrap")

		self._host_comms.start()
		self._host_comms.send_msg("started", {})

		self._install_code_importer()

		talus_mod = __import__("talus", globals(), locals(), fromlist=["job"])

		fileset_mod = getattr(talus_mod, "fileset")
		fileset_mod.set_connection(self._db_host)

		job_mod = getattr(talus_mod, "job")
		Job = getattr(job_mod, "Job")

		try:
			job = Job(
				id					= self._job_id,
				idx					= self._idx,
				tool				= self._tool,
				params				= self._params,
				fileset_id			= self._fileset,
				progress_callback	= self._on_progress,
				results_callback	= self._on_result,
			)
			job.run()
		except Exception as e:
			self._log.exception("Job had an error!")
			formatted = traceback.format_exc()
			self._host_comms.send_msg("error", {
				"message"		: str(e),
				"backtrace"		: formatted,
				"logs"			: self._log_accumulator.get_records()
			})
		else:
			# if the debug flag was set, then ALWAYS store the logs!
			if self._debug:
				self._host_comms.send_msg("logs", {
					"message"		: "DEBUG LOGS",
					"backtrace"		: "",
					"logs"			: self._log_accumulator.get_records()
				})

		if self._num_progresses == 0:
			self._log.info("progress was never called, but job finished running, inc progress by 1")
			self._on_progress(1)

		self._host_comms.stop()
		self._log.debug("finished")

		self._host_comms.send_msg("finished", {})

		self._shutdown()
	
	def _shutdown(self):
		"""shutdown the vm"""
		os_name = os.name.lower()
		if os_name == "nt":
			os.system("shutdown /t 0 /s /f")
		else:
			os.system("shutdown -h now")
	
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
	
	def _on_result(self, result_type, result_data):
		"""Append this to the results for this job

		:param object result_data: Any python object to be stored with this job's results (str, dict, a number, etc)
		"""
		self._log.debug("sending result")
		self._host_comms.send_msg("result", {"type": result_type, "data": result_data})
	
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
