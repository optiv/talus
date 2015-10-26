

Workflows/Lifecycles
====================

Almost all methods of interacting with talus occur through the database. The
REST API that is exposed is the front-end to the database that UIs will use
to make changes to talus.

The general methodology goes like this:

#. Make a change to a model in the database through the REST API
#. Master daemon sees the change in the replica set oplog and acts on it
#. Master daemon moves the model from the intermediate state to the final state
    * E.g. A job will go from cancel -> (master daemon sees it) cancelling -> (master daemon finished cancelling) cancelled

Image
-----

Import
^^^^^^

Upload the VM image as temporary file, receive a temporary file id in return (gets saved as a :code:`TmpFile` model):

.. code-block:: python 

    # (from models.py in talus/src/web/app/api/models.py)
    class TmpFile(Document):
       path		= StringField(unique=True)

Create a new image in the database with the status.name set to "import" and status.tmpfile set to the temporary
file id:

.. code-block:: python

    # in talus_client/talus_client/api.py
    class TalusClient(...):
        # ...
        def image_import(self, ...)
            # ...
            image = Image(api_base=self._api_base)
            self._prep_model(image)
            image.name = image_name
            image.os = os.id
            image.desc = desc
            image.tags = tags
            image.status = {"name": "import", "tmpfile": uploaded_file}
            image.username = username
            image.password = password
            image.timestamps = {"created": time.time()}
            image.md5 = "blahblah"

            image.save()

At this point the master daemon will catch the new image insertion and see the status as being import.
The master daemon will then handle the import:

.. code-block:: python

    # in talus/src/master/watchers/vm.py
	def _handle_status(self, id_, obj=None, image=None):
		switch = {
			"import":		self._handle_import,
			"configure":	self._handle_configure,
			"create":		self._handle_create,
			"delete":		self._handle_delete
		}

		if image is None:
			images = master.models.Image.objects(id=id_)
			if len(images) == 0:
				return
			image = images[0]

		if image.status["name"] in switch:
			switch[image.status["name"]](id_, image)

	def _handle_import(self, id_, image):
        # ...
		vnc_info = self._vm_manager.import_image(
			image_path,
			str(image.id), # image name
			user_interaction	= True,
			username			= image.username,
			password			= image.password,
			on_success			= self._set_image_ready
		)

At this point the VMManager will start Vagrant_ and will import the image. Once the
vm has been shutdown (restarts are fine), the image will be saved and its status
will be cleared to :code:`{"name": "ready"}`.

The VMManager is found at :code:`talus/src/master/lib/vm/manage.py`

Code
----

CLI Code Create
^^^^^^^^^^^^^^^

Creating code through the CLI flows like this:

#. The talus_client creates a new code model

.. code-block:: python

    # in talus_client/talus_client/api.py
    class TalusClient(...)
        # ...
        def code_create(self, code_name, code_type, tags=None):
            """Create the code, and return the results"""
            data = {
                "name": code_name,
                "type": code_type,
            }

            if self._user is not None:
                if tags is None:
                    tags = []
                if self._user not in tags:
                    tags.append(self._user)

            if tags is not None:
                data["tags"] = json.dumps(tags)

            e = MultipartEncoder(fields=data)

            try:
                res = requests.post(self._api_base + "/api/code/create/",
                    data    = e,
                    headers = {"Content-Type": e.content_type}
                )
            except requests.ConnectionError as e:
                raise errors.TalusApiError("Could not connect to {}".format(self._api_base + "/api/code/create"))
            if res.status_code // 100 != 2:
                raise errors.TalusApiError("Could not create code!", error=res.text)

            return json.loads(res.text)

The master daemon sees the insert into the database, and creates a new tool/component folder
based on the template tool/component:

.. code-block:: python


    # in talus/src/master/watchers/code.py
	def _handle_new_code(self, id_, obj=None, code=None):
		if code is None:
			code = master.models.Code.objects(id=id_)[0]

		if not code.type.startswith("new_"):
			return

		code.type = code.type.replace("new_", "")

		self._log.info("creating new code from template ({}, {})".format(code.name, code.type))

		# TODO this should be in some central setting somewhere,
		# e.g. master.settings.TALUS_GIT or something
		tmpdir = tempfile.mkdtemp()
		git.clone(TALUS_GIT, tmpdir)
		self._log.info("cloned code into {}".format(tmpdir))
        # ...

After the master daemon has done its thing, everything should be good-to-go and the user
can :code:`git pull` and see the changes in the git repository.

Git Repo
^^^^^^^^

The git repo has two hooks: a :code:`pre-receive` hook and a :code:`post-receive` hook.

Pre-Receive
~~~~~~~~~~~

The pre-receive hook uses the python docutils module to parse the python code into an AST
without having to import the code. Syntax errors will still be caught, but the code will
not actually run.

