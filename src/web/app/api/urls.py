#!/usr/bin/env python
# encoding: utf-8

from django.conf.urls import url, include
from rest_framework import routers
from api import views

OBJ_ID = r'[0-9a-fA-F\-]+'

# Wire up our API using automatic URL routing.
# Additionally, we include login URLs for the browsable API.
urlpatterns = [
	# for temporary files
	url(r"^upload/$", views.TmpFileUpload.as_view()),

	url(r'^result/$', views.ResultList.as_view()),
	url(r'^result/(?P<id>' + OBJ_ID + ")/$", views.ResultDetails.as_view()),

	url(r'^slave/$', views.SlaveList.as_view()),
	url(r'^slave/(?P<id>' + OBJ_ID + ")/$", views.SlaveDetails.as_view()),

	url(r'^task/$', views.TaskList.as_view()),
	url(r'^task/(?P<id>' + OBJ_ID + ")/$", views.TaskDetails.as_view()),

	url(r'^job/$', views.JobList.as_view()),
	url(r'^job/(?P<id>' + OBJ_ID + ")/$", views.JobDetails.as_view()),

	url(r'^code/$', views.CodeList.as_view()),
	url(r'^code/(?P<id>' + OBJ_ID + ")/$", views.CodeDetails.as_view()),

	url(r'^os/$', views.OSList.as_view()),
	url(r'^os/(?P<id>' + OBJ_ID + ")/$", views.OSDetails.as_view()),

	url(r'^image/$', views.ImageList.as_view()),
	url(r'^image/(?P<id>' + OBJ_ID + ")/$", views.ImageDetails.as_view()),

	url(r'^api-auth/', include('rest_framework.urls', namespace='rest_framework'))
]
