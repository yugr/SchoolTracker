#!/usr/bin/python3

# Copyright 2019-2023 Yury Gribov
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

ensure_module('kdtree', user=True)
import kdtree

ensure_module('xlrd', user=True)
import xlrd

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

class City:
  def __init__(self, name, lat, lng, lat_span, lng_span):
    self.name = name
    self.lat = lat
    self.lng = lng
    self.lat_span = lat_span
    self.lng_span = lng_span

city_map = {
  'Москва' : City('Москва', 55.756994, 37.618920, 0.400552, 0.552069)
}

class House:
  "Holds info about house."

  def __init__(self, address, lat, lng):
    self.address = address
    self.lat = lat
    self.lng = lng

  def __str__(self):
    return "%s (%f, %f)" % (self.address, self.lat, self.lng)

class School:
  "Holds various info about school."

  def __init__(self, name, city, number, rating):
    self.name = name
    self.city = city
    self.number = number
    self.rating = rating
    self.address = None
    self.lat = self.lng = None
    self.station = None
    self.houses = []

  def __str__(self):
    parts = []
    parts.append("'%s' (rating %s" % (self.name, self.rating))
    if self.number is not None:
      parts.append("#%d" % self.number)
    if self.address is None:
      parts.append("@" + self.city)
    else:
      parts.append("@%s" % self.address)
    if self.lat is not None:
      parts.append("xy: %f %f" % (self.lat, self.lng))
    if self.station is not None:
      # TODO: distance
      parts.append("м. %s" % self.station)
    return ', '.join(parts) + ')'

  @property
  def short_name(self):
    return self.number if self.number is not None else self.name

def km2lat(km):
  # Based on https://gis.stackexchange.com/questions/142326/calculating-longitude-length-in-miles
  return km / 111

def km2lng(km, lat):
  # Based on https://gis.stackexchange.com/questions/142326/calculating-longitude-length-in-miles
  return km2lat(km) / math.cos(math.pi / 2 * lat / 90)

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
      if Re.match(r'^([0-9]+)\. +(.*) +\((?:[+-][0-9]+|0)\) *$', line):
        # Official rating (from schoolotzyv.ru)
        #   1. Школа №1535 (+1)
        rating = -int(Re.group(1))
        name = Re.group(2)
        city = 'Москва'
      elif Re.match(r'^(.*)\t([0-9.]+)$', line):
        # Non-official rating from schoolotzyv.ru
        #   Школа №179 Москва	94
        rating = int(float(Re.group(2)))
        name = Re.group(1)
        city = 'Москва'
      elif Re.match(r'^[0-9]+[ \t]+([^\t]+)\t+([^\t]+\t+[^\t]+)\t+([0-9,.]+)', line):
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
        num = int(nums[0])
      else:
        num = int(nums[0])
        # TODO: add rename table
        if num == 1567:
          num = 67
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

def locate_address(query, args, is_org, lat, lng, lat_span, lng_span):
  "Find location via Yandex API."

  if not hasattr(locate_address, 'cache'):
    cache_file = '.cache.txt'
    if os.path.exists(cache_file):
      cache = load_locations(cache_file)
    else:
      cache = {}
    setattr(locate_address, 'cache', cache)
    atexit.register(save_locations, cache, cache_file)
  cache = getattr(locate_address, 'cache')

  if query in cache:
    if v:
      sys.stderr.write("Reading from cache: '%s'\n" % query)
    address, coords = cache[query]
  else:
    if v:
      sys.stderr.write("Not in cache: '%s'\n" % query)

    if args.cache_only:
      warn("address '%s' not in cache, skipping" % query)
      return None, None, None

    params = {
      'apikey' : args.places_key,
      'text' : query,
      'type' : 'biz' if is_org else 'geo',
      'lang' : 'ru_RU',
      'll'   : ('%f,%f' % (lng, lat)),
      'spn'  : ('%f,%f' % (lng_span, lat_span))
    }

    r = requests.get('https://search-maps.yandex.ru/v1',
                     params=params, verify=args.verify)
    if v:
      sys.stderr.write("Geocode send query: %s\n" % r.url)
    if r.status_code != 200:
      msg = r.json()['message']
      warn("Geocode query failed with HTTP code %d: %s" % (r.status_code, msg))
      return None, None, None
    r = r.json()
    if v:
      _print_response(r)
    if not len(r['features']):
      warn("Failed to locate '%s'" % query)
      return None, None, None
    res0 = r['features'][0]
    if is_org:
      address = res0['properties']['description']
    else:
      # For 'geo' mode address is split across 'name' and 'description' fields
      props = res0['properties']
      address = props['name'] + ', ' + props['description']
    coords = res0['geometry']['coordinates']
    cache[query] = address, coords

  return address, coords[1], coords[0]  # Geocoder has longitude first

