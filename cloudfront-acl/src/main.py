import json
from os import environ
from logging import getLogger
import boto3


log = getLogger()
s3 = boto3.client('s3')


def setup():
    config = json.loads(environ['CONFIG'])
    log.setLevel(config['log_level'])
    log.debug('Config: %s', str(config))
    return config


def lambda_handler(event, context):
    config = setup()
    for record in event['Records']:
        bucket = record['s3']['bucket']['name']
        key = record['s3']['object']['key']
        canonical_user = 'id={0}'.format(config['canonical_user_id'])
        log.info('Granting read on %s/%s to %s', bucket, key, canonical_user)
        s3.put_object_acl(Bucket=bucket, Key=key, GrantRead=canonical_user)
