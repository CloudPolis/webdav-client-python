# -*- coding: utf-8

import pycurl
import re
import os
import shutil
import threading
import lxml.etree as etree
from io import BytesIO

try:
    from urllib.parse import unquote, quote
except ImportError:
    from urllib import unquote, quote

def listdir(directory):

    file_names = list()
    for filename in os.listdir(directory):
        filepath = os.path.join(directory, filename)
        if os.path.isdir(filepath):
            filename = "{filename}{separate}".format(filename=filename, separate=os.path.sep)
        file_names.append(filename)
    return file_names

class Urn(object):

    separate = "/"

    def __init__(self, path, directory=False):

        self._path = quote(path)
        expressions = "/\.+/", "/+"
        for expression in expressions:
            self._path = re.sub(expression, Urn.separate, self._path)

        if not self._path.startswith(Urn.separate):
            self._path = "{begin}{end}".format(begin=Urn.separate, end=self._path)

        if directory and not self._path.endswith(Urn.separate):
            self._path = "{begin}{end}".format(begin=self._path, end=Urn.separate)

    def __str__(self):
        return self.path()

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
        return self._path[-1] == Urn.separate

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

class MethodNotSupported(WebDavException):
    def __init__(self, name, server):
        self.name = name
        self.server = server

    def __str__(self):
        return "Method {name} not supported for {server}".format(name=self.name, server=self.server)

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

def add_options(request, options):

    for (key, value) in options.items():
        try:
            request.setopt(pycurl.__dict__[key], value)
        except TypeError:
            raise InvalidOption(key, value)
        except pycurl.error:
            raise InvalidOption(key, value)

