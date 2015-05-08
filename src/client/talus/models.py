#!/usr/bin/env python
# encoding: utf-8

from bson import json_util
import copy
import json
import os
import re
import sys


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

from requests_toolbelt.multipart.encoder import MultipartEncoder

import talus.errors as errors
import talus.utils as utils

# for the lazy
API_BASE = "http://localhost:8000"
def set_base(new_base):
	global API_BASE
	API_BASE = new_base

class Field(object):
	def __init__(self, default_value=None, details=False):
		self.value = default_value
		self.details = details
	
	def get_val(self):
		return self.value
	
	def dup(self):
		return self.__class__(self.get_val())

	def __getitem__(self, name):
		if hasattr(self.value, "__getitem__"):
			return self.value.__getitem__(name)
		else:
			raise AttributeError
	
	def __setitem__(self, name, value):
		if hasattr(self.value, "__setitem__"):
			return self.value.__setitem__(name, value)
		else:
			raise AttributeError

class RefField(Field):
	def __init__(self, default_value=None, details=False):
		Field.__init__(self, default_value, details)
	
	def get_val(self):
		if isinstance(self.value, dict) and "id" in self.value:
			return self.value["id"]
		return self.value

class TalusModel(object):
	"""The baseclass for Talus API models"""

	# the path of the model, e.g. "api/os"
	api_path = ""
	
	# the defined fields, with default values
	fields = {}

	@classmethod
	def api_url(cls, base):
		"""Add the base path and the model's api_path together"""
		if base is None:
			base = API_BASE

		return "{}/{}/".format(
			base,
			cls.api_path
		)
	
	@classmethod
	def headers(cls):
		res = ["id"]

		if "name" in cls.fields:
			res.append("name")

		if "hostname" in cls.fields:
			res.append("hostname")

		for k,v in cls.fields.iteritems():
			if k in res or v.details:
				continue
			res.append(k)
		return res
	
	@classmethod
	def find_one(cls, api_base=None, **search):
		"""Return the first matching model, or None if none matched

		:api_base: The base of the api url, If None, models.API_BASE will be used
		:**search: The search params
		:returns: The matched model or None
		"""
		res = cls.objects_raw(api_base, **search)
		if len(res) == 0:
			return None
		model = cls(**res[0])
		model.api_base = api_base
		return model

	@classmethod
	def objects(cls, api_base=None, **search):
		"""Return a list of models

		:api_base: The base of the api url. If none, models.API_BASE will be used
		:**search: search params
		:returns: A list of models

		"""
		res = []
		for item in cls.objects_raw(api_base, **search):
			model = cls(**item)
			model.api_base = api_base
			res.append(model)
		return res

	@classmethod
	def objects_raw(cls, api_base=None, **search):
		"""Return a list of json objects

		:api_base: The base of the api url. If none, models.API_BASE will be used
		:**search: search params
		:returns: A list of models as json objects (raw)

		"""
		r = utils.json_request(requests.get, cls.api_url(api_base), params=search)
		try:
			res = r.json()
			return res
		# TODO maybe there should be better error handling here??
		except:
			return []

	def __init__(self, api_base=API_BASE, **fields):
		"""Create a new model from a dictionary of its fields
		
		:**fields: dictionary of the model's fields"""
		if len(fields) == 0:
			fields = {}
			for k,v in self.fields.iteritems():
				fields[k] = v.dup()

		self._populate(fields)
		object.__setattr__(self, "api_base", api_base)
	
	# --------------------
	# other
	# --------------------

	def clear_id(self):
		if "id" in self._fields:
			del self._fields["id"]

	def save(self):
		"""Save this model's fields
		"""
		files = None
		data = json.dumps(self._filtered_fields())

		if "id" in self._fields:
			res = utils.json_request(
				requests.put,
				self._id_url(),
				data=data
			)
		else:
			res = utils.json_request(
				requests.post,
				self.api_url(self.api_base),
				data=data
			)

		# yes, that's intentional (the //) - look it up
		if res.status_code // 100 != 2:
			raise errors.TalusApiError("Could not save model", error=res.text)

		self._populate(res.json())
	
	def delete(self):
		"""Delete this model
		"""
		res = utils.json_request(requests.delete, self._id_url())
		if res.status_code // 100 != 2:
			raise errors.TalusApiError("Could not delete model", error=res.text)
		self._fields = {}
	
	def refresh(self):
		"""Refresh the current model
		"""
		if "id" not in self._fields:
			return
		matches = self.objects_raw(api_base=self.api_base, id=self.id)
		if len(matches) == 0:
			raise errors.TalusApiError("Error! current model no longer exists!")
		update = matches[0]
		self._populate(update)
	
	def _populate(self, fields):
		"""Populate this model's values from the given fields

		:fields: a dict of field values
		"""
		res = {}
		for k,v in self.__class__.fields.iteritems():
			res[k] = v.dup()
			if k in fields:
				if isinstance(fields[k], Field):
					res[k].value = fields[k].get_val()
				else:
					res[k].value = fields[k]

		for k,v in fields.iteritems():
			if k not in res:
				if isinstance(v, Field):
					res[k] = v.get_val()
				else:
					res[k] = v

		object.__setattr__(self, "_fields", res)
	
	def _filtered_fields(self):
		res = {}
		for k,v in self._fields.iteritems():
			if isinstance(v, Field):
				v = v.get_val()
			if v is None:
				continue
			res[k] = v
		return res
	
	def _id_url(self):
		return self.api_url(self.api_base) + self.id + "/"
	
	def __iter__(self):
		"""Used for printing the model in a table"""
		for name in self.headers():
			v = self._fields[name]
			if isinstance(v, Field):
				v = v.get_val()
			yield str(v)[0:40]
	
	def __getattr__(self, name):
		if name in self._fields:
			if isinstance(self._fields[name], Field):
				return self._fields[name].get_val()
			else:
				return self._fields[name]
		raise KeyError(name)
	
	def __setattr__(self, name, value):
		if name not in self._fields:
			return object.__setattr__(self, name, value)

		if isinstance(value, TalusModel):
			value = value.id

		if isinstance(self._fields[name], Field):
			self._fields[name].value = value
		else:
			self._fields[name] = value

