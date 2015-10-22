#!/usr/bin/env python
# encoding: utf-8

import base64
import json
import os
from sh import git as GIT
from sh import ls

from django.http import HttpResponse
from django.shortcuts import render

code_path = "/code_cache/code"
git = GIT.bake("--git-dir", os.path.join(code_path, ".git"), "--work-tree", code_path, _tty_out=False)

def git_info(request, ref, path):
	path = path
	data = {"ref": ref, "path": path}

	res = {}
	res["filename"] = path

	if path.startswith("talus/pypi"):
		file_path = os.path.join(code_path, path)
		if os.path.isdir(file_path):
			res["type"] = "listing"
			items = []
			for item in os.listdir(file_path):
				if os.path.isdir(os.path.join(file_path, item)):
					item += "/"
				items.append(item)
			res["items"] = items

		elif os.path.isfile(file_path):
			res["type"] = "file"
			with open(file_path, "rb") as f:
				res["contents"] = base64.b64encode(f.read())

	else:
		output = git.show(ref + ":" + path)
		output_stdout = output.stdout

		# it's a directory
		if output_stdout.startswith("tree {}:{}".format(ref, path)):
			lines = output_stdout.split("\n")
			res["type"] = "listing"
			res["items"] = filter(lambda x:len(x) > 0, [x.strip() for x in lines[2:]])

		# files
		else:
			res["type"] = "file"
			res["contents"] = base64.b64encode(output_stdout)

	return HttpResponse(json.dumps(res), "application/json")
