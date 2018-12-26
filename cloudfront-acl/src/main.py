import json
from os import getenv
from logging import getLogger
import boto3


log = getLogger()
log.setLevel('INFO')
config = json.loads(getenv('CONFIG'))
s3 = boto3.client('s3')

def lambda_handler(event, context):
    for record in event['Records']:
        bucket = record['s3']['bucket']['name']
        key = record['s3']['object']['key']
        canonical_user = 'id={0}'.format(config['canonical_user_id'])
        log.info('Granting read on %s/%s to %s', bucket, key, canonical_user)
        s3.put_object_acl(Bucket=bucket, Key=key, GrantRead=canonical_user)
