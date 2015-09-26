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

from api.models import Image, OS, TmpFile, Code, Task, Job, Slave, Result, DB, FileSet
from api.serializers import OSSerializer, ImageSerializer, ImageImportSerializer, CodeSerializer, TaskSerializer, JobSerializer, SlaveSerializer, ResultSerializer, FileSetSerializer

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
			filename = str(grid_file._id) + ext

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

class FilterableListView(ListCreateAPIView):
	def get_queryset(self):
		"""
		Return a queryset, filtered by query parameters
		"""
		# the query params are in the form
		#     {
		#    	"name": ["value"]
		#     }
		# so collapse the array value to the first value
		query_params = {}
		for k,v in dict(self.request.QUERY_PARAMS).iteritems():
			# TODO check for lists?
			v = v[0]

			# this is the syntax for embedded documents, ie.
			# status.tmpfile=/tmp/blah -> status__tmpfile="/tmp/blah"
			k = k.replace(".", "__")

			query_params[k] = v

		return self.model.objects(**query_params)

class ResultList(FilterableListView):
	renderer_classes = (TalusRenderer,)
	serializer_class = ResultSerializer
	model = Result

class ResultDetails(RetrieveUpdateDestroyAPIView):
	renderer_classes = (TalusRenderer,)
	queryset = Result.objects.all()
	serializer_class = ResultSerializer

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
