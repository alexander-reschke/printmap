#!/usr/bin/env python
# -*- coding: utf-8 -*-


import requests, json, argparse, time, datetime, csv, sys, math, os
from argparse import RawTextHelpFormatter
from PIL import Image


# TODO
# * remove y offset when resolution/devisor has a remainder (for example wid = 1700px, divisor = 3, 1700/3=566 (no half-pixels), 566*3=1698 instead of 1700)
# * save chunks in a temporary folder which gets deleted afterwards
# * add option to not delete chunks
# * fix bug occuring between resolution of 8k x 8k (still okay) and 10k x 10k (not downloading everything + very buggy merge)
# * check out different bing-key to get rid of bing water-mark
# * -or-
# * work with y-offsets to hide bing water-mark
# * add proper requirements.txt
# * add proper documentation and publish on github


# constants
BASE_URL = 'http://dev.virtualearth.net/REST/v1/Imagery/Map/Aerial'

NUM_CHUNKS_THRESHOLD = 36 # x^2 (4, 9, 16, 25, 36, 49, 64, 81, 100 etc (max. 324 for 15000x15000px))

MAX_W_BING = 900       # bings max width resolution
MAX_W = 15000          # max width resolution (NOTE: this program could work with much higher resolutions)
MIN_W = 80             # bings min width resolution

MAX_H_BING = 834       # bings max height resolution
MAX_H = 15000          # max height resolution (NOTE: this program could work with much higher resolutions)
MIN_H = 80             # bings min height resolution

EARTH_RADIUS = 6378137 # earth radius in meters

MAX_LATITUDE = 85.05   # 85.05112878
MIN_LATITUDE = -85.05  # -85.05112878
MAX_LONGITUDE = 180
MIN_LONGITUDE = -180
MAX_RADIUS = 2000      # 2000 kilometers
MIN_RADIUS = 0.05      # 50 meters


# global values
BING_KEY = ''            # should be provided in same dir in file bing.key
PICTURE_NAME = ''        # specified parameter or generated timestamp
DATA_URLS_CALLED = set() # data-urls already fetched, otherwise recursion leads to massive redundant calls


# utility functions
def pDebug(text):
    if args.verbose or args.full:
        print '[DEBUG]\t%s' % (text, )


def pInfo(text):
    if not args.quiet:
        print '[INFO]\t%s' % (text, )


def pError(text):
    print '[ERROR]\t%s' % (text, )


def formatJson(response):
    return json.dumps(response.json(), indent=2, sort_keys=True)


def f(num):
    return "{:.2f}".format(num)


def buildUrl(lat, lon, wid, hei, zoom, meta):
    center = "%s,%s" % (lat, lon)
    resolution = "mapSize=%s,%s" % (wid, hei)
    metadata = "mmd=%s" % ('1' if meta else '0', )
    key = "key=%s" % (BING_KEY, )
    url = '%s/%s/%s?%s&%s&%s' % (BASE_URL, center, zoom, resolution, metadata, key)
    return url


def questionYesNo(question, default='no'):
    valid = {
        'yes': True,
        'y': True,
        'no': False,
        'n': False,
    }
    if default is None:
        prompt = ' [y/n] '
    elif default == 'yes':
        prompt = ' [Y/n] '
    elif default == 'no':
        prompt = ' [y/N] '
    else:
        raise ValueError("invalid default answer: '%s'" % default)

    while True:
        sys.stdout.write('[!]\t%s' % (question, ) + prompt)
        choice = raw_input().lower()
        if default is not None and choice == '':
            return valid[default]
        elif choice in valid:
            return valid[choice]
        else:
            sys.stdout.write("Please respond with 'yes' or 'no' (or 'y' or 'n').\n")


# global setters
def setBingKey():
    global BING_KEY
    with open('bing.key', 'rb') as keyFile:
        key = list(csv.reader(keyFile))
        BING_KEY = str(key[0][0])


