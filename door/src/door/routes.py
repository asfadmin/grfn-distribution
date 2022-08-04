import os
from urllib.parse import quote_plus

import boto3
import jwt
from botocore.exceptions import ClientError
from flask import abort, g, redirect, request
from flask_cors import CORS

from door import app

CORS(app, origins=r'https?://([-\w]+\.)*asf\.alaska\.edu', supports_credentials=True)
s3 = boto3.client('s3')


def decode_token(token):
    try:
        payload = jwt.decode(token, os.environ['JWT_PUBLIC_KEY'], algorithms='RS256')
        return payload
    except (jwt.ExpiredSignatureError, jwt.DecodeError):
        return None


@app.before_request
def authenticate_user():
    cookie = request.cookies.get(os.environ['JWT_COOKIE_NAME'])
    token = decode_token(cookie)
    if not token:
        redirect_url = os.environ['AUTH_URL'] + '&state=' + quote_plus(request.base_url)
        if not request.headers.get('User-Agent', '').startswith('Mozilla'):
            redirect_url += '&app_type=401'
        return redirect(redirect_url)
    g.user_id = token['urs-user-id']


@app.route('/door/credentials', methods=['GET'])
def get_temporary_credentials():
    abort(410)


@app.route('/door/download/<path:object_key>')
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
    signed_url = s3.generate_presigned_url(
        ClientMethod='get_object',
        Params={'Bucket': os.environ['BUCKET'], 'Key': object_key},
        ExpiresIn=int(os.environ['EXPIRE_TIME_IN_SECONDS']),
    )
    signed_url += f'&user_id={user_id}'
    return signed_url
