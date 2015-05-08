import getpass
import json
import shutil
import tempfile
import time

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser,FormParser,FileUploadParser

from rest_framework_mongoengine.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView

from api.models import Image, OS, TmpFile, Code, Task, Job, Slave
from api.serializers import OSSerializer, ImageSerializer, ImageImportSerializer, CodeSerializer, TaskSerializer, JobSerializer, SlaveSerializer

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

class SlaveList(FilterableListView):
	serializer_class = SlaveSerializer
	model = Slave

class SlaveDetails(RetrieveUpdateDestroyAPIView):
	queryset = Slave.objects.all()
	serializer_class = SlaveSerializer

class TaskList(FilterableListView):
	serializer_class = TaskSerializer
	model = Task

class TaskDetails(RetrieveUpdateDestroyAPIView):
	queryset = Task.objects.all()
	serializer_class = TaskSerializer

class JobList(FilterableListView):
	serializer_class = JobSerializer
	model = Job

class JobDetails(RetrieveUpdateDestroyAPIView):
	queryset = Job.objects.all()
	serializer_class = JobSerializer

class CodeList(FilterableListView):
	serializer_class = CodeSerializer
	model = Code

class CodeDetails(RetrieveUpdateDestroyAPIView):
	queryset = Code.objects.all()
	serializer_class = CodeSerializer

class OSList(FilterableListView):
	serializer_class = OSSerializer
	model = OS

class OSDetails(RetrieveUpdateDestroyAPIView):
	queryset = OS.objects.all()
	serializer_class = OSSerializer

class ImageList(FilterableListView):
	serializer_class = ImageSerializer
	model = Image

class ImageDetails(RetrieveUpdateDestroyAPIView):
	queryset = Image.objects.all()
	serializer_class = ImageSerializer
