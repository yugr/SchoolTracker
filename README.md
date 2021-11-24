# What is this

Simple repo to show location of highly-rated Moscow schools.
School ratings have been taken from
* official school rating
* [RAEX rating](https://raex-a.ru/releases/2020/21April)
* [schoolotzyv.ru](https://schoolotzyv.ru/)

# Prerequisites

To run, obtain developer keys for
* JavaScript API и HTTP Геокодер
* API Поиска по организациям
(it's free) and add them to settings\_example.ini.

On Linux you may also need to install pip:
```
$ sudo apt-get install python3-pip
```

# How to use

To draw a map with 75 best schools based on RAEX rating, excluding the HSE, run
```
$ python3 SchoolTracker.py -m 75 --skip-schools 'ВШЭ' ratings/raex/top300.2019.txt settings.ini
```
This will generate Schools.html (and marks.js) file which can be viewed in your favourite browser.

You can also draw more schools and use another rating:
```
$ python3 SchoolTracker.py -m -100 ratings/official/2018.txt settings.ini
```

To add house-school affinity, add house-school mapping:
```
$ python3 SchoolTracker.py --house-map SchoolAttributions.xlsx ...
```
(presently affinity file has to be written by hand).

To also print textual info on schools, use
```
$ python3 --print-schools ...
```
(this is mainly used for debugging).

To print station mapping, use
```
$ python3 --print-metro-map ...
```

For more details, run
```
$ python3 SchoolTracker.py -h
```

# TODO

* use standard school affinity file from Moscow education department
* draw all school locations for schools with multiple buildings
* draw metro stations
* support https://www.mos.ru/donm/documents/antimonopolnyi-komplaens/view/173858220/
