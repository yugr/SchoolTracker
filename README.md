# What is this

Simple tool to show location of highly-rated Moscow schools.
School ratings have been taken from
* official school rating
* [RAEX rating](https://raex-a.ru/releases/2020/21April)
* [schoolotzyv.ru](https://schoolotzyv.ru/)

# Prerequisites

To run, obtain developer keys for
* JavaScript API и HTTP Геокодер
* API Поиска по организациям

They are free and can be obtained in
[Кабинет Разработчика](https://developer.tech.yandex.ru/keys).

On Linux you need to install pip:
```
$ sudo apt-get install python3-pip
```

# How to use

To draw a map with 75 best schools based on RAEX rating, excluding the HSE, run
```
# XXX and YYY need to be replaced with your Yandex tokens
$ python3 SchoolTracker.py -m 75 --jsapi-key XXX --places-key YYY ratings/raex/top300.2022.txt
```
This will generate Schools.html (and marks.js) file which can be viewed in your favourite browser.

You can also draw more schools or use another rating:
```
$ python3 SchoolTracker.py -m -100 ratings/schoolotzyv/2021/ege.cumulative.2021.txt
```

To also print textual info on schools, use
```
$ python3 --print-schools ...
```
(this is mainly used for debugging).

To print metro station mapping, use
```
$ python3 --print-metro-map ...
```

For more details, run
```
$ python3 SchoolTracker.py -h
```

# TODO

* use standard school affinity file from Moscow education department (https://obrmos.ru/dop/docs/prikr/docs_prikr_dom_okruga.html)
* draw all school locations for schools with multiple buildings
* write scripts to automatically download ratings (RAEX, schoolotzyv.ru)
