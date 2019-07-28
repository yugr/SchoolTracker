#!/usr/bin/python3

# Copyright 2019 Yury Gribov
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

import imp, site

def ensure_module(module, package=None, user=True, quiet=False):
  """
  Installs module if it's missing. Call like
    ensure_module('configparser')
    ensure_module('wx', 'wxPython')
  """
  try:
    imp.find_module(module)
  except ImportError:
    if not quiet:
      print("Installing Python module %s..." % module)
    exe = sys.executable
    if package is None:
      package = module
    try:
      subprocess.check_call([exe, '-mensurepip'])
    except subprocess.CalledProcessError:
      warn("failed to ensure pip")
    subprocess.check_call(
      [exe, '-mpip', 'install'] + (['--user'] if user else []) + [package])
    # User site packages are often not in PATH by default
    for d in (site.getusersitepackages() if user else site.getsitepackages()):
      if d not in sys.path:
        sys.path.append(d)
    try:
      imp.find_module(module)
    except ImportError:
      error("module '%s' not found in package '%s'" % (module, package))

ensure_module('requests', user=True)
import requests

ensure_module('configparser', user=True)
import configparser

ensure_module('kdtree', user=True)
import kdtree

me = os.path.basename(__file__)
v = 0

def warn(msg):
  sys.stderr.write('%s: warning: %s\n' % (me, msg))

def error(msg):
  sys.stderr.write('%s: error: %s\n' % (me, msg))
  sys.exit(1)

class Re:
  """
  "Regex cacher" gets rid of temporary match objects e.g.
    if Re.match(...):
      x = Re.group(1)
  """

  _last_match = None

  @classmethod
  def match(self, *args, **kwargs):
    self._last_match = re.match(*args, **kwargs)
    return self._last_match

  @classmethod
  def search(self, *args, **kwargs):
    self._last_match = re.search(*args, **kwargs)
    return self._last_match

  @classmethod
  def fullmatch(self, *args, **kwargs):
    self._last_match = re.fullmatch(*args, **kwargs)
    return self._last_match

  @classmethod
  def group(self, *args, **kwargs):
    return self._last_match.group(*args, *kwargs)

  @classmethod
  def groups(self, *args, **kwargs):
    return self._last_match.groups(*args, **kwargs)

class School:
  def __init__(self, name, city, number, goodness):
    self.name = name
    self.city = city
    self.number = number
    self.goodness = goodness
    self.address = None
    self.coords = None
    self.station = None

  def __str__(self):
    parts = []
    parts.append("\"%s\" (rating %s" % (self.name, self.goodness))
    if self.number is not None:
      parts.append("#%d" % self.number)
    if self.address is None:
      parts.append("@" + self.city)
    else:
      parts.append("@%s" % self.address)
    if self.coords is not None:
      parts.append(", xy: %g %g" % (self.coords[0], self.coords[1]))
    if self.station is not None:
      parts.append(", metro \"%s\"" % self.station)
    return ', '.join(parts) + ')'

def parse_rating(file):
  idx = {}
  schools = []
  place = 0
  with open(file, 'r') as f:
    for line in f:
      line = re.sub(r'#.*', '', line)
      line = line.strip()
      if not line:
        continue
      place += 1
      # Parse line
      goodness = name = city = None
      if Re.match(r'^([0-9]+)\. +(.*) +\(([+-][0-9]+)\) *$', line):
        # Official rating (from schoolotzyv.ru)
        #   1. Школа №1535 (+1)
        goodness = int(Re.group(1))
        name = Re.group(2)
        city = 'Москва'
      elif Re.match(r'^(.*)\t([0-9]+)$', line):
        # Non-official rating from schoolotzyv.ru
        #   Школа №179 Москва	94
        goodness = int(Re.group(2))
        name = Re.group(1)
        city = 'Москва'
      elif Re.match(r'^[0-9]+[ \t]+([^\t]+)\t+([^\t]+\t+[^\t]+)\t+([0-9,]+)', line):
        # RAEX rating
        #   1 	Лицей НИУ ВШЭ 	Москва 	Москва 	1000,00
        name = Re.group(1)
        city = Re.group(2)
        goodness = float(Re.group(3).replace(',', '.'))
      else:
        warn("failed to parse school info:\n  %s" % line)
        continue
      name = re.sub(r'\s+', ' ', name.strip())
      city = re.sub(r'\s+', ' ', city.strip())
      # Extract school's number
      nums = re.findall(r'\b[0-9]+\b', name)
      if not nums:
        warn("missing school number: %s" % name)
        num = None
      elif len(nums) > 1:
        warn("too many school numbers, school will be ignored: %s" % name)
        continue
      else:
        num = int(nums[0])
      schools.append(School(name, city, num, goodness))
      if num is not None:
        idx[num] = schools[-1]
  return schools, idx

def _print_response(r):
  s = json.dumps(r, sort_keys=True, indent=4, separators=(',', ': '))
  sys.stderr.write('%s\n' % s)

def load_locations(file):
  cache = {}
  with open(file, 'r') as f:
    i = iter(f)
    for line in f:
      query = line.strip()
      if not query:
          break
      address = next(i).strip()
      coords = eval(next(i).strip())
      cache[query] = address, coords
  return cache

