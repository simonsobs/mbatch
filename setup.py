#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""The setup script."""
from __future__ import print_function
import setuptools
from setuptools import find_packages, setup
import versioneer
import os, sys
import numpy as np
import glob

with open('README.rst') as readme_file:
    readme = readme_file.read()

with open('HISTORY.rst') as history_file:
    history = history_file.read()

requirements =  ['setuptools>=39',
                 'python_dateutil>=2.7',
                 'pyyaml>=5.0',
                 'pytest-cov>=2.6',
                 'coveralls>=1.5',
                 'pytest>=4.6',
                 'argunparse',
                 'prompt_toolkit']


test_requirements = ['pip>=9.0',
                     'bumpversion>=0.5.',
                     'wheel>=0.30',
                     'watchdog>=0.8',
                     'flake8>=3.5',
                     'coverage>=4.5',
                     'Sphinx>=1.7',
                     'twine>=1.10',
                     'setuptools>=39.2',
                     'python_dateutil>=2.7',
                     'cython>=0.28',
                     'pyyaml>=5.0',
                     'pytest-cov>=2.6',
                     'coveralls>=1.5',
                     'pytest>=4.6']
    
    
setup(
    author="Mathew Madhavacheril",
    author_email='mathewsyriac@gmail.com',
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Natural Language :: English',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
    ],
    description="mbatch",
    package_dir={"mbatch": "mbatch"},
    entry_points = {
    'console_scripts': ['mbatch=mbatch.mbatch:main','wmpi=mbatch.wmpi:main'],
    },
    install_requires=requirements,
    license="BSD license",
    long_description=readme + '\n\n' + history,
    package_data={'mbatch': ['mbatch/data/sites/*.yml']},
    include_package_data=True,    
    keywords='mbatch',
    name='mbatch',
    packages=find_packages(),
    test_suite='mbatch.tests',
    tests_require=test_requirements,
    url='https://github.com/msyriac/mbatch',
    version=versioneer.get_version(),
    zip_safe=False,
)

print('\n[setup.py request was successful.]')

