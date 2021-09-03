import json
import os

from botocore.exceptions import ClientError
from botocore.signers import CloudFrontSigner
from datetime import datetime, timedelta, timezone
from flask import abort, g, redirect
import boto3
import rsa

from door import app

s3 = boto3.client('s3')


@app.before_first_request
def init_app():
    private_key = get_secret(os.environ['PRIVATE_KEY_SECRET_NAME'])['private_key']
    os.environ['CLOUDFRONT_PRIVATE_KEY'] = str(private_key)


@app.before_request
def authenticate_user():
    g.user_id = 'asjohnston'  # FIXME


@app.route('/download/<path:object_key>')
def download_redirect(object_key):
    try:
        s3.head_object(Bucket=os.environ['BUCKET'], Key=object_key)
    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            abort(404)
        raise

    signed_url = get_signed_url(object_key, g.user_id)
    return redirect(signed_url)


def get_signed_url(object_key, user_id):
    def rsa_signer(message):
        key = rsa.PrivateKey.load_pkcs1(os.environ['CLOUDFRONT_PRIVATE_KEY'].encode(), 'PEM')
        return rsa.sign(message, key, 'SHA-1')

    base_url = f'https://{os.environ["CLOUDFRONT_DOMAIN_NAME"]}/{object_key}?userid={user_id}'
    expiration_datetime = datetime.now(tz=timezone.utc) + timedelta(seconds=int(os.environ['EXPIRE_TIME_IN_SECONDS']))
    cf_signer = CloudFrontSigner(os.environ['CLOUDFRONT_KEY_PAIR_ID'], rsa_signer)
    signed_url = cf_signer.generate_presigned_url(base_url, date_less_than=expiration_datetime)
    return signed_url


def get_secret(secret_name):
    sm = boto3.client('secretsmanager', os.environ['AWS_REGION'])
    response = sm.get_secret_value(SecretId=secret_name)
    secret = json.loads(response['SecretString'])
    return secret
