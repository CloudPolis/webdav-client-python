# -*- coding: utf-8

import argparse
import pycurl
import getpass
import re
import os
import threading
import xml.etree.ElementTree as ET

from io import BytesIO
from urllib.parse import unquote, quote

class Urn:
    separate = "/"

    def __init__(self, str, directory=False):
        self._path = quote(str)
        expressions = "/\.+/", "/+"
        for expression in expressions:
            self._path = re.sub(expression, Urn.separate, self._path)

        if not self._path.startswith(Urn.separate):
            self._path = "{begin}{end}".format(begin=Urn.separate, end=self._path)

        if directory and not self._path.endswith(Urn.separate):
            self._path = "{begin}{end}".format(begin=self._path, end=Urn.separate)

    def path(self):
        return unquote(self._path)

    def quote(self):
        return self._path

    def filename(self):
        path_split = self._path.split(Urn.separate)
        name = path_split[-2] + Urn.separate if path_split[-1] == '' else path_split[-1]
        return unquote(name)

    def parent(self):
        path_split = self._path.split(Urn.separate)
        nesting_level = self.nesting_level()
        parent_path_split = path_split[:nesting_level]
        parent = self.separate.join(parent_path_split) if nesting_level != 1 else Urn.separate
        return unquote(parent + Urn.separate)

    def nesting_level(self):
        return self._path.count(Urn.separate, 0, -1)

    def is_directory(self):
        return self._path[:-1] == Urn.separate

class WebDavException(Exception):
    pass

class NotFound(WebDavException):
    pass

class LocalResourceNotFound(NotFound):
    def __init__(self, path):
        self.path = path

    def __str__(self):
        return "Local file: {path} not found".format(path=self.path)

class RemoteResourceNotFound(NotFound):
    def __init__(self, path):
        self.path = path

    def __str__(self):
        return "Remote resource: {path} not found".format(path=self.path)

class RemoteParentNotFound(NotFound):
    def __init__(self, path):
        self.path = path

    def __str__(self):
        return "Remote parent for: {path} not found".format(path=self.path)

class InvalidOption(WebDavException):
    def __init__(self, name, value):
        self.name = name
        self.value = value

    def __str__(self):
        return "Option ({name}:{value}) have invalid name or value".format(name=self.name, value=self.value)

class NotConnection(WebDavException):
    def __init__(self, args):
        self.text = args[0]

    def __str__(self):
        return self.text

class NotEnoughSpace(WebDavException):
    def __init__(self):
        pass

    def __str__(self):
        return "Not enough space on the server"

