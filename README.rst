Webdavclient
============

|PyPI version| |Build Status| |Requirements Status|

The packet of Webdavclient ensures easy and convenient functioning with WebDAV-servers (Yandex. Disk, Dropbox, Google Disk, Box and 4shared). The following components are included in this packet: webdav API, resource API and wdc.

For operation with cloudy hranilashcha of Dropbox and Google the Disk according to the protocol
WebDAV need to use WebDAV-server DropDAV and DAV-pocket respectively.

It is possible to look at the source code of the project 
`here <https://github.com/designerror/webdavclient>`__ |Github|

Installation and updating
=========================

**Installation**

.. code:: bash

    $ sudo apt-get install libxml2-dev libxslt-dev python-dev
    $ sudo apt-get install libcurl4-openssl-dev python-pycurl 
    $ sudo easy_install webdavclient

**Updating**

.. code:: bash

    $ sudo pip install -U webdavclient

Webdav API
==========

Webdav API - is a set of webdav-methods of operation with
cloudy storages. The following methods enter this set: check,
free, info, list, mkdir, clean, copy, move, download, upload, publish and
unpublish.

+---------------+--------+--------+--------+---------+---------+--------+--------+------------+----------+
| Servers       | free   | info   | list   | mkdir   | clean   | copy   | move   | download   | upload   |
+===============+========+========+========+=========+=========+========+========+============+==========+
| Yandex.Disk   | \+     | \+     | \+     | \+      | \+      | \+     | \+     | \+         | \+       |
+---------------+--------+--------+--------+---------+---------+--------+--------+------------+----------+
| Dropbox       | \-     | \+     | \+     | \+      | \+      | \+     | \+     | \+         | \+       |
+---------------+--------+--------+--------+---------+---------+--------+--------+------------+----------+
| Google Disk   | \-     | \+     | \+     | \+      | \+      | \-     | \-     | \+         | \+       |
+---------------+--------+--------+--------+---------+---------+--------+--------+------------+----------+
| Box           | \+     | \+     | \+     | \+      | \+      | \-     | \-     | \+         | \+       |
+---------------+--------+--------+--------+---------+---------+--------+--------+------------+----------+
| 4shared       | \-     | \+     | \+     | \+      | \-      | \-     | \+     | \+         | \+       |
+---------------+--------+--------+--------+---------+---------+--------+--------+------------+----------+

The publish and unpublish methods are supported only by Yandex.Disk.

**Setup of the client**

Mandatory keys for setup of client connection with the WevDAV-server
are webdav\_hostname, webdav\_login, webdav\_password.

.. code:: python

    import webdav.client as wc
    options = {
        'webdav_hostname': "https://webdav.server.ru",
        'webdav_login': "login",
        'webdav_password': "password"
    }
    client = wc.Client(options)

In case of existence of a proxy server it is necessary to specify settings for connection through it.

.. code:: python

    import webdav.client as wc
    options = {
        'webdav_hostname': "https://webdav.server.ru",
        'webdav_login': "w_login",
        'webdav_password': "w_password",
        'proxy_hostname': "http://127.0.0.1:8080",
        'proxy_login': "p_login",
        'proxy_password': "p_password"
    }
    client = wc.Client(options)

In need of use of the certificate, way to the certificate and
to private key it is set as follows:

.. code:: python

    import webdav.client as wc
    options = {
        'webdav_hostname': "https://webdav.server.ru",
        'webdav_login': "w_login",
        'webdav_password': "w_password",
        'cert_path': "/etc/ssl/certs/certificate.crt",
        'key_path': "/etc/ssl/private/certificate.key"
    }
    client = wc.Client(options)

**Synchronous methods**

Check

.. code:: python

    client.check("dir1/file1")
    client.check("dir1")

Info

.. code:: python

    client.info("dir1/file1")
    client.info("dir1/")

Free

.. code:: python

    free_size = client.free()

List

.. code:: python

    files1 = client.list()
    files2 = client.list("dir1")

Mkdir

.. code:: python

    client.mkdir("dir1/dir2")

Clean

.. code:: python

    client.clean("dir1/dir2")

Copy

.. code:: python

    client.copy(remote_path_from="dir1/file1", remote_path_to="dir2/file1")
    client.copy(remote_path_from="dir2", remote_path_to="dir3")

Move

.. code:: python

    client.move(remote_path_from="dir1/file1", remote_path_to="dir2/file1")
    client.move(remote_path_from="dir2", remote_path_to="dir3")

Download

.. code:: python

    client.download_sync(remote_path="dir1/file1", local_path="~/Downloads/file1")
    client.download_sync(remote_path="dir1/dir2/", local_path="~/Downloads/dir2/")

Upload

