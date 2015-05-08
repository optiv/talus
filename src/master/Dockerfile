# sudo docker build -t talus-master . 
#
# see below for reference
# https://github.com/ianblenke/docker-kvm

FROM ubuntu:14.04

RUN apt-get -y update
RUN DEBIAN_FRONTEND=noninteractive apt-get -y install kvm qemu-kvm libvirt-bin bridge-utils libguestfs-tools aria2 unzip dos2unix unrar-free wget git

VOLUME /etc/libvirt
VOLUME /var/lib/libvirt

RUN apt-get install -y libxslt-dev libxml2-dev libvirt-dev libffi-dev make g++
RUN apt-get install -y ruby-dev python-pip wget python-libvirt

RUN cd /tmp && wget https://dl.bintray.com/mitchellh/vagrant/vagrant_1.7.2_x86_64.deb && dpkg -i vagrant*.deb

RUN vagrant plugin install vagrant-libvirt

RUN pip install xmltodict mongoengine mock pymongo==2.8.0

ADD data /master/data
ADD startup.sh /startup.sh
ADD __init__.py /master/__init__.py
ADD lib /master/lib

CMD []
ENTRYPOINT ["/startup.sh"]
