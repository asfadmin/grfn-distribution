import os
from logging import getLogger
import boto3
import json
import yaml
from botocore.exceptions import ClientError


log = getLogger()


def get_file_content_from_s3(bucket, key):
    s3 = boto3.resource('s3')
    obj = s3.Object(bucket, key)
    response = obj.get()
    contents = response['Body'].read()
    return contents


def get_maturity(arn):
    arn_tail = arn.split(':')[-1]
    if arn_tail in ['DEV', 'TEST', 'PROD']:
        maturity = arn_tail
    else:
        maturity = 'LATEST'
    return maturity


def get_config(bucket, key):
    config_contents = get_file_content_from_s3(bucket, key)
    return yaml.load(config_contents)


def setup(arn):
    maturity = get_maturity(arn)
    config = get_config(os.environ['CONFIG_BUCKET'], os.environ[maturity])
    log.setLevel(config['log_level'])
    log.debug('Config: %s', str(config))
    return config


def get_tier(receive_count, config):
    if receive_count <= config['expedited_attempts']:
        return 'Expedited'
    return config['fallback_tier']


def process_restore_requests(config):
    queue = boto3.resource('sqs').get_queue_by_name(QueueName=config['queue'])
    s3 = boto3.client('s3')
    while True:
        response = queue.receive_messages(AttributeNames=['ApproximateReceiveCount'])
        if not response:
            break
        for message in response:
            try:
                request = json.loads(message.body)
                receive_count = int(message.attributes['ApproximateReceiveCount'])
                tier = get_tier(receive_count, config['tier'])
                if restore_object(s3, request, config['retention_days'], tier):
                    message.delete()
            except ValueError:
                log.warn("Could not format JSON object '%s'", message.body)


def restore_object(s3, request, retention_days, tier):
    try:
        log.info('Tier: %s, Retention Days: %s, Object: s3://%s/%s', tier, retention_days, request['Bucket'], request['Key'])
        s3.restore_object(
            Bucket=request['Bucket'],
            Key=request['Key'],
            RestoreRequest={
                'Days': retention_days,
                'GlacierJobParameters': {
                    'Tier': tier,
                },
            }
        )
    except ClientError as e:
        if e.response['Error']['Code'] == 'RestoreAlreadyInProgress':
            return True
        return False

    return True


def lambda_handler(event, context):
    arn = context.invoked_function_arn
    config = setup(arn)
    process_restore_requests(config['restore_requests'])
