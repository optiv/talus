#!/usr/bin/env python
# encoding: utf-8

import ast
import docutils
import docutils.examples
import inspect
import os
import re
import sys

import logging

logging.basicConfig(level=logging.DEBUG)

class TalusError(Exception): pass

class PyFuncTypeComponent(object):
	def __init__(self, raw):
		self.raw = raw
		self.type = "component"
		
		match = re.match(r'^Component\(([a-zA-Z0-9_]+)\)$', raw)
		if match is None:
			raise TalusError("Could not determine the component name from: {!r}".format(raw))
		self.name = match.group(1)

class PyFuncTypeNative(object):
	def __init__(self, native_type):
		self.type = "native"
		if native_type not in ["str", "list", "tuple", "dict", "int", "unicode"]:
			raise TalusError("Unsupported native type specified for parameter: {!r}".format(native_type))
		self.name = native_type

class PyFuncParam(object):
	def __init__(self, unparsed_name, desc):
		self.desc = desc
		self.type, self.name = self.get_type_and_name(unparsed_name)
	
	def get_type_and_name(self, data):
		parts = data.split()
		if len(parts) != 3:
			raise TalusError("Error! Param declarations need to be of the form" +
				"\n\n\t:param <type> <param-name>: <desc>" +
				"\n\nBut you gave:\n\n\t{}".format(data))

		param,type,name = parts

		if type.startswith("Component"):
			type = PyFuncTypeComponent(type)
		else:
			type = PyFuncTypeNative(type)

		return type,name

class PyFunc(object):
	def __init__(self, log, filename, func_node):
		self.filename = filename
		self.node = func_node
		self.name = func_node.name
		self._log = log.getChild(self.name)

		self.doc = ""
		if hasattr(func_node.body[0], "value") and isinstance(func_node.body[0].value, ast.Str):
			self.doc = func_node.body[0].value.s

		try:
			self.params = self.get_params(self.doc)
		except TalusError as e:
			raise TalusError(e.message + "\n\nError at {}:{}".format(self.filename, self.node.lineno))
	
	def get_params(self, docstring):
		self._log.debug("determining params")
		# these need to be IN ORDER!!!!
		params = []
		doc,_ = docutils.examples.internals(unicode(docstring))
		if len(doc.children) == 0:
			return params

		for quote in doc.children:
			if not isinstance(quote, docutils.nodes.block_quote):
				continue
			for field in quote:
				if not isinstance(field, docutils.nodes.field_list):
					continue
				for f in field:
					name = str(f[0][0])
					desc = str(f[1][0][0])

					# simple test to avoid :returns: and such
					if "param" in name:
						params.append(PyFuncParam(name, desc))

		return params

class PyClass(object):
	def __init__(self, log, filename, cls_node):
		self.filename = filename
		self._log = log.getChild(cls_node.name)

		if "components" in self.filename:
			self.type = "component"
			self.param_method = "init"
		elif "tools" in self.filename:
			self.type = "tool"
			self.param_method = "run"

		self.node = cls_node
		self.desc = ""
		self.name = cls_node.name
		self.bases = self.get_bases()
		self.methods = {}
		for idx,node in enumerate(cls_node.body):
			if idx == 0 and isinstance(node, ast.Expr) and isinstance(node.value, ast.Str):
				self.desc = node.value.s
			elif isinstance(node, ast.FunctionDef):
				method = PyFunc(self._log, filename, node)
				self.methods[method.name] = method
	
	def get_bases(self):
		res = []
		for x in self.node.bases:
			if isinstance(x, ast.Attribute):
				res.append(x.attr)
			elif isinstance(x, ast.Name):
				res.append(x.id)
		return res
	
	def get_run_params(self, query_func):
		self._log.debug("getting run params")
		params = {}

		if self.param_method in self.methods:
			for param in self.methods[self.param_method].params:
				self._log.debug("  param: {} ({} - {})".format(param.name, param.type.type, param.type.name))
				if param.type.type == "component" and not query_func(param.type.name):
					raise TalusError("Invalid component specified ({}) in {}:{}".format(
						param.type.name,
						self.filename,
						self.name
					))

				params[param.name] = dict(
					name	= param.name,
					type	= dict(
						type	= param.type.type, # native or component
						name	= param.type.name  # str/list/etc or component name
					),
					desc	= param.desc
				)
		else:
			self._log.debug("no {} method was specified?".format(self.param_method))
		return params

class Job(object):

	"""This is the class that will run a task."""

	def __init__(self, id, idx, params, tool, progress_callback, results_callback):
		"""TODO: to be defined1.

		:idx: TODO
		:params: TODO
		:tool: TODO

		"""
		self._id = id
		self._idx = idx
		self._params = params
		self._tool = tool
		self._progress_callback = progress_callback
		self._results_callback = results_callback

		self._log = logging.getLogger("JOB:{}".format(self._id))
	
	def run(self):
		self._log.debug("preparing to run job")

		try:
			tool_cls = self._get_tool_cls()
			real_params = self._convert_params(self._params, tool_cls)
			tool = tool_cls(self._idx, self._progress_callback, self._results_callback, self._log)

			self._log.debug("RUNNING TOOL")

			tool.run(**real_params)
		except TalusError as e:
			self._log.error(e.message)

		self._log.debug("FINISHED RUNNING TOOL")
	
	def _camel_to_under(self, name):
		s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
		return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()
	
	def _get_tool_cls(self):
		mod_name = self._camel_to_under(self._tool)
		mod = __import__("talus.tools." + mod_name, globals(), locals(), fromlist=[str(self._tool)])
		return getattr(mod, self._tool)

	def _get_component_cls(self, cls_name):
		mod_name = self._camel_to_under(cls_name)
		mod_base = __import__("talus.components", globals(), locals(), fromlist=[mod_name])
		mod = getattr(mod_base, mod_name)
		return getattr(mod, cls_name)
	
	def _convert_params(self, params, code_cls):
		filename = inspect.getfile(code_cls)
		param_types = self._get_param_types(code_cls)
		real_params = {}

		for name,val in params.iteritems():
			if name not in param_types:
				raise TalusError("unmapped argument: {!r}".format(name))

			real_params[name] = self._convert_val(param_types[name]["type"], val)
		
		return real_params
	
	def _convert_val(self, param_type, val):
		if param_type["type"] == "native":
			switch = {
				"str"	: lambda x: str(x),
				"list"	: lambda x: list(x),
				"tuple"	: lambda x: tuple(x),
				"dict"	: lambda x: dict(x),
				"int"	: lambda x: int(x),
				"unicode"	: lambda x: unicode(x)
			}
			return switch[param_type["name"]](val)

		elif param_type["type"] == "component":
			component_cls = self._get_component_cls(param_type["name"])
			component_args = self._convert_params(val, component_cls)
			val = component_cls(parent_log = self._log)
			val.init(**component_args)
			return val
	
	def _get_param_types(self, cls):
		cls_name = cls.__name__
		filename = inspect.getfile(cls)

		with open(filename, "r") as f:
			source = f.read()

		pyclass = None
		mod = ast.parse(source)
		for node in mod.body:
			if isinstance(node,ast.ClassDef):
				cls = PyClass(self._log, filename, node)
				if cls.name == cls_name:
					pyclass = cls
					break

		# make the query func always return true - this is assuming the
		# pre-receive hook has done its job and prevented invalid components
		# from slipping in
		return pyclass.get_run_params(lambda x: True)
