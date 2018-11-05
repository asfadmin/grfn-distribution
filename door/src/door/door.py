import os
import json
import base64
from datetime import datetime
from time import time
import boto3
from flask import Flask, redirect, render_template, request, abort, url_for
from M2Crypto import EVP


app = Flask(__name__)


@app.before_first_request
def init_app():
    config = json.loads(get_environ_value('DOOR_CONFIG'))
    app.config.update(dict(config))
    boto3.setup_default_session(region_name=config['aws_region'])
    private_key = get_secret(app.config['private_key_secret_name'])['private_key']
    app.config['cloudfront']['private_key'] = str(private_key)


@app.route('/')
def index():
    return redirect(url_for('status'))


@app.route('/status')
def status():
    user = get_user(app.config['users_table'], get_environ_value('URS_USERID'))
    data = {
        'retention_days': app.config['retention_days'],
        'subscribed_to_emails': user['subscribed_to_emails'],
        'objects': get_objects_for_user(app.config['status_lambda'], user['user_id']),
        'helpurl': app.config['helpurl'],
    }
    return render_template('status.html', data=data), 200


@app.route('/status/<path:object_key>')
def object_status(object_key):
    payload = {
        'object_key': object_key
    }
    lamb = boto3.client('lambda')
    response = lamb.invoke(
        FunctionName=app.config['object_status_lambda'],
        Payload=json.dumps(payload),
    )

    response_payload = json.loads(response['Payload'].read())

    if 'errorType' in response_payload:
        if response_payload['errorType'] == 'ClientError' and '404' in response_payload['errorMessage']:
            abort(404)
        else:
            abort(500)

    response = app.response_class(
        response=json.dumps(response_payload, indent=4),
        status=200,
        mimetype='application/json'
    )
    return response


@app.route('/userprofile', methods=['POST'])
def set_user_profile():
    user_id = get_environ_value('URS_USERID')
    table = app.config['users_table']
    user = get_user(table, user_id)
    user['subscribed_to_emails'] = ('subscribed_to_emails' in request.form)
    update_user(table, user)
    return redirect(url_for('show_user_profile'))


@app.route('/userprofile', methods=['GET'])
def show_user_profile():
    user = get_user(app.config['users_table'], get_environ_value('URS_USERID'))
    return render_template('userprofile.html', user=user), 200


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


@app.before_request
def sync_user():
    table = app.config['users_table']
    user_id = get_environ_value('URS_USERID')
    email_address = get_environ_value('URS_EMAIL')
    user = get_user(table, user_id)
    if not user:
        user = {
            'user_id': user_id,
            'email_address': email_address,
            'subscribed_to_emails': True,
            'last_acknowledgement': str(datetime(1970, 1, 1)),
        }
        update_user(table, user)
    elif user['email_address'] != email_address:
        user['email_address'] = email_address
        update_user(table, user)


@app.route('/download/<path:object_key>')
def download_redirect(object_key):
    payload = {
        'object_key': object_key,
        'user_id': get_environ_value('URS_USERID'),
    }
    lamb = boto3.client('lambda')
    response = lamb.invoke(
        FunctionName=app.config['availability_lambda'],
        Payload=json.dumps(payload),
    )


    response_payload = json.loads(response['Payload'].read())

    if 'errorType' in response_payload:
        if response_payload['errorType'] == 'ClientError' and '404' in response_payload['errorMessage']:
            abort(404)
        else:
            abort(500)

    if response_payload['available']:
        signed_url = get_signed_url(object_key, get_environ_value('URS_USERID'), app.config['cloudfront'])
        return redirect(signed_url)

    if get_environ_value('BROWSER_USER_AGENT'):
        return redirect(url_for('status'))
    return render_template('cli_user_agent_response.html'), 202


def update_user(table, user):
    dynamodb = boto3.client('dynamodb')
    primary_key = {'user_id': {'S': user['user_id']}}
    dynamodb.update_item(
        TableName=table,
        Key=primary_key,
        UpdateExpression='set email_address = :1, subscribed_to_emails = :2, last_acknowledgement = :3',
        ExpressionAttributeValues={
            ':1': {'S': user['email_address']},
            ':2': {'BOOL': user['subscribed_to_emails']},
            ':3': {'S': user['last_acknowledgement']},
        },
    )


def get_user(table, user_id):
    dynamodb = boto3.client('dynamodb')
    primary_key = {'user_id': {'S': user_id}}
    response = dynamodb.get_item(TableName=table, Key=primary_key)
    if 'Item' not in response:
        return None
    user = {
        'user_id': response['Item']['user_id']['S'],
        'email_address': response['Item']['email_address']['S'],
        'subscribed_to_emails': response['Item']['subscribed_to_emails']['BOOL'],
        'last_acknowledgement': response['Item']['last_acknowledgement']['S'],
    }
    return user


def get_environ_value(key):
    if key in request.environ:
        return request.environ.get(key)
    if key in os.environ:
        return os.environ[key]
    return None


def get_objects_for_user(status_lambda, user_id):
    payload = {'user_id': user_id}
    lamb = boto3.client('lambda')
    response = lamb.invoke(
        FunctionName=status_lambda,
        Payload=json.dumps(payload),
    )
    objects = json.loads(response['Payload'].read())
    return objects


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
