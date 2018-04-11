import json
import re
from os import environ
from logging import getLogger
from datetime import datetime
import boto3


log = getLogger()
s3 = boto3.resource('s3')
dynamodb = boto3.client('dynamodb')


def setup():
    config = json.loads(environ['CONFIG'])
    log.setLevel(config['log_level'])
    log.debug('Config: %s', str(config))
    return config


def get_object(bucket, key):
    obj = s3.Object(bucket, key)
    obj.load()
    return obj


def get_request_status(restore_string):
    if restore_string is None:
        return 'new'
    if 'ongoing-request="true"' in restore_string:
        return 'pending'
    return 'available'


def update_object(event, expiration_date, table):
    log.info('Object is now available.  Object Key: %s, Expiration Date %s', event['object_key'], str(expiration_date))
    primary_key = {
        'bundle_id': {'S': event['bundle_id']},
        'object_key': {'S': event['object_key']},
    }
    dynamodb.update_item(
        TableName=table,
        Key=primary_key,
        UpdateExpression='set request_status = :1, expiration_date = :2',
        ExpressionAttributeValues={
            ':1': {'S': 'available'},
            ':2': {'S': str(expiration_date)},
        },
    )


def get_expiration_date(restore_string):
    expiration_date = re.search('expiry-date="(.+)"', restore_string).group(1)
    expiration_date = datetime.strptime(expiration_date, '%a, %d %b %Y %H:%M:%S %Z')
    return expiration_date


def poll_object(event, config):
    s3_obj = get_object(config['bucket'], event['object_key'])
    request_status = get_request_status(s3_obj.restore)
    if request_status == 'available':
        expiration_date = get_expiration_date(s3_obj.restore)
        update_object(event, expiration_date, config['objects_table'])


def lambda_handler(event, context):
    config = setup()
    poll_object(event, config['poll_object'])
