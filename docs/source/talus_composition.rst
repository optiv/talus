


Talus Composition
=========================

Generally speaking, talus has two main components:

1. Master
2. Slave(s)

Talus users interact with Talus via ``git`` and the :ref:`talus_client`.

Master
------

The Talus master is responsible for managing the slaves and processing
commands from the user.

The master is made up of three main parts:

1. Web API
2. RabbitMQ AMQP
3. MongoDB
4. Master Daemon

Clients interact with Talus via the Web API, which only makes changes to the
MongoDB database.

The Master Daemon monitors MongoDB for changes (using replica sets and the
oplog) and then acts on the changes. The Master Daemon then submits any jobs/messages
into the appropriate RabbitMQ AMQP queues.

Slave
-----

Slaves are responsible for consuming jobs from the jobs queue, running VMs, and
reporting on progress and results of the jobs.

Slaves interact directly with the Master by querying the database directly, and
sending/receiving messages via AMQP. Slaves report job results and progress back
to the Master via AMQP queues.

VMs run on a slave do not use the AMQP queues or MongoDB directly. Once a VM is
spun up for a job, the slave daemon injects a bootstrap script and a config file
into the VM.

The bootstrap is then run, which dynamically downloads the necessary code
from the git repository (via the ``code_cache`` app on the Master's web service).
