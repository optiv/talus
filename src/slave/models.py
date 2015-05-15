#!/usr/bin/env python
# encoding: utf-8

import datetime
from mongoengine import *
import os

def do_connect(host):
	connect("talus", host=host, port=27017)

class Result(Document):
	job			= ReferenceField("Job", required=True)
	timestamps	= DictField()
	data		= StringField()

class Task(Document):
	name		= StringField(unique_with="tool")
	tool		= ReferenceField("Code", required=True)
	params		= DictField()
	version		= StringField() # intended to be used for git versioning
	status		= DictField()
	limit		= IntField(default=1)

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

class Code(Document):
	name		= StringField(unique_with="type")
	type		= StringField()
	params		= ListField()
	bases		= ListField()
	desc		= StringField()
	timestamps	= DictField()

class TmpFile(Document):
	path		= StringField(unique=True)

class OS(Document):
	name		= StringField()
	version		= StringField()
	type		= StringField()
	arch		= StringField()

class Image(Document):
	name		= StringField(required=True)
	os			= ReferenceField("OS", required=True)
	desc		= StringField(required=False)
	tags		= ListField(StringField())
	status		= DictField()
	base_image	= ReferenceField("Image", null=True, required=False)
	username	= StringField(required=True, default="user")
	password	= StringField(required=True, default="password")
	md5			= StringField(required=False, null=True)
	timestamps	= DictField()

class Slave(Document):
	hostname		= StringField()
	uuid			= StringField()
	ip				= StringField()
	max_vms			= IntField(default=1)
	running_vms		= IntField(default=0)
	total_jobs_run	= IntField(default=0)
