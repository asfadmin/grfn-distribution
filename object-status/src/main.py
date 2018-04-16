import json
from os import environ
from logging import getLogger
import boto3


log = getLogger()
s3 = boto3.resource('s3')


def setup():
    config = json.loads(environ['CONFIG'])
    log.setLevel(config['log_level'])
    log.debug('Config: %s', str(config))
    return config


def get_glacier_status(restore_string):
    if restore_string is None:
        return 'archived'
    if 'ongoing-request="true"' in restore_string:
        return 'retrieving'
    return 'available'


def get_object_status(bucket, key):
    obj = s3.Object(bucket, key)
    if obj.storage_class == 'GLACIER':
        status = get_glacier_status(obj.restore)
    else:
        status = 'available'
    return {'status': status}


def lambda_handler(event, context):
    config = setup()
    response = get_object_status(config['bucket'], event['object_key'])
    return response
