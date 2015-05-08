#!/usr/bin/env python
# encoding: utf-8

import json
import libvirt
import logging
import os
import re
import sh
from sh import md5sum
from sh import wget
import sys
import threading
import time
import xmltodict

LIBVIRT_BASE = "/var/lib/libvirt/images"

from slave.models import Image

def image_id_to_volume(image):
	return "{}_vagrant_box_image_0.img".format(image)

def qemu_img_info(image_path):
	"""Return a dict of info returned by qemu-img info. Assumes the image_path exists
	and points to a valid VM image

	:image_path: path to the image
	:returns: dict of returned information about the image

	"""
	output = sh.qemu_img.info(image_path)

	res = {}
	for line in output.split("\n"):
		match = re.match(r'^\s*([^\s].*):\s*(.*)$', line)
		if match is None:
			continue
		res[match.group(1)] = match.group(2)

	return res

class ImageManager(object):
	_instance = None
	@classmethod
	def instance(cls):
		if cls._instance is None:
			cls._instance = cls()
		return cls._instance

	def __init__(self):
		self._cache = {}
		self._log = logging.getLogger("ImageMan")
		self.image_url = None
	
	def get_md5(self, path):
		"""Get the md5 of the file at ``path``. A cache will be used
		based on last modified time of the file. If the file does not
		exist, None will be returned.
		"""
		path = os.path.realpath(os.path.abspath(path))

		if not os.path.exists(path):
			self._log.debug("could not get md5, path does not exist: {}".format(path))
			return None

		if path in self._cache and os.path.getmtime(path) == self._cache[path]["modtime"]:
			self._log.debug("path was in cache ({}), md5: {}".format(path, self._cache[path]["md5"]))
			return self._cache[path]["md5"]

		self._log.debug("path not in cache ({}), calculating".format(path))
		output = md5sum(path).split()[0]
		self._cache[path] = {
			"md5": output,
			"modtime": os.path.getmtime(path),
		}
		return output
	
	def download_image(self, image_id):
		"""Download the image from the image_url"""
		image_filename = image_id_to_volume(image_id)
		dest = os.path.join(LIBVIRT_BASE, image_filename)
		self._log.debug("downloading image {} to {}".format(image_id, dest))

		wget("-q", "-O", dest, self.image_url + "/" + image_filename)
		self._log.debug("downloaded {}".format(image_id))
	
	def ensure_image(self, image_id):
		"""Ensure that the image ``image_id`` and its bases exist in LIBVIRT_BASE
		checking its md5 against the md5 sum stored in the database

		:returns: True/False on success
		"""
		self._log.info("ensuring image {} exists and is valid".format(image_id))

		dest = os.path.join(LIBVIRT_BASE, image_id_to_volume(image_id))
		if not os.path.exists(dest):
			self.download_image(image_id)

		else:
			images = Image.objects(id=image_id)
			if len(images) == 0:
				self._log.warn("image id {} does not reference a valid image".format(image_id))
				return False

			image = images[0]
			md5 = self.get_md5(dest)
			# all good, nothing has changed
			if md5 == image.md5:
				self._log.debug("image {} is unchanged".format(image_id))

			else:
				self._log.debug("image {} changed, redownloading".format(image_id))
				self.download_image(image_id)

		info = qemu_img_info(dest)
		if "backing file" in info:
			self._log.debug("checking backing files for validity")
			backing = info["backing file"]
			# backing will be a (absolute?) path
			backing_id = os.path.basename(backing).split("_")[0]
			self.ensure_image(backing_id)
		else:
			self._log.debug("no backing file, image looks good!")

		return True

