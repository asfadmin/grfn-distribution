import boto3
import yaml
import os
from flask import Flask, g, redirect, render_template, request
    
app = Flask(__name__)

@app.before_first_request
def init_app():
    with open(os.environ['DOOR_CONFIG'], 'r') as f:
        config = yaml.load(f)
        app.config.update(dict(config['content']))
    pass

@app.route('/')
def show_index():
   return get_content()

@app.route('/download/<granule>')
def download_redirect(granule):
   signed_url = get_link(app.config['bucket_name'], granule, app.config['expire_time_in_seconds'])
   signed_url = signed_url + "&userid=" + request.environ.get('URS_USERID')
   return redirect(signed_url)
   

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
