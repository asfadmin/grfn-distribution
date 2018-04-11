import json
from os import environ
from logging import getLogger
from datetime import datetime
import boto3


log = getLogger()
dynamodb = boto3.client('dynamodb')
lamb = boto3.client('lambda')
sqs = boto3.client('sqs')


def setup():
    config = json.loads(environ['CONFIG'])
    log.setLevel(config['log_level'])
    log.debug('Config: %s', str(config))
    return config


def get_objects_by_request_status(request_status, table):
    results = dynamodb.query(
        TableName=table,
        IndexName='request_status',
        KeyConditionExpression='request_status = :1',
        ExpressionAttributeValues={
            ':1': {'S': request_status},
        },
        ProjectionExpression='bundle_id,object_key',
    )
    objects = [
        {
            'bundle_id': item['bundle_id']['S'],
            'object_key': item['object_key']['S'],
        }
        for item in results['Items']
    ]
    return objects


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


def get_open_bundles(table):
    results = dynamodb.scan(
        TableName=table,
        FilterExpression='close_date = :1',
        ExpressionAttributeValues={
            ':1': {'S': 'none'},
        },
        ProjectionExpression='bundle_id,user_id',
    )
    bundles = [
        {
            'bundle_id': item['bundle_id']['S'],
            'user_id': item['user_id']['S'],
        }
        for item in results['Items']
    ]
    return bundles


def bundle_complete(bundle_id, table):
    results = dynamodb.query(
        TableName=table,
        KeyConditionExpression='bundle_id = :1',
        FilterExpression='not request_status in (:2, :3)',
        ExpressionAttributeValues={
            ':1': {'S': bundle_id},
            ':2': {'S': 'available'},
            ':3': {'S': 'refresh'},
        },
        ProjectionExpression='object_key',
    )
    return len(results['Items']) == 0


def upkeep(config):
    new_objects = get_objects_by_request_status('new', config['objects_table'])
    refresh_objects = get_objects_by_request_status('refresh', config['objects_table'])

    for obj in new_objects + refresh_objects:
        payload = {
            'bundle_id': obj['bundle_id'],
            'object_key': obj['object_key'],
            'tier': 'Expedited',
        }
        lamb.invoke(
            FunctionName=config['restore_object_lambda'],
            Payload=json.dumps(payload),
            InvocationType='Event',
        )

    pending_objects = get_objects_by_request_status('pending', config['objects_table'])
    for obj in pending_objects:
        payload = {
            'bundle_id': obj['bundle_id'],
            'object_key': obj['object_key'],
        }
        lamb.invoke(
            FunctionName=config['poll_object_lambda'],
            Payload=json.dumps(payload),
            InvocationType='Event',
        )

    open_bundles = get_open_bundles(config['bundles_table'])
    for bundle in open_bundles:
        if bundle_complete(bundle['bundle_id'], config['objects_table']):
            close_bundle(bundle['bundle_id'], config['bundles_table'])
            send_sqs_message(bundle, config['email_queue_name'])


def lambda_handler(event, context):
    config = setup()
    upkeep(config['upkeep'])