class Station:
  "Holds info about metro station."

  def __init__(self, name, line, lat, lng):
    self.name = name
    self.line = line
    self.lat = lat
    self.lng = lng

  def __str__(self):
    return "%s (%s)" % (self.name, self.line)

  # For kdtree
  def __len__(self):
    return 2

  # For kdtree
  def __getitem__(self, i):
    return self.lat if i == 0 else self.lng

def load_metro_map(metro_file):
  "Loads metro info from disk."
  stations = []
  with open(metro_file, 'r') as f:
    data = json.load(f)
  for line in data['lines']:
    for station in line['stations']:
      s = Station(station['name'], line['name'], float(station['lat']), float(station['lng']))
      stations.append(s)
  metro_map = kdtree.create(stations)
  return stations, metro_map

def assign_metros(schools, station_map):
  "Find nearest metro for each school."
  for s in schools:
    # Spherical coords are not Euclidean but ok for out purposes
    tree, _ = station_map.search_nn((s.lat, s.lng))
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

def generate_webpage(schools, html_file, js_file, args):
  "Generate Yandex map with marks."

  # HTML

  with open('templates/Schools.tpl', 'r') as t:
    html_code = string.Template(t.read()).substitute(API_KEY=args.jsapi_key)

  with open(html_file, 'w') as f:
    f.write(html_code)

  # JS

  parts = []
  rmin = float('inf')
  rmax = float('-inf')
  for s in schools:
    rmin = min(rmin, s.rating)
    rmax = max(rmax, s.rating)

  # First plot the houses
  for s in schools:
    for h in s.houses:
      parts.append('''\
     .add(new ymaps.Placemark([%f, %f], {
          balloonContent: '%s',
        }, {
          preset: 'islands#circleIcon',
          iconColor: '#0080FF'
        }))
''' % (h.lat, h.lng,
       h.address + ' (школа %s)' % s.short_name))

  # Then schools on top
  for s in schools:
    parts.append('''\
      .add(new ymaps.Placemark([%f, %f], {
          iconCaption: '%s',
          balloonContent: 'Рейтинг %s, %s'
      }, {
          preset: 'islands#greenDotIconWithCaption',
          iconColor: '#%s'
      }))
''' % (s.lat, s.lng,
       s.short_name,
       s.rating,
       s.address,
       rating_to_color(s.rating, rmin, rmax)))

  with open('templates/marks.js.tpl', 'r') as t:
    js_code = string.Template(t.read()).substitute(MARKS=''.join(parts))

  with open(js_file, 'w') as f:
    f.write(js_code)

