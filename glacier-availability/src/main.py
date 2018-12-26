import json
from datetime import datetime
from os import getenv
from logging import getLogger
from uuid import uuid4
import boto3


log = getLogger()
log.setLevel('INFO')
config = json.loads(getenv('CONFIG'))
dynamodb = boto3.client('dynamodb')
sqs = boto3.client('sqs')
lamb = boto3.client('lambda')


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


def update_object(bundle_id, object_key, request_status, table):
    primary_key = {'bundle_id': {'S': bundle_id}, 'object_key': {'S': object_key}}
    dynamodb.update_item(
        TableName=table,
        Key=primary_key,
        UpdateExpression='set request_status = :1, request_date = :2',
        ExpressionAttributeValues={
            ':1': {'S': request_status},
            ':2': {'S': str(datetime.utcnow())},
        },
    )


def submit_email_to_queue(user_id, queue_name):
    queue_url = sqs.get_queue_url(QueueName=queue_name)['QueueUrl']
    payload = {
        'type': 'acknowledgement',
        'user_id': user_id,
    }
    sqs.send_message(QueueUrl=queue_url, MessageBody=json.dumps(payload))


def restore_object(object_key, restore_object_lambda):
    payload = [{'object_key': object_key}]
    lamb.invoke(
        FunctionName=restore_object_lambda,
        Payload=json.dumps(payload),
        InvocationType='Event',
    )


def get_object_status(object_key, object_status_lambda):
    payload = {'object_key': object_key}
    response = lamb.invoke(
        FunctionName=object_status_lambda,
        Payload=json.dumps(payload),
    )
    object_status = json.loads(response['Payload'].read())
    return object_status


def process_availability(event, config):
    object_status = get_object_status(event['object_key'], config['object_status_lambda'])
    if 'errorType' in object_status:
        return object_status

    if object_status['status'] != 'available':
        bundle_id = get_open_bundle_for_user(event['user_id'], config['bundles_table'])
        if not bundle_id:
            bundle_id = create_new_bundle_for_user(event['user_id'], config['bundles_table'])
        update_object(bundle_id, event['object_key'], object_status['status'], config['objects_table'])
        submit_email_to_queue(event['user_id'], config['email_queue_name'])
    if 'expiration_date' in object_status:
        restore_object(event['object_key'], config['restore_object_lambda'])

    response = {
        'available': object_status['status'] == 'available',
    }
    return response


def lambda_handler(event, context):
    response = process_availability(event, config)
    return response
