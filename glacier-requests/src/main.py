from os import environ
from logging import getLogger
import boto3
import json
from botocore.exceptions import ClientError


log = getLogger()


def setup():
    config = json.loads(environ['CONFIG'])
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
    config = setup()
    process_restore_requests(config['restore_requests'])
