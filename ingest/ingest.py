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

log = logging.getLogger()


def get_isce_data(source_zip):
    source_dir = os.path.splitext(source_zip)[0]
    with zipfile.ZipFile(source_zip, 'r') as z:
        source_file = os.path.join(source_dir, 'isce.log')
        content = z.read(source_file)
    m = re.search('ctx: ({.*})\n\d', content, re.DOTALL)
    data = json.loads(m.group(1))
    data['bounding_box'] = {}
    pattern = 'geocode.(North|South|East|West) = (.*)$'
    for line in content.split('\n'):
        match = re.search(pattern, line)
        if match is not None:
            data['bounding_box'][match.group(1).lower()] = match.group(2)
    return data


def get_cmr_payload(source_zip, file_name, collection):
    isce_data = get_isce_data(source_zip)
    payload = {
        'file_name': file_name,
        'collection': collection,
        'master_granule_ur': os.path.splitext(min(isce_data['master_zip_file']))[0] + '-SLC',
        'slave_granule_ur': os.path.splitext(max(isce_data['slave_zip_file']))[0] + '-SLC',
        'file_size': os.path.getsize(file_name),
        'bounding_box': isce_data['bounding_box'],
    }
    return payload


def send_to_cmr(lambda_arn, payload):
    region_name = lambda_arn.split(':')[3]
    lam = boto3.client('lambda', region_name=region_name)
    lam.invoke(FunctionName=lambda_arn, InvocationType='Event', Payload=json.dumps(payload))


def create_output_zip(source_name, dest_name, files):
    source_dir = os.path.splitext(source_name)[0]
    with zipfile.ZipFile(source_name, 'r') as source_zip:
        with zipfile.ZipFile(dest_name, 'w') as dest_zip:
            for f in files:
                source_file = os.path.join(source_dir, f['source'])
                dest_zip.writestr(f['dest'], source_zip.read(source_file))
 

def get_bucket(bucket_name):
    return boto3.resource('s3').Bucket(bucket_name)


def upload_object(bucket_name, key, local_file_name):
    bucket = get_bucket(bucket_name)
    bucket.upload_file(local_file_name, key)


def process_output_file(output_file_config, input_file_name, content_bucket_name, cmr_lambda_arn):
    output_file_name = os.path.splitext(input_file_name)[0] + output_file_config['extension']
    log.info('Processing output file {0}'.format(output_file_name))
    create_output_zip(input_file_name, output_file_name, output_file_config['files'])
    upload_object(content_bucket_name, os.path.split(output_file_name)[1], output_file_name)
    if 'cmr_collection' in output_file_config:
        cmr_payload = get_cmr_payload(input_file_name, output_file_name, output_file_config['cmr_collection'])
        send_to_cmr(cmr_lambda_arn, cmr_payload)
    os.remove(output_file_name)
    log.info('Done processing output file {0}'.format(output_file_name))


def ingest_object(obj, content_bucket_name, output_file_configs, cmr_lambda_arn):
    obj.download_file(obj.key)
    for output_file_config in output_file_configs:
        process_output_file(output_file_config, obj.key, content_bucket_name, cmr_lambda_arn)
    upload_object(content_bucket_name, obj.key, obj.key)
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
    return asf.log.getLogger(screen=log_config['screen'], verbose=log_config['verbose'])


def ingest_loop(ingest_config):
    while True:
        obj = get_object_to_ingest(ingest_config['landing_bucket_name'])
        if obj:
            log.info('Processing input file {0}'.format(obj.key))
            ingest_object(obj, ingest_config['content_bucket_name'], ingest_config['output_files'], ingest_config['cmr_lambda_arn'])
            log.info('Done processing input file {0}'.format(obj.key))
        else:
            time.sleep(ingest_config['sleep_time_in_seconds'])


if __name__ == "__main__":
    try:
        options = get_command_line_options()
        config = get_config(options.config_file)
        log = get_logger(config['log'])
        os.chdir(config['working_directory'])
        ingest_loop(config['ingest'])
    except:
        log.exception('Unhandled exception!')
        raise

