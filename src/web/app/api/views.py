import getpass
import json
from bson import json_util, ObjectId
from django.http import HttpResponse
import magic # python-magic
import mimetypes
import os
import pwd
import re
from sh import git as GIT
import shutil
import tempfile
import time

code_path = "/code_cache/code"
git = GIT.bake("--git-dir", os.path.join(code_path, ".git"), "--work-tree", code_path, _tty_out=False)

import gridfs

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.renderers import JSONRenderer
from rest_framework.parsers import MultiPartParser,FormParser,FileUploadParser

from rest_framework_mongoengine.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView

from api.models import Image, OS, TmpFile, Code, Task, Job, Master, Slave, Result, DB, FileSet
from api.serializers import OSSerializer, ImageSerializer, ImageImportSerializer, CodeSerializer, TaskSerializer, JobSerializer, MasterSerializer, SlaveSerializer, ResultSerializer, FileSetSerializer

class TalusRenderer(JSONRenderer):
	def render(self, data, accepted_media_type=None, renderer_context=None):
		# this will handle ObjectIds correctly in the data
		return json_util.dumps(data)

class CorpusFiles(APIView):
	parser_classes = (MultiPartParser,FormParser,)

	def post(self, request, content_type=None, filename=None, format=None):
		fs = gridfs.GridFS(DB)

		file_obj = request.FILES["file"]
		if filename is None:
			filename = file_obj.name

		chunk_iters = iter(file_obj.chunks())
		first_chunk = chunk_iters.next()
		if content_type is None:
			content_type = magic.from_buffer(first_chunk, mime=True)

		metadata = {"filename": filename}
		for k,v in request.POST.iteritems():
			metadata[k] = v

		# fs.new_file(filename=filename, content_type=content_type, metadata={...custom attrs...})
		# no filenames, but we'll stash the orig data in the in the metadata
		# (not putting it in the metadata will cause problems when uploading
		# files with the same filename - they'll be considered different versions
		# of the same file
		with fs.new_file(content_type=content_type, metadata=metadata) as f:
			f.write(first_chunk)
			for chunk in chunk_iters:
				f.write(chunk)

		response =  Response(str(f._id))
		return response
	
	def delete(self, request, format=None):
		fs = gridfs.GridFS(DB)

		path = request.path
		id_part = request.path.split("/corpus")[-1]
		if id_part in ["/", ""]:
			response = Response({"error": "Invalid File ID"})
			return response

		if id_part.startswith("/"):
			id_part = id_part[1:]
		file_id = id_part

		if fs.exists(ObjectId(file_id)):
			fs.delete(ObjectId(file_id))
			return Response({"success": "ok"})
		else:
			return Response({"error": "file does not exist"})
	
	def get(self, request, format=None):
		fs = gridfs.GridFS(DB)

		path = request.path
		id_part = request.path.split("/corpus")[-1]
		if id_part == "/" or id_part == "":
			# return a listing of files, using the GET params to filter the results
			search_params = {}
			for k in request.GET.keys():
				v = request.GET.getlist(k)
				if len(v) == 1:
					v = v[0]

				if k == "id":
					k = "_id"

				if k == "_id":
					id_ary = search_params.setdefault("_id", {})["$in"] = []
					if isinstance(v, list):
						for i in v:
							id_ary.append(ObjectId(i))
					else:
						search_params["_id"] = ObjectId(v)

				else:
					search_params[k] = v

			files = DB["fs.files"].find(search_params)
			response = HttpResponse(json_util.dumps(files), content_type="application/json")
			return response
		else:
			if id_part.startswith("/"):
				id_part = id_part[1:]
			file_id = id_part
			try:
				grid_file = fs.get(ObjectId(file_id))
			except:
				response = Response({"error": "Invalid File ID"})
				return response

			if grid_file.content_type == "text/plain":
				ext = ".txt"
			else:
				ext = mimetypes.guess_extension(grid_file.content_type)

			if grid_file.filename is None:
				filename = str(grid_file._id) + ext
			else:
				filename = grid_file.filename

			response = HttpResponse(grid_file.read(), content_type=grid_file.content_type)
			response["Content-Disposition"] = "attachment; filename={}".format(filename)
			return response

