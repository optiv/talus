#!/usr/bin/env python
# encoding: utf-8

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

	output = git.show(ref + ":" + path)
	lines = output.split("\n")

	res = {}
	res["filename"] = path
	parts = lines[0].split()

	# directories
	if len(parts) > 1 and parts[0] == "tree" and len(parts) > 1 and parts[1].startswith(ref + ":" + path):
		res["type"] = "listing"
		res["items"] = filter(lambda x:len(x) > 0, [x.strip() for x in lines[2:]])
	
	# files
	else:
		res["type"] = "file"
		res["contents"] = str(output)

	return HttpResponse(json.dumps(res), "application/json")
