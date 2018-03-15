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
        ProjectionExpression='object_key, request_date',
    )
    bundle_objects = [
        {
            'object_key': item['object_key']['S'],
            'request_date': item['request_date']['S'],
        }
        for item in results['Items']
    ]
    return bundle_objects


def get_object(object_key, table):
    results = dynamodb.get_item(
        TableName=table,
        Key={'object_key': {'S': object_key}},
        ProjectionExpression='object_key, availability, expiration_date',
    )
    if 'Item' not in results:
        return None

    item = results['Item']
    obj = {
        'object_key': item['object_key']['S'],
        'availability': item['availability']['S'],
    }
    if 'expiration_date' in item:
        obj['expiration_date'] = item['expiration_date']['S']
    return obj


def get_status(user_id, config):
    cutoff_date = str(datetime.utcnow() - timedelta(days=config['retention_days']))
    status = []
    bundle_ids = get_bundles_for_user(user_id, cutoff_date, config['bundles_table'])
    for bundle_id in bundle_ids:
        bundle_objects = get_objects_for_bundle(bundle_id, cutoff_date, config['bundle_objects_table'])
        for bundle_object in bundle_objects:
            obj = get_object(bundle_object['object_key'], config['objects_table'])
            obj['request_date'] = bundle_object['request_date']
            status.append(obj)
    status.sort(key=itemgetter('request_date'), reverse=True)
    return status


def lambda_handler(event, context):
    config = setup()
    status = get_status(event['user_id'], config['status'])
    return status
