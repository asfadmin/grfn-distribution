import json
from os import environ
from logging import getLogger
import boto3


log = getLogger()
sts = boto3.client('sts')


def setup():
    config = json.loads(environ['CONFIG'])
    log.setLevel(config['log_level'])
    log.debug('Config: %s', str(config))
    return config


def get_temporary_credentials(user_id, config):
    log.info('Generating temporary credentials for user %s', user_id)
    response = sts.assume_role(
        RoleArn=config['role_arn'],
        RoleSessionName=user_id,
        DurationSeconds=config['duration_seconds'],
    )
    response['Credentials']['Expiration'] = str(response['Credentials']['Expiration'])
    return response['Credentials']


def lambda_handler(event, context):
    config = setup()
    response = get_temporary_credentials(event['user_id'], config['temporary_credentials'])
    return response
