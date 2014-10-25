#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import setup, find_packages

setup(
    name     = 'webdavclient',
    version  = '0.1.17',
    packages = find_packages(),
    requires = ['python (>= 2.7.6)'],
    description  = 'Webdav API, resource API and webdav tool for WebDAV services (Яндекс.Диск, Dropbox, Google Диск, Box и 4shared)',
    long_description = open('README.rst').read(),
    author = 'Designerror',
    author_email = 'designerror@yandex.ru',
    url          = 'https://github.com/designerror/webdavclient',
    download_url = 'https://github.com/designerror/webdavclient/tarball/master',
    license      = 'MIT License',
    keywords     = 'webdav',
    classifiers  = [
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'Programming Language :: Python',
    ],
)
