import os
import json

import boto3
from botocore.exceptions import ClientError
from flask import Flask, g, redirect, render_template, request, abort, url_for

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
    retention_days = app.config['retention_days']

    payload = {'user_id': get_environ_value('URS_USERID')}
    lamb = boto3.client('lambda')
    response = lamb.invoke(
        FunctionName=app.config['status_lambda'],
        Payload=json.dumps(payload),
    )
    objects = json.loads(response['Payload'].read())

    return render_template('status.html', objects=objects, retention_days=retention_days), 200


@app.route('/userprofile', methods=['GET', 'POST'])
def user_profile():
    g.perf = ''
    user_id = get_environ_value('URS_USERID')
    table = app.config['user_preference_table']

    if request.method == 'POST':
        if not request.form:
            put_user_preference(table, 0, user_id)
        else:
            # Leaving this lean as we only have one checkbox
            put_user_preference(table, 1, user_id)
            g.perf = 'checked'
        return render_template('userprofile.html'), 200

    response = get_user_preference(table, user_id)
    if response is None:
        put_user_preference(table, 1, user_id)
        g.perf = 'checked'
    else:
        if response is True:
            g.perf = 'checked'

    return render_template('userprofile.html'), 200


@app.route('/download/<file_name>')
def download_redirect(file_name):
    try:
        obj = get_s3_object(app.config['bucket_name'], file_name)
    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            abort(404)
        raise

    lamb = boto3.client('lambda')
    payload = {
        'object_key': file_name,
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

    return redirect(url_for('status'))


def get_s3_object(bucket, key):
    obj = s3_resource.Object(bucket, key)
    obj.load()
    return obj


def put_user_preference(table, pref, user_name):
    dynamodb = boto3.client('dynamodb')
    primary_key = {'user': {'S': user_name}}
    val = {'BOOL':  bool(pref)}
    dynamodb.update_item(
        TableName=table,
        Key=primary_key,
        UpdateExpression='set email =  :1',
        ExpressionAttributeValues={':1': val},
    )


def get_user_preference(table, user_name):
    dynamodb = boto3.client('dynamodb')
    primary_key = {'user': {'S': user_name}}
    response = dynamodb.get_item(TableName=table, Key=primary_key)

    if 'Item' not in response:
        return None
    return response['Item']['email']['BOOL']


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
