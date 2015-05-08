#!/usr/bin/env python
# encoding: utf-8

import os
import time

import talus.api
from talus.models import *
import talus.models

talus.models.set_base("http://localhost:8001")

def test_os_and_image_models():
	existing_os = OS.find_one(name="testing os")
	if existing_os is None:
		new_os = OS("http://localhost:8001")
		new_os.name = "testing os"
		new_os.arch = "x86"
		new_os.type = "windows"
		new_os.version = "10"
		new_os.save()
		existing_os = new_os

	new_image = Image("http://localhost:8001")
	new_image.name = "test image"
	new_image.os = existing_os
	new_image.desc = "this is a description"
	new_image.tags = ["these", "are", "some", "tags"]
	new_image.status = dict(name="importing", tmpfile="/tmp/blah")
	new_image.base_image = None

	new_image.save()
	new_image.delete()

def test_image_import(image_path, image_name):
	def progress_callback():
		sys.stdout.write(".")
		sys.stdout.flush()
	
	existing_os = OS.find_one(name="testing os")
	if existing_os is None:
		new_os = OS("http://localhost:8001")
		new_os.name = "testing os"
		new_os.arch = "x86"
		new_os.type = "windows"
		new_os.version = "10"
		new_os.save()
		existing_os = new_os
	
	client = talus.api.TalusClient("http://localhost:8001")

	client.image_delete(None, name=image_name)

	image = client.image_import(image_path, image_name, existing_os.id, "some description", ["windows", "7", "x64"])

	while image.status["name"] != "configuring":
		time.sleep(5)
		image.refresh()
	
	print("image is running and waiting to be configured!")
	print(image.status)
	print("shut down the VM when ready!, be sure the firewall is open and virtio drivers are installed!")
	print("a CD-ROM should be mounted in the VM containing the virtio drivers")

def test_image_configure_with_interaction(image_name):
	client = talus.api.TalusClient("http://localhost:8001")

	image = talus.models.Image.find_one(name=image_name)

	image = client.image_configure(
		image.id,
		user_interaction=True,
		vagrantfile=None
	)

	while image.status["name"] != "configuring":
		time.sleep(5)
		image.refresh()
	
	print("ready to interact with!")

def test_image_configure_without_interaction(image_name):
	image = talus.models.Image.find_one(name=image_name)

	client = talus.api.TalusClient("http://localhost:8001")
	image = client.image_configure(
		image.id,
		user_interaction=False,
		vagrantfile="""
			Vagrant.configure("2") do |config|
				config.vm.box = "blah"
				config.winrm.username = "user"
				config.winrm.password = "password"

				config.vm.provision "shell", inline: "echo blah >> C:\\\\Users\\\\user\\\\Desktop\\\\FROM_VAGRANT1.txt"
				config.vm.provision "shell", inline: "echo blah >> C:\\\\Users\\\\user\\\\Desktop\\\\FROM_VAGRANT2.txt"
				config.vm.provision "shell", inline: "echo blah >> C:\\\\Users\\\\user\\\\Desktop\\\\FROM_VAGRANT3.txt"
				config.vm.provision "shell", inline: "echo blah >> C:\\\\Users\\\\user\\\\Desktop\\\\FROM_VAGRANT4.txt"
			end
		"""
	)

	while image.status["name"] != "ready":
		time.sleep(5)
		image.refresh()
	
	print("update complete!")

if __name__ == "__main__":
		image_name = "win7pro_testing7",

		test_image_import("~/images/win7pro_x64-disk1.vmdk", image_name)
		#test_image_configure_with_interaction(image_name)
		#test_image_configure_without_interaction(image_name)