def setPictureName():
    global PICTURE_NAME
    PICTURE_NAME = '%s.jpg' % (args.name or int(time.time()))


# logical functions
def findZoom():

    # init some values
    targetWidth = (args.rad * 1000) * 2
    curDelta = prevDelta = -float("inf")
    curMeterPerPixel = curZoomWidth = 0

    # iterate over zooms, starting from 1 (very far) to 19 (very near)
    for zoom in range(1, 20):

        # save previous iteration
        prevMeterPerPixel = curMeterPerPixel
        prevZoomWidth = curZoomWidth
        prevDelta = curDelta

        # calculate current iteration
        curMeterPerPixel = (math.cos(args.lat * (math.pi / 180)) * 2 * math.pi * EARTH_RADIUS) / (256 * (2**zoom))
        curZoomWidth = (args.wid if args.wid < args.hei else args.hei) * curMeterPerPixel
        curDelta = targetWidth - curZoomWidth

        # check if done
        if curDelta >= 0:
            break

    # check if current or previous iteration fits better
    if math.fabs(prevDelta) < curDelta:
        zoom -= 1
        curMeterPerPixel = prevMeterPerPixel
        curZoomWidth = prevZoomWidth

    # some output and return
    kmWid = (curMeterPerPixel * args.wid) / 1000
    kmHei = (curMeterPerPixel * args.hei) / 1000
    pInfo('next best fitting radius is %skm (instead of %skm), the area covered is %skm x %skm (%skm²)' % (f((curZoomWidth / 1000) / 2), args.rad, f(kmWid), f(kmHei), f(kmWid * kmHei)))
    pDebug('the zoom level is %s, picture will display %s meter per pixel' % (zoom, f(curMeterPerPixel)))
    return zoom


def findSubResolution():
    global NUM_CHUNKS

    # start with divisor 1
    div = 1
    subWid = args.wid
    subHei = args.hei

    # continue increase of divisor until wid/hei within bings limits
    while subWid > MAX_W_BING or subHei > MAX_H_BING:
        div += 1
        subWid = args.wid / div
        subHei = args.hei / div
    NUM_CHUNKS = div**2
    return [subWid, subHei, div]


def getSubCoordinates(centerLat, centerLon, subWid, subHei, zoom, level, targetLevel, coordinates):
    global DATA_URLS_CALLED
    
    if level == targetLevel:
        if (centerLat, centerLon) not in coordinates:

            # when target-level is reached and coordinate not already found, add this coordinate to result
            coordinates.add((centerLat, centerLon))
            pDebug('* recursion end reached for coordinate (%s, %s), found %s / %s coordinates for full picture' % (centerLat, centerLon, len(coordinates), NUM_CHUNKS))
    else:

        # otherwise get coordinates of corners and call getSubCoordinates() on them
        urlData = buildUrl(centerLat, centerLon, subWid, subHei, zoom, True)
        if urlData not in DATA_URLS_CALLED:
            data = processData(urlData)
            getSubCoordinates(data['resourceSets'][0]['resources'][0]['bbox'][2], data['resourceSets'][0]['resources'][0]['bbox'][1], subWid, subHei, zoom, level + 1, targetLevel, coordinates)
            getSubCoordinates(data['resourceSets'][0]['resources'][0]['bbox'][2], data['resourceSets'][0]['resources'][0]['bbox'][3], subWid, subHei, zoom, level + 1, targetLevel, coordinates)
            getSubCoordinates(data['resourceSets'][0]['resources'][0]['bbox'][0], data['resourceSets'][0]['resources'][0]['bbox'][1], subWid, subHei, zoom, level + 1, targetLevel, coordinates)
            getSubCoordinates(data['resourceSets'][0]['resources'][0]['bbox'][0], data['resourceSets'][0]['resources'][0]['bbox'][3], subWid, subHei, zoom, level + 1, targetLevel, coordinates)
            DATA_URLS_CALLED.add(urlData)


