#!/bin/bash

cd /web

/usr/sbin/apache2ctl -D FOREGROUND -D NO_DETACH
