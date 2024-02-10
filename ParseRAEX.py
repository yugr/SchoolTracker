#!/usr/bin/python3

# Copyright 2024 Yury Gribov
# 
# Use of this source code is governed by MIT license that can be
# found in the LICENSE.txt file.
#
# A helper tool to visualize info about public schools in Moscow.

import sys
import os
import os.path
import re
import subprocess
import argparse
import json
import atexit
import pprint
import string
import math

def warn(msg):
  sys.stderr.write('%s: warning: %s\n' % (me, msg))

def error(msg):
  sys.stderr.write('%s: error: %s\n' % (me, msg))
  sys.exit(1)

def ensure_module(module, package=None, user=True, quiet=False):
  """
  Installs module if it's missing. Call like
    ensure_module('configparser')
    ensure_module('wx', 'wxPython')
  """
  import site
  try:
    exec('import ' + module)
  except ImportError:
    if not quiet:
      print("Installing Python module %s..." % module)
    exe = sys.executable
    package = package or module
    try:
      import pip
    except ImportError:
        error("install python3-pip")
    subprocess.check_call(
      [exe, '-mpip', 'install'] + (['--user'] if user else []) + [package])
    # User site packages are often not in PATH by default
    for d in (site.getusersitepackages() if user else site.getsitepackages()):
      if d not in sys.path:
        sys.path.append(d)
    try:
      exec('import ' + module)
    except ImportError:
      error("module '%s' not found in package '%s'\n" % (module, package))

ensure_module('requests', user=True)
import requests

ensure_module('bs4', user=True)
from bs4 import BeautifulSoup

me = os.path.basename(__file__)
v = 0

def main():
  parser = argparse.ArgumentParser(description="A helper tool to convert RAEX rating to text form.",
                                   formatter_class=argparse.RawDescriptionHelpFormatter,
                                   epilog="""\

Examples:
  # Рейтинг лучших школ России по конкурентоспособности выпускников
  $ python3 {0} https://raex-rr.com/education/best_schools/top-100_russian_schools/2023/

  # Рейтинг школ по количеству выпускников, поступивших в ведущие вузы России
  $ python3 {0} https://raex-rr.com/education/schools_rating/top-300_schools/2023/
""".format(me))
  parser.add_argument('--verbose', '-v',
                      help="Print diagnostic info (can be specified more than once).",
                      action='count', default=0)
  parser.add_argument('weblink',
                      help="Path to rating page.", metavar='WEBLINK')

  args = parser.parse_args()

  global v
  v = args.verbose

#  html = open('index.html').read()
  html = requests.get(args.weblink).text

  s = BeautifulSoup(html, 'html.parser')

  # First parse header

  toc = {}
  for i, th in enumerate(s.table.thead.tr.find_all('th')):
    name = th.span.text
    if name in ('Название', 'Школа'):
      toc['Name'] = i
    elif name in ('Субъект федерации', 'Регион'):
      toc['Region'] = i
    elif name == 'Город':
      toc['City'] = i
    elif name == 'Балл':
      toc['Rating'] = i

  if v:
    print('TOC: %s' % toc)

  # Then process rows

  for tr in s.table.tbody.find_all('tr'):
    # Collect fields
    row = []
    for th in tr.find_all('th'):
      row.append(th['data-content'])
    for td in tr.find_all('td'):
      row.append(td['data-content'])

    if v:
      print(row)

    # Print in text format expected by SchoolTracker.py
    name = row[toc['Name']]
    region = row[toc['Region']]
    city = row[toc['City']]
    rating = row[toc['Rating']]
    print("%s\t%s\t%s\t%s" % (name, region, city, rating))

if __name__ == '__main__':
  sys.exit(main())
