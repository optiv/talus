#!/usr/bin/env python
# encoding: utf-8

import json
import os
import select
import socket
import sys
import uuid

from twisted.internet import task
from twisted.internet.defer import Deferred
from twisted.internet.protocol import ClientFactory
from twisted.protocols.basic import LineReceiver

class GuestCommsClient(LineReceiver):
	def connectionMade(self):
		self.setRawMode()
		mac = uuid.getnode()
		self.send(json.dumps({
			"mac": mac,
			"type": 
		self.sendLine("Hello, world!")
		self.sendLine("What a fine day it is.")
		self.sendLine(self.end)
	
	def rawDataReceived(self, data):
		data = json.loads(data)
		if data["type"] == "config":
			params = data["params"]
			tool = data["tool"]
			code_loc = data["code_loc"]
			idx = data["idx"]

class GuestCommsClientFactory(ClientFactory):
	protocol = GuestCommsClient

	def __init__(self):
		self.done = Deferred()


	def clientConnectionFailed(self, connector, reason):
		print('connection failed:', reason.getErrorMessage())
		self.done.errback(reason)


	def clientConnectionLost(self, connector, reason):
		print('connection lost:', reason.getErrorMessage())
		self.done.callback(None)

def main(reactor):
	my_ip = socket.gethostbyname(socket.gethostname())
	host_ip = my_ip.rsplit(".", 1)[0] + ".1"

	factory = GuestCommsClientFactory()
	reactor.connectTCP(host_ip, 55555, factory)
	return factory.done

if __name__ == '__main__':
	task.react(main)

def main():

if __name__ == "__main__":
	main()
