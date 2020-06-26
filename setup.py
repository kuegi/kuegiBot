#!/usr/bin/env python
from setuptools import setup, find_packages
from os.path import dirname, join

import kuegi_bot


here = dirname(__file__)


setup(name='kuegi-bot',
      version=kuegi_bot.__version__,
      description='Cryptobot for executing multiple strategies',
      url='https://github.com/kuegi/kuegiBot',
      long_description=open(join(here, 'README.md')).read(),
      long_description_content_type='text/markdown',
      author='Kuegi',
      author_email='mythosMatheWG@gmail.com',
      install_requires=[
          'requests',
          'websocket-client',
          'future',
          'plotly',
          'bybit'
      ],
      packages=find_packages(),
      scripts=["backtest.py","history_crawler.py","cryptobot.py"],
      classifiers=["Development Status :: 3 - Alpha" ]
      )
