#!/usr/bin/env python
# encoding: utf-8

import bson
import logging
import os
import re
import sh
from sh import git
import shutil
import sys
import uuid
import tempfile

import master.models
from master.watchers import WatcherBase

logging.getLogger("sh").setLevel(logging.WARN)

TALUS_GIT = "/talus/talus_code.git"

class CodeWatcher(WatcherBase):
	collection = "talus.code"

	def __init__(self, *args, **kwargs):
		WatcherBase.__init__(self, *args, **kwargs)

		for code in master.models.Code.objects(type__in=["new_tool", "new_component"]):
			self._handle_new_code(code.id, code=code)

	def insert(self, id_, obj):
		self._log.debug("handling insert")

		self._handle_new_code(id_, obj)
	
	def update(self, id, mod):
		pass
	
	def delete(self, id):
		pass

	# -----------------------

	def _handle_new_code(self, id_, obj=None, code=None):
		if code is None:
			code = master.models.Code.objects(id=id_)[0]

		if not code.type.startswith("new_"):
			return

		code.type = code.type.replace("new_", "")

		self._log.info("creating new code from template ({}, {})".format(code.name, code.type))

		# TODO this should be in some central setting somewhere,
		# e.g. master.settings.TALUS_GIT or something
		tmpdir = tempfile.mkdtemp()
		git.clone(TALUS_GIT, tmpdir)
		self._log.info("cloned code into {}".format(tmpdir))

		if code.type == "tool":
			src_dir = os.path.join(tmpdir, "talus", "tools", "tool_template")
			dest_path = os.path.join(tmpdir, "talus", "tools", self._camel_to_under(code.name))
			replace_name = "ToolTemplate"

		elif code.type == "component":
			src_dir = os.path.join(tmpdir, "talus", "components", "component_template")
			dest_path = os.path.join(tmpdir, "talus", "components", self._camel_to_under(code.name))
			replace_name = "ComponentTemplate"

		self._log.info("copying template to {}".format(dest_path))
		shutil.copytree(src_dir, dest_path)

		files = ["__init__.py", "requirements.txt", "run_local.py"]

		for filename in files:
			filepath = os.path.join(dest_path, filename)
			if not os.path.exists(filepath):
				continue

			f = open(filepath, "rb+")
			file_data = f.read()
			f.seek(0)
			f.truncate()
			file_data = file_data.replace(replace_name, code.name)
			f.write(file_data)
			f.close()

		git_ = git.bake("--git-dir", os.path.join(tmpdir, ".git"), "--work-tree", tmpdir, _tty_out=False)
		git_.config("--local", "user.email", "master@talus")
		git_.config("--local", "user.name", "Talus Master")
		git_.add(dest_path)
		git_.commit(message="auto created from template by TALUS")
		git_.config("--local", "push.default", "matching")

		try:
			git_.push("origin")
		except Exception as e:
			self._log.error("ERROR COMMITTING CODE")
			self._log.error(e)
			self._log.error(e.stderr)

		# the git commit will have saved it!!!
		code.delete()

	def _camel_to_under(self, name):
		s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
		return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()		
