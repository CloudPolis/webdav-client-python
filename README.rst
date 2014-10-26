Webdavclient
============

|PyPI version|
|Travis master|

Пакет Webdavclient обеспечивает легкую и удобную работу с
WebDAV-серверами (Яндекс.Диск, Dropbox, Google Диск, Box и 4shared). В
данный пакет включены следующие компоненты: webdav API, resource API и
wdc.

Исходный код проекта можно посмотрететь `здесь`_ |Github|

.. _здесь: https://github.com/designerror/webdavclient%20github

.. |Github| image:: https://github.com/favicon.ico

Установка
=========

**Установка**

.. code:: bash

    $ sudo apt-get install libcurl4-openssl-dev python-pycurl python-dev
    $ sudo easy_install webdavclient

**Обновление**

.. code:: bash

    $ sudo pip install -U webdavclient

Webdav API
==========

Webdav API - представляет из себя набор webdav-методов работы с
облачными хранилищами. В этот набор входят следующие методы: check,
free, info, list, mkdir, clean, copy, move, download, upload, publish и
unpublish.

+---------------+--------+--------+--------+---------+---------+--------+--------+------------+----------+
| Сервисы       | free   | info   | list   | mkdir   | clean   | copy   | move   | download   | upload   |
+===============+========+========+========+=========+=========+========+========+============+==========+
| Яндекс.Диск   | \+     | \+     | \+     | \+      | \+      | \+     | \+     | \+         | \+       |
+---------------+--------+--------+--------+---------+---------+--------+--------+------------+----------+
| Dropbox       | \-     | \+     | \+     | \+      | \+      | \+     | \+     | \+         | \+       |
+---------------+--------+--------+--------+---------+---------+--------+--------+------------+----------+
| Google Диск   | \-     | \+     | \+     | \+      | \+      | \-     | \-     | \+         | \+       |
+---------------+--------+--------+--------+---------+---------+--------+--------+------------+----------+
| Box           | \+     | \+     | \+     | \+      | \+      | \-     | \-     | \+         | \+       |
+---------------+--------+--------+--------+---------+---------+--------+--------+------------+----------+
| 4shared       | \-     | \+     | \+     | \+      | \-      | \-     | \+     | \+         | \+       |
+---------------+--------+--------+--------+---------+---------+--------+--------+------------+----------+

Методы publish и unpublish поддерживает только Яндекс.Диск.

**Настройка клиента**

Обязательными ключами для настройки соединения клиента с WevDAV-сервером
являются webdav\_hostname, webdav\_login и webdav\_password.

.. code:: python

    import webdav.client as wc
    options = {
        'webdav_hostname': "https://webdav.server.ru",
        'webdav_login': "login",
        'webdav_paassword': "password"
    }
    client = wc.Client(options)

При наличие прокси-сервера необходимо указать настройки для подключения
через него.

.. code:: python

    import webdav.client as wc
    options = {
        'webdav_hostname': "https://webdav.server.ru",
        'webdav_login': "w_login",
        'webdav_paassword': "w_password",
        'proxy_hostname': "http://127.0.0.1:8080",
        'proxy_login': "p_login",
        'proxy_password': "p_password"
    }
    client = wc.Client(options)

При необходимости использования сертификата, путь к сертификату и
приватному ключу задается следующим образом:

.. code:: python

    import webdav.client as wc
    options = {
        'webdav_hostname': "https://webdav.server.ru",
        'webdav_login': "w_login",
        'webdav_paassword': "w_password",
        'cert_path': "/etc/ssl/certs/certificate.crt",
        'key_path': "/etc/ssl/private/certificate.key"
    }
    client = wc.Client(options)

**Синхронные методы**

Проверка существования ресурса

.. code:: python

    client.check("dir1/file1")
    client.check("dir1/")

Получение информации о ресурсе

.. code:: python

    client.info("dir1/file1")
    client.info("dir1/")

Проверка свободного места

.. code:: python

    free_size = client.free()

Получение списка ресурсов

.. code:: python

    files1 = client.list()
    files2 = client.list("dir1")

Создание директории

.. code:: python

    client.mkdir("dir1/dir2")

Удаление ресурса

.. code:: python

    client.clean("dir1/dir2/")

Копирование ресурса

.. code:: python

    client.copy(remote_path_from="dir1/file1", remote_path_to="dir2/file1")

Перемещения ресурса

.. code:: python

    client.move(remote_path_from="dir1/file1", remote_path_to="dir2/file1")

Загрузка ресурса

.. code:: python

    client.download_sync(remote_path="dir1/file1", local_path="~/Downloads/file1")
    client.download_sync(remote_path="dir1/dir2/", local_path="~/Downloads/dir2/")

Выгрузка ресурса

.. code:: python

    client.upload_sync(remote_path="dir1/file1", local_path="~/Documents/file1")
    client.upload_sync(remote_path="dir1/dir2/", local_path="~/Documents/dir2/")

Публикация ресурса

.. code:: python

    link = client.publish("dir1/file1")

Отмена публикации ресурса

.. code:: python

    client.unpublish("dir1/file1")

Обработка исключений

.. code:: python

    from webdav.client import WebDavException
    try:
        ...
    except WebDavException as e:
        loggin_except(e)

**Асинхронные методы**

Загрузка ресурса

.. code:: python

    client.download_async(remote_path="dir1/file1", local_path="~/Downloads/file1", callback=callback)
    client.download_async(remote_path="dir1/dir2/", local_path="~/Downloads/dir2/", callback=callback)

Выгрузка ресурса

.. code:: python

    client.upload_async(remote_path="dir1/file1", local_path="~/Documents/file1", callback=callback)
    client.upload_async(remote_path="dir1/dir2/", local_path="~/Documents/dir2/", callback=callback)

Resource API
============

Resource API - используя концепцию ООП, обеспечивает работу с облачными
хранилищами на уровне ресурсов.

Получение ресурса

.. code:: python

    res1 = client.resource("dir1/file1")

Работа с ресурсом

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

wdc - кросплатформенная утилита, обеспечивающая удобную работу с
WebDAV-серверами прямо из Вашей консоли. Помимо полной реализации
методов из webdav API, также добавлены методы синхронизации содержимого
локальной и удаленной директорий.

**Настройка подключения**

.. code:: bash

    $ wdc login https://wedbav.server.ru -p http://127.0.0.1:8080
    webdav_login: w_login
    webdav_password: w_password
    proxy_login: p_login
    proxy_password: p_password

Также имеются дополнительные ключи ``--cert-path[-c]`` и
``--key-path[-k]``.

**Пример работы с утилитой**

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
    $ wdc push dir1/ -f ~/Documents/di1/
    $ wdc info dir1/file1
    {'name': 'file1', 'modified': 'Thu, 23 Oct 2014 16:16:37 GMT',
    'size': '3460064', 'created': '2014-10-23T16:16:37Z'}
    

.. |PyPI version| image:: https://badge.fury.io/py/webdavclient.svg
   :target: http://badge.fury.io/py/webdavclient
   
.. |Travis master| image:: https://travis-ci.org/designerror/webdavclient.svg?branch=master
    :target: https://travis-ci.org/designerror/webdavclient

.. |Tip4commit| image:: https://tip4commit.com/projects/1044.svg   
    :target: https://tip4commit.com/github/designerror/webdavclient
