#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import setup, find_packages

setup(
    name     = 'webdavclient',
    version  = '0.2.9',
    packages = find_packages(),
    requires = ['python (>= 2.7.6)'],
    install_requires=['pycurl', 'lxml'],
    scripts = ['wdc'],
    description  = 'Webdav API, resource API and webdav tool for WebDAV services (Яндекс.Диск, Dropbox, Google Диск, Box и 4shared)',
    long_description = open('README.rst').read(),
    author = 'Designerror',
    author_email = 'designerror@yandex.ru',
    url          = 'https://github.com/designerror/webdavclient',
    download_url = 'https://github.com/designerror/webdavclient/tarball/master',
    license      = 'MIT License',
    keywords     = 'webdav, client, python, module, library, packet, Яндекс.Диск, Dropbox, Google Диск, Box, 4shared',
    classifiers  = [
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 3',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
)