def save_locations(cache, file):
  with open(file, 'w') as f:
    for query, (address, coords) in sorted(cache.items()):
      f.write('%s\n%s\n%s\n' % (query, address, coords))

def locate_school(s, cfg):
  if not hasattr(locate_school, 'cache'):
    # TODO: read cache from curdir
    cache_file = 'coords.txt'
    if os.path.exists(cache_file):
      cache = load_locations(cache_file)
    else:
      cache = {}
    setattr(locate_school, 'cache', cache)
    atexit.register(save_locations, cache, cache_file)
  cache = getattr(locate_school, 'cache')

  query = s.name + ' ' + s.city
  if query in cache:
    if v:
      sys.stderr.write("Reading from cache: '%s'\n" % query)
    address, coords = cache[query]
  else:
    if v:
      sys.stderr.write("Not in cache: '%s'\n" % query)
#    params = {
#      'apikey'  : cfg['API']['jsapi_key'],
#      'geocode' : query,
#      'format' : 'json',
#      'lang' : 'en_RU',
#    }

    params = {
      'apikey' : cfg['API']['search_api_key'],
      'text' : query,
      'type' : 'biz',
      'lang' : 'ru_RU',
      'll'   : '37.618920,55.756994',
      'spn'  : '0.552069,0.400552',
    }

    verify = cfg['API']['verify']
    verify = verify.lower() not in ('false', '0', 'n', 'no')

#    r = requests.post('https://geocode-maps.yandex.ru/1.x',
#                      params=params, verify=verify)
    r = requests.get('https://search-maps.yandex.ru/v1',
                     params=params, verify=verify)
    if v:
      sys.stderr.write("Geocode send query: %s\n" % r.url)
    if r.status_code != 200:
      msg = r.json()['message']
      warn("Geocode query failed with HTTP code %d: %s" % (r.status_code, msg))
      return
    r = r.json()
    if v:
      _print_response(r)
    res0 = r['features'][0]
    address = res0['properties']['description']
    coords = res0['geometry']['coordinates']
    cache[query] = address, coords

  s.address = address
  s.coords = coords

class Station:
  def __init__(self, name, line, coords):
    self.name = name
    self.line = line
    self.coords = coords

  def __str__(self):
    return "%s (%s, @%g %g)" % (self.name, self.line,
                                self.coords[0], self.coords[1])

  # For kdtree
  def __len__(self):
    return len(self.coords)

  # For kdtree
  def __getitem__(self, i):
    return self.coords[i]

def load_metro_map(metro_file):
  stations = []
  with open(metro_file, 'r') as f:
    data = json.load(f)
  for line in data['lines']:
    for station in line['stations']:
      coords = [float(station['lng']), float(station['lat'])]
      s = Station(station['name'], line['name'], coords)
      stations.append(s)
  metro_map = kdtree.create(stations)
  return stations, metro_map

def assign_metros(schools, station_map):
  for s in schools:
    # Spherical coords are not Euclidean but ok for out purposes
    tree, _ = station_map.search_nn(s.coords)
    assert tree, "failed to locate station"
    s.station = tree.data

def main():
  parser = argparse.ArgumentParser(description="A helper tool to visualize info about public schools in Moscow.",
                                   formatter_class=argparse.RawDescriptionHelpFormatter,
                                   epilog="""\
Examples:
  $ python {0} ratings/raex/top300.2019.txt settings.ini
""".format(me))
#  parser.add_argument('--flag', '-f',
#                      help="Describe flag here.",
#                      dest='flag', action='store_true', default=False)
#  parser.add_argument('--no-flag',
#                      help="Inverse of --flag.",
#                      dest='flag', action='store_false')
#  parser.add_argument('--param', '-p',
#                      help="Describe scalar parameter here.",
#                      default='0')
#  parser.add_argument('--multi', '-m',
#                      help="Describe array parameter here (can be specified more than once).",
#                      action='append')
  parser.add_argument('--verbose', '-v',
                      help="Print diagnostic info (can be specified more than once).",
                      action='count', default=0)
  parser.add_argument('rating_file',
                      help="Text file with rating.", metavar='RATING')
  parser.add_argument('settings_file',
                      help="Settings .ini file.", metavar='SETTINGS.INI')

  args = parser.parse_args()

  global v
  v = args.verbose

  cfg = configparser.ConfigParser(inline_comment_prefixes=';')
  if not cfg.read(args.settings_file):
    error("failed to parse config file %s" % args.settings_file)

  schools, idx = parse_rating(args.rating_file)
  schools = list(filter(lambda s: 'Москва' in s.city, schools))
  for s in schools:
    locate_school(s, cfg)

  stations, station_map = load_metro_map('maps/moscow_metro.json')

#  print("Stations:")
#  for s in stations:
#    print("  %s" % s)

  assign_metros(schools, station_map)

  print("Schools:")
  for s in schools:
    print("  %s" % s)

  # TODO:
  # * generate map/report

  return 0

if __name__ == '__main__':
  sys.exit(main())
