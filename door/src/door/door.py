import os
import json
import boto3
from botocore.exceptions import ClientError
from botocore.signers import CloudFrontSigner
from datetime import datetime, timedelta
from flask import Flask, redirect, request, abort
import rsa


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
    abort(410)


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
    def rsa_signer(message):
        private_key = config['private_key']
        key = rsa.PrivateKey.load_pkcs1(private_key.encode(), 'PEM')
        return rsa.sign(message, key, 'SHA-1')

    base_url = 'https://{0}/{1}?userid={2}'.format(config['domain_name'], object_key, user_id)
    expiration_datetime = datetime.utcnow() + timedelta(seconds=config['expire_time_in_seconds'])
    cf_signer = CloudFrontSigner(config['key_pair_id'], rsa_signer)
    signed_url = cf_signer.generate_presigned_url(base_url, date_less_than=expiration_datetime)
    return signed_url


def get_secret(secret_name):
    sm = boto3.client('secretsmanager')
    response = sm.get_secret_value(SecretId=secret_name)
    secret = json.loads(response['SecretString'])
    return secret
