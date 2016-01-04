#!/usr/bin/env python
# encoding: utf-8

from contextlib import contextmanager
import json
import libvirt
import logging
import netifaces
import os
import random
import re
import sh
from sh import md5sum
from sh import wget
from sh import arp
import shutil
import socket
import sys
import tempfile
import threading
import time
import uuid
import xmltodict

LIBVIRT_BASE = "/var/lib/libvirt/images"

from slave.models import Image
from slave.vm.comms import VMComms

logging.getLogger("sh").setLevel(logging.WARN)

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

		# will be a hash of image_name => threading.Event() that can be
		# waited on
		self._downloading_images = {}
		self._downloading_images_lock = threading.Lock()

		self._calc_md5_images = {}
		self._calc_md5_images_lock = threading.Lock()
	
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

		md5ing_already = False
		with self._calc_md5_images_lock:
			md5ing_already = (path in self._calc_md5_images)
			if not md5ing_already:
				e = self._calc_md5_images[path] = threading.Event()
				e.clear()

		if md5ing_already:
			self._log.debug("already calculating md5, waiting for it to finish")
			self._calc_md5_images[path].wait()
			self._log.debug("image md5 done")
			return self._cache[path]["md5"]

		self._log.info("path not in cache ({}), calculating".format(path))
		output = md5sum(path).split()[0]
		self._log.info("calculated md5: " + output)
		self._cache[path] = {
			"md5": output,
			"modtime": os.path.getmtime(path),
		}

		self._calc_md5_images[path].set()
		del self._calc_md5_images[path]

		return output
	
	def download_image(self, image_id):
		"""Download the image from the image_url"""
		downloading_already = False
		with self._downloading_images_lock:
			downloading_already = (image_id in self._downloading_images)
			if not downloading_already:
				e = self._downloading_images[image_id] = threading.Event()
				e.clear()

		if downloading_already:
			self._log.debug("image is already being downloaded, waiting for it to finish")
			self._downloading_images[image_id].wait()
			self._log.debug("image finished downloading")
			return

		image_filename = image_id_to_volume(image_id)
		dest = os.path.join(LIBVIRT_BASE, image_filename)
		self._log.debug("downloading image {} to {}".format(image_id, dest))

		wget("-q", "-O", dest, self.image_url + "/" + image_filename)
		self._log.debug("downloaded {}".format(image_id))

		self._downloading_images[image_id].set()
		del self._downloading_images[image_id]
	
	def ensure_image(self, image_id):
		"""Ensure that the image ``image_id`` and its bases exist in LIBVIRT_BASE
		checking its md5 against the md5 sum stored in the database

		:returns: True/False on success
		"""
		self._log.info("ensuring image {} exists and is valid".format(image_id))

		# XXX DEBUG
		# since we're running on the master, they're always up to date
		return True

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
				self._log.debug("image {} changed (model: {}, disk: {}), redownloading".format(image_id, image.md5, md5))
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
	def __init__(self, job, idx, image, image_username, image_password, os_type, tool, params, code_loc, code_username, code_password, fileset, db_host, timeout=1800, network="whitelist", on_finished=None, on_vnc_available=None, startup_timeout=120, debug=False, cpus=1, ram=int(1024*3), libvirt_conn=None, mac=None, vnc_port=None):
		"""Start up the VM image ``image`` in libvirt, with a timeout of ``timeout``,
		and params ``params, using network ``network``.

		:image: The name of the image
		:params: Params that specify what to run inside of the VM
		:timeout: The timeout for the vm
		"""
		super(VMHandler, self).__init__()

		self.job = job
		self.idx = idx
		self.debug = debug
		self.image = image
		self.image_username = image_username
		self.image_password = image_password
		self.os_type = os_type
		self.tool = tool
		self.params = params
		self.code_loc = code_loc
		self.code_username = code_username
		self.code_password = code_password
		self.timeout = timeout
		self.startup_timeout = startup_timeout
		self.fileset = fileset
		self.db_host = db_host
		self.cpus = cpus
		self.mac = mac
		self.vnc_port = vnc_port
		self.vm_status = ""

		self._released_boot_lock = False

		self.libvirt_conn = libvirt_conn
		self.libvirt_domain_obj = None
		self._opened_libvirt = False

		self.total_progress = 0

		# network can be 'all' or 'whitelist'
		# whitelist values can also be followed by a semicolon
		# and a comma-separated list of domain names/ip addresses
		self.network = network

		parts = self.network.split(":")
		self.network = parts[0]
		self.whitelisted_hosts = []
		if self.network == "whitelist":
			if len(parts) > 1:
				self.whitelisted_hosts = [x.strip() for x in parts[1].split(",")]

		self.ram = ram
		self.on_finished = on_finished
		self.start_time = time.time()

		self._log = logging.getLogger("VM-JOB:{}:{}".format(self.job, self.idx))
		self._running = threading.Event()

		self._image_man = ImageManager.instance()

		self._vm_image_loc = None
		self._domain = None
		self._ip = None
		self._vm_killed = False
		self._received_started_msg = False
	
	def on_received_started(self):
		self.vm_status = "running tool"
		self._received_started_msg = True
	
	# DEAD CODE
	def unplug_bootstrap_img(self):
		#self._log.debug("hotunplugging bootstrap disk")

		# bootstrap image is always attached as vdb
		# sh.virsh("detach-disk", self._domain, "sda")
		pass
	
	def run(self):
		self._running.set()
		self.start_time = time.time()
		self._log.debug("starting")

		try:
			self.do_run()
		finally:
			#if not self._released_boot_lock:
			#	self.boot_lock.release()
			self._vm_cleanup()

		self._log.debug("finished, calling on_finished")

		if self.on_finished is not None:
			self.on_finished(self)
	
	def do_run(self):
		"""Run the VMHandler
		"""

		if not self._vm_start():
			self._log.warn("error, could not start vm, bailing")
			self._running.clear()
			return

		total_time = 0
		# wait for the VM to startup before waiting for it to be shutdown
