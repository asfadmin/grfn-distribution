import os
import json
import re

import boto3
from botocore.exceptions import ClientError
from flask import Flask, g, redirect, render_template, request, abort, url_for

app = Flask(__name__)


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
    products = get_glacier_products()
    return render_template('status.html', products=products), 200


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
        obj = get_object(app.config['bucket_name'], file_name)
    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            abort(404)
        raise

    available = process_availability(obj)

    if available:
        signed_url = get_link(obj.bucket_name, obj.key, app.config['expire_time_in_seconds'])
        signed_url = signed_url + '&userid=' + get_environ_value('URS_USERID')
        return redirect(signed_url)
    else:
        response = get_user_preference(app.config['user_preference_table'], get_environ_value('URS_USERID'))
        if response is not False:
            log_restore_request(app.config['restore_request_table'], obj, get_environ_value('URS_EMAIL'))
        return redirect(url_for('status'))


def get_object(bucket, key):
    s3 = boto3.resource('s3')
    obj = s3.Object(bucket, key)
    obj.load()
    return obj


def get_object_body(bucket, key):
    obj = get_object(bucket, key)
    response = obj.get()
    return response['Body'].read()


def process_availability(obj):
    available = True
    if obj.storage_class == 'GLACIER':
        restore_status = translate_restore_status(obj.restore)
        if restore_status in ['not_available', 'in_progress']:
            available = False
        if restore_status in ['not_available', 'available']:  # restoring available objects extends their expiration date
            queue_restore_request(obj)

    return available


def translate_restore_status(restore):
    if restore is None:
        return 'not_available'
    if 'ongoing-request="true"' in restore:
        return 'in_progress'
    return 'available'


def queue_restore_request(obj):
    sqs = boto3.resource('sqs')
    queue = sqs.get_queue_by_name(QueueName=app.config['glacier_restore_sqs'])
    queue.send_message(MessageBody=json.dumps({'Bucket':obj.bucket_name, 'Key':obj.key}))


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


def log_restore_request(table, obj, email_address):
    dynamodb = boto3.client('dynamodb')
    primary_key = {'bucket': {'S': obj.bucket_name}, 'key': {'S': obj.key}}
    val = {'SS': [email_address]}
    dynamodb.update_item(
        TableName=table,
        Key=primary_key,
        UpdateExpression='ADD email_addresses :1',
        ExpressionAttributeValues={':1': val},
    )


def get_environ_value(key):
    if key in request.environ:
        return request.environ.get(key)
    if key in os.environ:
        return os.environ[key]
    return None


def get_link(bucket_name, object_key, expire_time_in_seconds):
    s3_client = boto3.client('s3')

    url = s3_client.generate_presigned_url(
        ClientMethod='get_object',
        Params={
            'Bucket': bucket_name,
            'Key': object_key,
        },
        ExpiresIn=expire_time_in_seconds,
    )
    return url


def get_glacier_products():
    dynamodb = boto3.client('dynamodb')
    response = dynamodb.scan(TableName=app.config['restore_request_table'])
    keys = [item['key']['S'] for item in response['Items'] if get_environ_value('URS_EMAIL') in item['email_addresses']['SS']]
    products = []
    for key in keys:
        obj = get_object(app.config['bucket_name'], key)
        product = {
            'key': key,
            'status': translate_restore_status(obj.restore),
            'url': url_for('download_redirect', file_name=key),
        }
        if product['status'] == 'available':
            product['expiration'] = re.search('expiry-date="(.+)"', obj.restore).group(1)
        products.append(product)
    return products