class TmpFileUpload(APIView):
	parser_classes = (MultiPartParser,FormParser,)
	
	def post(self, request, filename=None, format=None):
		file_obj = request.FILES["file"]

		new_file_path = tempfile.mktemp(dir="/tmp")
		with open(new_file_path, "wb") as f:
			for chunk in file_obj.chunks():
				f.write(chunk)

		# don't auto-delete the file when it's closed
		file_obj.delete = False

		tmp_file = TmpFile()
		tmp_file.path = new_file_path
		tmp_file.save()

		response =  Response(str(tmp_file.id))
		return response

class CodeCreate(APIView):
	parser_classes = (MultiPartParser,FormParser,)

	def post(self, request, filename=None, format=None):
		if "type" not in request.POST:
			# TODO shouldn't these use better status codes and such?
			return Response({"status": "error", "message": "You must provide the code type (tool/component)"})
		code_type = request.POST["type"]
		if code_type not in ["tool", "component"]:
			# TODO shouldn't these use better status codes and such?
			return Response({"status": "error", "message": "Code type must be one of ['tool', 'component']"})

		if "name" not in request.POST:
			# TODO shouldn't these use better status codes and such?
			return Response({"status": "error", "message": "You must provide a pascal-cased name (e.g. SomeToolThatIMade)"})
		code_name = request.POST["name"]
		if re.match(r'^[a-zA-Z][a-zA-Z0-9]*$', code_name) is None:
			# TODO shouldn't these use better status codes and such?
			return Response({"status": "error", "message": "Invalid name format, must be PascalCase"})

		tags = []
		if "tags" in request.POST:
			tags = json.loads(request.POST["tags"])

		new_code = Code()
		new_code.name = code_name
		new_code.type = "new_" + code_type
		new_code.bases = []
		new_code.tags = tags
		new_code.save()

		return Response({"status": "success", "message": "git pull to see your new tool"})

class FilterableListView(ListCreateAPIView):
	def _to_bool(self, v):
		if v.lower() not in ["true", "false"]:
			raise Exception("not a valid boolean value")
		return v.lower() == "true"
	
	def _to_none(self, v):
		if v.lower() not in ["none", "null"]:
			raise Exception("not a valid null/none value")

		return None
	
	def _handle_query_param(self, k, v, res):
		operator_regex = re.compile(r'(^.*)__(\$[a-z]+)$')
		op_match = operator_regex.match(k)

		target = res
		if op_match is not None:
			term = op_match.group(1)
			op = op_match.group(2)

			if "$" in term:
				target = {}
			else:
				target = res.setdefault(term, {})
			k = op

		if isinstance(v, (list,tuple)):
			if len(v) > 1:
				# not an OR operation, make it an AND operation
				target[k] = {"$all": v}
			else:
				# TODO check for lists?
				v = v[0]
				target[k] = v
		else:
			target[k] = v

		if op_match is not None and "$" in term:
			self._handle_query_param(term, target, res)

	def get_queryset(self):
		"""
		Return a queryset, filtered by query parameters
		"""
		# TODO id fields within __raw__ queries need to be converted to _id and ObjectId
		# if it looks like an ObjectId, make it one? with a special case to change
		# _id to id? Need this to get __raw__={"$or":[{"id":<ID>},{"name":<ID>}]} to work
		sort = [] # .order_by(*sort_fields)
		num = None
		skip = None

		# automatically convert to int,float,bool,null
		casts = [int,float,self._to_bool,self._to_none]

		# the query params are in the form
		#     {
		#    	"name": ["value"]
		#     }
		# so collapse the array value to the first value
		query_params = {}
		for k,v in dict(self.request.QUERY_PARAMS).iteritems():
			# this is the syntax for embedded documents, ie.
			# status.tmpfile=/tmp/blah -> status__tmpfile="/tmp/blah"
			k = k.replace(".", "__")
			#k = k.replace("$", "")
			v_ = []
			for v_part in v:
				for cast in casts:
					try:
						v_part = cast(v_part)
						break
					except:
						pass
				v_.append(v_part)
			v = v_

			if k == "sort":
				sort = v
				continue

			if k == "num":
				num = int(v[0])
				continue

			if k == "skip":
				skip = int(v[0])
				continue

			# this allows the user to use raw mongodb operators:
			#	talus fileset list --files.\$size 10
			#	talus job list --name.\$regex ".*win.*test.*"
			if "$" in k:
				raw = query_params.setdefault("__raw__", {})
				self._handle_query_param(k, v, raw)

			# otherwise the user can use mongoengine operator wrappers (that use
			# double underscores
			#	talus job list --files__size 10
			else:
				if len(v) > 1:
					# not an OR operation, make it an AND operation
					query_params[k] = {"$all": v}
				else:
					# TODO check for lists?
					v = v[0]
					query_params[k] = v

		cursor = self.model.objects(**query_params)

		if len(sort) > 0:
			cursor = cursor.order_by(*sort)

		if num is not None and skip is None:
			cursor = cursor[:num]
		elif skip is not None and num is None:
			cursor = cursor[skip:]
		elif skip is not None and num is not None:
			cursor = cursor[skip:skip+num]

		return cursor

