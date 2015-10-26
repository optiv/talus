.. _Vagrant: https://www.vagrantup.com/
.. _Vagrantfile: https://docs.vagrantup.com/v2/vagrantfile/index.html
.. _Docker: https://www.docker.com/
.. _Dockerfile: https://docs.docker.com/reference/builder/

Debugging Talus
===============

There are many components to talus. This will attempt to give some insight into ways you might
go about debugging the individual components of talus.

Master Daemon
-------------

The talus master daemon is an upstart job. The job configuration is found
in :code:`/etc/init/talus_master.conf`:

.. code-block:: bash

    description "Talus Master Daemon"
    author          "Optiv Labs"

    start on filesystem or runlevel [2345]
    stop on shutdown
    respawn

    script
            /home/talus/talus/src/master/bin/start_raw em1
    end script

Logs for the master daemon can be found in :code:`/var/log/upstart/talus_master.log`. These logs
are automatically rotated and are created by upstart.

Restarting
^^^^^^^^^^

To restart the master daemon (say, after having made some code changes, to force it to reconnect
to the AMQP server, etc), run :code:`sudo stop talus_master`. This *should* stop the master
daemon. If after a few seconds the master daemon does not gracefully quit (confirm with :code:`ps aux | grep master`),
force-kill any running master daemons with a good ol' :code:`kill -KILL`.

After the master daemon has been killed, start it again with :code:`sudo start talus_master`.

Slave Daemon
------------

The talus slave daemon that is present on each of the slaves is an upstart job. The job
configuration is found in :code:`/etc/init/talus_slave.conf`:

.. code-block:: bash

    description "Talus Slave Daemon"
    author          "Optiv Labs"

    start on (started networking)
    stop on shutdown
    respawn

    script
            aa-complain /usr/sbin/libvirtd
            /home/talus/talus/src/slave/bin/start_raw 1.1.1.3 10 em1 2>&1 >> /var/log/talus/slave.log
    end script

The aa-complain is to force apparmor to only complain about libvirtd and not
enforce any policies. Libvirt runs extremely slow if apparmor is allowed to enforce policies
on libvirtd. There might be a better way around this, but this works.

Restarting
^^^^^^^^^^

To restart the slave daemon, run :code:`sudo restart talus_slave`. The slave daemon will
gracefully shutdown, killing all running vms before doing so. Sometimes this can take up to a minute
before the slave daemon has completely quit.

If you are paranoid that the slave daemon isn't going restart cleanly, stop and start the daemon
separately, checking in between to make sure that it had completely exited before starting it again.
If it never fully quits, force-kill it with :code:`kill -KILL`.

Vagrant
-------

