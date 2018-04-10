import json
from datetime import datetime
from os import environ
from logging import getLogger
from uuid import uuid4
import boto3


log = getLogger()
s3 = boto3.resource('s3')
dynamodb = boto3.client('dynamodb')
sqs = boto3.client('sqs')
lamb = boto3.client('lambda')


def setup():
    config = json.loads(environ['CONFIG'])
    log.setLevel(config['log_level'])
    log.debug('Config: %s', str(config))
    return config


def get_s3_object(bucket, key):
    obj = s3.Object(bucket, key)
    obj.load()
    return obj


def translate_restore_state(restore):
    if restore is None:
        return 'new'
    if 'ongoing-request="true"' in restore:
        return 'pending'
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


def update_object(bundle_id, object_key, state, table):
    primary_key = {'bundle_id': {'S': bundle_id}, 'object_key': {'S': object_key}}
    dynamodb.update_item(
        TableName=table,
        Key=primary_key,
        UpdateExpression='set state = :1, request_date = :2',
        ExpressionAttributeValues={
            ':1': {'S': state},
            ':2': {'S', str(datetime.utcnow())},
        },
    )


def submit_email_to_queue(user_id, queue_name):
    queue_url = sqs.get_queue_url(QueueName=queue_name)['QueueUrl']
    payload = {
        'type': 'acknowledgement',
        'user_id': user_id,
    }
    sqs.send_message(QueueUrl=queue_url, MessageBody=json.dumps(payload))


def process_availability(event, config):
    available = True
    obj = get_s3_object(config['bucket'], event['object_key'])
    if obj.storage_class == 'GLACIER':
        restore_state = translate_restore_state(obj.restore)
        if restore_state in ['new', 'pending']:
            available = False
            bundle_id = get_open_bundle_for_user(event['user_id'], config['bundles_table'])
            if not bundle_id:
                bundle_id = create_new_bundle_for_user(event['user_id'], config['bundles_table'])
            update_object(bundle_id, obj.key, restore_state, config['objects_table'])
            submit_email_to_queue(event['user_id'], config['email_queue_name'])
        # TODO implement refreshes
        #if restore_state == 'available':
        #    refresh_object(obj.key, config['refresh_lambda'])
    return {'available': available}


def lambda_handler(event, context):
    config = setup()
    response = process_availability(event, config['availability'])
    return response
