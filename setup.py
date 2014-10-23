#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import setup, find_packages

setup(
    name     = 'webdavclient',
    version  = '0.1.3',
    packages = find_packages(),
    requires = ['python (>= 3.4.0)'],
    description  = 'Webdav API, resource API and webdav tool for Webdav services (Yandex.Disk)',
    long_description = open('README.rst').read(), 
    author       = 'Oleg Postnikov',
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
