#!/usr/bin/env python

import os
import shlex
import shutil
import subprocess
import sys
import re

def run(args, async=False, shell=True, env=None, output_to_stdout=False, group=False):
	"""Run the command specified by the array `args` and return
	the output. If ``async`` is True, the proc object will be returned

	:args: An array of command arguments to be run
	:async: If true, return immediately with the proc object
	:returns: output of the command or the proc object if ``async``
	"""
	if env is None:
		proc_env = os.environ.copy()
	else:
		proc_env = os.environ.copy()
		proc_env.update(env)

	opts = {}
	if group:
		opts["preexec_fn"] = os.setsid
	if shell:
		if output_to_stdout:
			proc = subprocess.Popen(args, stderr=subprocess.STDOUT, env=proc_env, **opts)
		else:
			proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=proc_env, **opts)
	else:
		proc = subprocess.Popen(args, shell=False, env=proc_env, **opts)

	if async:
		return proc
	
	# don't block
	else:
		stdout,_ = proc.communicate()
	return stdout
	
def qemu_img_info(image_path):
	"""Return a dict of info returned by qemu-img info. Assumes the image_path exists
	and points to a valid VM image

	:image_path: path to the image
	:returns: dict of returned information about the image

	"""
	output = run(["qemu-img", "info", image_path])

	res = {}
	for line in output.split("\n"):
		match = re.match(r'^\s*([^\s].*):\s*(.*)$', line)
		if match is None:
			continue
		res[match.group(1)] = match.group(2)

	return res

def qemu_convert_image(image_path, target_format, target_path=None, orig_format=None):
	"""`qemu_convert_image` will conver the image found at `image_path` to the specified format.
	It is expected that original file-type detection will be used. The resulting image
	will be saved to `target_path`

	:image_path: The path to the image (e.g. qcow2, vmdk, vdi, raw)
	:target_format: The target format (e.g. qcow2, vmdk, vdi, raw)
	:target_path: [optional] The path to save the converted image to
	:orig_format: [optional] the format of the original image
	:returns: The path the converted image was saved to, potentially the same as the original path
	:raises: Exception if the original file format cannot be determined or if the image path does
	not exist
	"""
	if not os.path.exists(image_path):
		raise Exception("Error, image path {} does not exist!".format(image_path))

	if orig_format is None:
		orig_format = get_image_format(image_path)
	if orig_format is None:
		raise Exception("Error, cannot determine original image format")

	if target_path is None:
		basename = os.path.basename(image_path)
		parts = basename.split(".")[:-1]
		if len(parts) > 1:
			left_side = parts[:-1]
		else:
			left_side = "converted_" + basename
		target_path = os.path.dirname(image_path) + os.path.sep + left_side + "." + target_format.lower()
	
	# it's already in the desired format, so just copy the file if needed
	if orig_format == target_format:
		return target_path

	args = ["qemu-img", "convert", "-f", orig_format, "-O", target_format, image_path, target_path]
	output = run(args)

	return target_path

def get_image_format(image_path):
	"""Get the format of the VM image at `image_path`

	:image_path: The path to the VM image
	:returns: The format of the VM image, or None if it cannot be determined
	"""
	info = qemu_img_info(image_path)
	if "file format" in info:
		return info["file format"]
	else:
		# try using the `file` command
		output = run(["file", image_path])
		if "VDI" in output:
			return "vdi"
		if "VMDK" in output or "vmdk" in output:
			return "vmdk"
		else:
			return None

	return None