class VMHandler(threading.Thread):
	def __init__(self, job, idx, image, tool, params, code_loc, timeout=120, network="all", on_finished=None):
		"""Start up the VM image ``image`` in libvirt, with a timeout of ``timeout``,
		and params ``params, using network ``network``.

		:image: The name of the image
		:params: Params that specify what to run inside of the VM
		:timeout: The timeout for the vm
		"""
		super(VMHandler, self).__init__()

		self.job = job
		self.idx = idx
		self.image = image
		self.tool = tool
		self.params = params
		self.code_loc = code_loc
		self.timeout = timeout
		self.network = network
		self.ram = 1024
		self.on_finished = on_finished

		self._log = logging.getLogger("VM-JOB:" + self.job)
		self._running = threading.Event()

		self._image_man = ImageManager.instance()

		self._libvirt_conn = None
		self._vm_image_loc = None
		self._domain = None
	
	def run(self):
		"""Run the VMHandler
		"""
		self._running.set()

		self._log.debug("starting")

		if not self._vm_start():
			self._log.warn("error, could not start vm, bailing")
			self._running.clear()
			return

		start_time = time.time()
		total_time = 0
		while self._running.is_set() and self._vm_is_running() and total_time < self.timeout:
			time.sleep(1)
			total_time = time.time() - start_time

		self._vm_cleanup()

		self._log.debug("finished")
	
	def stop(self):
		self._log.debug("stopping")
		self._running.clear()
	
	def handle_comms(self, data):
		"""Handle guest communications"""
		self._log.info("handling comms: {}".format(data))

		switch = dict(
			startup		= self.handle_guest_startup
		)

		if "type" not in data:
			self._log.debug("guest comms does not include a type")
			return "{}"

		return switch[data["type"]](data)

	def handle_guest_startup(self, data):
		res = dict(
			id			= self.job,
			tool		= self.tool,
			params		= self.params,
			idx			= self.idx,
			code_loc	= self.code_loc
		)

		return json.dumps(res)
	
	def _libvirt(self):
		if self._libvirt_conn is None:
			self._libvirt_conn = libvirt.open("qemu:///system")
		return self._libvirt_conn

	def _libvirt_domain(self):
		"""Return the libvirt domain for the currently-running vagrant box
		:returns: libvirt.Domain if exists, None if it does not exist

		"""
		conn = self._libvirt()
		try:
			domain = conn.lookupByName(self._domain)
			return domain
		except libvirt.libvirtError as e:
			return None
	
	def _vm_start(self):
		if not self._image_man.ensure_image(self.image):
			return False
		
		self._vm_create()
		self._vm_run()

		return True
	
	def _vm_cleanup(self):
		self._log.info("cleaning up")
		self._vm_kill()
		os.remove(self._vm_image_loc)
	
	def _vm_kill(self):
		vm_name = os.path.basename(self._vm_image_loc)
		sh.virsh.undefine(vm_name)
		sh.virsh.destroy(vm_name)
	
	def _vm_is_running(self):
		"""Return True/False if the current image is still running
		:returns: True/False
		"""
		conn = self._libvirt()
		try:
			domain = conn.lookupByName(self._domain)
		except libvirt.libvirtError as e:
			return False

		if domain is None:
			return False
		state,reason = domain.state()
		if state == libvirt.VIR_DOMAIN_RUNNING:
			return True
		else:
			return False

	def _vm_vnc_port(self):
		"""Return the vnc port of the vagrant VM
		:returns: The vnc port. If the domain is not running, None is returned. If vnc is not (yet?) available, -1 is returned.

		"""
		domain = self._libvirt_domain()
		# VM isn't running (yet?)
		if domain is None:
			return None

		info = xmltodict.parse(domain.XMLDesc())
		port = int(info["domain"]["devices"]["graphics"]["@port"])

		return port
	
	def _vm_create(self):
		self._vm_image_loc = "/tmp/{}_{}.img".format(self.job, self.idx)
		self._domain = os.path.basename(self._vm_image_loc)
		output = sh.qemu_img.create(
			self._vm_image_loc,
			b	= os.path.join(LIBVIRT_BASE, image_id_to_volume(self.image)),
			f	= "qcow2",
		)
	
	def _vm_run(self):
		"""Creates the domain and runs it"""
		vm_name = os.path.basename(self._vm_image_loc)
		self._log.info("running VM {}".format(vm_name))

		sh.virt_install(
			"--import", # stupid python keywords
			r				= self.ram,
			accelerate		= True,
			n				= vm_name,
			disk			= "{},device=disk,bus=virtio".format(self._vm_image_loc),
			vnc				= True,
			w				= "bridge=virbr0,model=virtio",
			noautoconsole	= True,
			# network		= "filter...."
		)
