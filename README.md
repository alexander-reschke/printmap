printmap
========

Create high-resolution, printable maps using bing maps. Just provide latitude/longitude, the radius around that point you would like to include and the resolution you are aiming for.

How
---

* `git clone` this repository to the machine you are working on
* `cd` into the new folder
* run `pip install -r requirements.txt` to install required libraries you might currently miss
* create a file named `bing.key` at paste your bing-maps API key here (if you do not have one, get one here: https://www.bingmapsportal.com)
* run `python printmap.py --help` for options
* run any of the examples provided
* play around with options and become familiar with this small tool

Why
---

Easy birthday present: just put in the coordinates of the gift-receiver, choose a high enough resolution (check out some articles regarding DPI etc.) and let the tool do its thing. Afterward let the result be printed in high quality in some shop, put it in a proper frame and done! Tell 'em you did it yourself and that it took hours, nay, days to get it right ...

Manual
------

Examples:
```
python printmap.py --rad 1 --wid 2000 --hei 2000 --inf
```
* get nothing (info-run), but see informations on what the picture would show

```
python printmap.py --rad 1 --wid 2000 --hei 2000 -v --name berlin
```
* get above descripted picture, save it as `berlin.jpg` and let the tool tell you most of what it is doing

```
python printmap.py --lat 55.751879 --lon 37.616937 --rad 15 --wid 8000 --hei 6000
```
* get a 8000x6000px picture of moscow with an approx. radius of 15km

Optional arguments:
* `-h, --help`     show this help message and exit
* `--name NAME`    name of the picture to create; overwrites existing files (default: <timestamp>)
* `--dry`          dry run, do not download pictures or modify local data (default false)
* `--inf`          only show infos for the parameters provided, do not call _any_ external services or modify local data (default false)
* `-q, --quiet`    show no output (beside errors)
* `-v, --verbose`  show more output than normal
* `-f, --full`     show more output than normal and include all API calls
* `--lat LAT`      latitude for map center (default 52.520852 (Berlin, Germany), range [-85.05..85.05])
* `--lon LON`      longitude for map center (default 13.409531 (Berlin, Germany, range [-180..180])
* `--rad RAD`      estimated radius from center in km (default 5, range [0.05..2000])
* `--wid WID`      resolution in pixel for picture width (default 800, range [80..15000])
* `--hei HEI`      resolution in pixel for picture height (default 600, range [80..15000])

Notes
-----

Currently all the chunks of the picture have the bing maps watermark on it. You can either purchase a non-free licence from Microsoft or solve this problem yourself.
