import boto3
import yaml
import os
import json
from flask import Flask, g, redirect, render_template, request, abort
from botocore.exceptions import ClientError
 
app = Flask(__name__)


@app.before_first_request
def init_app():
    if get_environ_value('DOOR_CONFIG').startswith('s3://'):
        path_parts = get_environ_value('DOOR_CONFIG').split('/')
        config_body = get_object_body(path_parts[2], '/'.join(path_parts[3:]))
        config = yaml.load(config_body)
    else: 
        with open(get_environ_value('DOOR_CONFIG'), 'r') as f:
            config = yaml.load(f)
    app.config.update(dict(config))
    boto3.setup_default_session(region_name=config['aws_region'])


@app.route('/')
def show_index():
   return get_content()

@app.route('/userprofile', methods=['GET','POST'])
def user_profile():
  g.perf = ''
        user_id = get_environ_value('URS_USERID')
        table = app.config['user_preference_table']

  if request.method == 'POST':
    if not request.form:
      put_user_preference(table,0,user_id)
    else:
      # Leaving this lean as we only have one checkbox
      put_user_preference(table,1,user_id)
      g.perf = "checked"
    return render_template('userprofile.html'), 200   
  
  response = get_user_preference(table,user_id)
  if response is None:
    put_user_preference(table,1,user_id)
    g.perf = "checked"
  else:
    if response is True:
      g.perf = "checked"  
      
  return render_template('userprofile.html'), 200

@app.route('/download/<file_name>')
def download_redirect(file_name):

    try:
        obj = get_object(app.config['bucket_name'], file_name)
    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            abort(404)
        raise
  
    available = process_availability(obj, app.config['glacier_retrieval'])

    if available:
        signed_url = get_link(obj.bucket_name, obj.key, app.config['expire_time_in_seconds'])
        signed_url = signed_url + "&userid=" + get_environ_value('URS_USERID')
        return redirect(signed_url)
    else:
        response = get_user_preference(app.config['user_preference_table'],get_environ_value('URS_USERID'))
        if response is not False:
           log_restore_request(app.config['restore_request_table'], obj, get_environ_value('URS_EMAIL'))
           g.email = get_environ_value('URS_EMAIL')
        return render_template('notavailable.html'), 202


def get_object(bucket, key):
    s3 = boto3.resource('s3')
    obj = s3.Object(bucket, key)
    obj.load()
    return obj

def get_object_body(bucket, key):
    obj = get_object(bucket, key)
    response = obj.get()
    return response["Body"].read()


def process_availability(obj, retrieval_opts):
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
    response = queue.send_message(MessageBody=json.dumps({'Bucket':obj.bucket_name, 'Key':obj.key}))

def restore_object(obj, days, tier):
    try: 
        obj.restore_object(
            RestoreRequest = {
                'Days': days,
                'GlacierJobParameters': {
                    'Tier': tier,
                },
            }
        ) 
    except ClientError as e:
        if e.response['Error']['Code'] == 'GlacierExpeditedRetrievalNotAvailable':
            queue_restore_request( obj )
        else: 
            raise

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
    response = dynamodb.get_item(
        TableName=table,
        Key=primary_key,
    )

    if not response
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
    elif key in os.environ:
        return os.environ[key]
    else:
        return None


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
