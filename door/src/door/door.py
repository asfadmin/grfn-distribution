import os
import json
from datetime import datetime

import boto3
from botocore.exceptions import ClientError
from flask import Flask, redirect, render_template, request, abort, url_for

app = Flask(__name__)
s3_resource = boto3.resource('s3')
s3_client = boto3.client('s3')


@app.before_first_request
def init_app():
    config = json.loads(get_environ_value('DOOR_CONFIG'))
    app.config.update(dict(config))
    boto3.setup_default_session(region_name=config['aws_region'])


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
    }
    return render_template('status.html', data=data), 200


@app.route('/status/<path:object_key>')
def object_status(object_key):

    lamb = boto3.client('lambda')
    payload = {
        'object_key': object_key
    }
    response = lamb.invoke(
        FunctionName=app.config['object_status_lambda'],
        Payload=json.dumps(payload),
    )

    response = app.response_class(
        response=response['Payload'].read(),
        status=200,
        mimetype='application/json'
    )
    return(response)


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
    try:
        obj = get_s3_object(app.config['bucket_name'], object_key)
    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            abort(404)
        raise

    lamb = boto3.client('lambda')
    payload = {
        'object_key': object_key,
        'user_id': get_environ_value('URS_USERID'),
    }
    response = lamb.invoke(
        FunctionName=app.config['availability_lambda'],
        Payload=json.dumps(payload),
    )
    available = json.loads(response['Payload'].read())['available']

    if available:
        signed_url = get_link(obj.bucket_name, obj.key, app.config['expire_time_in_seconds'])
        signed_url = signed_url + '&userid=' + get_environ_value('URS_USERID')
        return redirect(signed_url)

    if get_environ_value('CLI_USER_AGENT'):
        return render_template('cli_user_agent_response.html'), 202

    return redirect(url_for('status'))


def get_s3_object(bucket, key):
    obj = s3_resource.Object(bucket, key)
    obj.load()
    return obj


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


def get_link(bucket_name, object_key, expire_time_in_seconds):
    url = s3_client.generate_presigned_url(
        ClientMethod='get_object',
        Params={
            'Bucket': bucket_name,
            'Key': object_key,
        },
        ExpiresIn=expire_time_in_seconds,
    )
    return url


def get_objects_for_user(status_lambda, user_id):
    payload = {'user_id': user_id}
    lamb = boto3.client('lambda')
    response = lamb.invoke(
        FunctionName=status_lambda,
        Payload=json.dumps(payload),
    )
    objects = json.loads(response['Payload'].read())
    return objects