def main():
  parser = argparse.ArgumentParser(description="A helper tool to visualize info about public schools.",
                                   formatter_class=argparse.RawDescriptionHelpFormatter,
                                   epilog="""\

Examples:
  # XXX and YYY need to be replaced with your API tokens
  $ python {0} --jsapi-key XXX --places-key YYY ratings/raex/top300.2019.txt
""".format(me))
  parser.add_argument('--cache-only',
                      help="Do not use Yandex API (only consult previously cache data).",
                      dest='cache_only', action='store_true', default=False)
  parser.add_argument('--no-cache_only',
                      help="Inverse of --cache-only.",
                      dest='cache_only', action='store_false')
  parser.add_argument('--verify',
                      help="Verify SSL certificates",
                      dest='verify', action='store_true', default=True)
  parser.add_argument('--no-verify',
                      help="Do not verify SSL certificates.",
                      dest='verify', action='store_false')
  parser.add_argument('--city', '-c',
                      help="Skip schools not in CITY (default is 'Москва').",
                      default='Москва')
  parser.add_argument('--skip-schools',
                      help="Ignore schools that match regex.")
  parser.add_argument('--min-rating', '-m',
                      help="Only consider schools with rating above MIN_RATING.",
                      type=float,
                      default=float('-inf'))
  parser.add_argument('--print-schools', '-p',
                      help="Print school info.",
                      action='store_true', default=False)
  parser.add_argument('--print-metro-map',
                      help="Print schools near each metro station.",
                      action='store_true', default=False)
  parser.add_argument('--house-map',
                      help="House-school mapping.")
  parser.add_argument('--jsapi-key',
                      help="Token for JavaScript/Geocoder API "
                           "(https://yandex.ru/dev/maps/jsapi)")
  parser.add_argument('--places-key',
                      help="Token for Places API "
                           "(https://yandex.ru/dev/maps/geosearch)")
  parser.add_argument('--verbose', '-v',
                      help="Print diagnostic info (can be specified more than once).",
                      action='count', default=0)
  parser.add_argument('rating_file',
                      help="Text file with rating.", metavar='RATING')

  args = parser.parse_args()

  global v
  v = args.verbose

  if not args.jsapi_key:
    error("specify --jsapi-key via command-line")

  if not args.places_key:
    error("specify --places-key via command-line")

  city = city_map.get(args.city, None)
  if city is None:
    error("unknown city '%s'" % args.city)

  schools, school_idx = parse_rating(args.rating_file)
  num_all_schools = len(schools)
  schools = list(filter(lambda s: city.name in s.city, schools))
  num_city_schools = len(schools)
  if num_all_schools != num_city_schools:
    warn("filtered %d schools not in \'%s\' (out of %d)"
         % (num_all_schools - num_city_schools,
            city.name, num_all_schools))
  schools = list(filter(lambda s: s.rating >= args.min_rating, schools))
  num_rated_schools = len(schools)
  if num_rated_schools != num_city_schools:
    warn("filtered %d schools with rating below %s (out of %d)"
         % (num_city_schools - num_rated_schools,
            args.min_rating, num_all_schools))
  if args.skip_schools:
    skip_schools = re.compile(args.skip_schools)
    schools = list(filter(lambda s: not skip_schools.search(s.name), schools))
    num_whitelist_schools = len(schools)
    if num_whitelist_schools != num_rated_schools:
      warn("filtered %d blacklisted schools (out of %d)"
           % (num_rated_schools - num_whitelist_schools,
              num_all_schools))
  for s in schools:
    s.address, s.lat, s.lng = locate_address(s.name + ' ' + s.city, args, True,
                                             city.lat, city.lng,
                                             city.lat_span, city.lng_span)
  schools = [s for s in schools if s.address is not None]

  if args.house_map is not None:
    wb = xlrd.open_workbook(args.house_map)
    for sht in wb.sheets():
      if Re.match(r'^([0-9]+)-', sht.name):
        num = int(Re.group(1))
        s = school_idx.get(num, None)
        if s is None:
          warn("%s: unknown school no. %d" % (args.house_map, num))
          continue
        for r in range(sht.nrows):
          address = str(sht.cell(r, 0)).strip('\'')
          # E.g. "Юго-Западный / Ленинский пр-кт, д.62/1"
          if not Re.match(r'^.+ \/ (.*)', address):
            warn("%s: unknown house address format: %s" % (args.house_map, address))
            continue
          lat_span = km2lat(4)
          lng_span = km2lng(4, s.lat)
          address, lat, lng = locate_address(Re.group(1) + ' ' + city.name, args, False,
                                             s.lat, s.lng, lat_span, lng_span)
          if address is not None:
            s.houses.append(House(address, lat, lng))

  stations, station_map = load_metro_map('maps/moscow_metro.json')
  if v:
    print("Stations:")
    for s in stations:
      print("  %s" % s)

  assign_metros(schools, station_map)

  if args.print_schools:
    print("Schools:")
    for s in schools:
      print("  %s" % s)

  if args.print_metro_map:
    # Build map ...
    line_idx = {}
    for s in schools:
      st = s.station
      station_idx = line_idx.setdefault(st.line, {})
      station_idx.setdefault(st.name, []).append(s)

    # ... and print it
    print("Metro map:")
    for line, station_idx in sorted(line_idx.items()):
      print("  %s" % line)
      for station_name, station_schools in sorted(station_idx.items()):
        print("    %s" % station_name)
        for s in station_schools:
          print("     %s" % s)

  generate_webpage(schools, 'Schools.html', 'marks.js', args)

  return 0

if __name__ == '__main__':
  sys.exit(main())
