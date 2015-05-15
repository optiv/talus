import datetime
from mongoengine import *
import pymongo

import talus_web.settings

if not talus_web.settings.NO_CONNECT:
	connect("talus", host="talus_db", port=27017, read_preference=pymongo.ReadPreference.NEAREST, slaveOk=True)

class Result(Document):
	job			= ReferenceField("Job", required=True)
	type		= StringField(required=True)
	tool		= StringField(required=True)
	data		= DictField()
	created		= DateTimeField(default=datetime.datetime.now)

class Code(Document):
	name		= StringField(unique_with="type")
	type		= StringField()
	params		= ListField()
	bases		= ListField()
	desc		= StringField()
	timestamps	= DictField()

class Task(Document):
	name		= StringField(unique_with="tool")
	tool		= ReferenceField("Code", required=True)
	params		= DictField()
	version		= StringField() # intended to be used for git versioning
	timestamps	= DictField()
	limit		= IntField(default=1)

class Job(Document):
	name		= StringField()
	task		= ReferenceField("Task", required=True)
	params		= DictField()
	status		= DictField()
	timestamps	= DictField()
	version		= StringField() # intended to be used for git versioning
	priority	= IntField(default=50) # 0-50
	queue		= StringField()
	limit		= IntField(default=1)
	progress	= IntField(default=0)
	image		= ReferenceField("Image", required=True)
	network		= StringField()

class TmpFile(Document):
	path		= StringField(unique=True)

class OS(Document):
	name		= StringField(unique=True)
	version		= StringField()
	type		= StringField()
	arch		= StringField()

class Image(Document):
	name		= StringField(unique=True)
	os			= ReferenceField('OS')
	desc		= StringField(default="desc")
	tags		= ListField(StringField())
	status		= DictField()
	base_image	= ReferenceField('Image', null=True, required=False)
	username	= StringField(required=True, default="user")
	password	= StringField(required=True, default="password")
	md5			= StringField(required=False, null=True, default=None)
	timestamps	= DictField()

class Slave(Document):
	hostname		= StringField()
	uuid			= StringField()
	ip				= StringField()
	max_vms			= IntField(default=1)
	running_vms		= IntField(default=0)
	total_jobs_run	= IntField(default=0)
	vms				= ListField(DictField())