.. code:: python

    client.upload_sync(remote_path="dir1/file1", local_path="~/Documents/file1")
    client.upload_sync(remote_path="dir1/dir2/", local_path="~/Documents/dir2/")

Publish

.. code:: python

    link = client.publish("dir1/file1")
    link = client.publish("dir2")

Unpublish

.. code:: python

    client.unpublish("dir1/file1")
    client.unpublish("dir2")

Exception

.. code:: python

    from webdav.client import WebDavException
    try:
        ...
    except WebDavException as exception:
        ...

Pull

.. code:: python

    client.pull(remote_directory='dir1', local_directory='~/Documents/dir1')

Push

.. code:: python

    client.push(remote_directory='dir1', local_directory='~/Documents/dir1')

**Asynchronous methods**

Download

.. code:: python

    client.download_async(remote_path="dir1/file1", local_path="~/Downloads/file1", callback=callback)
    client.download_async(remote_path="dir1/dir2/", local_path="~/Downloads/dir2/", callback=callback)

Upload

.. code:: python

    client.upload_async(remote_path="dir1/file1", local_path="~/Documents/file1", callback=callback)
    client.upload_async(remote_path="dir1/dir2/", local_path="~/Documents/dir2/", callback=callback)

Resource API
============

Resource API - using the concept of OOP, ensures functioning with the cloudy
storages at the level of resources.

Get resource

.. code:: python

    res1 = client.resource("dir1/file1")

Examples

.. code:: python

    res1.rename("file2")

    res1.move("dir1/file2")

    res1.copy("dir2/file1")

    info = res1.info()

    res1.read_from(buffer)

    res1.read(local_path="~/Documents/file1")

    res1.read_async(local_path="~/Documents/file1", callback)

    res1.write_to(buffer)

    res1.write(local_path="~/Downloads/file1")

    res1.write_async(local_path="~/Downloads/file1", callback)

wdc
===

wdc - the cross-platform utility ensuring convenient functioning with
WebDAV-servers directly from your console. In addition to full implementation
methods from webdav API, methods of synchronization of contents are also added
local and remote directories.

**Setup of the client**

The list of settings for WebDAV - servers:

.. code:: yml

    webdav-servers:
      - yandex:
        hostname: https://webdav.yandex.ru
        login:    #login_for_yandex
        password: #pass_for_yandex
      - dropbox:
        hostname: https://dav.dropdav.com
        login:    #login_for dropdav
        password: #pass_for_dropdav
      - google
        hostname: https://dav-pocket.appspot.com/docs/
        login:    #login_for_dav-pocket
        password: #pass_for_dav-pocket
      - box:
        hostname: https://dav.box.com/dav
        login:    #login_for_box
        password: #pass_for_box
      - 4shared:
        hostname: https://webdav.4shared.com
        login:    #login_for_4shared
        password: #pass_for_4shared

Authentication

.. code:: bash

    $ wdc login https://wedbav.server.ru -p http://127.0.0.1:8080
    webdav_login: w_login
    webdav_password: w_password
    proxy_login: p_login
    proxy_password: p_password

Also there are additional keys ``--cert-path[-c]`` and
``--key-path[-k]``.

**Examples**

.. code:: bash

    $ wdc check
    success
    $ wdc check file1
    not success
    $ wdc free
    245234120344
    $ wdc ls dir1
    file1
    ...
    fileN
    $ wdc mkdir dir2
    $ wdc copy dir1/file1 -t dir2/file1
    $ wdc move dir2/file1 -t dir2/file2
    $ wdc download dir1/file1 -t ~/Downloads/file1
    $ wdc download dir1/ -t ~/Downloads/dir1/
    $ wdc upload dir2/file2 -f ~/Documents/file1
    $ wdc upload dir2/ -f ~/Documents/
    $ wdc publish di2/file2
    https://yadi.sk/i/vWtTUcBucAc6k
    $ wdc unpublish dir2/file2
    $ wdc pull dir1/ -t ~/Documents/dir1/
    $ wdc push dir1/ -f ~/Documents/dir1/
    $ wdc info dir1/file1
    {'name': 'file1', 'modified': 'Thu, 23 Oct 2014 16:16:37 GMT',
    'size': '3460064', 'created': '2014-10-23T16:16:37Z'}

.. |PyPI version| image:: https://badge.fury.io/py/webdavclient.svg
   :target: http://badge.fury.io/py/webdavclient
.. |Build Status| image:: https://travis-ci.org/designerror/webdavclient.svg?branch=master
   :target: https://travis-ci.org/designerror/webdavclient
.. |Requirements Status| image:: https://requires.io/github/designerror/webdavclient/requirements.svg?branch=master
     :target: https://requires.io/github/designerror/webdavclient/requirements/?branch=master
     :alt: Requirements Status
.. |Github| image:: https://github.com/favicon.ico
