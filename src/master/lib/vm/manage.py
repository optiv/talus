#!/usr/bin/env python
# encoding: utf-8

"""
The manage module contains classes to manage VM creation,
conversion, snapshots, and exporting
"""

from collections import deque
import json
import libvirt
import logging
import os
import re
import sh
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import threading
import uuid
import xmltodict

from . import utils

DATA_DIR = os.path.join(os.path.abspath(os.path.dirname(__file__)), "..", "..", "data")

def libvirt_callback(ignore, err):
	if err[3] != libvirt.VIR_ERR_ERROR:
		# log it?
		pass
libvirt.registerErrorHandler(f=libvirt_callback, ctx=None)

class VMWorker(threading.Thread):
	"""A threaded class that manages individual VMs"""

	daemon = True

	def __init__(self, idx, log):
		"""docstring for VMWorker constructor
		
		:log: The parent log of the worker"""
		super(VMWorker, self).__init__()
		self._idx = idx
		self._log = log.getChild("{}[{}]".format(self.__class__.__name__, idx))

		self._running = threading.Event()
		# used to signal that the machine is up and running
		self._accessible = threading.Event()
	
	def run(self, user_interaction_cb):
		"""Run the VM
		:returns: TODO
		"""
		raise NotImplemented("Inheriting classes must implement the run function")
	
	def stop(self, force=False):
		"""Stop the running VM and block until everything is cleaned up

		:force: TODO
		:returns: TODO

		"""
		self._log.info("STOPPING")
		self._running.clear()
		self.join()
	
	def wait_for_ready(self, timeout=None):
		"""Block until the VM is up and running
		:timeout: max amount of time to wait for (seconds)
		:returns: None
		"""
		self._log.debug("waiting for box to become accessible")
		if timeout is not None:
			self._accessible.wait(timeout)
		else:
			self._accessible.wait(2**31)
		self._log.debug("box is accessible")
	
	def get_vnc_info(self):
		"""Return the vnc info for the worker
		:returns: TODO

		"""
		raise NotImplemented("Inheriting classes must implement the get_vnc_info function")
	
	def status(self):
		"""Get the status of the VM
		:returns: A status string

		"""
		raise NotImplemented("Inheriting classes must implement the status function")

