import json
from os import environ
from logging import getLogger
from re import search
from datetime import datetime
import boto3


log = getLogger()
s3 = boto3.resource('s3')


def setup():
    config = json.loads(environ['CONFIG'])
    log.setLevel(config['log_level'])
    log.debug('Config: %s', str(config))
    return config


def get_expiration_date(restore_string):
    match = search('expiry-date="(.+)"', restore_string)
    expiration_date = datetime.strptime(match.group(1), '%a, %d %b %Y %H:%M:%S %Z')
    return expiration_date


def get_glacier_status(restore_string):
    response = {}
    if restore_string is None:
        response['status'] = 'archived'
    elif 'ongoing-request="true"' in restore_string:
        response['status'] = 'retrieving'
    else:
        response['status'] = 'available'
        response['expiration_date'] = str(get_expiration_date(restore_string))
    return response


def get_object_status(bucket, key):
    obj = s3.Object(bucket, key)
    if obj.storage_class == 'GLACIER':
        response = get_glacier_status(obj.restore)
    else:
        response = {'status': 'available'}
    return response


def lambda_handler(event, context):
    config = setup()
    response = get_object_status(config['bucket'], event['object_key'])
    return response
