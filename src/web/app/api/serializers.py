from api.models import Image,OS,Code,Task,Job,Master,Slave,Result,JobError,FileSet
from rest_framework_mongoengine.serializers import DocumentSerializer, EmbeddedDocumentSerializer

class ResultSerializer(DocumentSerializer):
	class Meta:
		model = Result
		depth = 2

class TaskSerializer(DocumentSerializer):
	class Meta:
		model = Task
		depth = 2

class JobError(EmbeddedDocumentSerializer):
	class Meta:
		model = JobError
		depth = 2

class JobSerializer(DocumentSerializer):
	class Meta:
		model = Job
		depth = 2

class CodeSerializer(DocumentSerializer):
	class Meta:
		model = Code
		depth = 2

class OSSerializer(DocumentSerializer):
	class Meta:
		model = OS
		depth = 2

class ImageSerializer(DocumentSerializer):
	class Meta:
		model = Image
		depth = 2

class MasterSerializer(DocumentSerializer):
	class Meta:
		model = Master
		depth = 2

class SlaveSerializer(DocumentSerializer):
	class Meta:
		model = Slave
		depth = 2

class ImageImportSerializer(DocumentSerializer):
	class Meta:
		model = Image
		depth = 2

class FileSetSerializer(DocumentSerializer):
	class Meta:
		model = FileSet
		depth = 2