# not gonna be needed on the Master
class KvmWorker(VMWorker):
	"""A worker for managing a running libvirt vms directly (not via vagrant)"""

	def __init__(self, image_path, idx, log, iso_path=None, on_success=None):
		"""docstring for LibvirtWorker constructor"""
		super(LibvirtWorker, self).__init__(idx, log)

		self._image_path = image_path
		self._vagrant_base = vagrant
		self._iso_path = iso_path
		self._on_success = on_success

		self._libvirt_conn = None
		self._domain = None
	
	def run(self):
		self._running.set()

		self._domain = self._image_path.replace(os.path.sep, "__")
	
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
				</disk>
				<interface type='network'>
				  <source network='default'/>
				  <model type='virtio'/>
				</interface>
				<input type='tablet' bus='usb'/>
				<graphics type='vnc' port='-1' keymap='en-us'/>
				<console type='pty'/>
				<video>
				  <model type='vga'/>
				</video>
			  </devices>
			</domain>
		""".format(
			domain_name = self._domain,
			domain_uuid = str(uuid.uuid4()),
			mem_size	= 1024 * 1024,
			num_cpus	= 2,
			image_path	= self._image_path,
		)

		import pdb; pdb.set_trace()

		conn = self._libvirt()

		domain = conn.createXML(domain_xml, 0)
	
	def _libvirt(self):
		if self._libvirt_conn is None:
			self._libvirt_conn = libvirt.open("qemu:///system")
		return self._libvirt_conn
	
	def _libvirt_domain(self):
		if self._domain is None:
			return None

		conn = self._libvirt()
		try:
			domain = conn.lookupByName(self._domain)
			return domain
		except libvirt.libvirtError as e:
			return None

class VagrantWorker(VMWorker):
	"""A worker for managing a running vagrant image"""

	def __init__(self, box_name, vagrantfile, idx, log, vagrant_base="~/.vagrant.d", image_store="/var/lib/libvirt/images", dest_name=None, import_image_path=None, iso_path=None, on_success=None, user_interaction=False, **options):
		"""docstring for VagrantWorker constructor
		
		:box_name: the name of the box to be run
		:vagrantfile: the Vagrantfile to run against the box
		:vagrant_base: the base directory of vagrant (defaults to ~/.vagrant.d)
		:image_store: The directory where all the images are stored (default /var/lib/libvirt/images)
		:dest_name: the name of the resulting, modified box. If None, the original box will be overwritten with the new changes
		:import_only: if True, the image_path will be used to create a new vagrant-libvirt compatible box
		:import_image_path: The path to the VM image that is to be imported (a new vagrant box created)
		:iso_path: Path to the ``iso`` to be mounted in the VM after booting
		:on_success: A callback that is called when the operation is successfully completed (VM is shutdown)
		:user_interaction: Whether or not user interaction is expected
		"""
		super(VagrantWorker, self).__init__(idx, log)

		self._image_store = image_store
		self._libvirt_conn = None

		self._vagrant_base = os.path.expanduser(vagrant_base)
		self._box_name = box_name
		self._vagrantfile = vagrantfile
		self._dest_name = dest_name
		self._import_image_path = import_image_path
		self._iso_path = iso_path
		self._on_success = on_success
		self._log.debug("on_success = {}".format(self._on_success))
		self._user_interaction = user_interaction
		self._options = options
		self._tmpdir = None
	
	def run(self):
		"""Run the vagrant box by creating a project that uses the specified box
		"""
		self._running.set()

		self._maybe_do_import()

		self._project_dir = self._create_vagrant_project(self._vagrantfile, base_name=self._box_name)
		self._run_env = {
			"VAGRANT_CWD": self._project_dir
		}

		self._log.debug("created temporary vagrant project at {!r}".format(self._project_dir))
		self._domain = os.path.basename(self._project_dir + "_default")

		args = ["vagrant", "up", "--provider", "libvirt"]
		self._log.debug("running {}".format(" ".join(args)))
		proc = utils.run(args, async=True, output_to_stdout=True, env=self._run_env, group=True)

		# wait for it to initally spin up, or for the proc to exit
		# break if the box is running or "vagrant up" has exited already
		count = 0
		while not self._box_is_running() and proc.poll() is None:
			if count % 10 == 0:
				self._log.debug("box isn't running yet, and 'vagrant up' has not exited yet")
			count += 1
			time.sleep(0.5)
		self._log.debug("box should be up and running")

		self._hotplug_empty_disk()

		if proc.poll() is not None:
			self._log.debug("vagrant up quit before the VM started, likely some error")
			self._running.clear()
		else:
			# the box is up, so let's wait until we have a valid vnc port
			# TODO should probably have some sort of time on this
			port = self.get_vnc_port()
			while port is None or port == -1:
				time.sleep(0.2)
				port = self.get_vnc_port()

			self._log.debug("setting accessible event")
			# signal that the VM is now accessible via VNC
			self._accessible.set()

		while True:
			# don't need to wait for user interaction, and the VM has been provisioned (vagrant up exited)
			if not self._user_interaction and proc.poll() is not None:
				self._log.debug("non-interactive mode, vagrant up exited, shutting down VM and continuing on with my short life")

				# give the shutdown command a chance to execute before we pull the plug
				for x in range(10):
					if not self._box_is_running():
						self._log.debug("shutdown script worked, box shut down on its own")
						break
					time.sleep(1)

				# if the VM hasn't shutdown on its own by now, kill it
				if self._box_is_running():
					args = ["vagrant", "halt"]
					self._log.debug("running {}".format(" ".join(args)))
					output = utils.run(args, env=self._run_env)

			# someone has told us to bail
			if not self._running.is_set():
				self._log.debug("running event cleared. someone doesn't like me")
				break

			# if the VM has been shutdown
			if not self._box_is_running():
				self._log.debug("running VM has been shutdown. continuing on")
				break

			time.sleep(0.2)

		# the vagrant up command is still running. KILL IT. FORCIBLY. WITH PREJUDICE
		if proc.poll() is None:
			self._log.debug("vagrant up process is still running, forcefully terminating it")

			kill_methods = [
				# should kill all child processes too
				[os.killpg, [proc.pid, signal.SIGKILL]],
				[proc.terminate, []],
				[proc.kill, []],
				[proc.send_signal, [signal.SIGKILL]]
			]
			for kill_method,kill_args in kill_methods:
				try:
					kill_method(kill_args)
				except:
					pass

		# TODO do we want a temporary "run this VM and let me poke around"?
		# if not self._temporary:
		#	self._save
		self._save()

		self._cleanup()

		# in case _box_is_running() returned False, we should clear the _running Event
		self._running.clear()

		if self._on_success is not None:
			self._log.debug("going to call self._on_success")
			# create new from base
			if self._dest_name is not None:
				self._log.debug("calling self._on_success({})".format(self._dest_name))
				self._on_success(self._dest_name)
			
			# configure/import an image
			else:
				self._log.debug("calling self._on_success({})".format(self._box_name))
				self._on_success(self._box_name)

		self._log.debug("vagrant worker finished")
	
	def _hotplug_empty_disk(self):
		self._tmpdir = tempfile.mkdtemp()
		sh.chmod("o+rwx", self._tmpdir)
		self._tmpdisk = os.path.join(self._tmpdir, "tmpdisk.img")

		sh.dd("if=/dev/null", "bs=1K", "of={}".format(self._tmpdisk), "seek=1030")
		sh.Command("mkfs.ntfs")("-F", self._tmpdisk)

		disk_file = os.path.join(self._tmpdir, "disk.xml")
		with open(disk_file, "wb") as f:
			f.write("""
