import boto3
import yaml
import os
from flask import Flask, g, redirect, render_template, request, abort
from botocore.exceptions import ClientError
 
app = Flask(__name__)


@app.before_first_request
def init_app():
    with open(os.environ['DOOR_CONFIG'], 'r') as f:
        config = yaml.load(f)
        app.config.update(dict(config))


@app.route('/')
def show_index():
   return get_content()


@app.route('/download/<file_name>')
def download_redirect(file_name):

    try:
        obj = get_object(app.config['bucket_name'], file_name)
    except ClientError as e:
        if e.response['Error']['Code'] == "404":
            abort(404)
        raise

    available = process_availability(obj, app.config['retrieval_lifetime_in_days'], app.config['retrieval_tier'])

    if available:
        signed_url = get_link(obj.bucket_name, obj.key, app.config['expire_time_in_seconds'])
        signed_url = signed_url + "&userid=" + request.environ.get('URS_USERID')
        return redirect(signed_url)
    else:
        return render_template('notavailable.html'), 409


def get_object(bucket, key):
    s3 = boto3.resource('s3')
    obj = s3.Object(bucket, key)
    obj.load()
    return obj


def process_availability(obj, days, tier):
    available = True
    if obj.storage_class == 'GLACIER':
        restore_status = get_restore_status(obj.restore)
        if restore_status in ['not_available', 'in_progress']:
            available = False
        if restore_status in ['not_available', 'available']:
            restore_object(obj, days, tier)
    return available


def get_restore_status(restore):
    if restore is None:
        return 'not_available'
    if 'ongoing-request="true"' in restore:
        return 'in_progress'
    return 'available'


def restore_object(obj, days, tier):
    obj.restore_object(
        RestoreRequest = {
            'Days': days,
            'GlacierJobParameters': {
                'Tier': tier,
            },
        }
    ) # TODO handle error when expedited retrievals are not available


def get_link(bucket_name, object_key, expire_time_in_seconds):
    s3_client = boto3.client('s3')

    url = s3_client.generate_presigned_url(
       ClientMethod='get_object',
       Params = {
          'Bucket': bucket_name,
          'Key': object_key,
           },
       ExpiresIn = expire_time_in_seconds
    )
    return url


def get_objects(bucket_name):
    s3_client = boto3.client('s3')
    bucket = boto3.resource('s3').Bucket(bucket_name)
    
    object_keys = []
    for obj in bucket.objects.all():
       object_keys.append({'text': obj.key})

    return object_keys 


def get_content():
    g.objects = get_objects(app.config['bucket_name'])
    content = render_template('index.html')
    return content
