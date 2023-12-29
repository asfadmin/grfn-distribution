import json
import os

import boto3
import serverless_wsgi

from door import app


serverless_wsgi.TEXT_MIME_TYPES.append('application/problem+json')


def get_secret(secret_name):
    sm = boto3.client('secretsmanager', os.environ['AWS_REGION'])
    response = sm.get_secret_value(SecretId=secret_name)
    secret = json.loads(response['SecretString'])
    return secret


private_key = get_secret(os.environ['PRIVATE_KEY_SECRET_NAME'])['private_key']
os.environ['CLOUDFRONT_PRIVATE_KEY'] = str(private_key)


def handler(event, context):
    return serverless_wsgi.handle_request(app, event, context)
