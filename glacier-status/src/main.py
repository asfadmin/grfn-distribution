import json
from os import environ
from logging import getLogger
from datetime import datetime
from datetime import timedelta
from operator import itemgetter
import boto3


log = getLogger()
s3 = boto3.resource('s3')
dynamodb = boto3.client('dynamodb')


def setup():
    config = json.loads(environ['CONFIG'])
    log.setLevel(config['log_level'])
    log.debug('Config: %s', str(config))
    return config


def get_bundles_for_user(user_id, cutoff_date, table):
    results = dynamodb.query(
        TableName=table,
        IndexName='user',
        KeyConditionExpression='user_id = :1 and close_date >= :2',
        ExpressionAttributeValues={
            ':1': {'S': user_id},
            ':2': {'S': cutoff_date},
        },
        ProjectionExpression='bundle_id',
    )
    bundle_ids = [item['bundle_id']['S'] for item in results['Items']]
    return bundle_ids


def get_objects_for_bundle(bundle_id, cutoff_date, table):
    results = dynamodb.query(
        TableName=table,
        KeyConditionExpression='bundle_id = :1',
        FilterExpression='request_date >= :2',
        ExpressionAttributeValues={
            ':1': {'S': bundle_id},
            ':2': {'S': cutoff_date},
        },
        ProjectionExpression='object_key, request_date, expiration_date, request_status',
    )
    objects = []
    for item in results['Items']:
        obj = {
            'object_key': item['object_key']['S'],
            'request_date': item['request_date']['S'],
            'available': item['request_status']['S'] == 'available',
        }
        if 'expiration_date' in item:
            obj['expiration_date'] = item['expiration_date']['S']
        objects.append(obj)
    return objects


def get_status(user_id, config):
    cutoff_date = str(datetime.utcnow() - timedelta(days=config['retention_days']))
    status = []
    bundle_ids = get_bundles_for_user(user_id, cutoff_date, config['bundles_table'])
    for bundle_id in bundle_ids:
        status += get_objects_for_bundle(bundle_id, cutoff_date, config['objects_table'])
    status.sort(key=itemgetter('request_date'), reverse=True)
    return status


def lambda_handler(event, context):
    config = setup()
    status = get_status(event['user_id'], config['status'])
    return status
