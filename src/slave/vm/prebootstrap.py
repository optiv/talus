#!/usr/bin/env python
# encoding: utf-8

import imp
import logging
import os
import shutil
import sys
import time

logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger("PREBOOT")

def run_bootstrap(bootstrap_path):
	log.info("importing bootstrap")
	bootstrap = imp.load_source("bootstrap", bootstrap_path)

	log.info("running bootstrap")
	bootstrap.main()

	log.info("done running bootstrap")

def init_comms():
	log.info("initing comms")

	# for windows
	if os.name == "nt":
		log.info("flushing arp cache")
		os.system("netsh interface ip delete arpcache")

		log.info("forcing WinRM service to start")
		os.system("sc start WinRM")

def find_bootstrap(attempts=25):
	#log.info("determining temporary folder")
	log.info("determining bootstrap location")

	for x in xrange(attempts):
		sys.stdout.write(".")

		os_name = os.name.lower()
		# WINDOWS
		if os_name == "nt":
			drives = [
				"A", "B", "C", "D", "E", "F", "G", "H", "I", "J",
				"K", "L", "M", "N", "O", "P", "Q", "R", "S", "T",
				"U", "V", "W", "X", "Y", "Z"
			]
			found_drive = None
			for drive_letter in drives:
				if os.path.exists(drive_letter + r":\bootstrap.py"):
					found_drive = drive_letter
					break

			if found_drive is not None:
				res = found_drive + ":\\"
				sys.stdout.write("\n")
				log.info("found CD drive at {}".format(res))
				return res

		# *NIX
		elif os_name == "posix":
			# TODO - this is leftover from the ssh/winrm injection version
			return "/tmp"

		time.sleep(0.2)
	
	sys.stdout.write("\n")
	return None

def main():
	init_comms()

	bootstrap_dir = find_bootstrap()
	if bootstrap_dir is None:
		log.error("Could not find bootstrap!")
		return

	log.info("bootstrap folder is at {!r}".format(bootstrap_dir))
	
	this_dir = os.path.dirname(__file__)
	shutil.copy(os.path.join(bootstrap_dir, "bootstrap.py"), os.path.join(this_dir, "bootstrap.py"))
	shutil.copy(os.path.join(bootstrap_dir, "config.json"), os.path.join(this_dir, "config.json"))

	run_bootstrap(os.path.join(this_dir, "bootstrap.py"))

if __name__ == "__main__":
	main()
