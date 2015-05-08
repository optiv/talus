#!/usr/bin/env python
# encoding: utf-8

import sys

import slave

if __name__ == "__main__":
	if len(sys.argv) < 3:
		sys.stderr.write("USAGE: {} <AMQP_HOST> <MAX_VMS>\n")
		exit(1)

	slave.main(sys.argv[1], int(sys.argv[2]))