def mergeChunks(wid, hei, subWid, subHei, targetLevel, chunkNames):
    if not args.dry:
        if targetLevel == 1:

            # if chunk is already full picture, just rename it since thats the least resource-heavy operation
            os.rename('chunk_x1_y1.jpg', PICTURE_NAME)
        else:

            # merge all chunks into one picture
            curX = 0
            curY = 1
            maxDim = (len(chunkNames) / targetLevel) - 1
            fullPicture = Image.new('RGB', (wid, hei))
            for name in chunkNames:
                chunk = Image.open('%s.jpg' % (name, ))
                fullPicture.paste(chunk, ((curX * subWid), hei - (curY * subHei)))
                if curX < maxDim:
                    curX += 1
                else:
                    curX = 0
                    curY += 1

            # save picture
            fullPicture.save(PICTURE_NAME)


def processData(url):

    # call bing for data and return the response
    if args.full:
        pDebug('... fetching data %s' % (url, ))
    response = requests.get(url)
    if response:
        return json.loads(response.text) 


def processPicture(url, pictureName):

    # call bing for picture and save that picture as a chunk in the current dir
    if args.full:
        pDebug('... fetching picture %s' % (url, ))
    if not args.dry:
        with open('%s.jpg' % (pictureName, ), 'wb') as handle:
            response = requests.get(url, stream=True)
            if response:
                if not response.ok:
                    pError(formatJson(response))
                    return
                else:
                    for block in response.iter_content(1024):
                        if not block:
                            break
                        handle.write(block)


def main(args):

    # init
    start = time.time()
    pInfo('start: center-point (%s, %s), radius %skm, resolution %sx%spx' % (f(args.lat), f(args.lon), args.rad, args.wid, args.hei))

    # set up everything
    setBingKey()
    setPictureName()

    # find out zoom and number of needed sublevels and the according resolution
    zoom = findZoom()
    subResoultion = findSubResolution()
    subWid = subResoultion[0]
    subHei = subResoultion[1]
    targetLevel = subResoultion[2]
    pInfo('will need to download %s chunks of pictures, each %sx%spx' % (NUM_CHUNKS, subWid, subHei))

    # check number of chunks, if its above a threshold, ask the user if that is even okay
    if (NUM_CHUNKS) >= NUM_CHUNKS_THRESHOLD and not args.inf:
        if args.dry:
            if not questionYesNo('Is that okay? (Note: a dry-run will not download pictures, but still needs to call external services)'):
                return
        else:
            if not questionYesNo('Is that okay?'):
                return

    # end here if this is an info-run, otherwise we now need to call external services
    if args.inf:
        pInfo('NOTE: this was an info-run and did not call any external service or modify any data on the disk')
        return

    # find all coordinates recursivly
    coordinates = set()
    pInfo('searching for all sub-coordinates now ...')
    getSubCoordinates(args.lat, args.lon, subWid, subHei, zoom, 1, targetLevel, coordinates)
    pInfo('... done, found all %s sub-coordinates' % (NUM_CHUNKS, ))
    coordinates = sorted(coordinates)
    # print len(coordinates)
    # return

    # process coordinates
    i = x = y = 1
    chunkNames = list()
    pInfo('downloading picture chunks now ...')
    for coor in coordinates:
        # print coor
        url = buildUrl(coor[0], coor[1], subWid, subHei, zoom, False)
        chunkName = 'chunk_x%s_y%s' % (x, y)
        chunkNames.append(chunkName)
        processPicture(url, chunkName)
        pDebug('... downloaded chunk for coordinate (%s, %s), processed %s / %s chunks' % (coor[0], coor[1], i, len(coordinates)))
        if y == targetLevel:
            x += 1
            y = 1
        else:
            y += 1
        i += 1
    pInfo('... done, downloaded %s chunks of pictures' % (len(coordinates), ))

    # merge chunks into one picture
    mergeChunks(args.wid, args.hei, subWid, subHei, targetLevel, chunkNames)
    pInfo('merged all chunks and created picture \'%s\' in current dir' % (PICTURE_NAME, ))

    # cleanup
    if not args.dry:
        if targetLevel > 1:
            pDebug('cleaning up, deleting %s chunks of pictures' % (len(chunkNames), ))
            for name in chunkNames:
                os.remove('%s.jpg' % (name, ))

    # wrap everything up and end
    elapsed = time.time() - start
    pInfo('duration: %s' % str(datetime.timedelta(seconds=int(elapsed))))
    if args.dry:
        pInfo('NOTE: this was a dry-run and did not download pictures or modify any data on the disk')


