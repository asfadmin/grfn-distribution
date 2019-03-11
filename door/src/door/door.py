import os
import json
import base64
from time import time
import boto3
from botocore.exceptions import ClientError
from flask import Flask, redirect, request, abort
from M2Crypto import EVP


app = Flask(__name__)
s3 = boto3.client('s3')


@app.before_first_request
def init_app():
    config = json.loads(get_environ_value('DOOR_CONFIG'))
    app.config.update(dict(config))
    boto3.setup_default_session(region_name=config['aws_region'])
    private_key = get_secret(app.config['private_key_secret_name'])['private_key']
    app.config['cloudfront']['private_key'] = str(private_key)


@app.route('/credentials', methods=['GET'])
def get_temporary_credentials():
    payload = {'user_id': get_environ_value('URS_USERID')}
    lamb = boto3.client('lambda')
    response = lamb.invoke(
        FunctionName=app.config['temporary_credentials_lambda'],
        Payload=json.dumps(payload),
    )
    response_payload = json.loads(response['Payload'].read())
    if 'errorType' in response_payload:
        abort(500)
    response = app.response_class(
        response=json.dumps(response_payload, indent=4),
        status=200,
        mimetype='application/json'
    )
    return response


@app.route('/download/<path:object_key>')
def download_redirect(object_key):
    try:
        s3.head_object(Bucket=app.config['bucket'], Key=object_key)
    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            abort(404)
        raise

    signed_url = get_signed_url(object_key, get_environ_value('URS_USERID'), app.config['cloudfront'])
    return redirect(signed_url)


def get_environ_value(key):
    if key in request.environ:
        return request.environ.get(key)
    if key in os.environ:
        return os.environ[key]
    return None


def get_signed_url(object_key, user_id, config):
    base_url = 'https://{0}/{1}?userid={2}'.format(config['domain_name'], object_key, user_id)
    expires = int(time()) + config['expire_time_in_seconds']
    policy = create_policy(base_url, expires)
    signature = get_signed_signature_for_string(policy, config['private_key'])
    signed_url = create_url(base_url, expires, config['key_pair_id'], signature)
    return signed_url


def aws_url_base64_encode(msg):
    msg_base64 = base64.b64encode(msg)
    msg_base64 = msg_base64.replace('+', '-')
    msg_base64 = msg_base64.replace('=', '_')
    msg_base64 = msg_base64.replace('/', '~')
    return msg_base64


def get_signed_signature_for_string(message, private_key_string):
    key = EVP.load_key_string(private_key_string)
    key.reset_context(md='sha1')
    key.sign_init()
    key.sign_update(str(message))
    signature = key.sign_final()
    signature = aws_url_base64_encode(signature)
    return signature


def get_secret(secret_name):
    sm = boto3.client('secretsmanager')
    response = sm.get_secret_value(SecretId=secret_name)
    secret = json.loads(response['SecretString'])
    return secret


def create_policy(url, expires):
    policy = '{"Statement":[{"Resource":"%(url)s","Condition":{"DateLessThan":{"AWS:EpochTime":%(expires)s}}}]}' % {'url':url, 'expires':expires}
    return policy


def create_url(base_url, expires, key_pair_id, signature):
    signed_url = '{0}&Expires={1}&Key-Pair-Id={2}&Signature={3}'.format(base_url, expires, key_pair_id, signature)
    return signed_url
