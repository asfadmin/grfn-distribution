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


def translate_restore_status(restore):
    if restore is None:
        return 'not_available'
    if 'ongoing-request="true"' in restore:
        return 'in_progress'
    return 'available'


def update_object(table, object_key, expiration_date):
    log.info('Object is now available.  Object Key: %s, Expiration Date %s', object_key, str(expiration_date))
    primary_key = {'object_key': {'S': object_key}}
    dynamodb.update_item(
        TableName=table,
        Key=primary_key,
        UpdateExpression='set availability = :1, expiration_date = :2',
        ExpressionAttributeValues={
            ':1': {'S': 'available'},
            ':2': {'S': str(expiration_date)},
        },
    )


def get_expiration_date(restore_string):
    expiration_date = re.search('expiry-date="(.+)"', restore_string).group(1)
    expiration_date = datetime.strptime(expiration_date, '%a, %d %b %Y %H:%M:%S %Z')
    return expiration_date


def restore_object(obj, config):
    log.info('Restoring object.  Object Key: %s, Tier: %s, Retention Days: %s', obj.key, config['tier'], config['retention_days'])
    try:
        obj.restore_object(
            RestoreRequest={
                'Days': config['retention_days'],
                'GlacierJobParameters': {
                    'Tier': config['tier'],
                },
            }
        )
    except ClientError as e:
        log.exception('Failed to restore object.')


def process_object(obj, config):
    s3_obj = get_object(config['bucket'], obj['object_key'])
    status = translate_restore_status(s3_obj.restore)
    if status == 'not_available' or obj['refresh']:
        restore_object(s3_obj, config['restore'])
    if status == 'available':
        expiration_date = get_expiration_date(s3_obj.restore)
        update_object(config['objects_table'], obj['object_key'], expiration_date)


def lambda_handler(event, context):
    config = setup()
    process_object(event, config['process_object'])