class Client:
    root = '/'

    http_header = {
        'list': ["Accept: */*", "Depth: 1"],
        'free': ["Accept: */*", "Depth: 0", "Content-Type: text/xml"],
        'copy': ["Accept: */*"],
        'move': ["Accept: */*"],
        'mkdir': ["Accept: */*", "Connection: Keep-Alive"],
        'clean': ["Accept: */*", "Connection: Keep-Alive"],
        'check': ["Accept: */*", "Depth: 0"],
        'info': ["Accept: */*", "Depth: 1"],
        'get_metadata': ["Accept: */*", "Depth: 1", "Content-Type: application/x-www-form-urlencoded"],
        'set_metadata': ["Accept: */*", "Depth: 1", "Content-Type: application/x-www-form-urlencoded"]
    }

    requests = {
        'copy': "COPY",
        'move': "MOVE",
        'mkdir': "MKCOL",
        'clean': "DELETE",
        'check': "PROPFIND",
        'list': "PROPFIND",
        'free': "PROPFIND",
        'info': "PROPFIND",
        'get_metadata': "PROPFIND",
        'publish': "PROPPATCH",
        'unpublish': "PROPPATCH",
        'published': "PROPPATCH",
        'set_metadata': "PROPPATCH"
    }

    def __init__(self, options):
        self.options = options
        self.server_hostname = options.get("webdav_hostname", '')
        self.server_login = options.get("webdav_login", '')
        self.server_password = options.get("webdav_password", '')
        self.proxy_hostname = options.get("proxy_hostname", '')
        self.proxy_login = options.get("proxy_login", '')
        self.proxy_password = options.get("proxy_password", '')
        self.cert_path = options.get("cert_path", '')
        self.key_path = options.get("key_path", '')

        webdav_root = options.get("webdav_root", '')
        self.webdav_root = Urn(webdav_root).quote() if webdav_root else ''
        self.webdav_root = self.webdav_root.rstrip(Urn.separate)

        pycurl.global_init(pycurl.GLOBAL_DEFAULT)

        self.default_options = {}

    def __del__(self):
        pycurl.global_cleanup()

    def __str__(self):
        return "client with options {options}".format(options=self.options)

    def Request(self, options=None):

        curl = pycurl.Curl()

        self.default_options.update({
            'SSL_VERIFYPEER': 0,
            'SSL_VERIFYHOST': 0,
            'URL': self.server_hostname,
            'USERPWD': '{login}:{password}'.format(login=self.server_login, password=self.server_password),
        })

        if self.proxy_login:
            if not self.proxy_password:
                self.default_options['PROXYUSERNAME'] = self.proxy_login
            else:
                self.default_options['PROXYUSERPWD'] = '{login}:{password}'.format(login=self.proxy_login,
                                                                                   password=self.proxy_password)

        if self.cert_path:
            self.default_options['SSLCERT'] = self.cert_path

        if self.key_path:
            self.default_options['SSLKEY'] = self.key_path

        if self.default_options:
            Client._add_options(curl, self.default_options)

        if options:
            Client._add_options(curl, options)

        return curl

    def list(self, remote_path=root) -> list:

        def parse(response) -> list:
            response_str = response.getvalue().decode('utf-8')
            tree = ET.fromstring(response_str)
            hrees = [unquote(hree.text) for hree in tree.findall(".//{DAV:}href")]
            return [Urn(hree) for hree in hrees]

        try:

            directory_urn = Urn(remote_path, directory=True)

            if directory_urn.path() != Client.root:
                if not self.check(directory_urn.path()):
                    raise RemoteResourceNotFound(directory_urn.path())

            response = BytesIO()

            options = {
                'CUSTOMREQUEST': Client.requests['list'],
                'URL': '{hostname}{root}{path}'.format(hostname=self.server_hostname, root=self.webdav_root,
                                                       path=directory_urn.quote()),
                'HTTPHEADER': Client.http_header['list'],
                'WRITEDATA': response
            }

            request = self.Request(options=options)

            request.perform()
            request.close()

            urns = parse(response)
            return [urn.filename() for urn in urns if urn.path() != directory_urn.path()]

        except pycurl.error as e:
            raise NotConnection(e.args[-1:])

    def free(self) -> int:

        def parse(response) -> int:

            response_str = response.getvalue().decode('utf-8')
            root = ET.fromstring(response_str)
            size = root.find('.//{DAV:}quota-available-bytes')
            return int(size.text)

        def data() -> str:
            root = ET.Element("D:propfind")
            root.set('xmlns:D', "DAV:")
            prop = ET.SubElement(root, "D:prop")
            ET.SubElement(prop, "D:quota-available-bytes")
            ET.SubElement(prop, "D:quota-used-bytes")
            tree = ET.ElementTree(root)

            buffer = BytesIO()

            tree.write(buffer)
            return buffer.getvalue().decode('utf-8')

        try:
            response = BytesIO()

            options = {
                'CUSTOMREQUEST': Client.requests['free'],
                'HTTPHEADER': Client.http_header['free'],
                'POSTFIELDS': data(),
                'WRITEDATA': response
            }

            request = self.Request(options)

            request.perform()
            request.close()

            return parse(response)

        except pycurl.error as e:
            raise NotConnection(e.args[-1:])

    def check(self, remote_path=root) -> int:

        try:
            urn = Urn(remote_path)
            options = {
                'CUSTOMREQUEST': Client.requests['check'],
                'URL': '{hostname}{root}{path}'.format(hostname=self.server_hostname, root=self.webdav_root,
                                                       path=urn.quote()),
                'HTTPHEADER': Client.http_header['check'],
                'NOBODY': 1
            }

            request = self.Request(options)
            request.perform()
            code = request.getinfo(pycurl.HTTP_CODE)
            result = str(code)
            request.close()
            return result.startswith("2")

        except pycurl.error as e:
            raise NotConnection(e.args[-1:])

    def mkdir(self, remote_path) -> None:

        try:
            directory_urn = Urn(remote_path, directory=True)

            if not self.check(directory_urn.parent()):
                raise RemoteParentNotFound(directory_urn.path())

            options = {
                'CUSTOMREQUEST': Client.requests['mkdir'],
                'URL': '{hostname}{root}{path}'.format(hostname=self.server_hostname, root=self.webdav_root,
                                                       path=directory_urn.quote()),
                'HTTPHEADER': Client.http_header['mkdir']
            }

            request = self.Request(options)

            request.perform()
            request.close()

        except pycurl.error as e:
            raise NotConnection(e.args[-1:])

    def download_to(self, buffer, remote_path) -> None:

        try:
            urn = Urn(remote_path)

            if urn.is_directory():
                raise InvalidOption(name="remote_path", value=remote_path)

            if not self.check(urn.path()):
                raise RemoteResourceNotFound(urn.path())

            options = {
                'URL': '{hostname}{root}{path}'.format(hostname=self.server_hostname, root=self.webdav_root,
                                                       path=urn.quote()),
                'WRITEDATA': buffer,
                'WRITEFUNCTION': buffer.write
            }

            request = self.Request(options)

            request.perform()
            request.close()

        except pycurl.error as e:
            raise NotConnection(e.args[-1:])

    def download(self, remote_path, local_path) -> None:

        urn = Urn(remote_path)

        if urn.is_directory():
            self.download_directory(local_path=local_path, remote_path=remote_path)
        else:
            self.download_file(local_path=local_path, remote_path=remote_path)

    def download_directory(self, remote_path, local_path) -> None:

        urn = Urn(remote_path)

        if not urn.is_directory():
            raise InvalidOption(name="remote_path", value=remote_path)

        if not os.path.isdir(local_path):
            raise InvalidOption(name="local_path", value=local_path)

        if not self.check(urn.path()):
            raise RemoteResourceNotFound(urn.path())

        if os.path.exists(local_path):
            os.remove(local_path)

        os.makedirs(local_path)

        for resource_name in self.list(remote_path):
            _remote_path = "{parent}{name}".format(parent=urn.path(), name=resource_name)
            _local_path = os.path.join(local_path, resource_name)
            self.download(local_path=_local_path, remote_path=_remote_path)

    def download_file(self, remote_path, local_path) -> None:

        try:
            urn = Urn(remote_path)

            if urn.is_directory():
                raise InvalidOption(name="remote_path", value=remote_path)

            if os.path.isdir(local_path):
                raise InvalidOption(name="local_path", value=local_path)

            if not self.check(urn.path()):
                raise RemoteResourceNotFound(urn.path())

            with open(local_path, 'wb') as file:

                options = {
                    'URL': '{hostname}{root}{path}'.format(hostname=self.server_hostname, root=self.webdav_root,
                                                           path=urn.quote()),
                    'WRITEDATA': file,
                    'NOPROGRESS': 0
                }

                request = self.Request(options)

                request.perform()
                request.close()

        except pycurl.error as e:
            raise NotConnection(e.args[-1:])

    def download_sync(self, remote_path, local_path, callback=None) -> None:

        self.download(local_path=local_path, remote_path=remote_path)

        if callback:
            callback()

    def download_async(self, remote_path, local_path, callback=None) -> None:
        target = (lambda: self.download_sync(local_path=local_path, remote_path=remote_path, callback=callback))
        threading.Thread(target=target).start()

    def upload_from(self, buffer, remote_path) -> None:

        try:
            urn = Urn(remote_path)

            if urn.is_directory():
                raise InvalidOption(name="remote_path", value=remote_path)

            if not self.check(urn.parent()):
                raise RemoteParentNotFound(urn.path())

            options = {
                'UPLOAD': 1,
                'URL': '{hostname}{root}{path}'.format(hostname=self.server_hostname, root=self.webdav_root,
                                                       path=urn.quote()),
                'READDATA': buffer,
                'READFUNCTION': buffer.read,
            }

            request = self.Request(options)

            request.perform()
            code = request.getinfo(pycurl.HTTP_CODE)
            if code == "507":
                raise NotEnoughSpace()  # TODO

            request.close()

        except pycurl.error as e:
            raise NotConnection(e.args[-1:])

    def upload(self, remote_path, local_path) -> None:

        if os.path.isdir(local_path):
            self.upload_directory(local_path=local_path, remote_path=remote_path)
        else:
            self.upload_file(local_path=local_path, remote_path=remote_path)

    def upload_directory(self, remote_path, local_path) -> None:

        urn = Urn(remote_path)

        if not urn.is_directory():
            raise InvalidOption(name="remote_path", value=remote_path)

        if not os.path.isdir(local_path):
            raise InvalidOption(name="local_path", value=local_path)

        if not os.path.exists(local_path):
            raise LocalResourceNotFound(local_path)

        if self.check(remote_path):
            self.clean(remote_path)

        self.mkdir(remote_path)

        for resource_name in os.listdir(local_path):
            _remote_path = "{parent}{name}".format(parent=urn.path(), name=resource_name)
            _local_path = os.path.join(local_path, resource_name)
            self.upload(local_path=_local_path, remote_path=_remote_path)

    def upload_file(self, remote_path, local_path) -> None:

        try:
            if not os.path.exists(local_path):
                raise LocalResourceNotFound(local_path)

            urn = Urn(remote_path)

            if urn.is_directory():
                raise InvalidOption(name="remote_path", value=remote_path)

            if os.path.isdir(local_path):
                raise InvalidOption(name="local_path", value=local_path)

            if not os.path.exists(local_path):
                raise LocalResourceNotFound(local_path)

            if not self.check(urn.parent()):
                raise RemoteParentNotFound(urn.path())

            with open(local_path, 'rb') as file:

                options = {
                    'UPLOAD': 1,
                    'URL': '{hostname}{root}{path}'.format(hostname=self.server_hostname, root=self.webdav_root,
                                                           path=urn.quote()),
                    'READDATA': file,
                    'NOBODY': 1,
                    'READFUNCTION': file.read,
                    'INFILESIZE_LARGE': os.path.getsize(local_path),
                    'NOPROGRESS': 0
                }

                request = self.Request(options)

                request.perform()
                code = request.getinfo(pycurl.HTTP_CODE)
                if code == "507":
                    raise NotEnoughSpace()  # TODO

                request.close()

        except pycurl.error as e:
            raise NotConnection(e.args[-1:])

    def upload_sync(self, remote_path, local_path, callback=None) -> None:

        self.upload(local_path=local_path, remote_path=remote_path)

        if callback:
            callback()

    def upload_async(self, remote_path, local_path, callback=None) -> None:
        target = (lambda: self.upload_sync(local_path=local_path, remote_path=remote_path, callback=callback))
        threading.Thread(target=target).start()

    def copy(self, remote_path_from, remote_path_to) -> None:

        def header(remote_path_to) -> list:
            destination = Urn(remote_path_to).path()
            header_item = "Destination: {destination}".format(destination=destination)
            header = Client.http_header['copy'].copy()
            header.append(header_item)
            return header

        try:
            urn_from = Urn(remote_path_from)

            if not self.check(urn_from.path()):
                raise RemoteResourceNotFound(urn_from.path())

            urn_to = Urn(remote_path_to)

            if not self.check(urn_to.parent()):
                raise RemoteParentNotFound(urn_to.path())

            options = {
                'CUSTOMREQUEST': Client.requests['copy'],
                'URL': '{hostname}{root}{path}'.format(hostname=self.server_hostname, root=self.webdav_root,
                                                       path=urn_from.quote()),
                'HTTPHEADER': header(remote_path_to)
            }

            request = self.Request(options)

            request.perform()
            request.close()

        except pycurl.error as e:
            raise NotConnection(e.args[-1:])

    def move(self, remote_path_from, remote_path_to) -> None:

        def header(remote_path_to) -> list:
            destination = Urn(remote_path_to).path()
            header_item = "Destination: {destination}".format(destination=destination)
            header = Client.http_header['copy'].copy()
            header.append(header_item)
            return header

        try:
            urn_from = Urn(remote_path_from)

            if not self.check(urn_from.path()):
                raise RemoteResourceNotFound(urn_from.path())

            urn_to = Urn(remote_path_to)

            if not self.check(urn_to.parent()):
                raise RemoteParentNotFound(urn_to.path())

            options = {
                'CUSTOMREQUEST': Client.requests['move'],
                'URL': '{hostname}{root}{path}'.format(hostname=self.server_hostname, root=self.webdav_root,
                                                       path=urn_from.quote()),
                'HTTPHEADER': header(remote_path_to)
            }

            request = self.Request(options)

            request.perform()
            request.close()

        except pycurl.error as e:
            raise NotConnection(e.args[-1:])

    def clean(self, remote_path) -> None:

        try:
            urn = Urn(remote_path)

            if not self.check(urn.path()):
                raise RemoteResourceNotFound(urn.path())

            options = {
                'CUSTOMREQUEST': Client.requests['clean'],
                'URL': '{hostname}{root}{path}'.format(hostname=self.server_hostname, root=self.webdav_root,
                                                       path=urn.quote()),
                'HTTPHEADER': Client.http_header['clean']
            }

            request = self.Request(options)

            request.perform()
            request.close()

        except pycurl.error as e:
            raise NotConnection(e.args[-1:])

    def publish(self, remote_path) -> str:

        def parse(response) -> str:
            response_str = response.getvalue().decode('utf-8')
            root = ET.fromstring(response_str)
            public_url = root.find('.//{urn:yandex:disk:meta}public_url') #TODO common webdav-server
            return public_url.text

        def data() -> str:
            root = ET.Element("propertyupdate", xmlns="DAV:")
            set = ET.SubElement(root, "set")
            prop = ET.SubElement(set, "prop")
            public_url = ET.SubElement(prop, "public_url", xmlns="urn:yandex:disk:meta")
            public_url.text = "true"
            tree = ET.ElementTree(root)

            buffer = BytesIO()
            tree.write(buffer)

            return buffer.getvalue().decode('utf-8')

        try:
            urn = Urn(remote_path)

            link = self.published(urn.path())
            if link: return link

            if not self.check(urn.path()):
                raise RemoteResourceNotFound(urn.path())

            response = BytesIO()

            options = {
                'CUSTOMREQUEST': Client.requests['publish'],
                'URL': '{hostname}{root}{path}'.format(hostname=self.server_hostname, root=self.webdav_root,
                                                       path=urn.quote()),
                'POSTFIELDS': data(),
                'WRITEDATA': response
            }

            request = self.Request(options)

            request.perform()
            request.close()

            return parse(response)

        except pycurl.error as e:
            raise NotConnection(e.args[-1:])

    def unpublish(self, remote_path) -> None:

        def data() -> str:
            root = ET.Element("propertyupdate", xmlns="DAV:")
            remove = ET.SubElement(root, "remove")
            prop = ET.SubElement(remove, "prop")
            ET.SubElement(prop, "public_url", xmlns="urn:yandex:disk:meta")
            tree = ET.ElementTree(root)

            buffer = BytesIO()
            tree.write(buffer)

            return buffer.getvalue().decode('utf-8')

        try:
            urn = Urn(remote_path)

            if not self.check(urn.path()):
                raise RemoteResourceNotFound(urn.path())

            response = BytesIO()

            options = {
                'CUSTOMREQUEST': Client.requests['unpublish'],
                'URL': '{hostname}{root}{path}'.format(hostname=self.server_hostname, root=self.webdav_root,
                                                       path=urn.quote()),
                'POSTFIELDS': data(),
                'WRITEDATA': response
            }

            request = self.Request(options)

            request.perform()
            request.close()

        except pycurl.error as e:
            raise NotConnection(e.args[-1:])

    def published(self, remote_path) -> str:

        def parse(response) -> str:
            response_str = response.getvalue().decode('utf-8')
            root = ET.fromstring(response_str)
            public_url = root.find('.//{DAV:}public_url')
            return public_url.text if public_url else ""

        def data() -> str:
            root = ET.Element("D:propfind")
            root.set('xmlns:D', "DAV:")
            prop = ET.SubElement(root, "prop")
            ET.SubElement(prop, "public_url", xmlns="urn:yandex:disk:meta")
            tree = ET.ElementTree(root)

            buffer = BytesIO()
            tree.write(buffer)

            return buffer.getvalue().decode('utf-8')

        try:
            urn = Urn(remote_path)

            if not self.check(urn.path()):
                raise RemoteResourceNotFound(urn.path())

            response = BytesIO()

            options = {
                'CUSTOMREQUEST': Client.requests['published'],
                'URL': '{hostname}{root}{path}'.format(hostname=self.server_hostname, root=self.webdav_root,
                                                       path=urn.quote()),
                'POSTFIELDS': data(),
                'WRITEDATA': response
            }

            request = self.Request(options)

            request.perform()
            request.close()

            return parse(response)

        except pycurl.error as e:
            raise NotConnection(e.args[-1:])

    def info(self, remote_path) -> dict:

        def parse(response) -> dict:
            response_str = response.getvalue().decode('utf-8')
            root = ET.fromstring(response_str)

            info = {}

            responses = root.findall("{DAV:}response")
            for response in responses:

                href = response.findtext("{DAV:}href")

                urn = Urn(href)

                find_attributes = {
                    'created': ".//{DAV:}creationdate",
                    'name': ".//{DAV:}displayname",
                    'size': ".//{DAV:}getcontentlength",
                    'modified': ".//{DAV:}getlastmodified",
                    'type': ".//{DAV:}resourcetype"
                }

                record = {}
                for (name, value) in find_attributes:
                    node = response.find(value)
                    record[name] = node.text if node else ''

                info[urn.filename()] = record

            return info

        try:
            urn = Urn(remote_path)

            if not self.check(urn.path()):
                raise RemoteResourceNotFound(urn.path())

            response = BytesIO()

            parent_urn = Urn(urn.parent())
            options = {
                'CUSTOMREQUEST': Client.requests['info'],
                'URL': '{hostname}{root}{path}'.format(hostname=self.server_hostname, root=self.webdav_root,
                                                       path=parent_urn),
                'HTTPHEADER': Client.http_header['info'],
                'WRITEDATA': response
            }

            request = self.Request(options)

            request.perform()
            request.close()

            info = parse(response)
            name = urn.filename()

            return info[name] if name in info else dict()

        except pycurl.error as e:
            raise NotConnection(e.args[-1:])

    def resource(self, remote_path):
        urn = Urn(remote_path)
        return Resource(self, urn)

    def _add_options(request, options: dict) -> None:

        for (key, value) in options.items():
            try:
                request.setopt(pycurl.__dict__[key], value)
            except TypeError or pycurl.error:
                raise InvalidOption(key, value)

    def get_property(self, remote_path, option: dict) -> str:

        def parse(response, option) -> str:
            response_str = response.getvalue().decode('utf-8')
            root = ET.fromstring(response_str)
            xpath = "{xpath_prefix}{xpath_exp}".format(xpath_prefix=".//", xpath_exp=option['name'])
            return root.findtext(xpath)

        def data(option) -> str:
            root = ET.Element("propfind", xmlns="DAV:")
            prop = ET.SubElement(root, "prop")
            ET.SubElement(prop, option.get('name', ""), xmlns=option.get('namespace', ""))
            tree = ET.ElementTree(root)

            buffer = BytesIO()

            tree.write(buffer)
            return buffer.getvalue().decode('utf-8')

        try:
            urn = Urn(remote_path)

            if not self.check(urn.path()):
                raise RemoteResourceNotFound(urn.path())

            response = BytesIO()

            options = {
                'URL': '{hostname}{root}{path}'.format(hostname=self.server_hostname, root=self.webdav_root,
                                                       path=urn.path()),
                'CUSTOMREQUEST': Client.requests['get_metadata'],
                'HTTPHEADER': Client.http_header['get_metadata'],
                'POSTFIELDS': data(option),
                'WRITEDATA': response
            }

            request = self.Request(options)

            request.perform()
            request.close()

            return parse(response, option)

        except pycurl.error as e:
            raise NotConnection(e.args[-1:])

    def set_property(self, remote_path, option: dict) -> None:

        def data(option) -> str:
            root = ET.Element("propertyupdate", xmlns="DAV:")
            root.set('xmlns:u', option.get('namespace', ""))

            set = ET.SubElement(root, "set")
            prop = ET.SubElement(set, "prop")
            opt = ET.SubElement(prop, "{namespace}:{name}".format(namespace='u', name=option['name']))
            opt.text = option.get('value', "")

            tree = ET.ElementTree(root)

            buffer = BytesIO()
            tree.write(buffer)

            return buffer.getvalue().decode('utf-8')

        try:
            urn = Urn(remote_path)

            if not self.check(urn.path()):
                raise RemoteResourceNotFound(urn.path())

            options = {
                'URL': '{hostname}{root}{path}'.format(hostname=self.server_hostname, root=self.webdav_root,
                                                       path=urn.path()),
                'CUSTOMREQUEST': Client.requests['set_metadata'],
                'HTTPHEADER': Client.http_header['set_metadata'],
                'POSTFIELDS': data(option)
            }

            request = self.Request(options)

            request.perform()
            request.close()

        except pycurl.error as e:
            raise NotConnection(e.args[-1:])

    def push(self, remote_directory, local_directory) -> None:

        def slice(src, exp) -> list:
            return [re.sub(exp, "", item) for item in src]

        urn = Urn(remote_directory)

        if not urn.is_directory():
            raise InvalidOption(name="remote_path", value=remote_directory)

        if not os.path.isdir(local_directory):
            raise InvalidOption(name="local_path", value=local_directory)

        if not os.path.exists(local_directory):
            raise LocalResourceNotFound(local_directory)

        paths = self.list(remote_directory)
        remote_resource_names = slice(paths, remote_directory)

        for local_resource_name in os.listdir(local_directory):

            if local_resource_name in remote_resource_names:
                continue

            local_path = os.path.join(local_directory, local_resource_name)
            remote_path = "{remote_directory}{resource_name}".format(remote_directory=urn.path(), resource_name=local_resource_name)

            if os.path.isdir(local_path):
                self.push(remote_directory=remote_path, local_directory=local_path)
            else:
                self.upload_file(remote_path=remote_path, local_path=local_path)

    def pull(self, remote_directory, local_directory) -> None:

        def slice(src, exp) -> list:
            return [re.sub(exp, "", item) for item in src]

        urn = Urn(remote_directory)

        if not urn.is_directory():
            raise InvalidOption(name="remote_path", value=remote_directory)

        if not os.path.isdir(local_directory):
            raise InvalidOption(name="local_path", value=local_directory)

        if not os.path.exists(local_directory):
            raise LocalResourceNotFound(local_directory)

        local_resource_names = os.listdir(local_directory)

        paths = self.list(remote_directory)
        remote_resource_names = slice(paths, remote_directory)

        for remote_resource_name in remote_resource_names:

            if remote_resource_name in local_resource_names:
                continue

            local_path = os.path.join(local_directory, remote_resource_name)
            remote_path = "{remote_directory}{resource_name}".format(remote_directory=urn.path(), resource_name=remote_resource_name)

            remote_urn = Urn(remote_path)

            if remote_urn.is_directory():
                self.pull(remote_directory=remote_path, local_directory=local_path)
            else:
                self.download_file(remote_path=remote_path, local_path=local_path)

    def sync(self, remote_directory, local_directory) -> None:

        self.pull(remote_directory=remote_directory, local_directory=local_directory)
        self.push(remote_directory=remote_directory, local_directory=local_directory)

