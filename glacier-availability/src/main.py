import json
from datetime import datetime
from os import environ
from logging import getLogger
from uuid import uuid4
import boto3


log = getLogger()
s3 = boto3.resource('s3')
dynamodb = boto3.client('dynamodb')


def setup():
    config = json.loads(environ['CONFIG'])
    log.setLevel(config['log_level'])
    log.debug('Config: %s', str(config))
    return config


def get_s3_object(bucket, key):
    obj = s3.Object(bucket, key)
    obj.load()
    return obj


def translate_restore_status(restore):
    if restore is None:
        return 'not_available'
    if 'ongoing-request="true"' in restore:
        return 'in_progress'
    return 'available'


def get_open_bundle_for_user(user_id, table):
    results = dynamodb.query(
        TableName=table,
        IndexName='user',
        KeyConditionExpression='user_id = :1 and close_date = :2',
        ExpressionAttributeValues={
            ':1': {'S': user_id},
            ':2': {'S': 'none'},
        },
        ProjectionExpression='bundle_id',
    )
    if not results['Items']:
        return None
    return results['Items'][0]['bundle_id']['S']


def create_new_bundle_for_user(user_id, table):
    bundle_id = str(uuid4())
    primary_key = {'bundle_id': {'S': bundle_id}}
    dynamodb.update_item(
        TableName=table,
        Key=primary_key,
        UpdateExpression='set user_id = :1, open_date = :2, close_date = :3',
        ExpressionAttributeValues={
            ':1': {'S': user_id},
            ':2': {'S': str(datetime.utcnow())},
            ':3': {'S': 'none'},
        },
    )
    return bundle_id


def add_object_to_bundle(object_key, bundle_id, table):
    primary_key = {'bundle_id': {'S': bundle_id}, 'object_key': {'S': object_key}}
    dynamodb.update_item(
        TableName=table,
        Key=primary_key,
        UpdateExpression='set request_date = :1',
        ExpressionAttributeValues={
            ':1': {'S': str(datetime.utcnow())},
        },
    )


def add_object(object_key, table):
    primary_key = {'object_key': {'S': object_key}}
    dynamodb.update_item(
        TableName=table,
        Key=primary_key,
        UpdateExpression='set availability = :1',
        ExpressionAttributeValues={
            ':1': {'S': 'pending'},
        },
    )


def process_availability(event, config):
    available = True
    obj = get_s3_object(config['bucket'], event['object_key'])
    if obj.storage_class == 'GLACIER':
        restore_status = translate_restore_status(obj.restore)
        if restore_status in ['not_available', 'in_progress']: # log user interest in object
            available = False
            bundle_id = get_open_bundle_for_user(event['user_id'], config['bundles_table'])
            if not bundle_id:
                bundle_id = create_new_bundle_for_user(event['user_id'], config['bundles_table'])
            add_object_to_bundle(obj.key, bundle_id, config['bundle_objects_table'])
        if restore_status == 'not_available': # issue restore request
            add_object(obj.key, config['objects_table'])
    return {'available': available}


def lambda_handler(event, context):
    config = setup()
    response = process_availability(event, config['availability'])
    return response
