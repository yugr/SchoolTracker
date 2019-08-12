# SchoolTracker
Simple repo to show location of Moscow schools.
School info is from [schoolotzyv.ru](https://schoolotzyv.ru/) and
RAEX ratings.

Run like
```
$ python3 SchoolTracker.py -m 75 --skip-schools 'ВШЭ' ratings/raex/top300.2019.txt settings.ini
$ python3 SchoolTracker.py -m -100 ratings/official/2018.txt settings.ini
```
to generate HTML with Yandex map.

To add houses on map, pass house-school mapping:
```
$ python3 SchoolTracker.py --house-map SchoolAttributions.xlsx ...
```

To print textual info on schools, use
```
$ python3 --print-schools ...
```

To print station mapping, use
```
$ python3 --print-metro-map ...
```

For more details, run
```
$ python3 SchoolTracker.py -h
```