class Resource:
    def __init__(self, client, urn):
        self.client = client
        self.urn = urn

    def __str__(self):
        return "resource {path}".format(path=self.urn.path())

    def rename(self, new_name) -> None:
        old_path = self.urn.path()
        parent_path = self.urn.parent()
        new_name = Urn(new_name).filename()
        new_path = "{directory}{filename}".format(directory=parent_path, filename=new_name)

        self.client.move(remote_path_from=old_path, remote_path_to=new_path)
        self.urn = Urn(new_path)

    def move(self, remote_path) -> None:
        new_urn = Urn(remote_path)
        self.client.move(remote_path_from=self.urn.path(), remote_path_to=new_urn.path())
        self.urn = new_urn

    def copy(self, remote_path):
        urn = Urn(remote_path)
        self.client.copy(remote_path_from=self.urn.path(), remote_path_to=remote_path)
        return Resource(self.client, urn)

    def info(self) -> dict:
        return self.client.info(self.urn.path())

    def read_from(self, buffer) -> None:
        self.client.upload_from(buffer=buffer, remote_path=self.urn.path())

    def read(self, local_path) -> None:
        self.client.upload_sync(local_path=local_path, remote_path=self.urn.path())

    def read_async(self, local_path, callback=None) -> None:
        self.client.upload_async(local_path=local_path, remote_path=self.urn.path(), callback=callback)

    def write_to(self, buffer) -> None:
        self.client.download_to(buffer=buffer, remote_path=self.urn.path())

    def write(self, local_path) -> None:
        self.client.download_sync(local_path=local_path, remote_path=self.urn.path())

    def write_async(self, local_path, callback=None) -> None:
        self.client.download_async(local_path=local_path, remote_path=self.urn.path(), callback=callback)

    @property
    def property(self, option: dict) -> str:
        return self.client.get_property(remote_path=self.urn.path(), option=option)

    @property.setter
    def property(self, option, value):
        option['value'] = value.__str__()
        self.client.set_property(remote_path=self.urn.path(), option=option)

