import json
from os import environ
from logging import getLogger
import boto3
from botocore.exceptions import ClientError


log = getLogger()
s3 = boto3.client('s3')
dynamodb = boto3.client('dynamodb')
lamb = boto3.client('lambda')


def setup():
    config = json.loads(environ['CONFIG'])
    log.setLevel(config['log_level'])
    log.debug('Config: %s', str(config))
    return config


def update_object(bundle_id, object_key, object_status, table):
    primary_key = {'bundle_id': {'S': bundle_id}, 'object_key': {'S': object_key}}

    update_expression = 'set request_status = :1'
    expression_attribute_values = {':1': {'S': object_status['status']}}

    if 'expiration_date' in object_status:
        update_expression += ', expiration_date = :2'
        expression_attribute_values[':2'] = {'S': object_status['expiration_date']}

    dynamodb.update_item(
        TableName=table,
        Key=primary_key,
        UpdateExpression=update_expression,
        ExpressionAttributeValues=expression_attribute_values,
    )


def restore_object(request, config):
    tier = request.get('tier', config['default_tier'])
    log.info('Restoring object.  Object Key: %s, Tier: %s', request['object_key'], tier)
    try:
        s3.restore_object(
            Bucket=config['bucket'],
            Key=request['object_key'],
            RestoreRequest={
                'Days': config['retention_days'],
                'GlacierJobParameters': {
                    'Tier': tier,
                },
            },
        )
    except ClientError as e:
        log.exception('Failed to restore object.')


def get_object_status(object_key, object_status_lambda):
    payload = {'object_key': object_key}
    response = lamb.invoke(
        FunctionName=object_status_lambda,
        Payload=json.dumps(payload),
    )
    object_status = json.loads(response['Payload'].read())
    return object_status


def process_request(request, config):
    restore_object(request, config['restore'])
    if 'bundle_id' in request:
        object_status = get_object_status(request['object_key'], config['object_status_lambda'])
        if object_status['status'] in ['retrieving', 'available']:
            update_object(request['bundle_id'], request['object_key'], object_status, config['objects_table'])


def lambda_handler(event, context):
    config = setup()
    for request in event:
        process_request(request, config['request'])