<disk type="file" device="disk">
	<driver name="qemu" type="raw" cache="none" io="native"/>
	<source file="{}"/>
	<target dev="sda" bus="usb"/>
</disk>
			""".format(self._tmpdisk))

		sh.virsh("attach-device", self._domain, disk_file)

#		sh.qemu_img("create", "-f", "raw", self._tmpdisk, "1.1M")
#		sh.Command("mkfs.ntfs")("-F", self._tmpdisk)
#
#		sh.virsh("attach-disk", self._domain, "--source", self._tmpdisk, "--target", "vdb")
	
	def _maybe_do_import(self):
		"""Maybe import an image into a vagrant box
		:returns: None

		"""
		if self._import_image_path is None:
			return

		# imports only configure a base image. Create a new image based on the newly imported one
		# to use a vagrant file
		self._vagrantfile = None

		self._log.debug("converting image at {!r} to qcow2 format".format(self._import_image_path))
		new_image_path = utils.qemu_convert_image(self._import_image_path, "qcow2")
		self._log.debug("qcow2 image now found at {!r}".format(new_image_path))
		
		# only copy it if the resulting file is the same as the original file
		# (otherwise the normal behavior is that a new file MUST be created)
		copy = (new_image_path == self._import_image_path)

		self._log.debug("imported image from\n\t{}\nto qcow2 image at\n\t{}".format(self._import_image_path, new_image_path))

		self._create_vagrant_box(
			new_image_path,
			self._box_name,
			# use the default vagrant file, we'll use the user's vagrantfile when
			# we modify the imported image
			vagrantfile=None,
			copy=copy
		)

		self._log.info("vagrant box {!r} created".format(self._box_name))
	
	def _box_is_running(self):
		"""Return True/False if the current box is still running
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
	
	def get_vnc_port(self):
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
	
	def get_vnc_info(self):
		"""Return the vnc info for the running vagrant worker
		:returns: TODO

		"""
		port = self.get_vnc_port()
		
		# TODO change this to some config setting?
		hostname = socket.gethostname()

		self._vnc_info = {
			"uri": "vnc://{}:{}".format(hostname, port)
		}

		return self._vnc_info
	
	def _libvirt(self):
		"""Return a libvirt connection
		:returns: TODO

		"""
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
	
	def _save(self):
		"""Save the VM by either overwriting an existing vagrant box or creating a new vagrant box
		"""
		vm_name = os.path.basename(self._project_dir + "_default.img")
		vm_path = os.path.join(self._image_store, vm_name)

		# merge the changes made with the image `box_name`
		if self._dest_name is None:
			# commit the changes into the base image. shouldn't have to move anything around here
			args = ["qemu-img", "commit", vm_path]
			self._log.debug("running {}".format(" ".join(args)))
			self._log.info("committing changes from {!r} into base image".format(vm_path))
			output = utils.run(args)

			self._log.debug("copying base image back into vagrant box...")
			# since it's symlinked now, we shouldn't have to copy anything around
			info = utils.qemu_img_info(vm_path)

			if "backing file" in info:
				shutil.copyfile(info["backing file"], os.path.join(self._vagrant_base, "boxes", self._box_name, "0", "libvirt", "box.img"))
			else:
				self._log.debug("ERROR saving image {!r}, could not determine backing file".format(vm_path))

		# create a new vagrant box
		else:
			self._create_vagrant_box(vm_path, self._dest_name)
	
	def _cleanup(self):
		"""Cleanup everything (remove tmp project files, etc.)
		:returns: None
		"""
		args = ["vagrant", "destroy"]
		self._log.debug("running {}".format(" ".join(args)))
		output = utils.run(args, env=self._run_env)

		shutil.rmtree(self._project_dir)

		if self._tmpdir is not None:
			shutil.rmtree(self._tmpdir)

	def _create_vagrant_project(self, vagrantfile, id="tmp", base_name=None):
		"""Create a project directory in which "vagrant up" can be run. Callers are
		responsible for destroying the new project (vagrant destroy) and removing
		the directory.

		:vagrantfile: The contents of the vagrant file
		:id: The id of the project, used as part of the project folder name
		:returns: The path to the new project directory

		"""
		# when importing an image, the user is not allowed to specify a vagrantfile
		# for the initial configuration and setup
		if vagrantfile is None:
			vagrantfile = """
				Vagrant.configure("2") do |config|
					config.vm.box = "some_box_name"

					config.vm.provider :libvirt do |libvirt|
					  libvirt.input :type => 'tablet', :bus => 'usb'

					  # always mount the isos
					  libvirt.storage :file, :device => :cdrom, :path => "{iso_path}"
					  libvirt.disk_bus = 'sata'
					  libvirt.video_type = 'vga'
					end
				end
			""".format(
				iso_path=os.path.join(DATA_DIR, "virtio-drivers.iso")
			)

		vagrantfile = self._prepare_vagrantfile(vagrantfile, base_name, auto_shutdown=(not self._user_interaction))

		# make a project directory
		tmpd = tempfile.mkdtemp(prefix=id)
		with open(os.path.join(tmpd, "Vagrantfile"), "w") as f:
			f.write(vagrantfile)

		return tmpd

	def _create_vagrant_box(self, image_path, box_name, copy=True, vagrantfile=None, ostype="windows"):
		"""Create a vagrant box in ~/.vagrant.d/boxes with the appropriate folder
		structure to play nicely with vagrant.

		:image_path: The path to the image with which the box should be created
		:box_name: The name of the box
		:bool copy: Copy (True, default) the image, or move (False) the image
		:vagrantfile: The contents of the Vagrantfile to be included with the Vagrant box
		:username: Username on the VM
		:password: Password on the VM
		:ostype: OS type (windows/linux), default=windows
		:returns: None
		:raises: Exception if a box already exists with `box_name`
		"""
		box_folder = os.path.join(self._vagrant_base, "boxes", box_name)

		self._log.debug("creating new vagrant box at {}".format(box_folder))

		# make sure the box name is unique! it *SHOULD* be a uuid or something
		if os.path.exists(box_folder):
			raise Exception("vagrant box {!r} already exists!".format(box_name))

		libvirt_folder = os.path.join(box_folder, "0", "libvirt")
		os.makedirs(libvirt_folder)

		if vagrantfile is None:
			comms = "winrm" if ostype is "windows" else "ssh"
			vagrantfile = """
				Vagrant.configure("2") do |config|
					config.ssh.insert_key = false
					config.ssh.username = "{username}"
					config.ssh.password = "{password}"
					config.winrm.username = "{username}"
					config.winrm.password = "{password}"
					config.vm.communicator = "{comms}"
					config.vm.synced_folder ".", "/vagrant", disabled: true
					config.vm.guest = :{ostype}
					config.vm.provider :libvirt do |libvirt|
					  libvirt.storage :file, :device => :cdrom, :path => "{iso_path}"
					  libvirt.disk_bus = 'sata'
					  libvirt.input :type => 'tablet', :bus => 'usb'
					  libvirt.video_type = 'vga'
					  libvirt.graphics_ip = '0.0.0.0'
					end
				end
			""".format(
				username=self._options.setdefault("username", "user"),
				password=self._options.setdefault("password", "password"),
				ostype=ostype,
				comms=comms,
				iso_path=os.path.join(DATA_DIR, "virtio-drivers.iso")
			)

		# create Vagrantfile
		with open(os.path.join(libvirt_folder, "Vagrantfile"), "w") as f:
			f.write(vagrantfile)

		info = utils.qemu_img_info(image_path)
		virtual_size = info["virtual size"].split(" ")[0]
		virtual_size = int(re.sub(r'[^0-9]', '', virtual_size))

		# create metadata.json
		with open(os.path.join(libvirt_folder, "metadata.json"), "w") as f:
			f.write("""
				{{
					"provider":"libvirt",
					"format":"qcow2",
					"virtual_size": {}
				}}
			""".format(virtual_size))

		# add the image
		img_dest = os.path.join(libvirt_folder, "box.img")
		libvirt_dest = "/var/lib/libvirt/images/{}_vagrant_box_image_0.img".format(box_name)
		if copy:
			shutil.copyfile(image_path, img_dest)
		else:
			shutil.move(image_path, img_dest)
	
	def _prepare_vagrantfile(self, vagrantfile, base_name, auto_shutdown=False):
		vagrantfile = re.sub(r'(vm\.box\s*=\s*["\'])([^"\"]+)(["\'])', '\g<1>' + base_name + '\g<3>', vagrantfile)

		if auto_shutdown:
			parts = vagrantfile.rsplit("end", 1)
			# TODO how do I detect linux???
			vagrantfile = parts[0] + """
					config.vm.provision "shell", inline: "shutdown /s /d p:0:0 /t 0"
				end
				""" + parts[1]

		return vagrantfile

