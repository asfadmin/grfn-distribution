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


def get_objects_by_availability(availability, table):
    results = dynamodb.query(
        TableName=table,
        IndexName='availability',
        KeyConditionExpression='availability = :1',
        ExpressionAttributeValues={
            ':1': {'S': availability},
        },
        ProjectionExpression='object_key',
    )
    objects = [item['object_key']['S'] for item in results['Items']]
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


def get_objects_for_bundle(bundle_id, table):
    results = dynamodb.query(
        TableName=table,
        KeyConditionExpression='bundle_id = :1',
        ExpressionAttributeValues={
            ':1': {'S': bundle_id},
        },
        ProjectionExpression='object_key',
    )
    objects = [item['object_key']['S'] for item in results['Items']]
    return objects


def bundle_complete(bundle_id, bundle_objects_table, pending_objects):
    bundle_objects = get_objects_for_bundle(bundle_id, bundle_objects_table)
    return not bool(set(bundle_objects) & set(pending_objects))


def upkeep(config):
    pending_objects = get_objects_by_availability('pending', config['objects_table'])
    refresh_objects = get_objects_by_availability('refresh', config['objects_table'])

    for obj in pending_objects + refresh_objects:
        payload = {'object_key': obj, 'refresh': obj in refresh_objects}
        lamb.invoke(
            FunctionName=config['glacier_objects_lambda'],
            Payload=json.dumps(payload),
            InvocationType='Event',
        )

    open_bundles = get_open_bundles(config['bundles_table'])
    for bundle in open_bundles:
        if bundle_complete(bundle['bundle_id'], config['bundle_objects_table'], pending_objects):
            close_bundle(bundle['bundle_id'], config['bundles_table'])
            send_sqs_message(bundle, config['email_queue_name'])


def lambda_handler(event, context):
    config = setup()
    upkeep(config['upkeep'])
