#!/usr/bin/python

import boto3
import zipfile
import os
import time
import yaml


def create_output_zip(source_name, dest_name, files):
    with zipfile.ZipFile(source_name, 'r') as source_zip:
        with zipfile.ZipFile(dest_name, 'w') as dest_zip:
            for f in files:
                dest_zip.writestr(f['dest'], source_zip.read(f['source']))
 

def get_bucket(bucket_name):
    return boto3.resource('s3').Bucket(bucket_name)


def upload_object(bucket_name, key, local_file_name):
    bucket = get_bucket(bucket_name)
    bucket.upload_file(local_file_name, key)


def process_output_file(output_file, input_file_name, content_bucket_name):
    output_file_name = os.path.splitext(input_file_name)[0] + output_file['extension']
    create_output_zip(input_file_name, output_file_name, output_file['files'])
    upload_object(content_bucket_name, os.path.split(output_file_name)[1], output_file_name)
    os.remove(output_file_name)


def ingest_object(obj, content_bucket_name, output_files):
    obj.download_file(obj.key)
    for output_file in output_files:
        process_output_file(output_file, obj.key, content_bucket_name)
    upload_object(content_bucket_name, obj.key, obj.key)
    os.remove(obj.key)
    obj.delete()


def get_objects_to_ingest(landing_bucket_name):
    landing_bucket = get_bucket(landing_bucket_name)
    object_summaries = landing_bucket.objects.all()
    objects = [s.Object() for s in object_summaries]
    return objects


def get_config(config_file_name):
    with open(config_file_name, 'r') as f:
        config = yaml.load(f)
    return config
 

if __name__ == "__main__":
    config = get_config('ingest_config.yaml')
    os.chdir(config['working_directory'])
    while True:
        for obj in get_objects_to_ingest(config['landing_bucket_name']):
            print('Processing {0}'.format(obj.key))
            ingest_object(obj, config['content_bucket_name'], config['output_files'])
            print('Done processing {0}'.format(obj.key))
        time.sleep(config['sleep_time_in_seconds'])