class VMManager(object):
	"""VMManager class is responsible for creating and managing VM images.
	
	It is intended to be able to handle:
	
	* converting VM images from various file formats to qcow2
	* running Vagrant files on base images to configure VMs
	* saving off a snapshot of the configured VM (in qcow2 format with backing files (a snapshot chain)
	* exporting VM images into various file formats
	* fetching a list of all backing file names/md5s
	
	This class will block until all operations are complete."""

	def __init__(self, vagrant_base="~/.vagrant.d", image_store="/var/lib/libvirt/images", parent_log=None, **opts):
		"""docstring for VMManager constructor
		
		:vagrant_base: The vagrant base folder (default = "~/.vagrant.d")
		:image_store: The directory that libvirt images will be stored in
		:parent_log: optional parent log of the VMManage instance
		:opts: Optionsn for the VMManager
		"""
		super(VMManager, self).__init__()

		self._vagrant_base = os.path.expanduser(vagrant_base)
		self._image_store = os.path.expanduser(image_store)
		self._libvirt_conn = None

		# TODO make this based on the # of cores available in the system
		self._max_vms = opts.setdefault("max_vms", 2)
		self._vm_lock = threading.Semaphore(self._max_vms)
		self._on_worker_exited = opts.setdefault("on_worker_exited", None)
		self._worker_numbers = deque(range(self._max_vms))
		self._workers = {}

		if parent_log is None:
			self._log= logging.getLogger("VMManager")
		else:
			self._log = parent_log.getChild("VMManager")

	# ---------------------------------
	# PUBLIC
	# ---------------------------------

	def import_image(self, image_path, image_name, user_interaction=False, iso_path=None, username="user", password="password", on_success=None):
		"""Import the image into talus with the name ``image_name``, optionally running ``vagrantfile`` on
		the newly created box and applying the changes. If ``user_interaction`` is True, worker and vnc
		info will be returned in a dict: ::

			{
				"worker": WORKER_NUMBER,
				"vnc": {
					"uri": "vnc:///HOSTNAME:PORT"
				}
			}

		The worker number may be passed to :meth:`.shutdown_worker` to shutdown a running VM if
		``user_interaction`` was set to True.

		:image_path: The path to the image to be imported
		:image_name: The name of the resulting image
		:user_interaction: True/False if the user should be allowed to interact with the imported VM (default=False)
		:iso_path: Path to an iso to be mounted after booting up (default: None)
		:on_success: Callback to be called with the image name on successful completion
		:returns: TODO

		"""
		return self._run_vagrant_worker(
			image_name,
			None,
			user_interaction=user_interaction,
			import_image_path=image_path,
			iso_path=iso_path,
			username=username,
			password=password,
			on_success=on_success
		)
	
	def delete_image(self, image_name):
		"""Delete the image specified by ``image_name``. Note that this WILL NOT check for
		images that use ``image_name`` as their base.

		:image_name: The name of the image to delete
		:returns: None
		"""
		vagrant_box_path = os.path.join(self._vagrant_base, "boxes", image_name)
		if os.path.exists(vagrant_box_path):
			# --force so it doesn't prompt for confirmation
			args = ["vagrant", "box", "remove", "--force", image_name]
			self._log.debug("running {}".format(" ".join(args)))
			self._log.info("deleting image named {!r}".format(image_name))
			output = utils.run(args)

			self._log.debug("removing vagrant box path: {!r}".format(vagrant_box_path))
			shutil.rmtree(vagrant_box_path)

			# update the machine index
			with open(os.path.join(self._vagrant_base, "data", "machine-index", "index")) as f:
				data = json.loads(f.read())
			del data["machines"][image_name]
			with open(ow.path.join(self._vagrant_base, "data", "machine-index", "index"), "wb") as f:
				f.write(json.dumps(data))

		# now also delete it from the libvirt pool
		conn = self._libvirt()
		default_pool = conn.storagePoolLookupByName("default")

		try:
			volume_name = image_name + "_vagrant_box_image_0.img"
			self._log.debug("deleting libvirt volume {!r}".format(volume_name))
			volume = default_pool.storageVolLookupByName(volume_name)
			if volume is not None:
				volume.delete()
		except libvirt.libvirtError as e:
			pass
		except Exception as e:
			pass
	
	def export_image(self, image_name, output_type=None):
		"""Export the image specified by `image_name` to `output_type` VM image. Supported output
		types are qcow2, ova, vmdk, and vid. (TODO: vagrant box output? <name>.box?)

		:image_name: Name of the image to export (probably a UUID)
		:output_type: Optionally specify the output format. Defaults to qcow2
		:returns: Path to an exported VM image
		"""
		# TODO should we allow this to be streamed?? ... nah
		pass
	
	def configure_image(self, box_name, vagrantfile, user_interaction=False, on_success=None, kvm=False):
		"""Configure the existing vagrant box with the supplied vagrantfile. If ``user_interaction`` is
		True, a dict will be returned with vm worker info in the format: ::

			{
				"worker": WORKER_NUMBER,
				"vnc": {
					"uri": "vnc:///HOSTNAME:PORT"
				}
			}

		The worker number may be passed to :meth:`.shutdown_worker` to shutdown a running VM if
		``user_interaction`` was set to True.

		:box_name: The name of the box to configure
		:vagrantfile: The name of the vagrantfile to configure
		:user_interaction: If user-interaction is expected (e.g. if only doing auto-updates w/ a Vagrantfile, set to False)
		:returns: None

		"""
		if kvm:
			return self._run_kvm_worker(
				box_name,
				dest_name=None, # update the existing vagrant box image!

				# TODO maybe be able to provide a script to run instead of a vagrant file??
				user_interaction=True, # no auto-configuring since it's kvm (no vagrant files)
				on_success=on_success
			)
		else:
			return self._run_vagrant_worker(
				box_name,
				vagrantfile,
				dest_name=None, # update the existing vagrant box image!
				user_interaction=user_interaction,
				on_success=on_success
			)
	
	def create_image(self, vagrantfile, base_name, dest_name, user_interaction=False, on_success=None):
		"""Use the `vagrantfile` to create a new image using the vagrant
		box specified by `base_name`. If ``user_interaction`` is
		True, a dict will be returned with vm worker info in the format: ::

			{
				"worker": WORKER_NUMBER,
				"vnc": {
					"uri": "vnc:///HOSTNAME:PORT"
				}
			}

		The worker number may be passed to :meth:`.shutdown_worker` to shutdown a running VM if
		``user_interaction`` was set to True.

		:vagrantfile: Contents of the Vagrant file with a $$BASE_IMAGE$$ placeholder for the base box
		:base_name: The name of the base vagrant box
		:dest_name: The name of the new vagrant box
		:user_interaction: If user interaction will be allowed (will not immediately cleanup, and a vnc url will be returned)
		:returns: A VM info (including vnc connection info) if ``user_interaction`` is True; else returns None
		"""
		return self._run_vagrant_worker(
			base_name,
			vagrantfile,
			dest_name=dest_name,
			user_interaction=user_interaction,
			on_success=on_success
		)
	
	def shutdown_vagrant_vm(self, worker_num):
		"""Shutdown the VM specified by worker_num.

		:worker_num: Number of the worker to shutdown (returned if user_interaction is True)
		:returns: None

		"""
		self._workers[worker_num].stop()
		del self._workers[worker_num]
		self._worker_numbers.append(worker_num)

		self._vm_lock.release()
	
	# ---------------------------------
	# PRIVATE
	# ---------------------------------

	def _wait_for_worker_to_exit(self, worker):
		worker.join(2**31)
		self._log.info("worker exited")

		del self._workers[worker._idx]
		self._worker_numbers.append(worker._idx)

		if self._on_worker_exited is not None:
			self._on_worker_exited()

		self._log.debug("releasing vm_lock")
		self._vm_lock.release()
	
	def _run_kvm_worker(self, base_name, dest_name=None, user_interaction=True):
		"""TODO: Docstring for _run_kvm_worker.

		:base_name: TODO
		:dest_name: TODO
		:user_interaction: TODO
		:returns: TODO

		"""
		# make sure we don't just will-nilly create too many VMs
		self._vm_lock.acquire()

		worker_num = self._next_worker_number()
		worker = KvmWorker(
			shutil.copyfile(info["backing file"], os.path.join(self._vagrant_base, "boxes", self._box_name, "0", "libvirt", "box.img"))
		)

	def _run_vagrant_worker(self, base_name, vagrantfile, dest_name=None, user_interaction=False, import_image_path=None, iso_path=None, on_success=None, **options):
		"""Run the vagrant worker with the supplied args. If dest_name is None, the existing image
		will be updated with the changes.

		:base_name: Base name of the Vagrant box
		:vagrantfile: Contents of the vagrant file to run on the box
		:dest_name: Optional name of the new box that is to be created after modifying the base box
		:user_interaction: True/False if user interaction is needed
		:import_image_path: The path to the VM image to be converted and imported
		:returns: None if no user interaction is needed, else dict of worker number and vnc info

		"""
		# make sure we don't just will-nilly create too many VMs
		self._vm_lock.acquire()

		worker_num = self._next_worker_number()
		worker = VagrantWorker(
			base_name,
			vagrantfile,
			worker_num,
			self._log,
			self._vagrant_base,
			self._image_store,
			dest_name=dest_name,
			import_image_path=import_image_path,
			iso_path=iso_path,
			on_success=on_success,
			user_interaction=user_interaction,
			**options
		)
		self._workers[worker_num] = worker
		worker.start()

		thread = threading.Thread(target=self._wait_for_worker_to_exit, args=[worker])
		thread.daemon = True
		thread.start()

		ret = None
		if user_interaction:
			worker.wait_for_ready()
			vnc_info = worker.get_vnc_info()
			ret = {
				"worker": worker_num,
				"vnc": vnc_info
			}

		# else we just let the VagrantWorker thread do its thing without
		# waiting for it

		return ret

	def _next_worker_number(self):
		return self._worker_numbers.popleft()

	def _libvirt(self):
		"""Return a libvirt connection
		:returns: TODO

		"""
		if self._libvirt_conn is None:
			self._libvirt_conn = libvirt.open("qemu:///system")
		return self._libvirt_conn