#		while self._running.is_set() and not self._vm_is_running() and total_time < self.startup_timeout:
#			time.sleep(1)
#			total_time = time.time() - self.start_time

		if self._running.is_set():
			if total_time >= self.startup_timeout:
				self._log.warn("VM took too long to startup, bailing")
				self._running.clear()
			
			# means it started up
			else:
				self._log.info("VM started up")

		# see the note below
		# see the note below
		# see the note below
		# see the note below
		#
#		if not self._connect_comms():
#			self._log.error("Could not connect comms!!! bailing")
#		else:
#			self._inject_and_run_bootstrap()
#
		# just keeping the indentation here for testing - if we DO want to go
		# back to injecting the bootstrap into a tmpdir on the device, remove
		# if True, (keep indentation), and uncomment the lines above

		self.run_time = time.time()
		total_time = 0
		#while self._running.is_set() and self._vm_is_running() and total_time < self.timeout:
		while self._running.is_set() and total_time < self.timeout:
			if not self._received_started_msg and total_time > self.startup_timeout:
				self._log.warn("never received startup message in {}s, bailing".format(self.startup_timeout))
				return

#			elif self._received_started_msg and not self._released_boot_lock:
#				self._released_boot_lock = True
#				self.boot_lock.release()
				
			time.sleep(5)
			total_time = time.time() - self.run_time

