#!/usr/bin/env python
# encoding: utf-8

import os
import re
import tempfile

class TalusApiError(Exception):
	def __init__(self, msg, error=None, *args, **kwargs):
		if error is not None:
			tmp_base = tempfile.gettempdir()
			tmp_path = os.path.join(tmp_base, "talus_client_error.html")
			with open(tmp_path, "w") as f:
				f.write(error)

			# TODO this is definitely not ideal... come back later and return an appropriate
			# structured response with an error message. Might be difficult to do with
			# django rest framework though
			match = re.match(r'.*<h1>(.*)</h1>.*', error, re.MULTILINE | re.DOTALL)
			if match is not None:
				e_match = re.match(r'.*<pre class=.exception_value.>([^<]*)</pre>.*', error, re.MULTILINE | re.DOTALL)
				if e_match is not None:
					msg += "\n\n{}: {}".format(
						match.group(1),
						e_match.group(1).
							replace("&quot;", '"').
							replace("&gt;", ">").
							replace("&lt;", "<").
							replace("&#39;", "'")
					)

			msg += "\n\nFull error text can be found at {}".format(tmp_path)

		Exception.__init__(self, msg, *args, **kwargs)
