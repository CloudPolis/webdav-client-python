#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import setup, find_packages

setup(
    name     = 'webdav-client',
    version  = '0.1.1',
    packages = find_packages(),
    requires = ['python (>= 3.4.0)'],
    description  = 'Webdav client',
    long_description = open('README.md').read(), 
    author       = 'Oleg Postnikov',
    author_email = 'designerror@yandex.ru',
    url          = 'https://github.com/designerror/webdav-client',
    download_url = 'https://github.com/designerror/webdav-client/tarball/master',
    license      = 'MIT License',
    keywords     = 'webdav',
    classifiers  = [
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'Programming Language :: Python',
    ],
)
