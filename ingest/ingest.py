#!/usr/bin/python

import boto3
import zipfile
import os
import time
import yaml
import argparse
import asf.log
import logging
import re
import json
import mimetypes

log = logging.getLogger()


def create_output_zip_file(output_file_name, input_zip_handle, files):
    with zipfile.ZipFile(output_file_name, 'w') as output_zip_handle:
        for f in files:
            output_zip_handle.writestr(f['dest'], input_zip_handle.read(f['source']))


def create_output_file(output_file_name, input_zip_handle, file_name):
    with open(output_file_name, 'w') as f:
        f.write(input_zip_handle.read(file_name))
 

def get_bucket(bucket_name):
    return boto3.resource('s3').Bucket(bucket_name)


def upload_object(bucket_name, key):
    bucket = get_bucket(bucket_name)
    content_type = mimetypes.guess_type(key)[0]
    bucket.upload_file(key, key, ExtraArgs={'ContentType': content_type})


def process_output_file(output_file_config, input_zip_handle):
    log.info('Processing output file {0}'.format(output_file_config['key']))
    if 'files' in output_file_config:
        create_output_zip_file(output_file_config['key'], input_zip_handle, output_file_config['files'])
    else:
        create_output_file(output_file_config['key'], input_zip_handle, output_file_config['file'])
    upload_object(output_file_config['bucket'], output_file_config['key'])
    os.remove(output_file_config['key'])
    log.info('Done processing output file {0}'.format(output_file_config['key']))


def process_input_file(obj, output_file_configs, master_bucket):
    obj.download_file(obj.key)
    with zipfile.ZipFile(obj.key, 'r') as input_zip_handle:
        for output_file_config in output_file_configs:
            process_output_file(output_file_config, input_zip_handle)
    # TODO figure out what to do with the original
    upload_object(master_bucket, obj.key)
    os.remove(obj.key)
    obj.delete()


def get_object_to_ingest(landing_bucket_name):
    landing_bucket = get_bucket(landing_bucket_name)
    for object_summary in landing_bucket.objects.limit(1):
        return object_summary.Object()
    return None


def get_config(config_file_name):
    with open(config_file_name, 'r') as f:
        config = yaml.load(f)
    return config
 

def get_command_line_options():
    parser = argparse.ArgumentParser('Ingest Sentinel-1 interferogram products')
    parser.add_argument(
        '-c', '--config',
        action = 'store',
        dest = 'config_file',
        default = 'ingest_config.yaml',
        help = 'use a specific config file',
    )
    options = parser.parse_args()
    return options


def get_logger(log_config):
    return asf.log.getLogger(**log_config)


def send_granule_to_cmr(lambda_arn, payload):
    region_name = lambda_arn.split(':')[3]
    lambda_client = boto3.client('lambda', region_name=region_name)
    lambda_client.invoke(FunctionName=lambda_arn, InvocationType='Event', Payload=json.dumps(payload))


def process_cmr_reporting(cmr_config):
    for granule in cmr_config['granules']:
        send_granule_to_cmr(cmr_config['lambda_arn'], granule)


def format_config(config, object_key):
    tokens = {'$NAME': os.path.splitext(object_key)[0]}
    config_str = str(config)
    for key, value in tokens.iteritems():
        config_str = config_str.replace(key, value)
    return yaml.load(config_str)


def ingest_loop(ingest_config):
    while True:
        obj = get_object_to_ingest(ingest_config['landing_bucket_name'])
        if obj:
            log.info('Processing input file {0}'.format(obj.key))
            formatted_config = format_config(ingest_config, obj.key)
            process_input_file(obj, formatted_config['output_files'], formatted_config['private_content_bucket_name'])
            process_cmr_reporting(formatted_config['cmr'])
            log.info('Done processing input file {0}'.format(obj.key))
        else:
            time.sleep(ingest_config['sleep_time_in_seconds'])


if __name__ == "__main__":
    try:
        options = get_command_line_options()
        config = get_config(options.config_file)
        log = get_logger(config['log'])
        for type, ext in config['extra_mime_types'].iteritems():
            mimetypes.add_type(type, ext)
        os.chdir(config['working_directory'])
        ingest_loop(config['ingest'])
    except:
        log.exception('Unhandled exception!')
        raise