Vagrant_ is a VM configuration utility (or that's how I think of it). It is intended for developers
to easily share build/development/production environments with other developers by only sharing their
Vagrantfile_. The Vagrantfile_ is a ruby script and can configure a VM from a base image. A lot of the
work that has gone into Vagrant is about being able to configure VMs from a Vagrantfile_.

Talus uses Vagrant during image configuration to provide a way for the user to perform automatic
VM updates (e.g. run a script after every MS update to create a new image with the latest patches, etc).

Vagrant images (or `boxes` in Vagrant lingo) are stored in :code:`/root/.vagrant.d/boxes`. When a box is
started, the image in the boxes directory is uploaded to :code:`/var/lib/libvirt/images` and then is
run.

Since we aren't using VMWare or VirtualBox (but litvirt instead), talus requires the vagrant-libvirt
plugin to be added. During development of talus, several pull requests were submitted to this plugin
to give us the functionality we needed.

Libvirt
-------------

Libvirtd
^^^^^^^^
Talus uses libvirt. Libvirt runs as a daemon (:code:`libvirtd`) and accepts messages via a unix domain
socket.

There have been major problems with using libvirt and networking issues amongst the vms. Talus has
resorted to using static mac address that mapped to static ip addresses that were defined in
the :code:`talus-network` xml, as well as disabling mac filtering with ebtables in :code:`/etc/libvirt/qemu.conf`
by setting :code:`mac_filters=0`.

Another notable configuration setting with libvirt is to set the vnc listen ip to :code:`0.0.0.0` in
:code:`/etc/libvirt/qemu.conf`. Otherwise you won't be able to remotely VNC to any running VMs.

Libvirt is restarted with :code:`/etc/init.d/libvirt-bin restart`.

Logs for libvirtd are found in in :code:`/var/log/libvirt/libvirtd.log`, and logs for individual
domains are found in :code:`/var/log/libvirt/qemu/<domain_name>.log` (iirc).

Virsh
^^^^^

:code:`virsh` is a command-line interface to sending messages to the libvirt daemon.

Common commands include:

* :code:`virsh list --all` - list all of the defined/running domains (vms)
* :code:`virsh destroy <domain_id_or_name>` - forcefully destroy a domain
* :code:`virsh dumpxml <domain_id_or_name>` - dump the xml that defines the domain
    * it may be useful to grep this for :code:`vnc` to see which vnc port it's on
    * it may be useful to grep this for :code:`mac` to see what the mac address is (can correlate macs to ips with :code:`arp -an`)
* :code:`virsh net-list` - list defined networks. Talus uses its own defined network :code:`talus-network`
* :code:`virsh net-dumpxml <network-name>` - dump the xml that defines a network

I commonly found myself doing something like:

.. code-block:: bash

    for id in $(sudo virsh list --all | tail -n+3 | awk '{print $1}') ; do sudo virsh destroy $id ; done

Docker
----

Several talus components are containerized using Docker_. Docker (essentially a wrapper around linux containers)
makes it easy to configure environments for a service. It uses an incremental build process to build containers.

In the talus source tree, the :code:`web`, :code:`amqp`, and :code:`db` directories contain scripts in
their bin directories to build, start, and stop their respective docker containers.

Docker users a Dockerfile_ to define the individual steps needed to build the container. Generally speaking you
either :code:`RUN` a command inside the container, or :code:`ADD` files and directories to the container. A default
entrypoint int the container specifies how the container should be started, unless an overriding :code:`--entrypoint`
parameter is passed with the :code:`docker run` command.

Dockers containers can be linked to other already-running docker containers. For example, the script to run the
:code:`talus_web` container links itself to the :code:`talus_db` container (:code:`--link ...`), exposes several ports so that it
can accept remote connections (:code:`-p ...`), and mounts several volumes inside the container (:code:`-v ...`). The full script can be found in :code:`talus/src/web/bin/start` in the source tree:

.. code-block:: bash

	sudo docker run \
		--rm \
		--link talus_db:talus_db \
		-p 80:80 \
		-p 8001:8001 \
		-v /var/lib/libvirt/images:/images:ro \
		-v /var/log/talus:/logs \
		-v /tmp/talus/tmp:/tmp \
		-v /talus/install:/talus_install \
		-v /talus/talus_code_cache:/code_cache \
		--name talus_web \
		$@ talus_web

MongoDB
-------

There is a specific order that docker containers must be started on the master. Most of the containers/services
rely on the :code:`talus_db` container being up and running. If the master needed to be rebooted and things
start complaining about connections, try shutting them down and restarting them in this order:

#. :code:`start talus_db`
#. :code:`start talus_amqp` - this does not depend on talus_db, so this could be first if you wanted)
#. :code:`start talus_web`
#. :code:`start talus_master`
#. :code:`start talus_slave` - if you also have a slave daemon running on the master server

Mongodb logs are stored in :code:`/var/log/talus/mongodb/*`.

Mongodb data is stored in :code:`/talus/data/*`.

Since the db is running in a container, you can't drop into a mongo shell on the master
and attempt to connect to localhost (and actually, no mongo tools are required to be installed
on the master, so you might not be able to that out of the box anyways). You could either lookup the connection
info of the :code:`talus_db` container (which port it's forwarded to locally), or you can start a
temporary container that has all of the necessary mongodb tools that will drop you into a mongo
shell. I highly recommend the second approach.

Such a script exists in the source tree at :code:`talus/src/db/bin/shell`. Run this script, and you
should be dropped into a mongo shell. You will have to tell it which database to use (the :code:`talus`
database), after which you can perform raw mongodb commands:

.. code-block:: bash

    talus@:~$ talus/src/db/bin/shell
    MongoDB shell version: 3.0.6
    connecting to: talus_db:27017/test
    Welcome to the MongoDB shell.
    For interactive help, type "help".
    For more comprehensive documentation, see
            http://docs.mongodb.org/
    Questions? Try the support group
            http://groups.google.com/group/mongodb-user
    Server has startup warnings:
    2015-10-28T22:32:32.001+0000 I CONTROL  [initandlisten] ** WARNING: You are running this process as the root user, which is not recommended.
    2015-10-28T22:32:32.001+0000 I CONTROL  [initandlisten]
    2015-10-28T22:32:32.001+0000 I CONTROL  [initandlisten]
    2015-10-28T22:32:32.002+0000 I CONTROL  [initandlisten] ** WARNING: You are running on a NUMA machine.
    2015-10-28T22:32:32.002+0000 I CONTROL  [initandlisten] **          We suggest launching mongod like this to avoid performance problems:
    2015-10-28T22:32:32.002+0000 I CONTROL  [initandlisten] **              numactl --interleave=all mongod [other options]
    2015-10-28T22:32:32.002+0000 I CONTROL  [initandlisten]
    2015-10-28T22:32:32.002+0000 I CONTROL  [initandlisten] ** WARNING: /sys/kernel/mm/transparent_hugepage/enabled is 'always'.
    2015-10-28T22:32:32.002+0000 I CONTROL  [initandlisten] **        We suggest setting it to 'never'
    2015-10-28T22:32:32.002+0000 I CONTROL  [initandlisten]
    2015-10-28T22:32:32.002+0000 I CONTROL  [initandlisten] ** WARNING: /sys/kernel/mm/transparent_hugepage/defrag is 'always'.
    2015-10-28T22:32:32.002+0000 I CONTROL  [initandlisten] **        We suggest setting it to 'never'
    2015-10-28T22:32:32.002+0000 I CONTROL  [initandlisten]
    rs0:PRIMARY> use talus
    switched to db talus
    rs0:PRIMARY> show collections
    code
    file_set
    fs.chunks
    fs.files
    image
    job
    master
    o_s
    result
    slave
    system.indexes
    task
    tmp_file
    rs0:PRIMARY> db.image.find()

Notice how the prompt says :code:`rs0:PRIMARY`. This is HUGELY important. Talus uses a single-host replica set with mongodb 
to be able to essentially have a cursor that will :code:`tail -f` all of the changes that occur in the database. This works
because, as a replica set, the intention is that database changes will have to be communicated to other databases on
different hosts (I believe shard is the term mongodb uses). A special collection called an :code:`oplog` is where all
of these changes are stored.

Talus uses the oplog to be notified of changes in the database so it won't have to poll the database for changes.

Back to the prompt and the :code:`rs0:PRIMARY`. If the prompt *DOES NOT* say PRIMARY after :code:`rs0` (replicat-set 0),
then you'll have to run a few commands in a mongo shell.

In the :code:`talus/src/db/startup.sh` script, a command is run that attempts to ensure that the current replica set
on talus (the only one), is also the PRIMARY replica set. Not being the primary replica set (called a slave) means that
you cannot make changes to the data (iirc). The code the startup.sh script runs in a mongo shell is below:

.. code-block:: javascript

    cfg={"_id" :"rs0", "version": 1, "members": [{"_id": 0, "host": "talus_db:27017"}]}
    rs.initiate(cfg)
    rs.reconfig(cfg, {force:true})
    rs.slaveOk()

If you notice that the shell is not PRIMARY, you would usually only have to run
the :code:`rs.slaveOk()` command from a mongo shell to get things back to
normal. You might need the other commands if the previously mentioned command
fails to work.

AMQP
----

AMQP is also containerized with docker and is run as an upstart job. The upstart config for the :code:`talus_amqp`
upstart job is found at :code:`/etc/init/talus_amqp.conf`.

Logs for amqp should be found at :code:`/var/log/talus/rabbitmq/*`.

This should rarely have to be debugged. Since it is debugged so rarely, debugging-specific scripts were never added.

However, if AMQP was suspected of being a problem, here's a few things I'd check
out:

* restart amqp with :code:`sudo restart talus_amqp`
* look in the logs at :code:`/var/log/talus/rabbitmq/*`
* setup the `RabbitMQ management console <https://www.rabbitmq.com/management.html>`_ and expose ports in the :code:`talus_amqp`
    container so that you can access the management console remotely.
* stop the :code:`talus_amqp` container and run it the container manually with
    the entrypoint set to bash so that you can do additional debugging:
    * :code:`talus/src/amqp/bin/start --entrypoint bash`

Webserver
----

Debugging the webserver should be fairly simple. The webserver is containerized
using docker and is run as an upstart job. The upstart script is found in
:code:`/etc/init/talus_web.conf`.

Logs for the talus web services are found in
:code:`/var/log/talus/apache2/*.log`.

The dynamic portion of the web application is made with django. Debugging django
application is fairly straightforward, especially if you use pdb.

The start script (:code:`talus/src/web/bin/start`) has some logic to check for a
dev parameter. If present, it will mount the directories local to the start script
inside the container so that you won't have to rebuild the container every time
you need to make some code changes.

My usual workflow goes like this:

#. Make sure :code:`talus_db` is running
#. Scp/rsync my code into the remote :code:`talus/src/web` directory
#. Start a dev talus_web container with bash as the new entrypoint:

.. code-block:: bash

    talus:~$ talus/src/web/bin/start dev --entrypoint bash
    Error response from daemon: Cannot kill container talus_web_dev: no such id: talus_web_dev
    Error: failed to kill containers: [talus_web_dev]
    Error response from daemon: no such id: talus_web_dev
    Error: failed to remove containers: [talus_web_dev]
    root@54f7352ff90b:/# cd web
    root@54f7352ff90b:/web# ls
    README  api  code_cache  launch.sh  manage.py  passwords  requirements  talus_web
    root@54f7352ff90b:/web# python manage.py runserver 0.0.0.0:8080
    DEBUG IS TRUE
    DEBUG IS TRUE
    Performing system checks...

    System check identified no issues (0 silenced).
    October 30, 2015 - 21:20:21
    Django version 1.8.1, using settings 'talus_web.settings'
    Starting development server at http://0.0.0.0:8080/
    Quit the server with CONTROL-C.

At this point you will be able to break and step through the handling of any requests
(if you have added a :code:`import pdb ; pdb.set_trace()` somewhere). Remember that
port :code:`8080` is exposed by default for the dev web container, so be sure to
run manage.py with port 8080 on ip 0.0.0.0.
