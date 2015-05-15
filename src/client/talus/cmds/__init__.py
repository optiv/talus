#!/usr/bin/env python
# encoding: utf-8

import cmd
import glob
import os
import re
import readline
import sys
import textwrap
import types

import talus.api
import talus.errors

ENABLED_COMMANDS = []

class TalusMetaClass(type):
	def __init__(cls, name, bases, namespace):
		global ENABLED_COMMANDS
		super(TalusMetaClass, cls).__init__(name, bases, namespace)

		if cls.__name__ in ["TalusCmdBase"]:
			return

		ENABLED_COMMANDS.append(cls)

class TalusCmdBase(object,cmd.Cmd):
	__metaclass__ = TalusMetaClass

	# to be overridden by inheriting classes
	command_name = ""

	def __init__(self, talus_host=None, talus_client=None):
		"""Create a new TalusCmdBase

		:talus_host: The root of the talus web app (e.g. http://localhost:8001 if the api is at http://localhost:8001/api)
		"""
		cmd.Cmd.__init__(self)

		self._talus_host = talus_host
		self._talus_client = talus_client
		if self._talus_host is not None and self._talus_client is None:
			self._talus_client = talus.api.TalusClient(self._talus_host)

	def emptyline(self):
		"""don't repeat the last successful command"""
		pass

	def do_quit(self, args):
		"""Quit the program"""
		exit()
	
	def onecmd(self, *args, **kwargs):
		try:
			cmd.Cmd.onecmd(self, *args, **kwargs)
		except talus.errors.TalusApiError as e:
			sys.stderr.write(e.message + "\n")
	
	@classmethod
	def get_command_helps(cls):
		"""Look for methods in this class starting with do_.

		:returns: A dict of commands and their help values. E.g. ``{"list": "List all the images"}``
		"""
		res = {}
		regex = re.compile(r'^do_(.*)$')
		for name in dir(cls):
			match = regex.match(name)
			if match is not None:
				cmd = match.group(1)
				prop = getattr(cls, name, None)
				doc = getattr(prop, "__doc__", None)
				if doc is not None:
					lines = doc.split("\n")
					res[cmd] = lines[0].lstrip() + textwrap.dedent("\n".join(lines[1:]).expandtabs(4))
		return res
	
	@classmethod
	def get_help(cls, args=None, abbrev=False, examples=False):
		args = "" if args is None else args
		cmd = None
		cmd_specific = (len(args) > 0)

		cmd_helps = ""
		if not cmd_specific:
			cmd_helps += "\n{name}\n{under}\n".format(
				name=cls.command_name,
				under=("-"*len(cls.command_name))
			)
		else:
			cmd = args.split(" ")[0]

		for subcmd_name,subcmd_help in cls.get_command_helps().iteritems():
			if cmd_specific and subcmd_name != cmd:
				continue

			if not examples and "\nExamples:\n" in subcmd_help:
				subcmd_help,_ = subcmd_help.split("\nExamples:\n")

			lines = subcmd_help.split("\n")
			first_line = lines[0].lstrip()

			label_start = "\n{:>10}   -   ".format(subcmd_name)
			spaces = " " * len(label_start)

			label_line = label_start + first_line
			cmd_helps += "\n".join(textwrap.wrap(
				label_line,
				subsequent_indent=spaces
			))

			if len(lines) > 2 and not abbrev:
				cmd_helps += "\n\n" + "\n".join(spaces + x for x in lines[1:])

			cmd_helps += "\n"
		
		return cmd_helps
	
	def do_help(self, args):
		examples = (len(args) > 0)

		print(self.get_help(args=args, examples=examples))

class TalusCmd(TalusCmdBase):
	"""The main talus command. This is what is invoked when dropping
	into a shell or when run from the command line"""

	command_name = "<ROOT>"

	def __init__(self, talus_host=None, talus_client=None, one_shot=False):
		"""Initialize the Talus command object
		:one_shot: True if only one command is to be processed (cmd-line args, no shell, etc)
		"""
		super(TalusCmd, self).__init__(talus_host=talus_host, talus_client=talus_client)

		self.one_shot = one_shot
	
	def _add_command(self, name, cls):
		"""Add a command by defining the ``do_<cmd_name>`` method"""
		def _handle_command(self_, args):
			processor = cls()
			if self.one_shot:
				processor.onecmd(args)
			else:
				process.cmdloop()
				sys.stdin.write(args + "\n")

		setattr(self, "do_" + name, _handle_command)

# auto-import all defined commands in talus/cmds/*.py

this_dir = os.path.dirname(__file__)
for filename in glob.glob(os.path.join(this_dir, "*.py")):
	basename = os.path.basename(filename)
	if basename == "__init__.py":
		continue
	mod_name = basename.replace(".py", "")
	mod_base = __import__("talus.cmds", globals(), locals(), fromlist=[mod_name])
	mod = getattr(mod_base, mod_name)

def make_cmd_handler(cls):
	def _handle_command(self, args):
		processor = cls(talus_host=self._talus_host, talus_client=self._talus_client)
		if self.one_shot:
			processor.onecmd(args)
		else:
			sys.stdin.write(args + "\n")
			process.cmdloop()

	return _handle_command

def define_root_commands():
	for cls in ENABLED_COMMANDS:
		if cls.command_name == "" or cls == TalusCmd:
			continue

		handler = make_cmd_handler(cls)

		# the baseclass cmd.Cmd always defines a do_help, so we need to check if it's
		# redefined in the specific subclass
		if "do_help" in cls.__dict__:
			handler.__doc__ = cls.do_help.__doc__
		else:
			handler.__doc__ = cls.__doc__

		setattr(TalusCmd, "do_" + cls.command_name, handler)
define_root_commands()