if __name__ == '__main__':

    # description and arguments
    argp = argparse.ArgumentParser(description=
'''Get custom map images via bing maps.
HINT: use the --inf option to check if the result suits you or if you want to fiddle with radius or resolution.

Examples:
> python bmaps_coor.py --rad 1 --wid 2000 --hei 2000 --inf
\tget nothing (info-run), but see informations on what the picture would show
> python bmaps_coor.py --rad 1 --wid 2000 --hei 2000 -v --name lindow
\tget above descripted picture, save it as \'lindow.jpg\' and let the program tell you all it is doing
> python bmaps_coor.py --lat 55.751879 --lon 37.616937 --rad 15 --wid 8000 --hei 6000
\tget a 8000x6000px picture of moscow with a approx. radius of 15km'''
        , formatter_class=RawTextHelpFormatter)

    argp.add_argument('--name', dest='name', help='name of the picture to create; overwrites existing files (default: <timestamp>)')

    group = argp.add_mutually_exclusive_group()
    group.add_argument('--dry', action='store_true', default=False, help='dry run, do not download pictures or modify local data (default false)')
    group.add_argument('--inf', action='store_true', default=False, help='only show infos for the parameters provided, do not call any external services or modify local data (default false)')

    groupcoor = argp.add_argument_group()
    groupcoor.add_argument('--lat', type=float, default=52.103570, help='latitude for map center (default 14.301484, range [%s..%s])' % (MIN_LATITUDE, MAX_LATITUDE))
    groupcoor.add_argument('--lon', type=float, default=14.301484, help='longitude for map center (default 52.103570, range [%s..%s])' % (MIN_LONGITUDE, MAX_LONGITUDE))
    groupcoor.add_argument('--rad', type=float, default=5, help='estimated radius from center in km (default 5, range [%s..%s])' % (MIN_RADIUS, MAX_RADIUS))

    groupres = argp.add_argument_group()
    groupres.add_argument('--wid', type=int, default=1600, help='resolution in pixel for picture width (default 800, range [%s..%s])' % (MIN_W, MAX_W))
    groupres.add_argument('--hei', type=int, default=1200, help='resolution in pixel for picture height (default 600, range [%s..%s])' % (MIN_H, MAX_H))

    groupoutput = argp.add_mutually_exclusive_group()
    groupoutput.add_argument('-q', '--quiet', action='store_true', default=False, help='show no output (beside errors)')
    groupoutput.add_argument('-v', '--verbose', action='store_true', default=False, help='show more output than normal')
    groupoutput.add_argument('-f', '--full', action='store_true', default=False, help='show more output than normal and including all called urls')
    
    args = argp.parse_args()

    # argument check and calling main when valid
    if args.lat > MAX_LATITUDE or args.lat < MIN_LATITUDE:
        pError('latitude needs to be within [%s..%s]' % (MIN_LATITUDE, MAX_LATITUDE))
    elif args.wid > MAX_W or args.wid < MIN_W:
        pError('width resolution needs to be within [%s..%s]' % (MIN_W, MAX_W))
    elif args.hei > MAX_H or args.hei < MIN_H :
        pError('height resolution needs to be within [%s..%s]' % (MIN_H, MAX_H))
    elif args.rad < MIN_RADIUS or args.rad > MAX_RADIUS:
        pError('radius needs to be within [%s..%s]' % (MIN_RADIUS, MAX_RADIUS))
    else:
        main(args)
