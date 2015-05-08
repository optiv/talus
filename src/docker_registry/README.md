# Talus Registry

The registry is more of a management tool. In docker, if you tag your
containers with <domain>:<port>/<name>, you can push the container to
a remote custom registry.

The script `bin/start.sh` will run a local registry. The goal of
this is to help with docker deployment/management/devops/etc.
