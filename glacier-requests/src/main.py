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
sqs = boto3.client('sqs')


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


def get_pending_objects(table):
    results = dynamodb.query(
        TableName=table,
        IndexName='availability',
        KeyConditionExpression='availability = :1',
        ExpressionAttributeValues={
            ':1': {'S': 'pending'},
        },
        ProjectionExpression='object_key',
    )
    object_keys = [item['object_key']['S'] for item in results['Items']]
    return object_keys


def process_restore_requests(config):
    object_keys = get_pending_objects(config['objects_table'])

    for object_key in object_keys:
        obj = get_object(config['bucket'], object_key)
        status = translate_restore_status(obj.restore)
        if status == 'not_available':
            restore_object(obj, config['restore'])
        if status == 'available':
            expiration_date = get_expiration_date(obj.restore)
            update_object(config['objects_table'], object_key, expiration_date)

    completed_bundles = get_completed_bundles(config['bundles_table'])
    for bundle in completed_bundles:
        close_bundle(bundle['bundle_id'], config['bundles_table'])
        send_sqs_message(bundle, config['email_queue_name'])


def close_bundle(bundle_id, table):
    primary_key = {'bundle_id': {'S': bundle_id}}
    dynamodb.update_item(
        TableName=table,
        Key=primary_key,
        UpdateExpression='set close_date = :1',
        ExpressionAttributeValues={
            ':1': {'S': str(datetime.utcnow())},
        },
    )


def send_sqs_message(bundle, queue_name):
    queue_url = sqs.get_queue_url(QueueName=queue_name)['QueueUrl']
    payload = {
        'type': 'availability',
        'user_id': bundle['user_id'],
        'bundle_id': bundle['bundle_id'],
    }
    sqs.send_message(QueueUrl=queue_url, MessageBody=json.dumps(payload))


def get_completed_bundles(table):
    #TODO implement
    completed_bundles = [
        {
            'bundle_id': '02b743dd-efb4-45c1-bff6-0039ee139c19',
            'user_id': 'asjohnston',
        },
    ]
    return completed_bundles


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


def lambda_handler(event, context):
    config = setup()
    process_restore_requests(config['restore_requests'])
