#!/usr/bin/env python
# encoding: utf-8

import requests

def json_request(method, *args, **params):
	content_type = "application/json"

	if "data" in params and hasattr(params["data"], "content_type"):
		content_type = params["data"].content_type

	params.setdefault("headers", {}).setdefault("content-type", content_type)

	try:
		res = method(*args, **params)
	except Exception as e:
		return None

	return res
