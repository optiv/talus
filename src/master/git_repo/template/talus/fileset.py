#!/usr/bin/env python
# encoding: utf-8

import pymongo
import bson # included with pymongo
import gridfs # included with pymongo
import time

DB = None
def set_connection(host):
	global DB
	DB = pymongo.MongoClient(host).talus

class FileSet(object):

	"""A class for handling filesets"""

	def __init__(self, fileset_id=None, name=None):
		"""Init the fileset with the fileset id

		:fileset_id: Id of an existing fileset, or None if it should be created
		:name: The name of the fileset. required if fileset_id is None
		"""
		if fileset_id is None:
			if name is None:
				raise Exception("name is required when creating new filesets")

			fileset_id = DB.file_set.insert_one({
				"name"			: name,
				"files"			: [],
				"timestamps"	: { "created": time.time() },
				"job"			: None
			})

		self._fileset_id = fileset_id

		self._info = DB.file_set.find_one({"_id": bson.ObjectId(self._fileset_id)})

		self.files = self._info["files"]
		self.name = self._info["name"]

		self.fs = gridfs.GridFS(DB)
	
	def add(self, contents, filename=None, content_type="application/octet-stream", **metadata):
		"""Add a new file to this fileset, with filename ``filename``, content type ``content_type``,
		and contents ``contents``. Additional attributes may be added with other key-word
		arguments.

		:param str contents: The contents of the file
		:param str filename: The name of the file
		:param str content_type: The content-type of the file (mimetype)
		:param str metadata: Other attributes that should be attached to this file
		"""
		with self.fs.new_file(filename=filename, content_type=content_type, metadata=metadata) as f:
			f.write(contents)

		DB.file_set.update(
			{"_id": bson.ObjectId(self._fileset_id)},	# query
			{
				"$addToSet": {"files": f._id},			# action
				"$set": {"timestamps.modified": time.time() }
			}
		)

		return str(f._id)

	# alias add_file to add
	add_file = add
	
	# TODO add_stream?
	
	def __getitem__(self, idx):
		"""Return an open GridFS object, which is a stream-like object
		that you can read/seek/close, etc. It loads everything over gridfs

		:returns: GridFS File object, or None
		:raises: IndexError if idx is out of bounds
		"""
		file_id = self.files[idx]
		try:
			return self.fs.get(bson.ObjectId(file_id))
		except:
			return None
	
	def __len__(self):
		return len(self.files)
