import json
import re
from os import environ
from logging import getLogger
from datetime import datetime
import boto3
from botocore.exceptions import ClientError


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


def update_object(bundle_id, object_key, request_status, expiration_date, table):
    primary_key = {'bundle_id': {'S': bundle_id}, 'object_key': {'S': object_key}}
    dynamodb.update_item(
        TableName=table,
        Key=primary_key,
        UpdateExpression='set request_status = :1, expiration_date = :2',
        ExpressionAttributeValues={
            ':1': {'S': request_status},
            ':2': {'S': str(expiration_date)},
        },
    )


def get_expiration_date(restore_string):
    match = re.search('expiry-date="(.+)"', restore_string)
    if match:
        return datetime.strptime(match.group(1), '%a, %d %b %Y %H:%M:%S %Z')
    return None


def restore_object(obj, tier, retention_days):
    log.info('Restoring object.  Object Key: %s, Tier: %s, Retention Days: %s', obj.key, tier, retention_days)
    try:
        obj.restore_object(
            RestoreRequest={
                'Days': retention_days,
                'GlacierJobParameters': {
                    'Tier': tier,
                },
            }
        )
    except ClientError as e:
        log.exception('Failed to restore object.')


def process_request(request, config):
    obj = get_object(config['bucket'], request['object_key'])
    tier = request.get('tier', config['default_tier'])
    restore_object(obj, tier, config['retention_days'])
    if 'bundle_id' in request:
        request_status = get_request_status(obj.restore)
        if request_status in ['pending', 'available']:
            expiration_date = get_expiration_date(obj.restore)
            update_object(request['bundle_id'], request['object_key'], request_status, expiration_date, config['objects_table'])


def lambda_handler(event, context):
    config = setup()
    for request in event:
        process_request(request, config['request'])