class ResultList(FilterableListView):
	renderer_classes = (TalusRenderer,)
	serializer_class = ResultSerializer
	model = Result

class ResultDetails(RetrieveUpdateDestroyAPIView):
	renderer_classes = (TalusRenderer,)
	queryset = Result.objects.all()
	serializer_class = ResultSerializer

class MasterList(FilterableListView):
	renderer_classes = (TalusRenderer,)
	serializer_class = MasterSerializer
	model = Master

class MasterDetails(RetrieveUpdateDestroyAPIView):
	renderer_classes = (TalusRenderer,)
	queryset = Master.objects.all()
	serializer_class = MasterSerializer

class SlaveList(FilterableListView):
	renderer_classes = (TalusRenderer,)
	serializer_class = SlaveSerializer
	model = Slave

class SlaveDetails(RetrieveUpdateDestroyAPIView):
	renderer_classes = (TalusRenderer,)
	queryset = Slave.objects.all()
	serializer_class = SlaveSerializer

class TaskList(FilterableListView):
	renderer_classes = (TalusRenderer,)
	serializer_class = TaskSerializer
	model = Task

class TaskDetails(RetrieveUpdateDestroyAPIView):
	renderer_classes = (TalusRenderer,)
	queryset = Task.objects.all()
	serializer_class = TaskSerializer

class JobList(FilterableListView):
	renderer_classes = (TalusRenderer,)
	serializer_class = JobSerializer
	model = Job

class JobDetails(RetrieveUpdateDestroyAPIView):
	renderer_classes = (TalusRenderer,)
	queryset = Job.objects.all()
	serializer_class = JobSerializer

class CodeList(FilterableListView):
	renderer_classes = (TalusRenderer,)
	serializer_class = CodeSerializer
	model = Code

	def post(self, request):
		return Response("NO")

class CodeDetails(RetrieveUpdateDestroyAPIView):
	renderer_classes = (TalusRenderer,)
	queryset = Code.objects.all()
	serializer_class = CodeSerializer

class OSList(FilterableListView):
	renderer_classes = (TalusRenderer,)
	serializer_class = OSSerializer
	model = OS

class OSDetails(RetrieveUpdateDestroyAPIView):
	renderer_classes = (TalusRenderer,)
	queryset = OS.objects.all()
	serializer_class = OSSerializer

class ImageList(FilterableListView):
	renderer_classes = (TalusRenderer,)
	serializer_class = ImageSerializer
	model = Image

class ImageDetails(RetrieveUpdateDestroyAPIView):
	renderer_classes = (TalusRenderer,)
	queryset = Image.objects.all()
	serializer_class = ImageSerializer

class FileSetList(FilterableListView):
	renderer_classes = (TalusRenderer,)
	serializer_class = FileSetSerializer
	model = FileSet

class FileSetDetails(RetrieveUpdateDestroyAPIView):
	renderer_classes = (TalusRenderer,)
	queryset = FileSet.objects.all()
	serializer_class = FileSetSerializer