#		if not self._released_boot_lock:
#			self.boot_lock.release()
	
	def stop(self):
		self._log.info("stopping")
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
	
	# ----------------------------

	def _get_filter_params(self):
		if self.network == "all":
			return ""

		elif self.network == "whitelist":
			code_loc_host = self.code_loc.replace("http://", "").replace("https://", "").split("/", 1)[0]
			code_loc_ip = socket.gethostbyname(code_loc_host)

			this_ip = netifaces.ifaddresses('virbr2')[2][0]['addr']
			bcast = this_ip.rsplit(".",1)[0] + ".255"

			ips = [
				"255.255.255.255",

				# always include the guest comms ip
				bcast,
				this_ip,
				code_loc_ip
			]

			for other_host in self.whitelisted_hosts:
				ips.append(socket.gethostbyname(other_host))

			res = []
			for ip in ips:
				res.append("<parameter name='WHITELIST' value='{}' />".format(ip))
			return "\n".join(res)

	def _connect_comms(self):
		self._log.debug("waiting for vm to get an ip")

		self._ip = ip_addr = self._vm_ip_address()
		while self._running.is_set() and self._vm_is_running() and ip_addr is None:
			time.sleep(1)
			self._ip = ip_addr = self._vm_ip_address()

		if not self._running.is_set() or not self._vm_is_running():
			self._log.debug("stopped waiting for ip, was told to quit (or vm shutdown)")
			return

		self._log.info("vm has an ip ({} [{}])! connecting comms".format(ip_addr, self._mac_addr))

		# TODO probe ports 22/5569 instead of this?
		self._comms = VMComms.get_comms(self.os_type, self._log)
		return self._comms.connect(ip_addr, self.image_username, self.image_password, self._running)
	
	def _create_bootstrap_img(self):
		self._bootstrap_dir = tempfile.mkdtemp()
		sh.chmod("o+rwx", self._bootstrap_dir)

		self._bootstrap_files = os.path.join(self._bootstrap_dir, "files")
		os.makedirs(self._bootstrap_files)

		with open(os.path.join(os.path.dirname(__file__), "bootstrap.py"), "r") as f:
			bootstrap_contents = f.read()
		with open(os.path.join(self._bootstrap_files, "bootstrap.py"), "wb") as f:
			f.write(bootstrap_contents)

		with open(os.path.join(self._bootstrap_files, "config.json"), "wb") as f:
			f.write(self._make_config())

		self._bootstrap_img = os.path.join(self._bootstrap_dir, "bootstrap.img")
		
		sh.dd("if=/dev/null", "bs=1K", "of={}".format(self._bootstrap_img), "seek=2040")
		sh.Command("mkfs.ntfs")("-F", self._bootstrap_img)
		#sh.Command("mkfs.vfat")(self._bootstrap_img)

		mounted_dir = os.path.join(self._bootstrap_dir, "mounted")
		os.makedirs(mounted_dir)

		output = sh.mount("-t", "ntfs", "-o", "loop", self._bootstrap_img, mounted_dir)
		#output = sh.mount("-t", "vfat", "-o", "loop", self._bootstrap_img, mounted_dir)
		#self._log.debug("mount output: " + str(output))

		shutil.copy(os.path.join(self._bootstrap_files, "bootstrap.py"), mounted_dir)
		shutil.copy(os.path.join(self._bootstrap_files, "config.json"), mounted_dir)

		try:
			sh.umount(mounted_dir)
		except:
			pass

		return self._bootstrap_img
	
	def _create_cdrom(self):
		self._cdrom_dir = tempfile.mkdtemp()

		with open(os.path.join(os.path.dirname(__file__), "bootstrap.py"), "r") as f:
			bootstrap_contents = f.read()
		with open(os.path.join(self._cdrom_dir, "bootstrap.py"), "wb") as f:
			f.write(bootstrap_contents)

		with open(os.path.join(self._cdrom_dir, "config.json"), "wb") as f:
			f.write(self._make_config())

		self._cdrom_path = self._cdrom_dir + ".iso"
		sh.mkisofs("-JlL", "-joliet-long", "-allow-lowercase", "--max-iso9660-filenames", "-o", self._cdrom_path, self._cdrom_dir)

		return self._cdrom_path
	
	def _inject_and_run_bootstrap(self):
		"""Inject and run the bootstrap inside the VM
		"""
		self._log.info("injecting bootstrap")

		with open(os.path.join(os.path.dirname(__file__), "bootstrap.py"), "r") as f:
			bootstrap_contents = f.read()

		if not self._running.is_set() or not self._vm_is_running():
			return

		tmp_path = self._comms.sep.join([self._comms.tmp_loc(), "bootstrap.py"])
		self._log.debug("saving bootstrap to {}".format(tmp_path))

		self._retry_put_file(tmp_path, bootstrap_contents)

		if not self._running.is_set() or not self._vm_is_running():
			return

		config_path = self._comms.sep.join([self._comms.tmp_loc(), "config.json"])
		self._log.debug("writing config to {}".format(config_path))
		self._retry_put_file(config_path, self._make_config())

		if not self._running.is_set() or not self._vm_is_running():
			return

		self._log.info("signaling that the bootstrap should be run")
		tmp_path = self._comms.sep.join([self._comms.tmp_loc(), "RUN_TALUS_RUN"])
		self._retry_put_file(tmp_path, "RUN YOU FOOLS!")

		#self._comms.run_script("python \"" + tmp_path + "\"", background=True)
		#self._comms.run_script('start-process "python" "{}" -WindowStyle Normal'.format(tmp_path))
		#self._comms.run_script("start cmd /k python \"" + tmp_path + "\"", background=True)

		if not self._running.is_set() or not self._vm_is_running():
			return

		self._log.debug("started bootstrap")
	
	def _retry_put_file(self, path, contents):
		count = 0
		while self._running.is_set():
			count += 1
			if self._comms.put_file(path, contents):
				break
			time.sleep(1)
	
	def _make_config(self):
		res = dict(
			id		= self.job,
			idx		= self.idx,
			tool	= self.tool,
			debug	= self.debug,
			params	= self.params,
			fileset	= self.fileset,
			db_host	= self.db_host,
			code	= dict(
				loc			= self.code_loc,
				username	= self.code_username,
				password	= self.code_password,
			)
		)

		return json.dumps(res, indent=4, separators=(',', ': '))
	
	# ----------------------------

	def _libvirt(self):
		if self.libvirt_conn is None:
			#self.libvirt_conn = libvirt.open("qemu:///system")
			#self._opened_libvirt = True
			raise("who you lookin at, foo!")

		# should be thread safe
		return self.libvirt_conn
	
	def _libvirt_domain(self):
		"""Return the libvirt domain for the currently-running vagrant box
		:returns: libvirt.Domain if exists, None if it does not exist

		"""
		if self.libvirt_domain_obj is None:
			conn = self._libvirt()
			try:
				self.libvirt_domain_obj = conn.lookupByName(self._domain)
			except libvirt.libvirtError as e:
				return None

		return self.libvirt_domain_obj
	
	def _vm_start(self):
		self.vm_status = "ensuring"
		if not self._image_man.ensure_image(self.image):
			return False
		
		self.vm_status = "creating"
		self._vm_create()

		#self.boot_lock.acquire()
		self._released_boot_lock = False
		self.vm_status = "booting"
		self._vm_run()

		return True
	
	def _vm_cleanup(self):
		self._log.info("cleaning up")
		self.vm_status = "stopping"
		self._vm_kill()

		try:
			os.remove(self._vm_image_loc)
		except:
			pass

		try:
			#shutil.rmtree(self._bootstrap_dir)
			shutil.rmtree(self._cdrom_dir)
			os.remove(self._cdrom_path)
		except:
			pass
	
	def _vm_kill(self):
		if self._vm_image_loc is None:
			return

		self._log.debug("killing vm")

		#vm_name = os.path.basename(self._vm_image_loc)
		# the domains created are transient, don't need to undefine them
		# sh.virsh.undefine(vm_name)

		start = time.time()

		# if the VM has already been shutdown, this will fail

		#self._libvirt_domain().destroy()
		# USE THIS!!!! MUCH MUCH MUCH FASTER!!!! (orders of magnitude faster)
		# I think there's some flags that you can pass to the destroy() function
		# in the python libvirt bindings, but I couldn't figure those out. And,
		# this works, and works well.
		#sh.virsh.destroy(self._domain)

		pid_path = "/var/run/libvirt/qemu/{}.pid".format(self._domain)
		if os.path.exists(pid_path):
			with open(pid_path, "r") as f:
				pid = f.read()
			os.system("kill -KILL {}".format(pid))
		else:
			self._log.debug("vm not running, nothing to kill")

		self._vm_killed = True

		self._log.debug("vm is killed - took {} seconds".format(round(time.time() - start, 2)))

		if self._opened_libvirt:
			self._log.debug("closing libvirt connection")
			try:
				self.libvirt_conn.close()
			except:
				pass

		self._remove_ip_from_arp_cache()

		self._log.debug("vm should be completely killed now")
	
	def _remove_ip_from_arp_cache(self):
		return
