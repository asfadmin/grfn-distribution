#!/usr/bin/python

# one-off utility script to spider JPL's static S3 front-end website and recursively download files
# this isn't production quality code, use at your own risk

import requests
import xml.etree.ElementTree as ET
import os


search_url = 'http://hysds-aria-products.s3-us-gov-west-1.amazonaws.com/?delimiter=/&prefix='
download_url = 'http://hysds-aria-products.s3-website-us-gov-west-1.amazonaws.com/'
starting_path = 'interferogram/v1.0/2016/10/07'


def process(path):
    req = requests.get(search_url + path)
    xml = ET.fromstring(req.text)
    for key in xml.iter('{http://s3.amazonaws.com/doc/2006-03-01/}Key'):
        file_url = download_url + key.text
        wget_command = 'wget --recursive --no-clobber "{0}"'.format(file_url)
        os.system(wget_command)
    for prefix in xml.iter('{http://s3.amazonaws.com/doc/2006-03-01/}Prefix'):
        if prefix.text != path:
            process(prefix.text)


process(starting_path)