class Client(object):

    root = '/'
    large_size = 2 * 1024 * 1024 * 1024

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

    meta_xmlns = {
        'https://webdav.yandex.ru': "urn:yandex:disk:meta",
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

        user_token = '{login}:{password}'.format(login=self.server_login, password=self.server_password)
        self.default_options.update({
            'SSL_VERIFYPEER': 0,
            'SSL_VERIFYHOST': 0,
            'URL': self.server_hostname,
            'USERPWD': user_token
        })

        if self.proxy_hostname:
            self.default_options['PROXY'] = self.proxy_hostname

            if self.proxy_login:
                if not self.proxy_password:
                    self.default_options['PROXYUSERNAME'] = self.proxy_login
                else:
                    proxy_token = '{login}:{password}'.format(login=self.proxy_login, password=self.proxy_password)
                    self.default_options['PROXYUSERPWD'] = proxy_token

        if self.cert_path:
            self.default_options['SSLCERT'] = self.cert_path

        if self.key_path:
            self.default_options['SSLKEY'] = self.key_path

        if self.default_options:
            add_options(curl, self.default_options)

        if options:
            add_options(curl, options)

        return curl

    def list(self, remote_path=root):

        def parse(response):

            response_str = response.getvalue()
            tree = etree.fromstring(response_str)
            hrees = [unquote(hree.text) for hree in tree.findall(".//{DAV:}href")]
            return [Urn(hree) for hree in hrees]

        try:

            directory_urn = Urn(remote_path, directory=True)

            if directory_urn.path() != Client.root:
                if not self.check(directory_urn.path()):
                    raise RemoteResourceNotFound(directory_urn.path())

            response = BytesIO()

            url = {'hostname': self.server_hostname, 'root': self.webdav_root, 'path': directory_urn.quote()}
            options = {
                'CUSTOMREQUEST': Client.requests['list'],
                'URL': "{hostname}{root}{path}".format(**url),
                'HTTPHEADER': Client.http_header['list'],
                'WRITEDATA': response
            }

            request = self.Request(options=options)

            request.perform()
            request.close()

            urns = parse(response)
            return [urn.filename() for urn in urns if urn.path() != directory_urn.path()]

        except pycurl.error as exception:
            raise NotConnection(exception.args[-1:])

    def free(self):

        def parse(response):

            response_str = response.getvalue()
            tree = etree.fromstring(response_str)
            node = tree.find('.//{DAV:}quota-available-bytes')
            try:
                if node is not None:
                    return int(node.text)
                else:
                    raise MethodNotSupported(name='free', server=self.server_hostname)
            except TypeError:
                raise MethodNotSupported(name='free', server=self.server_hostname)

        def data():
            root = etree.Element("D:propfind", xmlns="DAV:")
            prop = etree.SubElement(root, "D:prop")
            etree.SubElement(prop, "D:quota-available-bytes")
            etree.SubElement(prop, "D:quota-used-bytes")
            tree = etree.ElementTree(root)

            buff = BytesIO()

            tree.write(buff)
            return buff.getvalue()

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

        except pycurl.error as exception:
            raise NotConnection(exception.args[-1:])

    def check(self, remote_path=root):

        try:
            urn = Urn(remote_path)
            url = {'hostname': self.server_hostname, 'root': self.webdav_root, 'path': urn.quote()}
            options = {
                'CUSTOMREQUEST': Client.requests['check'],
                'URL': "{hostname}{root}{path}".format(**url),
                'HTTPHEADER': Client.http_header['check'],
                'NOBODY': 1
            }

            request = self.Request(options)
            request.perform()
            code = request.getinfo(pycurl.HTTP_CODE)
            result = str(code)
            request.close()
            return result.startswith("2")

        except pycurl.error as exception:
            raise NotConnection(exception.args[-1:])

    def mkdir(self, remote_path):

        try:
            directory_urn = Urn(remote_path, directory=True)

            if not self.check(directory_urn.parent()):
                raise RemoteParentNotFound(directory_urn.path())

            url = {'hostname': self.server_hostname, 'root': self.webdav_root, 'path': directory_urn.quote()}
            options = {
                'CUSTOMREQUEST': Client.requests['mkdir'],
                'URL': "{hostname}{root}{path}".format(**url),
                'HTTPHEADER': Client.http_header['mkdir']
            }

            request = self.Request(options)

            request.perform()
            request.close()

        except pycurl.error as exception:
            raise NotConnection(exception.args[-1:])

    def download_to(self, buff, remote_path):

        try:
            urn = Urn(remote_path)

            if urn.is_directory():
                raise InvalidOption(name="remote_path", value=remote_path)

            if not self.check(urn.path()):
                raise RemoteResourceNotFound(urn.path())

            url = {'hostname': self.server_hostname, 'root': self.webdav_root, 'path': urn.quote()}
            options = {
                'URL': "{hostname}{root}{path}".format(**url),
                'WRITEFUNCTION': buff.write
            }

            request = self.Request(options)

            request.perform()
            request.close()

        except pycurl.error as exception:
            raise NotConnection(exception.args[-1:])

    def download(self, remote_path, local_path):

        urn = Urn(remote_path)
        if urn.is_directory():
            self.download_directory(local_path=local_path, remote_path=remote_path)
        else:
            self.download_file(local_path=local_path, remote_path=remote_path)

    def download_directory(self, remote_path, local_path):

        urn = Urn(remote_path)

        if not urn.is_directory():
            raise InvalidOption(name="remote_path", value=remote_path)

        if os.path.exists(local_path):
            shutil.rmtree(local_path)

        os.makedirs(local_path)

        for resource_name in self.list(remote_path):
            _remote_path = "{parent}{name}".format(parent=urn.path(), name=resource_name)
            _local_path = os.path.join(local_path, resource_name)
            self.download(local_path=_local_path, remote_path=_remote_path)

    def download_file(self, remote_path, local_path):

        try:
            urn = Urn(remote_path)

            if urn.is_directory():
                raise InvalidOption(name="remote_path", value=remote_path)

            if os.path.isdir(local_path):
                raise InvalidOption(name="local_path", value=local_path)

            if not self.check(urn.path()):
                raise RemoteResourceNotFound(urn.path())

            with open(local_path, 'wb') as local_file:

                url = {'hostname': self.server_hostname, 'root': self.webdav_root, 'path': urn.quote()}
                options = {
                    'URL': "{hostname}{root}{path}".format(**url),
                    'WRITEDATA': local_file,
                    'NOPROGRESS': 0
                }

                request = self.Request(options)

                request.perform()
                request.close()

        except pycurl.error as exception:
            raise NotConnection(exception.args[-1:])

    def download_sync(self, remote_path, local_path, callback=None):

        self.download(local_path=local_path, remote_path=remote_path)

        if callback:
            callback()

    def download_async(self, remote_path, local_path, callback=None):

        target = (lambda: self.download_sync(local_path=local_path, remote_path=remote_path, callback=callback))
        threading.Thread(target=target).start()

    def upload_from(self, buff, remote_path):

        try:
            urn = Urn(remote_path)

            if urn.is_directory():
                raise InvalidOption(name="remote_path", value=remote_path)

            if not self.check(urn.parent()):
                raise RemoteParentNotFound(urn.path())

            url = {'hostname': self.server_hostname, 'root': self.webdav_root, 'path': urn.quote()}
            options = {
                'UPLOAD': 1,
                'URL': "{hostname}{root}{path}".format(**url),
                'READFUNCTION': buff.read,
            }

            request = self.Request(options)

            request.perform()
            code = request.getinfo(pycurl.HTTP_CODE)
            if code == "507":
                raise NotEnoughSpace()

            request.close()

        except pycurl.error as exception:
            raise NotConnection(exception.args[-1:])

    def upload(self, remote_path, local_path):

        if os.path.isdir(local_path):
            self.upload_directory(local_path=local_path, remote_path=remote_path)
        else:
            self.upload_file(local_path=local_path, remote_path=remote_path)

    def upload_directory(self, remote_path, local_path):

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

        for resource_name in listdir(local_path):
            _remote_path = "{parent}{name}".format(parent=urn.path(), name=resource_name)
            _local_path = os.path.join(local_path, resource_name)
            self.upload(local_path=_local_path, remote_path=_remote_path)

    def upload_file(self, remote_path, local_path):

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

            with open(local_path, "rb") as local_file:

                url = {'hostname': self.server_hostname, 'root': self.webdav_root, 'path': urn.quote()}
                options = {
                    'UPLOAD': 1,
                    'URL': "{hostname}{root}{path}".format(**url),
                    'READFUNCTION': local_file.read,
                    'NOPROGRESS': 0
                }

                file_size = os.path.getsize(local_path)
                if file_size > self.large_size:
                    options['INFILESIZE_LARGE'] = file_size
                else:
                    options['INFILESIZE'] = file_size

                request = self.Request(options)

                request.perform()
                code = request.getinfo(pycurl.HTTP_CODE)
                if code == "507":
                    raise NotEnoughSpace()

                request.close()

        except pycurl.error as exception:
            raise NotConnection(exception.args[-1:])

    def upload_sync(self, remote_path, local_path, callback=None):

        self.upload(local_path=local_path, remote_path=remote_path)

        if callback:
            callback()

    def upload_async(self, remote_path, local_path, callback=None):

        target = (lambda: self.upload_sync(local_path=local_path, remote_path=remote_path, callback=callback))
        threading.Thread(target=target).start()

    def copy(self, remote_path_from, remote_path_to):

        def header(remote_path_to):

            destination = Urn(remote_path_to).path()
            header_item = "Destination: {destination}".format(destination=destination)
            try:
                header = Client.http_header['copy'].copy()
            except AttributeError:
                header = Client.http_header['copy'][:]
            header.append(header_item)
            return header

        try:
            urn_from = Urn(remote_path_from)

            if not self.check(urn_from.path()):
                raise RemoteResourceNotFound(urn_from.path())

            urn_to = Urn(remote_path_to)

            if not self.check(urn_to.parent()):
                raise RemoteParentNotFound(urn_to.path())

            url = {'hostname': self.server_hostname, 'root': self.webdav_root, 'path': urn_from.quote()}
            options = {
                'CUSTOMREQUEST': Client.requests['copy'],
                'URL': "{hostname}{root}{path}".format(**url),
                'HTTPHEADER': header(remote_path_to)
            }

            request = self.Request(options)

            request.perform()
            request.close()

        except pycurl.error as exception:
            raise NotConnection(exception.args[-1:])

    def move(self, remote_path_from, remote_path_to):

        def header(remote_path_to):

            destination = Urn(remote_path_to).path()
            header_item = "Destination: {destination}".format(destination=destination)
            try:
                header = Client.http_header['move'].copy()
            except AttributeError:
                header = Client.http_header['move'][:]
            header.append(header_item)
            return header

        try:
            urn_from = Urn(remote_path_from)

            if not self.check(urn_from.path()):
                raise RemoteResourceNotFound(urn_from.path())

            urn_to = Urn(remote_path_to)

            if not self.check(urn_to.parent()):
                raise RemoteParentNotFound(urn_to.path())

            url = {'hostname': self.server_hostname, 'root': self.webdav_root, 'path': urn_from.quote()}
            options = {
                'CUSTOMREQUEST': Client.requests['move'],
                'URL': "{hostname}{root}{path}".format(**url),
                'HTTPHEADER': header(remote_path_to)
            }

            request = self.Request(options)

            request.perform()
            request.close()

        except pycurl.error as exception:
            raise NotConnection(exception.args[-1:])

    def clean(self, remote_path):

        try:
            urn = Urn(remote_path)

            if not self.check(urn.path()):
                raise RemoteResourceNotFound(urn.path())

            url = {'hostname': self.server_hostname, 'root': self.webdav_root, 'path': urn.quote()}
            options = {
                'CUSTOMREQUEST': Client.requests['clean'],
                'URL': "{hostname}{root}{path}".format(**url),
                'HTTPHEADER': Client.http_header['clean']
            }

            request = self.Request(options)

            request.perform()
            request.close()

        except pycurl.error as exception:
            raise NotConnection(exception.args[-1:])

    def publish(self, remote_path):

        def parse(response):

            response_str = response.getvalue()
            tree = etree.fromstring(response_str)
            result = tree.xpath("//*[local-name() = 'public_url']")
            try:
                public_url = result[0]
                return public_url.text
            except IndexError:
                raise MethodNotSupported(name="publish", server=self.server_hostname)

        def data(for_server):

            root_node = etree.Element("propertyupdate", xmlns="DAV:")
            set_node = etree.SubElement(root_node, "set")
            prop_node = etree.SubElement(set_node, "prop")
            xmlns = Client.meta_xmlns.get(for_server, "")
            public_url = etree.SubElement(prop_node, "public_url", xmlns=xmlns)
            public_url.text = "true"
            tree = etree.ElementTree(root_node)

            buff = BytesIO()
            tree.write(buff)

            return buff.getvalue()

        try:
            urn = Urn(remote_path)

            if not self.check(urn.path()):
                raise RemoteResourceNotFound(urn.path())

            response = BytesIO()

            url = {'hostname': self.server_hostname, 'root': self.webdav_root, 'path': urn.quote()}
            options = {
                'CUSTOMREQUEST': Client.requests['publish'],
                'URL': "{hostname}{root}{path}".format(**url),
                'POSTFIELDS': data(for_server=self.server_hostname),
                'WRITEDATA': response
            }

            request = self.Request(options)

            request.perform()
            request.close()

            return parse(response)

        except pycurl.error as exception:
            raise NotConnection(exception.args[-1:])

    def unpublish(self, remote_path):

        def data(for_server):

            root = etree.Element("propertyupdate", xmlns="DAV:")
            remove = etree.SubElement(root, "remove")
            prop = etree.SubElement(remove, "prop")
            xmlns = Client.meta_xmlns.get(for_server, "")
            etree.SubElement(prop, "public_url", xmlns=xmlns)
            tree = etree.ElementTree(root)

            buff = BytesIO()
            tree.write(buff)

            return buff.getvalue()

        try:
            urn = Urn(remote_path)

            if not self.check(urn.path()):
                raise RemoteResourceNotFound(urn.path())

            response = BytesIO()

            url = {'hostname': self.server_hostname, 'root': self.webdav_root, 'path': urn.quote()}
            options = {
                'CUSTOMREQUEST': Client.requests['unpublish'],
                'URL': "{hostname}{root}{path}".format(**url),
                'POSTFIELDS': data(for_server=self.server_hostname),
                'WRITEDATA': response
            }

            request = self.Request(options)

            request.perform()
            request.close()

        except pycurl.error as exception:
            raise NotConnection(exception.args[-1:])

    def info(self, remote_path):

        def parse(response):

            response_str = response.getvalue()
            tree = etree.fromstring(response_str)

            find_attributes = {
                'created': ".//{DAV:}creationdate",
                'name': ".//{DAV:}displayname",
                'size': ".//{DAV:}getcontentlength",
                'modified': ".//{DAV:}getlastmodified"
            }

            info = dict()
            for (name, value) in find_attributes.items():
                info[name] = tree.findtext(value)

            return info

        try:
            urn = Urn(remote_path)

            if not self.check(urn.path()):
                raise RemoteResourceNotFound(urn.path())

            response = BytesIO()

            url = {'hostname': self.server_hostname, 'root': self.webdav_root, 'path': urn.quote()}
            options = {
                'CUSTOMREQUEST': Client.requests['info'],
                'URL': "{hostname}{root}{path}".format(**url),
                'HTTPHEADER': Client.http_header['info'],
                'WRITEDATA': response
            }

            request = self.Request(options)

            request.perform()
            request.close()

            return parse(response)

        except pycurl.error as exception:
            raise NotConnection(exception.args[-1:])

    def resource(self, remote_path):

        urn = Urn(remote_path)
        return Resource(self, urn)

    def get_property(self, remote_path, option):

        def parse(response, option):

            response_str = response.getvalue()
            tree = etree.fromstring(response_str)
            xpath = "{xpath_prefix}{xpath_exp}".format(xpath_prefix=".//", xpath_exp=option['name'])
            return tree.findtext(xpath)

        def data(option):
            root = etree.Element("propfind", xmlns="DAV:")
            prop = etree.SubElement(root, "prop")
            etree.SubElement(prop, option.get('name', ""), xmlns=option.get('namespace', ""))
            tree = etree.ElementTree(root)

            buff = BytesIO()

            tree.write(buff)
            return buff.getvalue()

        try:
            urn = Urn(remote_path)

            if not self.check(urn.path()):
                raise RemoteResourceNotFound(urn.path())

            response = BytesIO()

            url = {'hostname': self.server_hostname, 'root': self.webdav_root, 'path': urn.quote()}
            options = {
                'URL': "{hostname}{root}{path}".format(**url),
                'CUSTOMREQUEST': Client.requests['get_metadata'],
                'HTTPHEADER': Client.http_header['get_metadata'],
                'POSTFIELDS': data(option),
                'WRITEDATA': response
            }

            request = self.Request(options)

            request.perform()
            request.close()

            return parse(response, option)

        except pycurl.error as exception:
            raise NotConnection(exception.args[-1:])

    def set_property(self, remote_path, option):

        def data(option):

            root_node = etree.Element("propertyupdate", xmlns="DAV:")
            root_node.set('xmlns:u', option.get('namespace', ""))
            set_node = etree.SubElement(root_node, "set")
            prop_node = etree.SubElement(set_node, "prop")
            opt_node = etree.SubElement(prop_node, "{namespace}:{name}".format(namespace='u', name=option['name']))
            opt_node.text = option.get('value', "")

            tree = etree.ElementTree(root_node)

            buff = BytesIO()
            tree.write(buff)

            return buff.getvalue()

        try:
            urn = Urn(remote_path)

            if not self.check(urn.path()):
                raise RemoteResourceNotFound(urn.path())

            url = {'hostname': self.server_hostname, 'root': self.webdav_root, 'path': urn.quote()}
            options = {
                'URL': "{hostname}{root}{path}".format(**url),
                'CUSTOMREQUEST': Client.requests['set_metadata'],
                'HTTPHEADER': Client.http_header['set_metadata'],
                'POSTFIELDS': data(option)
            }

            request = self.Request(options)

            request.perform()
            request.close()

        except pycurl.error as exception:
            raise NotConnection(exception.args[-1:])

    def push(self, remote_directory, local_directory):

        def prune(src, exp):
            return [re.sub(exp, "", item) for item in src]

        urn = Urn(remote_directory)

        if not urn.is_directory():
            raise InvalidOption(name="remote_path", value=remote_directory)

        if not os.path.isdir(local_directory):
            raise InvalidOption(name="local_path", value=local_directory)

        if not os.path.exists(local_directory):
            raise LocalResourceNotFound(local_directory)

        paths = self.list(remote_directory)
        expression = "{begin}{end}".format(begin="^", end=remote_directory)
        remote_resource_names = prune(paths, expression)

        for local_resource_name in listdir(local_directory):

            local_path = os.path.join(local_directory, local_resource_name)
            remote_path = "{remote_directory}{resource_name}".format(remote_directory=urn.path(), resource_name=local_resource_name)

            if os.path.isdir(local_path):
                if not self.check(remote_path=remote_path):
                    self.mkdir(remote_path=remote_path)
                self.push(remote_directory=remote_path, local_directory=local_path)
            else:
                if local_resource_name in remote_resource_names:
                    continue
                self.upload_file(remote_path=remote_path, local_path=local_path)

    def pull(self, remote_directory, local_directory):

        def prune(src, exp):
            return [re.sub(exp, "", item) for item in src]

        urn = Urn(remote_directory)

        if not urn.is_directory():
            raise InvalidOption(name="remote_path", value=remote_directory)

        if not os.path.exists(local_directory):
            raise LocalResourceNotFound(local_directory)

        local_resource_names = listdir(local_directory)

        paths = self.list(remote_directory)
        expression = "{begin}{end}".format(begin="^", end=remote_directory)
        remote_resource_names = prune(paths, expression)

        for remote_resource_name in remote_resource_names:

            local_path = os.path.join(local_directory, remote_resource_name)
            remote_path = "{remote_directory}{resource_name}".format(remote_directory=urn.path(), resource_name=remote_resource_name)

            remote_urn = Urn(remote_path)

            if remote_urn.is_directory():
                if not os.path.exists(local_path):
                    os.mkdir(local_path)
                self.pull(remote_directory=remote_path, local_directory=local_path)
            else:
                if remote_resource_name in local_resource_names:
                    continue
                self.download_file(remote_path=remote_path, local_path=local_path)

    def sync(self, remote_directory, local_directory):

        self.pull(remote_directory=remote_directory, local_directory=local_directory)
        self.push(remote_directory=remote_directory, local_directory=local_directory)

class Resource(object):
    def __init__(self, client, urn):
        self.client = client
        self.urn = urn

    def __str__(self):
        return "resource {path}".format(path=self.urn.path())

    def rename(self, new_name):

        old_path = self.urn.path()
        parent_path = self.urn.parent()
        new_name = Urn(new_name).filename()
        new_path = "{directory}{filename}".format(directory=parent_path, filename=new_name)

        self.client.move(remote_path_from=old_path, remote_path_to=new_path)
        self.urn = Urn(new_path)

    def move(self, remote_path):

        new_urn = Urn(remote_path)
        self.client.move(remote_path_from=self.urn.path(), remote_path_to=new_urn.path())
        self.urn = new_urn

    def copy(self, remote_path):

        urn = Urn(remote_path)
        self.client.copy(remote_path_from=self.urn.path(), remote_path_to=remote_path)
        return Resource(self.client, urn)

    def info(self):
        return self.client.info(self.urn.path())

    def read_from(self, buff):
        self.client.upload_from(buff=buff, remote_path=self.urn.path())

    def read(self, local_path):
        self.client.upload_sync(local_path=local_path, remote_path=self.urn.path())

    def read_async(self, local_path, callback=None):
        self.client.upload_async(local_path=local_path, remote_path=self.urn.path(), callback=callback)

    def write_to(self, buff):
        self.client.download_to(buff=buff, remote_path=self.urn.path())

    def write(self, local_path):
        self.client.download_sync(local_path=local_path, remote_path=self.urn.path())

    def write_async(self, local_path, callback=None):
        self.client.download_async(local_path=local_path, remote_path=self.urn.path(), callback=callback)

    @property
    def property(self, option):
        return self.client.get_property(remote_path=self.urn.path(), option=option)

    @property.setter
    def property(self, option, value):
        option['value'] = value.__str__()
        self.client.set_property(remote_path=self.urn.path(), option=option)