The pre-receive hook is responsible for validating and saving to the database parameter information defined in a tools run function,
as well as the parameters in a component's init function.

.. code-block:: python

    # in talus/src/master/git_repo/hooks/pre-receive
    # ...
    class ChangeHandler(...):
        # ...
        def handle(self):
            changes = self.get_changes()

            switch = {
                "A": self.handle_fileadd,
                "M": self.handle_filemod,
                "D": self.handle_filedel
            }
            success = True
            for filename,op in changes.iteritems():
                # we only care about tools in the talus/{components,tools} directories,
                # and the __init__.py two levels deep:
                #
                # The main Tool and Component definitions are only going
                # to be defined in the __init__.py file of the module,
                # e.g.
                # 
                #	tools/
                #		browser_fuzzer/
                #			__init__.py <--- contains the BrowserFuzzer class
                #			... supporting files ...
                #
                match = re.match(r'^talus/(tools|components)/(\w+)/__init__.py', filename)
                if match is None:
                    continue

                if op in switch:
                    res = switch[op](filename, match.group(2))
                    if not res:
                        success = False
                else:
                    self._log.warn("unknown operation type {} for file {}".format(op, filename))

            self.update_code_defs()
            
            return success
    # ...
    if __name__ == "__main__":
        try:
            errored = False
            for line in sys.stdin.readlines():
                oldrev, newrev, revname = line.split()
                handler = ChangeHandler(oldrev, newrev, revname)
                if not handler.handle():
                    errored = True
                    continue
        except TalusError as e:
            errored = True
            add_error_message("\n" + e.message)

        if errored:
            do_error("\n\n".join(ERROR_MESSAGES))

Post-Receive
~~~~~~~~~~~~

The post-receive git hook is responsible for updating the talus code cache. The code
cache is talus' way of providing a means to do partial checkouts of a git repository.
(Unlike with svn, I have not found this to be possible).

The post-receive hook is found in :code:`talus/src/master/git_repo/hooks/post-receive`

.. code-block:: bash
    #!/bin/bash

    while read oldrev newrev ref
    do
        if [[ $ref =~ .*/master$ ]];
        then
            echo "master ref received. updating talus code cache"
            code_cache="/talus/talus_code_cache/code"
            if [ ! -d "$code_cache" ]; then
                echo "code hasn't been checked out yet, performing initial git clone"
                git clone /talus/talus_code.git "$code_cache"
            fi

            GIT="git --git-dir $code_cache/.git --work-tree $code_cache"
            changed_requirements=$($GIT pull --all | grep requirements.txt | awk '{print $1}')

            cmd="pip2pi $code_cache/talus/pypi"
            for req in $changed_requirements; do
                if [ $(basename "$req") = "requirements.txt" ] && [ -f "$code_cache/$req" ] ; then
                    echo requirements changed in $req
                    pip2pi "$code_cache/talus/pypi" -r "$code_cache/$req"
                fi
            done
        fi
    done

If permission issues arise with the talus_code_cache, check for inconsistent permissions
in :code:`/talus/talus_code_cache` on the talus master server, as that is the locally-cloned
talus repository that git-pull is performed on whenever a changeset is received.

Code Cache
~~~~~~~~~~

The code cache has two parts - the post-receive hook mentioned above, and the django
web app that actually fetches information from the cloned git repo on the master. The
django web-app accepts requests of the form:

.. code-block:: bash

    http://master.talus/code_cache/<REF>/path/to/resource

This resource is protected via basic authentication, with the username and password being:

.. code-block:: bash

    user="talus_job"
    password="Monkeys eat bananas and poop all day."

Sorry about the password - I think I had recently gone to the zoo, and I never felt like changing
it once it was in place. The hashed password itself is stored in :code:`talus/src/web/app/passwords`
if you really want to change it.

Sample output from the code cache looks like:

.. code-block:: javascript

    // for request on the directory http://master.talus/code_cache/HEAD/talus/
    {
        "items": [
            ".gitignore",
            "__init__.py",
            "components/",
            "fileset.py",
            "job.py",
            "lib/",
            "requirements.txt",
            "tools/"
         ],
         "type": "listing",
         "filename": "talus/"
    }

Task
----

Job
---

Creation
~~~~~~~~

Run Process
~~~~~~~~~~~

Results
-------

Crashes
-------

Master Daemon
-------------

Mongodb Watchers
~~~~~~~~~~~~~~~~

AMQP
~~~~

Vagrant
~~~~~~~

Slave Daemon
------------

libvirt
~~~~~~~

Image Syncing
~~~~~~~~~~~~~

VM Code Injection
~~~~~~~~~~~~~~~~~

VM Comms
~~~~~~~~

AMQP
~~~~
