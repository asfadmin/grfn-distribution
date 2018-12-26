import json
from os import getenv
from logging import getLogger
import boto3


log = getLogger()
log.setLevel('INFO')
config = json.loads(getenv('CONFIG'))
dynamodb = boto3.client('dynamodb')
lamb = boto3.client('lambda')


def update_object(request, expiration_date, table):
    log.info('Object is now available.  Object Key: %s, Expiration Date %s', request['object_key'], str(expiration_date))
    primary_key = {
        'bundle_id': {'S': request['bundle_id']},
        'object_key': {'S': request['object_key']},
    }
    dynamodb.update_item(
        TableName=table,
        Key=primary_key,
        UpdateExpression='set request_status = :1, expiration_date = :2',
        ExpressionAttributeValues={
            ':1': {'S': 'available'},
            ':2': {'S': expiration_date},
        },
    )


def get_object_status(object_key, object_status_lambda):
    payload = {'object_key': object_key}
    response = lamb.invoke(
        FunctionName=object_status_lambda,
        Payload=json.dumps(payload),
    )
    object_status = json.loads(response['Payload'].read())
    return object_status


def poll_object(request, config):
    object_status = get_object_status(request['object_key'], config['object_status_lambda'])
    if object_status['status'] == 'available':
        update_object(request, object_status['expiration_date'], config['objects_table'])


def lambda_handler(event, context):
    for request in event:
        poll_object(request, config)
