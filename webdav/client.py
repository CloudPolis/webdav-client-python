# -*- coding: utf-8

import pycurl
import os
import shutil
import threading
import lxml.etree as etree
from io import BytesIO
from re import sub
from webdav.connection import *
from webdav.exceptions import *
from webdav.urn import Urn

try:
    from urllib.parse import unquote
except ImportError:
    from urllib import unquote

__version__ = "1.0.8"


def listdir(directory):

    file_names = list()
    for filename in os.listdir(directory):
        file_path = os.path.join(directory, filename)
        if os.path.isdir(file_path):
            filename = "{filename}{separate}".format(filename=filename, separate=os.path.sep)
        file_names.append(filename)
    return file_names


def add_options(request, options):

    for (key, value) in options.items():
        if value is None:
            continue
        try:
            request.setopt(pycurl.__dict__[key], value)
        except TypeError:
            raise OptionNotValid(key, value)
        except pycurl.error:
            raise OptionNotValid(key, value)


def get_options(type, from_options):

    _options = dict()

    for key in type.keys:
        key_with_prefix = "{prefix}{key}".format(prefix=type.prefix, key=key)
        if key not in from_options and key_with_prefix not in from_options:
            _options[key] = ""
        elif key in from_options:
            _options[key] = from_options.get(key)
        else:
            _options[key] = from_options.get(key_with_prefix)

    return _options


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
        'check': ["Accept: */*"],
        'info': ["Accept: */*", "Depth: 1"],
        'get_metadata': ["Accept: */*", "Depth: 1", "Content-Type: application/x-www-form-urlencoded"],
        'set_metadata': ["Accept: */*", "Depth: 1", "Content-Type: application/x-www-form-urlencoded"]
    }

    def get_header(self, method):

        if method in Client.http_header:
            try:
                header = Client.http_header[method].copy()
            except AttributeError:
                header = Client.http_header[method][:]
        else:
            header = list()

        if self.webdav.token:
            webdav_token = "Authorization: OAuth {token}".format(token=self.webdav.token)
            header.append(webdav_token)

        return header

    requests = {
        'copy': "COPY",
        'move': "MOVE",
        'mkdir': "MKCOL",
        'clean': "DELETE",
        'check': "HEAD",
        'list': "PROPFIND",
        'free': "PROPFIND",
        'info': "PROPFIND",
        'publish': "PROPPATCH",
        'unpublish': "PROPPATCH",
        'published': "PROPPATCH",
        'get_metadata': "PROPFIND",
        'set_metadata': "PROPPATCH"
    }

    meta_xmlns = {
        'https://webdav.yandex.ru': "urn:yandex:disk:meta",
    }

    def __init__(self, options):

        webdav_options = get_options(type=WebDAVSettings, from_options=options)
        proxy_options = get_options(type=ProxySettings, from_options=options)

        self.webdav = WebDAVSettings(webdav_options)
        self.proxy = ProxySettings(proxy_options)

        pycurl.global_init(pycurl.GLOBAL_DEFAULT)

        self.default_options = {}

    def __del__(self):
        pycurl.global_cleanup()

    def valid(self):
        return True if self.webdav.valid() and self.proxy.valid() else False

    def Request(self, options=None):

        curl = pycurl.Curl()

        self.default_options.update({
            'URL': self.webdav.hostname,
            'NOBODY': 1,
            'SSLVERSION': pycurl.SSLVERSION_TLSv1,
        })

        if not self.webdav.token:
            server_token = '{login}:{password}'.format(login=self.webdav.login, password=self.webdav.password)
            self.default_options.update({
                'USERPWD': server_token,
            })

        if self.proxy.valid():
            if self.proxy.hostname:
                self.default_options['PROXY'] = self.proxy.hostname

            if self.proxy.login:
                if not self.proxy.password:
                    self.default_options['PROXYUSERNAME'] = self.proxy.login
                else:
                    proxy_token = '{login}:{password}'.format(login=self.proxy.login, password=self.proxy.password)
                    self.default_options['PROXYUSERPWD'] = proxy_token

        if self.webdav.cert_path:
            self.default_options['SSLCERT'] = self.webdav.cert_path

        if self.webdav.key_path:
            self.default_options['SSLKEY'] = self.webdav.key_path

        if self.webdav.recv_speed:
            self.default_options['MAX_RECV_SPEED_LARGE'] = self.webdav.recv_speed

        if self.webdav.send_speed:
            self.default_options['MAX_SEND_SPEED_LARGE'] = self.webdav.send_speed

        if self.webdav.verbose:
            self.default_options['VERBOSE'] = self.webdav.verbose
        
        if self.default_options:
            add_options(curl, self.default_options)

        if options:
            add_options(curl, options)

        return curl

    def list(self, remote_path=root):

        def parse(response):

            try:
                response_str = response.getvalue()
                tree = etree.fromstring(response_str)
                hrees = [unquote(hree.text) for hree in tree.findall(".//{DAV:}href")]
                return [Urn(hree) for hree in hrees]
            except etree.XMLSyntaxError:
                return list()

        try:
            directory_urn = Urn(remote_path, directory=True)

            if directory_urn.path() != Client.root:
                if not self.check(directory_urn.path()):
                    raise RemoteResourceNotFound(directory_urn.path())

            response = BytesIO()

            url = {'hostname': self.webdav.hostname, 'root': self.webdav.root, 'path': directory_urn.quote()}
            options = {
                'URL': "{hostname}{root}{path}".format(**url),
                'CUSTOMREQUEST': Client.requests['list'],
                'HTTPHEADER': self.get_header('list'),
                'WRITEDATA': response,
                'NOBODY': 0
            }

            request = self.Request(options=options)

            request.perform()
            request.close()

            urns = parse(response)

            path = "{root}{path}".format(root=self.webdav.root, path=directory_urn.path())
            return [urn.filename() for urn in urns if urn.path() != path and urn.path() != path[:-1]]

        except pycurl.error:
            raise NotConnection(self.webdav.hostname)

    def free(self):

        def parse(response):

            try:
                response_str = response.getvalue()
                tree = etree.fromstring(response_str)
                node = tree.find('.//{DAV:}quota-available-bytes')
                if node is not None:
                    return int(node.text)
                else:
                    raise MethodNotSupported(name='free', server=self.webdav.hostname)
            except TypeError:
                raise MethodNotSupported(name='free', server=self.webdav.hostname)
            except etree.XMLSyntaxError:
                return str()

        def data():

            root = etree.Element("propfind", xmlns="DAV:")
            prop = etree.SubElement(root, "prop")
            etree.SubElement(prop, "quota-available-bytes")
            etree.SubElement(prop, "quota-used-bytes")
            tree = etree.ElementTree(root)
            buff = BytesIO()
            tree.write(buff)
            return buff.getvalue()

        try:
            response = BytesIO()

            options = {
                'CUSTOMREQUEST': Client.requests['free'],
                'HTTPHEADER': self.get_header('free'),
                'POSTFIELDS': data(),
                'WRITEDATA': response,
                'NOBODY': 0
            }

            request = self.Request(options=options)

            request.perform()
            request.close()

            return parse(response)

        except pycurl.error:
            raise NotConnection(self.webdav.hostname)

    def check(self, remote_path=root):

        try:
            urn = Urn(remote_path)
            response = BytesIO()

            url = {'hostname': self.webdav.hostname, 'root': self.webdav.root, 'path': urn.quote()}
            options = {
                'URL': "{hostname}{root}{path}".format(**url),
                'CUSTOMREQUEST': Client.requests['check'],
                'HTTPHEADER': self.get_header('check'),
                'WRITEDATA': response,
                'NOBODY': 1
            }

            request = self.Request(options=options)

            request.perform()
            code = request.getinfo(pycurl.HTTP_CODE)
            request.close()

            if int(code) == 200:
                return True
        
            return False

        except pycurl.error:
            raise NotConnection(self.webdav.hostname)

    def mkdir(self, remote_path):

        try:
            directory_urn = Urn(remote_path, directory=True)

            if not self.check(directory_urn.parent()):
                raise RemoteParentNotFound(directory_urn.path())

            url = {'hostname': self.webdav.hostname, 'root': self.webdav.root, 'path': directory_urn.quote()}
            options = {
                'URL': "{hostname}{root}{path}".format(**url),
                'CUSTOMREQUEST': Client.requests['mkdir'],
                'HTTPHEADER': self.get_header('mkdir')
            }

            request = self.Request(options=options)

            request.perform()
            request.close()

        except pycurl.error:
            raise NotConnection(self.webdav.hostname)

    def download_to(self, buff, remote_path):

        try:
            urn = Urn(remote_path)

            if self.is_dir(urn.path()):
                raise OptionNotValid(name="remote_path", value=remote_path)

            if not self.check(urn.path()):
                raise RemoteResourceNotFound(urn.path())

            url = {'hostname': self.webdav.hostname, 'root': self.webdav.root, 'path': urn.quote()}
            options = {
                'URL': "{hostname}{root}{path}".format(**url),
                'WRITEFUNCTION': buff.write,
                'HTTPHEADER': self.get_header('download_to'),
                'NOBODY': 0
            }

            request = self.Request(options=options)

            request.perform()
            request.close()

        except pycurl.error:
            raise NotConnection(self.webdav.hostname)

    def download(self, remote_path, local_path, progress=None):

        urn = Urn(remote_path)
        if self.is_dir(urn.path()):
            self.download_directory(local_path=local_path, remote_path=remote_path, progress=progress)
        else:
            self.download_file(local_path=local_path, remote_path=remote_path, progress=progress)

    def download_directory(self, remote_path, local_path, progress=None):

        urn = Urn(remote_path, directory=True)

        if not self.is_dir(urn.path()):
            raise OptionNotValid(name="remote_path", value=remote_path)

        if os.path.exists(local_path):
            shutil.rmtree(local_path)

        os.makedirs(local_path)

        for resource_name in self.list(urn.path()):
            _remote_path = "{parent}{name}".format(parent=urn.path(), name=resource_name)
            _local_path = os.path.join(local_path, resource_name)
            self.download(local_path=_local_path, remote_path=_remote_path, progress=progress)

    def download_file(self, remote_path, local_path, progress=None):

        try:
            urn = Urn(remote_path)

            if self.is_dir(urn.path()):
                raise OptionNotValid(name="remote_path", value=remote_path)

            if os.path.isdir(local_path):
                raise OptionNotValid(name="local_path", value=local_path)

            if not self.check(urn.path()):
                raise RemoteResourceNotFound(urn.path())

            with open(local_path, 'wb') as local_file:

                url = {'hostname': self.webdav.hostname, 'root': self.webdav.root, 'path': urn.quote()}
                options = {
                    'URL': "{hostname}{root}{path}".format(**url),
                    'HTTPHEADER': self.get_header('download_file'),
                    'WRITEDATA': local_file,
                    'NOPROGRESS': 0 if progress else 1,
                    'NOBODY': 0
                }

                if progress:
                   options["PROGRESSFUNCTION"] = progress

                request = self.Request(options=options)

                request.perform()
                request.close()

        except pycurl.error:
            raise NotConnection(self.webdav.hostname)

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

            if urn.is_dir():
                raise OptionNotValid(name="remote_path", value=remote_path)

            if not self.check(urn.parent()):
                raise RemoteParentNotFound(urn.path())

            url = {'hostname': self.webdav.hostname, 'root': self.webdav.root, 'path': urn.quote()}
            options = {
                'URL': "{hostname}{root}{path}".format(**url),
                'HTTPHEADER': self.get_header('upload_from'),
                'UPLOAD': 1,
                'READFUNCTION': buff.read,
            }

            request = self.Request(options=options)

            request.perform()
            code = request.getinfo(pycurl.HTTP_CODE)
            if code == "507":
                raise NotEnoughSpace()

            request.close()

        except pycurl.error:
            raise NotConnection(self.webdav.hostname)

    def upload(self, remote_path, local_path, progress=None):

        if os.path.isdir(local_path):
            self.upload_directory(local_path=local_path, remote_path=remote_path, progress=progress)
        else:
            self.upload_file(local_path=local_path, remote_path=remote_path, progress=progress)

    def upload_directory(self, remote_path, local_path, progress=None):

        urn = Urn(remote_path, directory=True)

        if not urn.is_dir():
            raise OptionNotValid(name="remote_path", value=remote_path)

        if not os.path.isdir(local_path):
            raise OptionNotValid(name="local_path", value=local_path)

        if not os.path.exists(local_path):
            raise LocalResourceNotFound(local_path)

        if self.check(urn.path()):
            self.clean(urn.path())

        self.mkdir(remote_path)

        for resource_name in listdir(local_path):
            _remote_path = "{parent}{name}".format(parent=urn.path(), name=resource_name)
            _local_path = os.path.join(local_path, resource_name)
            self.upload(local_path=_local_path, remote_path=_remote_path, progress=progress)

    def upload_file(self, remote_path, local_path, progress=None):

        try:
            if not os.path.exists(local_path):
                raise LocalResourceNotFound(local_path)

            urn = Urn(remote_path)

            if urn.is_dir():
                raise OptionNotValid(name="remote_path", value=remote_path)

            if os.path.isdir(local_path):
                raise OptionNotValid(name="local_path", value=local_path)

            if not self.check(urn.parent()):
                raise RemoteParentNotFound(urn.path())

            with open(local_path, "rb") as local_file:

                url = {'hostname': self.webdav.hostname, 'root': self.webdav.root, 'path': urn.quote()}
                options = {
                    'URL': "{hostname}{root}{path}".format(**url),
                    'HTTPHEADER': self.get_header('upload_file'),
                    'UPLOAD': 1,
                    'READFUNCTION': local_file.read,
                    'NOPROGRESS': 0 if progress else 1
                }

                if progress:
                   options["PROGRESSFUNCTION"] = progress

                file_size = os.path.getsize(local_path)
                if file_size > self.large_size:
                    options['INFILESIZE_LARGE'] = file_size
                else:
                    options['INFILESIZE'] = file_size

                request = self.Request(options=options)

                request.perform()
                code = request.getinfo(pycurl.HTTP_CODE)
                if code == "507":
                    raise NotEnoughSpace()

                request.close()

        except pycurl.error:
            raise NotConnection(self.webdav.hostname)

    def upload_sync(self, remote_path, local_path, callback=None):

        self.upload(local_path=local_path, remote_path=remote_path)

        if callback:
            callback()

    def upload_async(self, remote_path, local_path, callback=None):

        target = (lambda: self.upload_sync(local_path=local_path, remote_path=remote_path, callback=callback))
        threading.Thread(target=target).start()

    def copy(self, remote_path_from, remote_path_to):

        def header(remote_path_to):

            path = Urn(remote_path_to).path()
            destination = "{root}{path}".format(root=self.webdav.root, path=path)
            header_item = "Destination: {destination}".format(destination=destination)

            header = self.get_header('copy')
            header.append(header_item)

            return header

        try:
            urn_from = Urn(remote_path_from)

            if not self.check(urn_from.path()):
                raise RemoteResourceNotFound(urn_from.path())

            urn_to = Urn(remote_path_to)

            if not self.check(urn_to.parent()):
                raise RemoteParentNotFound(urn_to.path())

            url = {'hostname': self.webdav.hostname, 'root': self.webdav.root, 'path': urn_from.quote()}
            options = {
                'URL': "{hostname}{root}{path}".format(**url),
                'CUSTOMREQUEST': Client.requests['copy'],
                'HTTPHEADER': header(remote_path_to)
            }

            request = self.Request(options=options)

            request.perform()
            request.close()

        except pycurl.error:
            raise NotConnection(self.webdav.hostname)

    def move(self, remote_path_from, remote_path_to):

        def header(remote_path_to):

            path = Urn(remote_path_to).path()
            destination = "{root}{path}".format(root=self.webdav.root, path=path)
            header_item = "Destination: {destination}".format(destination=destination)
            header = self.get_header('move')
            header.append(header_item)
            return header

        try:
            urn_from = Urn(remote_path_from)

            if not self.check(urn_from.path()):
                raise RemoteResourceNotFound(urn_from.path())

            urn_to = Urn(remote_path_to)

            if not self.check(urn_to.parent()):
                raise RemoteParentNotFound(urn_to.path())

            url = {'hostname': self.webdav.hostname, 'root': self.webdav.root, 'path': urn_from.quote()}
            options = {
                'URL': "{hostname}{root}{path}".format(**url),
                'CUSTOMREQUEST': Client.requests['move'],
                'HTTPHEADER': header(remote_path_to)
            }

            request = self.Request(options=options)

            request.perform()
            request.close()

        except pycurl.error:
            raise NotConnection(self.webdav.hostname)

    def clean(self, remote_path):

        try:
            urn = Urn(remote_path)

            url = {'hostname': self.webdav.hostname, 'root': self.webdav.root, 'path': urn.quote()}
            options = {
                'URL': "{hostname}{root}{path}".format(**url),
                'CUSTOMREQUEST': Client.requests['clean'],
                'HTTPHEADER': self.get_header('clean')
            }

            request = self.Request(options=options)

            request.perform()
            request.close()

        except pycurl.error:
            raise NotConnection(self.webdav.hostname)

    def publish(self, remote_path):

        def parse(response):

            try:
                response_str = response.getvalue()
                tree = etree.fromstring(response_str)
                result = tree.xpath("//*[local-name() = 'public_url']")
                public_url = result[0]
                return public_url.text
            except IndexError:
                raise MethodNotSupported(name="publish", server=self.webdav.hostname)
            except etree.XMLSyntaxError:
                return ""

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

            url = {'hostname': self.webdav.hostname, 'root': self.webdav.root, 'path': urn.quote()}
            options = {
                'URL': "{hostname}{root}{path}".format(**url),
                'CUSTOMREQUEST': Client.requests['publish'],
                'HTTPHEADER': self.get_header('publish'),
                'POSTFIELDS': data(for_server=self.webdav.hostname),
                'WRITEDATA': response,
                'NOBODY': 0
            }

            request = self.Request(options=options)

            request.perform()
            request.close()

            return parse(response)

        except pycurl.error:
            raise NotConnection(self.webdav.hostname)

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

            url = {'hostname': self.webdav.hostname, 'root': self.webdav.root, 'path': urn.quote()}
            options = {
                'URL': "{hostname}{root}{path}".format(**url),
                'CUSTOMREQUEST': Client.requests['unpublish'],
                'HTTPHEADER': self.get_header('unpublish'),
                'POSTFIELDS': data(for_server=self.webdav.hostname)
            }

            request = self.Request(options=options)

            request.perform()
            request.close()

        except pycurl.error:
            raise NotConnection(self.webdav.hostname)

    def info(self, remote_path):

        def parse(response, path):

            try:
                response_str = response.getvalue()
                tree = etree.fromstring(response_str)

                find_attributes = {
                    'created': ".//{DAV:}creationdate",
                    'name': ".//{DAV:}displayname",
                    'size': ".//{DAV:}getcontentlength",
                    'modified': ".//{DAV:}getlastmodified"
                }

                resps = tree.findall("{DAV:}response")

                for resp in resps:
                    href = resp.findtext("{DAV:}href")
                    urn = unquote(href)

                    if path[-1] == Urn.separate:
                        if not path == urn:
                            continue
                    else:
                        path_with_sep = "{path}{sep}".format(path=path, sep=Urn.separate)
                        if not path == urn and not path_with_sep == urn:
                            continue

                    info = dict()
                    for (name, value) in find_attributes.items():
                        info[name] = resp.findtext(value)
                    return info

                raise RemoteResourceNotFound(path)
            except etree.XMLSyntaxError:
                raise MethodNotSupported(name="info", server=self.webdav.hostname)

        try:
            urn = Urn(remote_path)
            response = BytesIO()

            if not self.check(urn.path()) and not self.check(Urn(remote_path, directory=True).path()):
                raise RemoteResourceNotFound(remote_path)

            url = {'hostname': self.webdav.hostname, 'root': self.webdav.root, 'path': urn.quote()}
            options = {
                'URL': "{hostname}{root}{path}".format(**url),
                'CUSTOMREQUEST': Client.requests['info'],
                'HTTPHEADER': self.get_header('info'),
                'WRITEDATA': response,
                'NOBODY': 0
            }

            request = self.Request(options=options)

            request.perform()
            request.close()

            path = "{root}{path}".format(root=self.webdav.root, path=urn.path())

            return parse(response, path)

        except pycurl.error:
            raise NotConnection(self.webdav.hostname)

    def is_dir(self, remote_path):

        def parse(response, path):

            try:
                response_str = response.getvalue()
                tree = etree.fromstring(response_str)

                resps = tree.findall("{DAV:}response")

                for resp in resps:
                    href = resp.findtext("{DAV:}href")
                    urn = unquote(href)

                    if path[-1] == Urn.separate:
                        if not path == urn:
                            continue
                    else:
                        path_with_sep = "{path}{sep}".format(path=path, sep=Urn.separate)
                        if not path == urn and not path_with_sep == urn:
                            continue
                    type = resp.find(".//{DAV:}resourcetype")
                    if type is None:
                        raise MethodNotSupported(name="is_dir", server=self.webdav.hostname)
                    dir_type = type.find("{DAV:}collection")

                    return True if dir_type is not None else False

                raise RemoteResourceNotFound(path)

            except etree.XMLSyntaxError:
                raise MethodNotSupported(name="is_dir", server=self.webdav.hostname)

        try:
            urn = Urn(remote_path)
            parent_urn = Urn(urn.parent())
            if not self.check(urn.path()) and not self.check(Urn(remote_path, directory=True).path()):
                raise RemoteResourceNotFound(remote_path)

            response = BytesIO()

            url = {'hostname': self.webdav.hostname, 'root': self.webdav.root, 'path': parent_urn.quote()}
            options = {
                'URL': "{hostname}{root}{path}".format(**url),
                'CUSTOMREQUEST': Client.requests['info'],
                'HTTPHEADER': self.get_header('info'),
                'WRITEDATA': response,
                'NOBODY': 0
            }

            request = self.Request(options=options)

            request.perform()
            request.close()

            path = "{root}{path}".format(root=self.webdav.root, path=urn.path())

            return parse(response, path)

        except pycurl.error:
            raise NotConnection(self.webdav.hostname)

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

            url = {'hostname': self.webdav.hostname, 'root': self.webdav.root, 'path': urn.quote()}
            options = {
                'URL': "{hostname}{root}{path}".format(**url),
                'CUSTOMREQUEST': Client.requests['get_metadata'],
                'HTTPHEADER': self.get_header('get_metadata'),
                'POSTFIELDS': data(option),
                'WRITEDATA': response,
                'NOBODY': 0
            }

            request = self.Request(options=options)

            request.perform()
            request.close()

            return parse(response, option)

        except pycurl.error:
            raise NotConnection(self.webdav.hostname)

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

            url = {'hostname': self.webdav.hostname, 'root': self.webdav.root, 'path': urn.quote()}
            options = {
                'URL': "{hostname}{root}{path}".format(**url),
                'CUSTOMREQUEST': Client.requests['set_metadata'],
                'HTTPHEADER': self.get_header('get_metadata'),
                'POSTFIELDS': data(option)
            }

            request = self.Request(options=options)

            request.perform()
            request.close()

        except pycurl.error:
            raise NotConnection(self.webdav.hostname)

    def push(self, remote_directory, local_directory):

        def prune(src, exp):
            return [sub(exp, "", item) for item in src]

        urn = Urn(remote_directory, directory=True)

        if not self.is_dir(urn.path()):
            raise OptionNotValid(name="remote_path", value=remote_directory)

        if not os.path.isdir(local_directory):
            raise OptionNotValid(name="local_path", value=local_directory)

        if not os.path.exists(local_directory):
            raise LocalResourceNotFound(local_directory)

        paths = self.list(urn.path())
        expression = "{begin}{end}".format(begin="^", end=urn.path())
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
            return [sub(exp, "", item) for item in src]

        urn = Urn(remote_directory, directory=True)

        if not self.is_dir(urn.path()):
            raise OptionNotValid(name="remote_path", value=remote_directory)

        if not os.path.exists(local_directory):
            raise LocalResourceNotFound(local_directory)

        local_resource_names = listdir(local_directory)

        paths = self.list(urn.path())
        expression = "{begin}{end}".format(begin="^", end=remote_directory)
        remote_resource_names = prune(paths, expression)

        for remote_resource_name in remote_resource_names:

            local_path = os.path.join(local_directory, remote_resource_name)
            remote_path = "{remote_directory}{resource_name}".format(remote_directory=urn.path(), resource_name=remote_resource_name)

            remote_urn = Urn(remote_path)

            if self.is_dir(remote_urn.path()):
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

    def is_dir(self):
        return self.client.is_dir(self.urn.path())

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

    def info(self, params=None):

        info = self.client.info(self.urn.path())
        if not params:
            return info

        return {key: value for (key, value) in info.items() if key in params}

    def clean(self):
        return self.client.clean(self.urn.path())

    def check(self):
        return self.client.check(self.urn.path())

    def read_from(self, buff):
        self.client.upload_from(buff=buff, remote_path=self.urn.path())

    def read(self, local_path):
        return self.client.upload_sync(local_path=local_path, remote_path=self.urn.path())

    def read_async(self, local_path, callback=None):
        return self.client.upload_async(local_path=local_path, remote_path=self.urn.path(), callback=callback)

    def write_to(self, buff):
        return self.client.download_to(buff=buff, remote_path=self.urn.path())

    def write(self, local_path):
        return self.client.download_sync(local_path=local_path, remote_path=self.urn.path())

    def write_async(self, local_path, callback=None):
        return self.client.download_async(local_path=local_path, remote_path=self.urn.path(), callback=callback)

    def publish(self):
        return self.client.publish(self.urn.path())

    def unpublish(self):
        return self.client.unpublish(self.urn.path())

    @property
    def property(self, option):
        return self.client.get_property(remote_path=self.urn.path(), option=option)

    @property.setter
    def property(self, option, value):
        option['value'] = value.__str__()
        self.client.set_property(remote_path=self.urn.path(), option=option)
