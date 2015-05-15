#!/usr/bin/env python
# encoding: utf-8

from django.conf.urls import url, include
from code_cache import views

urlpatterns = [
	url(r'^(?P<ref>[a-zA-Z0-9]+)/(?P<path>[a-z\.A-Z_0-9\- /]+)', views.git_info)
]
