# -*- coding: utf-8

import pycurl
import os
import math
import shutil
import threading
import lxml.etree as etree
import sys
from io import BytesIO
from re import sub
from webdav.connection import *
from webdav.exceptions import *
from webdav.urn import Urn

try:
    from urllib.parse import unquote
except ImportError:
    from urllib import unquote

__version__ = "0.5.8"

def listdir(directory):

    file_names = list()
    for filename in os.listdir(directory):
        filepath = os.path.join(directory, filename)
        if os.path.isdir(filepath):
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

def get_options(type, options):

    _options = dict()

    for key in type.keys:
        key_with_prefix = "{prefix}{key}".format(prefix=type.prefix, key=key)
        if not key in options and not key_with_prefix in options:
            _options[key] = ""
        elif key in options:
            _options[key] = options.get(key)
        else:
            _options[key] = options.get(key_with_prefix)

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

    round = 0
    percent = 0

    def default_progress_download(self, download_t, download_d, upload_t, upload_d):
        self.default_progress(current=download_d, total=download_t)

    def default_progress_upload(self, download_t, download_d, upload_t, upload_d):
        self.default_progress(current=upload_d, total=upload_t)

    def bar_thermometer(self, current, total, width=80):
        avail_dots = width-2
        shaded_dots = int(math.floor(float(current) / total * avail_dots))
        return '[' + '='*(shaded_dots-1) + '>' + ' '*(avail_dots-shaded_dots) + ']'

    def default_progress(self, current, total, width=80):

        if not total or total < 0:
            msg = "%s / unknown" % current
            if len(msg) < width:
                return msg
            if len("%s" % current) < width:
                return "%s" % current

        min_width = {
          'percent': 4,
          'bar': 3,      # [=]
          'size': len("%s" % total)*2 + 3,
        }
        priority = ['percent', 'bar', 'size']

        selected = []
        avail = width
        for field in priority:
            if min_width[field] < avail:
                selected.append(field)
                avail -= min_width[field]+1

        output = ''
        for field in selected:

            if field == 'percent':
                # fixed size width for percentage
                output += ('%s%%' % (100 * current // total)).rjust(min_width['percent'])
            elif field == 'bar':  # [. ]
                # bar takes its min width + all available space
                output += self.bar_thermometer(current=current, total=total, width=min_width['bar']+avail)
            elif field == 'size':
                # size field has a constant width (min == max)
                output += ("%s / %s" % (current, total)).rjust(min_width['size']-1)

            selected = selected[1:]
            if selected:
                output += ' '

        sys.stdout.write("\r" + output)

    def __init__(self, options):

        webdav_options = get_options(WebDAVSettings, options)
        proxy_options = get_options(ProxySettings, options)

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

        host = "Host: {host}".format(host=self.webdav.hostname)

        webdav_token = '{login}:{password}'.format(login=self.webdav.login, password=self.webdav.password)
        self.default_options.update({
            'SSL_VERIFYPEER': 0,
            'SSL_VERIFYHOST': 0,
            'URL': self.webdav.hostname,
            'USERPWD': webdav_token,
            'HTTPHEADER': list(host),
            'NOBODY': 1
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

            host = "Host: {host}".format(host=self.webdav.hostname)
            headers = Client.http_header['list']
            headers = headers[:]
            #headers.append(host)

            url = {'hostname': self.webdav.hostname, 'root': self.webdav.root, 'path': directory_urn.quote()}
            options = {
                'CUSTOMREQUEST': Client.requests['list'],
                'URL': "{hostname}{root}{path}".format(**url),
                'HTTPHEADER': headers,
                'WRITEDATA': response,
                'NOBODY': 0
            }

            request = self.Request(options=options)

            request.perform()
            request.close()

            urns = parse(response)

            path = "{root}{path}".format(root=self.webdav.root, path=directory_urn.path())
            return [urn.filename() for urn in urns if urn.path() != path]

        except pycurl.error as exception:
            raise NotConnection(exception.args[-1:])

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

            host = "Host: {host}".format(host=self.webdav.hostname)
            headers = Client.http_header['free']
            headers = headers[:]
           # headers.append(host)

            options = {
                'CUSTOMREQUEST': Client.requests['free'],
                'HTTPHEADER': headers,
                'POSTFIELDS': data(),
                'WRITEDATA': response,
                'NOBODY': 1
            }

            request = self.Request(options)

            request.perform()
            request.close()

            return parse(response)

        except pycurl.error as exception:
            raise NotConnection(exception.args[-1:])

    def check(self, remote_path=root):

        def parse(response, path):

            try:
                response_str = response.getvalue()
                tree = etree.fromstring(response_str)

                resps = tree.findall("{DAV:}response")

                for resp in resps:
                    href = resp.findtext("{DAV:}href")

                    if not href == path:
                        continue
                    else:
                        return True

                return False

            except etree.XMLSyntaxError:
                raise MethodNotSupported(name="check", server=self.webdav.hostname)

        try:
            urn = Urn(remote_path)
            parent_urn = Urn(urn.parent())
            response = BytesIO()

            host = "Host: {host}".format(host=self.webdav.hostname)
            headers = Client.http_header['info']
            headers = headers[:]
            #headers.append(host)

            url = {'hostname': self.webdav.hostname, 'root': self.webdav.root, 'path': parent_urn.quote()}
            options = {
                'CUSTOMREQUEST': Client.requests['info'],
                'URL': "{hostname}{root}{path}".format(**url),
                'HTTPHEADER': headers,
                'WRITEDATA': response,
                'NOBODY': 0
            }

            request = self.Request(options)

            request.perform()
            request.close()

            path = "{root}{path}".format(root=self.webdav.root, path=urn.path())

            return parse(response, path)

        except pycurl.error as exception:
            raise NotConnection(exception.args[-1:])

    def mkdir(self, remote_path):

        try:
            directory_urn = Urn(remote_path, directory=True)

            if not self.check(directory_urn.parent()):
                raise RemoteParentNotFound(directory_urn.path())

            host = "Host: {host}".format(host=self.webdav.hostname)
            headers = Client.http_header['mkdir']
            headers = headers[:]
            #headers.append(host)

            url = {'hostname': self.webdav.hostname, 'root': self.webdav.root, 'path': directory_urn.quote()}
            options = {
                'CUSTOMREQUEST': Client.requests['mkdir'],
                'URL': "{hostname}{root}{path}".format(**url),
                'HTTPHEADER': headers
            }

            request = self.Request(options)

            request.perform()
            request.close()

        except pycurl.error as exception:
            raise NotConnection(exception.args[-1:])

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
                'NOBODY': 0
            }

            request = self.Request(options)

            request.perform()
            request.close()

        except pycurl.error as exception:
            raise NotConnection(exception.args[-1:])

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
                    'WRITEDATA': local_file,
                    'NOPROGRESS': 0 if progress else 1,
                    'NOBODY': 0
                }

                if progress:
                   options["PROGRESSFUNCTION"] = progress

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

            if urn.is_dir():
                raise OptionNotValid(name="remote_path", value=remote_path)

            if not self.check(urn.parent()):
                raise RemoteParentNotFound(urn.path())

            url = {'hostname': self.webdav.hostname, 'root': self.webdav.root, 'path': urn.quote()}
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

    def upload(self, remote_path, local_path, progress=None):

        if os.path.isdir(local_path):
            self.upload_directory(local_path=local_path, remote_path=remote_path, progress=progress)
        else:
            self.upload_file(local_path=local_path, remote_path=remote_path, progress=progress)

    def upload_directory(self, remote_path, local_path, progress=None):

        urn = Urn(remote_path, directory=True)

        if urn.is_dir():
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

            if not os.path.exists(local_path):
                raise LocalResourceNotFound(local_path)

            if not self.check(urn.parent()):
                raise RemoteParentNotFound(urn.path())

            with open(local_path, "rb") as local_file:

                url = {'hostname': self.webdav.hostname, 'root': self.webdav.root, 'path': urn.quote()}
                options = {
                    'UPLOAD': 1,
                    'URL': "{hostname}{root}{path}".format(**url),
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

            path = Urn(remote_path_to).path()
            destination = "{root}{path}".format(root=self.webdav.root, path=path)
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

            host = "Host: {host}".format(host=self.webdav.hostname)
            headers = header(remote_path_to)
            #headers.append(host)

            url = {'hostname': self.webdav.hostname, 'root': self.webdav.root, 'path': urn_from.quote()}
            options = {
                'CUSTOMREQUEST': Client.requests['copy'],
                'URL': "{hostname}{root}{path}".format(**url),
                'HTTPHEADER': headers
            }

            request = self.Request(options)

            request.perform()
            request.close()

        except pycurl.error as exception:
            raise NotConnection(exception.args[-1:])

    def move(self, remote_path_from, remote_path_to):

        def header(remote_path_to):

            path = Urn(remote_path_to).path()
            destination = "{root}{path}".format(root=self.webdav.root, path=path)
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

            host = "Host: {host}".format(host=self.webdav.hostname)
            headers = header(remote_path_to)
            #headers.append(host)

            url = {'hostname': self.webdav.hostname, 'root': self.webdav.root, 'path': urn_from.quote()}
            options = {
                'CUSTOMREQUEST': Client.requests['move'],
                'URL': "{hostname}{root}{path}".format(**url),
                'HTTPHEADER': headers
            }

            request = self.Request(options)

            request.perform()
            request.close()

        except pycurl.error as exception:
            raise NotConnection(exception.args[-1:])

    def clean(self, remote_path):

        try:
            urn = Urn(remote_path)
            host = "Host: {host}".format(host=self.webdav.hostname)
            headers = Client.http_header['clean']
            headers = headers[:]
            #headers.append(host)
            url = {'hostname': self.webdav.hostname, 'root': self.webdav.root, 'path': urn.quote()}
            options = {
                'CUSTOMREQUEST': Client.requests['clean'],
                'URL': "{hostname}{root}{path}".format(**url),
                'HTTPHEADER': headers
            }

            request = self.Request(options)

            request.perform()
            request.close()

        except pycurl.error as exception:
            raise NotConnection(exception.args[-1:])

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
                'CUSTOMREQUEST': Client.requests['publish'],
                'URL': "{hostname}{root}{path}".format(**url),
                'POSTFIELDS': data(for_server=self.webdav.hostname),
                'WRITEDATA': response,
                'NOBODY': 0
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

            url = {'hostname': self.webdav.hostname, 'root': self.webdav.root, 'path': urn.quote()}
            options = {
                'CUSTOMREQUEST': Client.requests['unpublish'],
                'URL': "{hostname}{root}{path}".format(**url),
                'POSTFIELDS': data(for_server=self.webdav.hostname)
            }

            request = self.Request(options)

            request.perform()
            request.close()

        except pycurl.error as exception:
            raise NotConnection(exception.args[-1:])

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

                    if path[-1] == Urn.separate:
                        if not path == href:
                            continue
                    else:
                        path_with_sep = "{path}{sep}".format(path=path, sep=Urn.separate)
                        if not path == href and not path_with_sep == href:
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

            host = "Host: {host}".format(host=self.webdav.hostname)
            headers = Client.http_header['info']
            headers = headers[:]
            #headers.append(host)

            url = {'hostname': self.webdav.hostname, 'root': self.webdav.root, 'path': urn.quote()}
            options = {
                'CUSTOMREQUEST': Client.requests['info'],
                'URL': "{hostname}{root}{path}".format(**url),
                'HTTPHEADER': headers,
                'WRITEDATA': response,
                'NOBODY': 0
            }

            request = self.Request(options)

            request.perform()
            request.close()

            path = "{root}{path}".format(root=self.webdav.root, path=urn.path())

            return parse(response, path)

        except pycurl.error as exception:
            raise NotConnection(exception.args[-1:])

    def is_dir(self, remote_path):

        def parse(response, path):

            try:
                response_str = response.getvalue()
                tree = etree.fromstring(response_str)

                resps = tree.findall("{DAV:}response")

                for resp in resps:
                    href = resp.findtext("{DAV:}href")

                    if path[-1] == Urn.separate:
                        if not path == href:
                            continue
                    else:
                        path_with_sep = "{path}{sep}".format(path=path, sep=Urn.separate)
                        if not path == href and not path_with_sep == href:
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

            host = "Host: {host}".format(host=self.webdav.hostname)
            headers = Client.http_header['info']
            headers = headers[:]
            #headers.append(host)

            url = {'hostname': self.webdav.hostname, 'root': self.webdav.root, 'path': parent_urn.quote()}
            options = {
                'CUSTOMREQUEST': Client.requests['info'],
                'URL': "{hostname}{root}{path}".format(**url),
                'HTTPHEADER': headers,
                'WRITEDATA': response,
                'NOBODY': 0
            }

            request = self.Request(options)

            request.perform()
            request.close()

            path = "{root}{path}".format(root=self.webdav.root, path=urn.path())

            return parse(response, path)

        except pycurl.error as exception:
            raise NotConnection(exception.args[-1:])

    def resource(self, remote_path):

        urn = Urn(remote_path)
        return Resource(self, urn.path())

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
                'HTTPHEADER': Client.http_header['get_metadata'],
                'POSTFIELDS': data(option),
                'WRITEDATA': response,
                'NOBODY': 0
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

            host = "Host: {host}".format(host=self.webdav.hostname)
            headers = Client.http_header['set_metadata']
            headers = headers[:]
            #headers.append(host)

            url = {'hostname': self.webdav.hostname, 'root': self.webdav.root, 'path': urn.quote()}
            options = {
                'URL': "{hostname}{root}{path}".format(**url),
                'CUSTOMREQUEST': Client.requests['set_metadata'],
                'HTTPHEADER': headers,
                'POSTFIELDS': data(option)
            }

            request = self.Request(options)

            request.perform()
            request.close()

        except pycurl.error as exception:
            raise NotConnection(exception.args[-1:])

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