class Task(TalusModel):
	"""The model for Tasks"""
	api_path = "api/task"
	fields = {
		"name": Field(""),
		"tool": RefField(),
		"params": Field({}, details=True),
		"version": Field(""),
		"timestamps": Field({}, details=True),
		"limit": Field(1)
	}

class Job(TalusModel):
	"""The model for running tasks ("Jobs")"""
	api_path = "api/job"
	fields = {
		"name": Field(""),
		"task": RefField(),
		"params": Field({}, details=True),
		"status": Field({}),
		"timestamps": Field({}),
		"priority": Field(50), # 0-100
		"queue": Field(""),
		"limit": Field(1),
		"progress": Field(),
		"image": RefField()
	}

class Code(TalusModel):
	"""The model for Tools/Components"""
	api_path = "api/code"
	fields = {
		"name": Field(""),
		"type": Field(""),
		"params": Field([], details=True),
		"bases": Field([]),
		"desc": Field("", details=True),
		"timestamps": Field({}, details=True)
	}

class OS(TalusModel):
	"""The model for OS API objects"""
	api_path = "api/os"
	fields = {
		"name": Field(""),
		"version": Field(""),
		"type": Field(""),
		"arch": Field("")
	}
		
class Image(TalusModel):
	"""The model for Image API objects"""
	api_path = "api/image"
	fields = {
		"name": Field(""),
		"os": RefField(),
		"desc": Field("", details=True),
		"tags": Field([]),
		"status": Field({}),
		"username": Field(details=True),
		"password": Field(details=True),
		"base_image": RefField(),
		"timestamps": Field({}, details=True)
	}

class Slave(TalusModel):
	"""The model for Slave API objects -- intended to be READ ONLY"""
	api_path = "api/slave"
	fields = {
		"hostname": Field(""),
		"uuid": Field(""),
		"ip": Field(""),
		"max_vms": Field(1),
		"running_vms": Field(0),
		"total_jobs_run": Field(0)
	}
