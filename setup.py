# -*- coding: utf8 -*-
from __future__ import unicode_literals

import re

from setuptools import setup, find_packages

def get_version(filename):
    content = open(filename).read()
    metadata = dict(re.findall("__([a-z]+)__ = '([^']+)'", content))
    return metadata['version']

setup(
    name='Mopidy-Local-ZODB',
    version=get_version('mopidy_local_zodb/__init__.py'),
    url='https://github.com/perrinjerome/mopidy-local-zodb',
    license='Apache License, Version 2.0',
    author='Jérome Perrin',
    author_email='perrinjerome@gmail.com',
    description='ZODB local library extension',
    long_description=open('README.rst').read(),
    packages=find_packages(exclude=['tests', 'tests.*']),
    zip_safe=False,
    include_package_data=True,
    install_requires=[
        'setuptools',
        'Mopidy >= 0.18',
        'ZODB',
    ],
    test_suite='nose.collector',
    tests_require=[
        'nose',
        'mock >= 1.0',
    ],
    entry_points={
        b'mopidy.ext': [
            'local-zodb = mopidy_local_zodb:Extension',
        ],
    },
    classifiers=[
        'Environment :: No Input/Output (Daemon)',
        'Intended Audience :: End Users/Desktop',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 2',
        'Topic :: Multimedia :: Sound/Audio :: Players',
    ],
)