#
#		if self._ip is None:
#			return
#
#		self._log.debug("removing ip {} from arp cache".format(self._ip))
#
#		try:
#			sh.arp("-d", self._ip)
#		except:
#			pass
	
	def _vm_is_running(self):
		"""Return True/False if the current image is still running
		:returns: True/False
		"""
		domain = self._libvirt_domain()
		if domain is None:
			return False

		try:
			state,reason = domain.state()
			if state == libvirt.VIR_DOMAIN_RUNNING:
				return True
			else:
				return False
		except:
			return False

	def _vm_vnc_port(self):
		"""Return the vnc port of the vagrant VM
		:returns: The vnc port. If the domain is not running, None is returned. If vnc is not (yet?) available, -1 is returned.

		"""
		domain = self._libvirt_domain()
		# VM isn't running (yet?)
		if domain is None:
			return None

		try:
			info = xmltodict.parse(domain.XMLDesc())
		except:
			return None

		port = int(info["domain"]["devices"]["graphics"]["@port"])

		return port
	
	def _vm_ip_address(self):
		"""Return the ip address (on the host) of the VM being handled
		:returns: IP Address, or None if it does not yet have one
		"""
		domain = self._libvirt_domain()
		if domain is None:
			return None

		info = xmltodict.parse(domain.XMLDesc())
		mac_addr = self._mac_addr = info["domain"]["devices"]["interface"]["mac"]["@address"]
		output = arp("-a", "-n")
		for line in output.split("\n"):
			if mac_addr in line:
				ip_address = re.search(r'(\d{1,3}.\d{1,3}.\d{1,3}.\d{1,3})', line)
				return ip_address.group(1)

		return None
	
	def _vm_create(self):
		self._vm_image_loc = "/tmp/{}_{}.img".format(self.job, self.idx)
		self._domain = os.path.basename(self._vm_image_loc)

		errors = 0
		max_errors = 3

		while errors < max_errors:
			try:
				output = sh.qemu_img.create(
					self._vm_image_loc,
					b	= os.path.join(LIBVIRT_BASE, image_id_to_volume(self.image)),
					f	= "qcow2",
				)
				return
			except Exception as e:
				os.remove(self._vm_image_loc)
				errors += 1

		raise e
	
	def _vm_run(self):
		"""Creates the domain and runs it"""
		vm_name = os.path.basename(self._vm_image_loc)
		self._log.info("running VM {} with mac {} (ip {}, vnc port {})".format(
			vm_name,
			self.mac,
			".".join(str(int(x,16)) for x in self.mac.split(":")[-4:]),
			self.vnc_port
		))
		
		domain_xml = """
			<domain type='kvm'>
			  <name>{domain_name}</name>
			  <uuid>{domain_uuid}</uuid>
			  <memory>{mem_size}</memory>
			  <currentMemory>{mem_size}</currentMemory>
			  <vcpu>{num_cpus}</vcpu>
			  <os>
				<type arch='x86_64'>hvm</type>
				<boot dev='hd'/>
			  </os>
			  <features>
				<acpi/><apic/><pae/>
			  </features>
			  <cpu mode="host-model">
				<model fallback="allow"/>
			  </cpu>
			  <clock offset="utc"/>
			  <on_poweroff>destroy</on_poweroff>
			  <on_reboot>restart</on_reboot>
			  <on_crash>destroy</on_crash>
			  <devices>
				<emulator>/usr/bin/kvm-spice</emulator>

				<disk type='file' device='disk'>
				  <driver name='qemu' type='qcow2'/>
				  <source file='{image_path}'/>
				  <target dev='vda' bus='sata'/>
				  <address type='drive' controller='0' bus='0' target='0' unit='0'/>
				</disk>
				<controller type='sata' index='0'>
				  <alias name='sata0'/>
				  <address type='pci' bus='0x00' slot='0x03' function='0x0'/>
				</controller>

				<!-- 2ND DISK -->
				<!--
				<disk type="file" device="disk">
					<driver name="qemu" type="raw" cache="none" io="native"/>
					<source file="{{bootstrap_img}}"/>
					<target dev="vdb" bus="virtio"/>
					<address type='pci' domain='0x0000' bus='0x00' slot='0x06' function='0x0'/>
				</disk>
				-->

				<!-- USB -->
				<!--
				<disk type="file" device="disk">
					<driver name="qemu" type="raw" cache="none" io="native"/>
					<source file="{{bootstrap_img}}"/>
					<target dev="sda" bus="usb"/>
				</disk>
				-->
				
				<!-- CDROM -->
				<disk type='file' device='cdrom'>
				  <driver name='qemu' type='raw' cache="none" io="native"/>
				  <source file='{config_cdrom}'/>
				  <target dev='hda' bus='ide'/>
				  <readonly/>
				  <alias name='ide0-0-0'/>
				  <address type='drive' controller='0' bus='0' target='0' unit='0'/>
				</disk>
				<controller type='ide' index='0'>
				  <alias name='ide0'/>
				  <address type='pci' domain='0x0000' bus='0x00' slot='0x01' function='0x1'/>
				</controller>
				<!-- 
				-->
				
				<interface type='network'>
				  <mac address='{mac}'/>
				  <source network='talus-network'/>
				  <model type='virtio'/>
				  <filterref filter='{filter_name}'>
					{filter_params}
				  </filterref>
				  <address type='pci' bus='0x00' slot='0x05' function='0x0'/>
				</interface>
				<input type='tablet' bus='usb'/>
				<graphics type='vnc' port='{vnc_port}' keymap='en-us'/>
				<console type='pty'/>
				<video>
				  <model type='vga'/>
				  <address type='pci' bus='0x00' slot='0x02' function='0x0'/>
				</video>
			  </devices>
			</domain>
		""".format(
			config_cdrom	= self._create_cdrom(),
			#bootstrap_img	= self._create_bootstrap_img(),
			domain_name		= vm_name,
			domain_uuid		= str(uuid.uuid4()),
			mem_size		= self.ram * 1024, # ram is in MB
			num_cpus		= self.cpus,
			image_path		= self._vm_image_loc,
			filter_name		= "talus-" + self.network,
			filter_params	= self._get_filter_params(),
			mac				= self.mac,
			vnc_port		= self.vnc_port
		)

		conn = self._libvirt()
		#domain = conn.defineXML(domain_xml)
		# should create and start the VM
		domain = conn.createXML(domain_xml, 0)

		self._log.debug("should be running now")
#
		#sh.virt_install(
			#"--import", # stupid python keywords
			#virt_type		= "kvm",
			#r				= self.ram,
			#accelerate		= True,
			#n				= vm_name,
			#disk			= "{},device=disk,bus=sata,format=qcow2".format(self._vm_image_loc),
			#vnc				= True,
			##w				= "bridge=virbr2,model=virtio",
			#w				= True,
			#noautoconsole	= True,
			## network		= "filter...."
		#)
