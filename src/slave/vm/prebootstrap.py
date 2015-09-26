#!/usr/bin/env python
# encoding: utf-8

import imp
import logging
import os
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

def main():
	log.info("determining temporary folder")
	os_name = os.name.lower()
	watch_dir = None
	# WINDOWS
	if os_name == "nt":
		watch_dir = os.path.expandvars("%TEMP%")
	# *NIX
	elif os_name == "posix":
		watch_dir = "/tmp"
	log.info("temporary folder is at {!r}".format(watch_dir))
	
	go_path = os.path.join(watch_dir, "RUN_TALUS_RUN")
	bootstrap_path = os.path.join(watch_dir, "bootstrap.py")

	log.info("waiting for talus go flag to appear at {!r}".format(go_path))
	while True:
		if os.path.exists(go_path):
			log.info("go path exists! attempting to run!")
			run_bootstrap(bootstrap_path)
			break
		time.sleep(0.5)

if __name__ == "__main__":
	main()
