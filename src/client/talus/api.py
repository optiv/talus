#!/usr/bin/env python
# encoding: utf-8

import os
import collections
import datetime
import mmap
import requests
import shlex
import sys
import time

try:
	import requests
except ImportError as e:
	print("Error! requests module could not be imported. Perhaps install it with\n\n    pip install requests")
	exit()

try:
	import requests_toolbelt
except ImportError as e:
	print("Error! requests_toolbelt module could not be imported. Perhaps install it with\n\n    pip install requests-toolbelt")
	exit()

from requests_toolbelt.multipart.encoder import MultipartEncoder, MultipartEncoderMonitor

from talus.models import *

class TalusClient(object):

	"""An api client that will communicate with Talus"""

	def __init__(self, api_base="http://localhost:8001"):
		"""TODO: to be defined1. """
		object.__init__(self)

		self._api_base = api_base

	# -------------------------
	# VM image handling
	# -------------------------

	def image_iter(self):
		"""Return an iterator that iterates over all existing images in Talus
		:returns: iterator over all existing images
		"""
		for image in Image.objects(api_base=self._api_base):
			yield image

	def image_import(self, image_path, image_name, os_id, desc="desc", tags=None, username="user", password="password", file_id=None):
		"""TODO: Docstring for import_image.

		:image_path: The path to the image to be uploaded
		:image_name: The name of the resulting image
		:os_id: The id or name of the operating system document (string)
		:desc: A description of the image
		:tags: An array of tags associated with this VM image (e.g. ["browser", "ie", "ie10", "windows"])
		:username: The username to be used in the image
		:password: The password associated with the username
		:file_id: The id of the file that has already been uploaded to the server
		:returns: The configured image
		"""
		os = self._name_or_id(OS, os_id)
		if os is None:
			raise errors.TalusApiError("Could not locate OS by id/name {!r}".format(os_id))

		uploaded_file = file_id
		if uploaded_file is None:
			print("uploading file {!r}".format(image_path))
			image_path = self._clean_path(image_path)
			uploaded_file = self._upload_file(image_path)

			print("uploaded file id: {}".format(uploaded_file))

		if tags is None:
			tags = []

		image = Image(api_base=self._api_base)
		image.name = image_name
		image.os = os.id
		image.desc = desc
		image.tags = tags
		image.status = {"name": "import", "tmpfile": uploaded_file}
		image.username = username
		image.password = password
		image.timestamps = {"created": time.time()}

		image.save()

		return image
	
	def image_configure(self, image_id_or_name, vagrantfile=None, user_interaction=False):
		"""Configure the image with id ``image_id``. An instance of the image will
		be spun up which you can then configure. Shutting down the image will commit
		any changes.

		:image_id_or_name: The id or name of the image that is to be configured
		:vagrantfile: The contents of a vagrantfile that is to be used to configure the image
		:user_interaction: If the user should be given a chance to manually interact
		:returns: The configured image
		"""
		image = self._name_or_id(Image, image_id_or_name)
		if image is None:
			print("image with id or name {!r} not found".format(image_id_or_name))
			return

		image.status = {
			"name": "configure",
			"vagrantfile": vagrantfile,
			"user_interaction": user_interaction
		}
		image.save()

		return image
	
	def image_create(self, image_name, base_image_id_or_name, os_id, desc="", tags=None, vagrantfile=None, user_interaction=False):
		"""Create a new VM image based on an existing image.

		:image_name: The name of the new VM image (to be created)
		:base_image_id_or_name: The id or name of the base image
		:os_id: The id of the operating system
		:desc: A description of the new image
		:tags: A list of tags associated with the new image
		:vagrantfile: The Vagrantfile to run when creating the new image
		:user_interaction: Allow user interaction to occur (vs automatically shutting down the VM after the vagrantfile is run)
		:returns: The created image
		"""
		base_image = self._name_or_id(Image, base_image_id_or_name)
		if base_image is None:
			print("Base image with id or name {!r} not found".format(base_image_id_or_name))
			return

		base_image_id = base_image.id

		# essentially use the base_image as the base for the new image
		base_image.clear_id()
		image = base_image 
		# required
		image.name = image_name
		image.base_image = base_image_id

		if os_id is not None:
			image.os = os_id
		if desc is not None:
			image.desc = desc
		if tags is not None:
			image.tags = tags

		image.status = {
			"name": "create",
			"vagrantfile": vagrantfile,
			"user_interaction": user_interaction
		}
		image.save()

		return image
	
	def image_delete(self, image_id_or_name):
		"""Delete the image with id ``image_id`` or name ``name``

		:image_id: The id of the image to delete
		:returns: None
		"""
		image = Image.find_one(api_base=self._api_base, id=image_id_or_name)
		if image is None:
			image = Image.find_one(api_base=self._api_base, name=image_id_or_name)
			if image is None:
				print("image with id or name {!r} not found".format(image_id_or_name))
				return

		image.status = {
			"name": "delete"
		}
		image.save()
		return image

	# -------------------------
	# VM os handling
	# -------------------------

	def os_iter(self):
		"""Return an iterator that iterates over all existing OS models in Talus
		:returns: iterator
		"""
		for os_ in OS.objects(api_base=self._api_base):
			yield os_
	
	def os_delete(self, os_id):
		"""Delete an os by ``os_id`` which may be the id or name
		
		:os_id: The name or id of the os to delete
		"""
		os_ = self._name_or_id(OS, os_id)
		if os_ is None:
			raise errors.TalusApiError("Could not locate os with name/id {!r}".format(os_id))
		if len(Image.objects(api_base=self._api_base, os=os_.id)) > 0:
			raise errors.TalusApiError("Could not delete OS, more than one image references it")
		os_.delete()

	# -------------------------
	# code handling
	# -------------------------

	def code_iter(self, type_=None):
		"""Return an iterator that iterates over all existing Code models in Talus
		:returns: iterator
		"""
		filter_ = {}
		if type_ is not None:
			filter_["type"] = type_
		for code in Code.objects(api_base=self._api_base, **filter_):
			yield code
	
	def code_find(self, name_or_id, **search):
		return self._name_or_id(Code, name_or_id, **search)

	# -------------------------
	# task handling
	# -------------------------

	def task_iter(self):
		"""Return an iterator that iterates over all existing Task models in Talus
		:returns: iterator
		"""
		for task in Task.objects(api_base=self._api_base):
			yield task

	def task_create(self, name, tool_id, params, version=None, limit=1):
		"""Create a new task with the supplied arguments

		:name: The name of the task
		:tool_id: The id or name of the tool the task will run
		:params: A dict of params for the task
		:version: The version of code to use. None defaults to the HEAD version (default: None)
		:limit: The default limit of any jobs that use this task
		:returns: The task model
		"""
		tool = self._name_or_id(Code, tool_id, type="tool")
		if tool is None:
			raise errors.TalusApiError("Could not locate Tool by id/name {!r}".format(tool_id))
		if not isinstance(params, dict):
			raise errors.TalusApiError("params must be a dict!")

		task = Task(api_base=self._api_base)
		task.name = name
		task.tool = tool.id
		task.version = version
		task.params = params
		task.limit = limit
		task.save()
	
	def task_delete(self, task_id):
		"""Delete a task by ``task_id`` which may be the id or name
		
		:task_id: The name or id of the task to delete
		"""
		task = self._name_or_id(Task, task_id)
		if task is None:
			raise errors.TalusApiError("Could not locate task with name/id {!r}".format(task_id))
		task.delete()
		
	# -------------------------
	# slave handling
	# -------------------------

	def slave_iter(self, **search):
		"""Iterate through all of the slaves

		:search: optional search parameters
		"""
		for slave in Slave.objects(api_base=self._api_base, **search):
			yield slave
		
	# -------------------------
	# job handling
	# -------------------------

	def job_iter(self, **search):
		"""Iterate through all of the jobs

		:search: optional search parameters
		"""
		for job in Job.objects(api_base=self._api_base, **search):
			yield job
	
	def job_create(self, task_name_or_id, image, name=None, params=None, priority=50, queue="jobs", limit=1):
		"""Create a new job (run a task)"""
		task = self._name_or_id(Task, task_name_or_id)
		if task is None:
			raise errors.TalusApiError("could not locate task with id/name {!r}".format(task_name_or_id))

		image_obj = self._name_or_id(Image, image)
		if image_obj is None:
			raise errors.TalusApiError("could not locate image with id/name {!r}".format(image))
		image = image_obj

		if name is None:
			name = task.name + " " + str(datetime.datetime.now())

		if limit is None:
			limit = task.limit

		# any params set will UPDATE the default params, not override them
		base_params = task.params
		if params is not None:
			base_params = self._dict_nested_updated(base_params, params)

		job = Job(api_base=self._api_base)
		job.name = name
		job.image = image.id
		job.params = base_params
		job.task = task.id
		job.status = {"name": "run"}
		job.timestamps = {"created": time.time()}
		job.priority = priority
		job.queue = queue
		job.limit = limit
		job.save()
		
	# -------------------------
	# utility
	# -------------------------

	def _dict_nested_updated(self, base, new):
		"""Update a nested dictionary

		:base: the base dict
		:new: the new values for the dict
		:returns: the updated dict
		""" 
		for k,v in new.iteritems():
			if isinstance(v, collections.Mapping):
				r = self._dict_nested_updated(base.get(k, {}), v)
				base[k] = r
			else:
				base[k] = new[k]
		return base
	
	def _name_or_id(self, cls, name_or_id, **extra):
		"""Find model by name or id

		:name_or_id: The name or id of the model
		:extra: Any additional search/filter arguments
		:returns: The first model if found, else None
		"""
		res = cls.find_one(api_base=self._api_base, id=name_or_id, **extra)
		if res is None:
			res = cls.find_one(api_base=self._api_base, name=name_or_id, **extra)
			if res is None:
				return None
		return res

	def _upload_file(self, path):
		"""Upload the file found at ``path`` to talus, returning an id

		:path: The (local) path to the file
		:returns: An id for the remote file

		"""
		if not os.path.exists(path):
			raise errors.TalusApiError("Cannot upload image, path {!r} does not exist".format(path))

		total_size = os.path.getsize(path)
		self.last_update = ""
		def print_progress(monitor):
			sys.stdout.write("\b" * len(self.last_update))
			percent = float(monitor.bytes_read) / monitor.len

			update = "{:0.2f}%".format(percent * 100)
			if len(update) < 7:
				u = " " * (7 - len(update)) + update

			if len(update) < len(self.last_update):
				update += " " * (len(self.last_update) - len(update))
			sys.stdout.write(update)
			sys.stdout.flush()
			self.last_update = update
		
		data = {
			"file": (os.path.basename(path), open(path, "rb"), "application/octet-stream")
		}
		e = MultipartEncoder(fields=data)
		m = MultipartEncoderMonitor(e, print_progress)
		res = requests.post(
			self._api_base + "/api/upload/",
			data=m,
			headers={"Content-Type":e.content_type},
			timeout=(60*60) # super long timeout for uploading massive files!
		)

		# clear out the last of the progress percent that was printed
		print("\b" * len(self.last_update))

		if res.status_code // 100 != 2:
			raise errors.TalusApiError("Could not upload file!", error=res.text)

		if res.text[0] in ["'", '"']:
			return res.text[1:-1]

		return res.text

	def _api(self, path):
		"""Join the api base with path"""
		return self._api_base + "/" + path
	
	def _clean_path(self, path):
		return os.path.realpath(os.path.expanduser(path))