def import_options():
    options = {
        'webdav_hostname': os.environ.get('WEBDAV_HOSTNAME'),
        'webdav_root': os.environ.get('WEBDAV_ROOT'),
        'webdav_login': os.environ.get('WEBDAV_LOGIN'),
        'webdav_password': os.environ.get('WEBDAV_PASSWORD'),
        'proxy_hostname': os.environ.get('PROXY_HOSTNAME'),
        'proxy_login': os.environ.get('PROXY_LOGIN'),
        'proxy_password': os.environ.get('PROXY_PASSWORD'),
        'cert_path': os.environ.get('CERT_PATH'),
        'key_path': os.environ.get('KEY_PATH')
    }

    return options

def logging_exception(e):
    print(e)

if __name__ == "__main__":

    parser = argparse.ArgumentParser(prog='webdav')
    parser.add_argument("action",
                        choices=["login", "check", "free", "ls", "clean", "mkdir", "copy", "move", "download", "upload",
                                 "publish", "unpublish", "push", "pull", "sync"])

    parser.add_argument("-r", "--root", help="example: dir1/dir2")
    parser.add_argument("-p", "--proxy", help="example: http://127.0.0.1:8080")
    parser.add_argument("path", help="example: dir1/dir2/file1", nargs='?')
    parser.add_argument("-f", '--from-path', help="example: ~/Documents/file1")
    parser.add_argument("-t", "--to-path", help="example: ~/Download/file1")
    parser.add_argument("-c", "--cert-path", help="example: /etc/ssl/certs/certificate.crt")
    parser.add_argument("-k", "--key-path", help="example: /etc/ssl/private/certificate.key")

    args = parser.parse_args()
    action = args.action

    if action == 'install':
        print("install")

    elif action == 'login':
        env = dict()
        if not args.path:
            parser.print_help()
        else:
            env['webdav_hostname'] = args.path
            env['webdav_login'] = input("webdav_login: ")
            env['webdav_password'] = getpass.getpass("webdav_password: ")

            if args.proxy:
                env['proxy_hostname'] = args.proxy
                env['proxy_login'] = input("proxy_login: ")
                env['proxy_password'] = getpass.getpass("proxy_password: ")

            if args.root:
                env['webdav_root'] = args.root

            if args.cert_path:
                env['cert_path'] = args.cert_path

            if args.key_path:
                env['key_path'] = args.key_path

            for (key, value) in env.items():
                os.putenv(key.upper(), value)

            os.system('bash')

    elif action == 'check':
        options = import_options()
        try:
            client = Client(options)
            check = client.check(args.path) if args.path else client.check()
            text = "success" if check else "not success"
            print(text)
        except WebDavException as e:
            logging_exception(e)

    elif action == 'free':
        options = import_options()
        try:
            client = Client(options)
            free_size = client.free()
            print(free_size)
        except WebDavException as e:
            logging_exception(e)

    elif action == 'ls':
        options = import_options()
        try:
            client = Client(options)
            paths = client.list(args.path) if args.path else client.list()
            for path in paths:
                print(path)
        except WebDavException as e:
            logging_exception(e)

    elif action == 'clean':
        options = import_options()
        try:
            client = Client(options)
            if not args.path:
                parser.print_help()
            else:
                client.clean(args.path)
        except WebDavException as e:
            logging_exception(e)

    elif action == 'mkdir':
        options = import_options()
        try:
            client = Client(options)
            if not args.path:
                parser.print_help()
            else:
                client.mkdir(args.path)
        except WebDavException as e:
            logging_exception(e)

    elif action == 'copy':
        options = import_options()
        try:
            client = Client(options)
            if not args.path and args.to_path:
                parser.print_help()
            else:
                client.copy(remote_path_from=args.path, remote_path_to=args.to_path)
        except WebDavException as e:
            logging_exception(e)

    elif action == 'move':
        options = import_options()
        try:
            client = Client(options)
            if not args.path and args.to_path:
                parser.print_help()
            else:
                client.move(remote_path_from=args.path, remote_path_to=args.to_path)
        except WebDavException as e:
            logging_exception(e)

    elif action == 'download':
        options = import_options()
        try:
            client = Client(options)
            if not args.path and args.to_path:
                parser.print_help()
            else:
                client.download_sync(remote_path=args.path, local_path=args.to_path)
        except WebDavException as e:
            logging_exception(e)

    elif action == 'upload':
        options = import_options()
        try:
            client = Client(options)
            if not args.path and args.from_path:
                parser.print_help()
            else:
                client.upload_sync(remote_path=args.path, local_path=args.from_path)
        except WebDavException as e:
            logging_exception(e)

    elif action == 'publish':
        options = import_options()
        try:
            client = Client(options)
            if not args.path:
                parser.print_help()
            else:
                link = client.publish(args.path)
                print(link)
        except WebDavException as e:
            logging_exception(e)

    elif action == 'unpublish':
        options = import_options()
        try:
            client = Client(options)
            if not args.path:
                parser.print_help()
            else:
                client.unpublish(args.path)
        except WebDavException as e:
            logging_exception(e)

    elif action == 'push':
        options = import_options()
        try:
            client = Client(options)
            if not args.path and args.from_path:
                parser.print_help()
            else:
                client.push(remote_directory=args.path, local_directory=args.from_path)
        except WebDavException as e:
            logging_exception(e)

    elif action == 'pull':
        options = import_options()
        try:
            client = Client(options)
            if not args.path and args.to_path:
                parser.print_help()
            else:
                client.pull(remote_directory=args.path, local_directory=args.to_path)
        except WebDavException as e:
            logging_exception(e)

    else:
        parser.print_help()
