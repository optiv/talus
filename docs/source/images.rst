



VM Images
=========

Talus uses Vagrant with the vagrant-libvirt provider to manage and configure VMs.
Once a VM is configured and in the Talus system, libvirt will be directly used to start/stop/shutdown
VMs on slave machines instead of Vagrant. Vagrant is solely a configuration tool.

Vagrant Benefits
----------------

Using Vagrant as the VM configurator allows Talus to easily reconfigure a VM before
running a task. This is beneficial when needing to perform some updates on an image before
running a task (e.g. to ensure that all products work with the latest vendor patches).

VM Configuration
----------------

Linux
^^^^^


Windows
^^^^^^^

Libvirt Requirements
""""""""""""""""""""
The ``virtio`` drivers must be installed.

Vagrant Requirements
""""""""""""""""""""

Talus will use ``WinRM`` (windows remote management).to configure the VM. This must be explicitly
turned on inside the VM before uploading. Below are the steps you should take to configure a windows
VM for working with Vagrant (mostly taken from "here":https://github.com/WinRb/vagrant-windows#winrm-configuration): ::

    winrm quickconfig -q
    winrm set winrm/config/winrs @{MaxMemoryPerShellMB="512"}
    winrm set winrm/config @{MaxTimeoutms="1800000"}
    winrm set winrm/config/service @{AllowUnencrypted="true"}
    winrm set winrm/config/service/auth @{Basic="true"}
    sc config WinRM start= auto

Also note that all created networks in the VM must be set the "Work" network. This can be set to be the
default action by going to: ::

    Open "gpedit.msc" -> Go to Computer Configration –> Windows Settings –> Security Settings –> Network list manager

and setting the appropriate options

The above commands must be run in an Administrator shell. Also, the network must not be set to public (use Work/Private/whatev)

It may also help to attempt to shrink the size of the VM using ``sdelete`` ::

    sdelete -z C:

Some additional tips specifically for VMWare Fusion "here":http://codyburleson.com/2013/01/05/how-to-shrink-a-windows-vm-on-vmware-fusion-for-mac/
