import boto3
import yaml
import os
from flask import Flask, g, redirect, render_template, request
    
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
    s3 = boto3.resource('s3')
    obj = s3.Object(app.config['bucket_name'], file_name) # TODO handle error when file not found

    available = True
    if obj.storage_class == 'GLACIER':
        if obj.restore is None or 'ongoing-request="true"' obj.restore:
            available = False
        if obj.restore is None or 'ongoing-request="false"' obj.restore:
            restore_object(obj)

    if available:
        signed_url = get_link(app.config['bucket_name'], file_name, app.config['expire_time_in_seconds'])
        signed_url = signed_url + "&userid=" + request.environ.get('URS_USERID')
        return redirect(signed_url)
    else:
        return redirect('https://grfn-door-dev.asf.alaska.edu/409.html', code=409)


def restore_object(obj):
    obj.restore_object(
        RestoreRequest = {
            'Days': 1, #TODO move to config
            'GlacierJobParameters': {
                'Tier': 'Expedited', # TODO move to config
            },
        }
    )


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
