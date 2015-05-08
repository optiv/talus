#!/usr/bin/env python
# encoding: utf-8

import datetime
from mongoengine import *
import os

# this is to be set by whatever starts the master docker container
talus_env = os.environ["TALUS_DB_PORT_27017_TCP"].replace("tcp://", "")
talus_host,talus_port = talus_env.split(":")
talus_port = int(talus_port)

connect("talus", host=talus_host, port=talus_port)

class Task(Document):
	name		= StringField(unique_with="tool")
	tool		= ReferenceField("Code", required=True)
	params		= DictField()
	version		= StringField() # intended to be used for git versioning
	status		= DictField()
	limit		= IntField(default=1)
	timestamps	= DictField()

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
