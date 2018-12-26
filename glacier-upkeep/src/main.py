import json
from os import getenv
from logging import getLogger
from datetime import datetime
from collections import defaultdict
import boto3


log = getLogger()
log.setLevel('INFO')
config = json.loads(getenv('CONFIG'))
dynamodb = boto3.client('dynamodb')
lamb = boto3.client('lambda')
sqs = boto3.client('sqs')


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
        FilterExpression='not request_status = :2',
        ExpressionAttributeValues={
            ':1': {'S': bundle_id},
            ':2': {'S': 'available'},
        },
        ProjectionExpression='object_key',
    )
    return len(results['Items']) == 0


def batch_invoke(lambda_name, payload, batch_size):
    batches = [payload[i:i+batch_size] for i in range(0, len(payload), batch_size)]
    for batch in batches:
        lamb.invoke(
            FunctionName=lambda_name,
            Payload=json.dumps(batch),
            InvocationType='Event',
        )


def process_archived_objects(objects_table, restore_object_lambda, max_expedited_requests):
    objects = get_objects_by_request_status('archived', objects_table)
    payload = []
    object_count_by_bundle = defaultdict(int)

    for obj in objects:
        item = {
            'bundle_id': obj['bundle_id'],
            'object_key': obj['object_key'],
        }
        object_count_by_bundle[obj['bundle_id']] += 1
        if object_count_by_bundle[item['bundle_id']] <= max_expedited_requests:
            item['tier'] = 'Expedited'
        payload.append(item)

    batch_invoke(restore_object_lambda, payload, 10)


def process_pending_objects(objects_table, poll_object_lambda):
    objects = get_objects_by_request_status('retrieving', objects_table)
    payload = [
        {
            'bundle_id': obj['bundle_id'],
            'object_key': obj['object_key'],
        }
        for obj in objects
    ]
    batch_invoke(poll_object_lambda, payload, 100)


def process_open_bundles(bundles_table, objects_table, email_queue_name):
    open_bundles = get_open_bundles(bundles_table)
    for bundle in open_bundles:
        if bundle_complete(bundle['bundle_id'], objects_table):
            close_bundle(bundle['bundle_id'], bundles_table)
            send_sqs_message(bundle, email_queue_name)


def upkeep(config):
    process_archived_objects(config['objects_table'], config['restore_object_lambda'], config['max_expedited_requests_per_bundle'])
    process_pending_objects(config['objects_table'], config['poll_object_lambda'])
    process_open_bundles(config['bundles_table'], config['objects_table'], config['email_queue_name'])


def lambda_handler(event, context):
    upkeep(config)
