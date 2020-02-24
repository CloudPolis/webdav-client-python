from webdav.exceptions import *
from webdav.urn import Urn
from os.path import exists


class ConnectionSettings:

    def is_valid(self):
        pass

    def valid(self):

        try:
            self.is_valid()
        except OptionNotValid:
            return False
        else:
            return True


class WebDAVSettings(ConnectionSettings):
    ns = "webdav:"
    prefix = "webdav_"
    keys = {'hostname', 'login', 'password', 'bearertoken', 'oauthtoken', 'root', 'cert_path', 'key_path', 'recv_speed',
            'send_speed', 'verbose'}

    def __init__(self, options):

        self.options = dict()

        for key in self.keys:
            value = options.get(key, '')
            self.options[key] = value
            self.__dict__[key] = value

        self.root = Urn(self.root).quote() if self.root else ''
        self.root = self.root.rstrip(Urn.separate)

    def is_valid(self):

        if not self.hostname:
            raise OptionNotValid(name="hostname", value=self.hostname, ns=self.ns)

        if self.cert_path and not exists(self.cert_path):
            raise OptionNotValid(name="cert_path", value=self.cert_path, ns=self.ns)

        if self.key_path and not exists(self.key_path):
            raise OptionNotValid(name="key_path", value=self.key_path, ns=self.ns)

        if self.key_path and not self.cert_path:
            raise OptionNotValid(name="cert_path", value=self.cert_path, ns=self.ns)

        if self.password and not self.login:
            raise OptionNotValid(name="login", value=self.login, ns=self.ns)

        if not self.bearertoken and not self.login:
            raise OptionNotValid(name="login", value=self.login, ns=self.ns)

        if not self.oauthtoken and not self.login:
            raise OptionNotValid(name="login", value=self.login, ns=self.ns)


class ProxySettings(ConnectionSettings):
    ns = "proxy:"
    prefix = "proxy_"
    keys = {'hostname', 'login', 'password'}

    def __init__(self, options):

        self.options = dict()

        for key in self.keys:
            value = options.get(key, '')
            self.options[key] = value
            self.__dict__[key] = value

    def is_valid(self):

        if self.password and not self.login:
            raise OptionNotValid(name="login", value=self.login, ns=self.ns)

        if self.login or self.password:
            if not self.hostname:
                raise OptionNotValid(name="hostname", value=self.hostname, ns=self.ns)
