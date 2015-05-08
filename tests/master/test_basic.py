#!/usr/bin/env python

import logging
import os
import random
import shutil
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from master.lib.vm.manage import VMManager

logging.basicConfig(level=logging.DEBUG)

class BasicMasterVMManageTests(unittest.TestCase):
	def setUp(self):
		self.mgr = VMManager()
		self.tmp = tempfile.mkdtemp()

	def tearDown(self):
		shutil.rmtree(self.tmp)
	
	def test_create_image(self):
		if os.path.exists("/home/user/.vagrant.d/boxes/precise32_clone"):
			shutil.rmtree(os.path.join("/home/user/.vagrant.d/boxes/precise32_clone"))

		output = self.mgr.create_image("""
			Vagrant.configure("2") do |config|
				config.vm.box = "some_box"
				config.vm.provision "shell", inline: "touch ~/EVIL2.txt"
			end
		""", "precise32", "precise32_clone", user_interaction=True)

		# should block
		self.mgr.shutdown_vagrant_vm(output["worker"])
		
		# do tests
		self.assertTrue(os.path.exists("/home/user/.vagrant.d/boxes/precise32_clone"))
		self.assertTrue(os.path.exists("/home/user/.vagrant.d/boxes/precise32_clone/0"))
		self.assertTrue(os.path.exists("/home/user/.vagrant.d/boxes/precise32_clone/0/libvirt"))
		self.assertTrue(os.path.exists("/home/user/.vagrant.d/boxes/precise32_clone/0/libvirt/box.img"))
		self.assertTrue(os.path.exists("/home/user/.vagrant.d/boxes/precise32_clone/0/libvirt/metadata.json"))
		self.assertTrue(os.path.exists("/home/user/.vagrant.d/boxes/precise32_clone/0/libvirt/Vagrantfile"))

		shutil.rmtree(os.path.join("/home/user/.vagrant.d/boxes/precise32_clone"))
	
	def test_configure_image(self):
		output = self.mgr.configure_image("modifyme", """
			Vagrant.configure("2") do |config|
				config.ssh.password = "vagrant"
				config.ssh.username = "vagrant"
				config.vm.box = "some_box"
				config.vm.provision "shell", inline: "echo blah >> ~/EVIL2_MODIFIED.txt"
			end
		""", user_interaction=True)

		# should block
		self.mgr.shutdown_vagrant_vm(output["worker"])
		
		# do tests
		# pass
	
	def test_import_windows_image(self):
		output = self.mgr.import_image(
			"/home/user/images/win7pro_x64-disk1.qcow2",
			#"/home/user/images/win7_setup.qcow2",
			"win7_setup_test",
			"""
			Vagrant.configure("2") do |config|
				config.ssh.pasword = "password"
				config.ssh.username = "username"
				config.vm.box = "some_box"
				config.vm.communicator = "winrm"
				config.vm.guest = "windows"

				config.vm.provision "shell", inline: "echo blah >> C:\\\\Users\\\\user\\\\Desktop\\\\MODIFIED.txt"
			end
			""",
			user_interaction=True,
			iso_path="/home/user/virtio-win-0.1-100.iso"
		)

		self.mgr.shutdown_vagrant_vm(output["worker"])

if __name__ == "__main__":
	unittest.main()
