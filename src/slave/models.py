#!/usr/bin/env python
# encoding: utf-8

import datetime
from mongoengine import *
import os

def do_connect(host):
	connect("talus", host=host, port=27017)

class Result(Document):
	job			= ReferenceField("Job", required=True)
	type		= StringField(required=True)
	tool		= StringField(required=True)
	data		= DictField()
	created		= DateTimeField(default=datetime.datetime.now)
	tags		= ListField(StringField())

class Code(Document):
	name		= StringField(unique_with="type")
	type		= StringField()
	params		= ListField()
	bases		= ListField()
	desc		= StringField()
	timestamps	= DictField()
	tags		= ListField(StringField())

class Task(Document):
	name		= StringField(unique_with="tool")
	tool		= ReferenceField("Code", required=True)
	image		= ReferenceField("Image", required=False)
	params		= DictField()
	version		= StringField() # intended to be used for git versioning
	timestamps	= DictField()
	limit		= IntField(default=1)
	vm_max		= IntField(default=30*60)
	network		= StringField()
	tags		= ListField(StringField())

class JobError(EmbeddedDocument):
	message		= StringField()
	backtrace	= StringField()
	logs		= ListField(StringField())

class Job(Document):
	name		= StringField()
	task		= ReferenceField("Task", required=True)
	params		= DictField()
	status		= DictField()
	timestamps	= DictField()
	queue		= StringField()
	priority	= IntField(default=50) # 0-100
	limit		= IntField(default=1)
	progress	= IntField(default=0)
	image		= ReferenceField("Image", required=True)
	network		= StringField()
	debug		= BooleanField(default=False)
	vm_max		= IntField(default=30*60)
	errors		= ListField(EmbeddedDocumentField(JobError))
	logs		= ListField(EmbeddedDocumentField(JobError))
	tags		= ListField(StringField())

class FileSet(Document):
	name		= StringField()
	files		= ListField()

	# created, modified
	timestamps	= DictField()

	# for use when it's the result set output of a job
	job			= ReferenceField("Job", required=False)

	tags		= ListField(StringField())

class TmpFile(Document):
	path		= StringField(unique=True)

class OS(Document):
	name		= StringField(unique=True)
	version		= StringField()
	type		= StringField()
	arch		= StringField()
	tags		= ListField(StringField())

class Image(Document):
	name		= StringField(unique=True)
	os			= ReferenceField('OS', required=True)
	desc		= StringField(default="desc", required=False)
	tags		= ListField(StringField())
	status		= DictField()
	base_image	= ReferenceField('Image', null=True, required=False)
	username	= StringField(required=True, default="user")
	password	= StringField(required=True, default="password")
	md5			= StringField(required=False, null=True, default=None)
	timestamps	= DictField()

class Master(Document):
	hostname		= StringField(unique=True)
	ip				= StringField()
	vms				= ListField(DictField())
	queues			= DictField()

class Slave(Document):
	hostname		= StringField()
	uuid			= StringField()
	ip				= StringField()
	max_vms			= IntField(default=1)
	running_vms		= IntField(default=0)
	total_jobs_run	= IntField(default=0)
	vms				= ListField(DictField())
	timestamps		= DictField()
