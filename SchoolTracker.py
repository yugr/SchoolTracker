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
import string

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
  "Holds various info about school."

  def __init__(self, name, city, number, rating):
    self.name = name
    self.city = city
    self.number = number
    self.rating = rating
    self.address = None
    self.coords = None
    self.station = None

  def __str__(self):
    parts = []
    parts.append("\"%s\" (rating %s" % (self.name, self.rating))
    if self.number is not None:
      parts.append("#%d" % self.number)
    if self.address is None:
      parts.append("@" + self.city)
    else:
      parts.append("@%s" % self.address)
    if self.coords is not None:
      parts.append("xy: %g %g" % (self.coords[0], self.coords[1]))
    if self.station is not None:
      parts.append("м. %s" % self.station)
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
      rating = name = city = None
      if Re.match(r'^([0-9]+)\. +(.*) +\(([+-][0-9]+)\) *$', line):
        # Official rating (from schoolotzyv.ru)
        #   1. Школа №1535 (+1)
        rating = -int(Re.group(1))
        name = Re.group(2)
        city = 'Москва'
      elif Re.match(r'^(.*)\t([0-9]+)$', line):
        # Non-official rating from schoolotzyv.ru
        #   Школа №179 Москва	94
        rating = int(Re.group(2))
        name = Re.group(1)
        city = 'Москва'
      elif Re.match(r'^[0-9]+[ \t]+([^\t]+)\t+([^\t]+\t+[^\t]+)\t+([0-9,]+)', line):
        # RAEX rating
        #   1 	Лицей НИУ ВШЭ 	Москва 	Москва 	1000,00
        name = Re.group(1)
        city = Re.group(2)
        rating = float(Re.group(3).replace(',', '.'))
      else:
        warn("failed to parse school info:\n  %s" % line)
        continue
      name = re.sub(r'\s+', ' ', name.strip())
      city = re.sub(r'\s+', ' ', city.strip())
      # Extract school's number
      nums = re.findall(r'\b[0-9]+\b', name)
      if not nums:
#        warn("missing school number: %s" % name)
        num = None
      elif len(nums) > 1:
#        warn("too many school numbers: %s" % name)
        num = None
      else:
        num = int(nums[0])
      schools.append(School(name, city, num, rating))
      if num is not None:
        idx[num] = schools[-1]
  return schools, idx

def load_locations(file):
  "Load query cache from disk."
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
  "Save query cache to disk."
  with open(file, 'w') as f:
    for query, (address, coords) in sorted(cache.items()):
      f.write('%s\n%s\n%s\n' % (query, address, coords))

def _print_response(r):
  "Helper for debug print."
  s = json.dumps(r, sort_keys=True, indent=4, separators=(',', ': '))
  sys.stderr.write('%s\n' % s)

def locate_school(s, cfg):
  "Find school location via Yandex API."

  if not hasattr(locate_school, 'cache'):
    cache_file = '.cache.txt'
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
  "Holds info about metro station."

  def __init__(self, name, line, coords):
    self.name = name
    self.line = line
    self.coords = coords

  def __str__(self):
    return "%s (%s)" % (self.name, self.line)

  # For kdtree
  def __len__(self):
    return len(self.coords)

  # For kdtree
  def __getitem__(self, i):
    return self.coords[i]

def load_metro_map(metro_file):
  "Loads metro info from disk."
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
  "Find nearest metro for each school."
  for s in schools:
    # Spherical coords are not Euclidean but ok for out purposes
    tree, _ = station_map.search_nn(s.coords)
    assert tree, "failed to locate station"
    s.station = tree.data

def rating_to_color(r, rmin, rmax):
  "Helper for gen_js_code."
  alpha = float(r - rmin) / (rmax - rmin)
#  A = (0, 0, 0)
#  B = (255, 255, 255)
  A = (255, 255, 255)
  B = (255, 0, 0)
  C = []
  for a, b in zip(A, B):
    c = round(b * alpha + a * (1 - alpha))
    C.append(c)
  return '%02x%02x%02x' % (*C,)

def generate_webpage(schools, html_file, js_file, cfg):
  "Generate Yandex map with marks."

  # HTML

  with open('templates/Schools.tpl', 'r') as t:
    html_code = string.Template(t.read()).substitute(API_KEY=cfg['API']['jsapi_key'])

  with open(html_file, 'w') as f:
    f.write(html_code)

  # JS

  parts = []
  rmin = float('inf')
  rmax = float('-inf')
  for s in schools:
    rmin = min(rmin, s.rating)
    rmax = max(rmax, s.rating)
  for s in schools:
    parts.append('''\
      .add(new ymaps.Placemark([%g, %g], {
          iconCaption: '%s',
          balloonContent: 'Рейтинг %s, %s'
      }, {
          preset: 'islands#greenDotIconWithCaption',
          iconColor: '#%s'
      }))
''' % (s.coords[1], s.coords[0],
       s.number if s.number is not None else s.name,
       s.rating,
       s.address,
       rating_to_color(s.rating, rmin, rmax)))

  with open('templates/marks.js.tpl', 'r') as t:
    js_code = string.Template(t.read()).substitute(MARKS=''.join(parts))

  with open(js_file, 'w') as f:
    f.write(js_code)

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
  parser.add_argument('--min-rating', '-m',
                      help="Only consider schools with rating above this threshold.",
                      type=float,
                      default=float('-inf'))
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
  num_all_schools = len(schools)
  schools = list(filter(lambda s: 'Москва' in s.city, schools))
  schools = list(filter(lambda s: s.rating >= args.min_rating, schools))
  num_moscow_schools = len(schools)
  if num_all_schools != num_moscow_schools:
    warn("filtered %d non-Moscow"
         "schools (out of %d)" % (num_all_schools - num_moscow_schools,
                                  num_all_schools))
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

  # TODO: sort schools by station

  generate_webpage(schools, 'Schools.html', 'marks.js', cfg)

  return 0

if __name__ == '__main__':
  sys.exit(main())
