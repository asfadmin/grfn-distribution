#!/usr/bin/python

import boto3
import zipfile
import os


landing_bucket_name = 'grfn-d-a4d38f59-5e57-590c-a2be-58640db02d91'
content_bucket_name = 'grfn-d-fe9f1b34-1425-56b9-939f-5f1431a6d1de'
working_directory = '/tmp/'


def get_bucket(bucket_name):
    return boto3.resource('s3').Bucket(bucket_name)


def upload_object(bucket_name, key, local_file_name):
    bucket = get_bucket(bucket_name)
    bucket.upload_file(local_file_name, key)


def ingest_object(obj):
    local_file = os.path.join(working_directory, obj.key)
    obj.download_file(local_file)
    upload_object(content_bucket_name, obj.key, local_file)
    os.remove(local_file)
    obj.delete()


def get_objects_to_ingest():
    landing_bucket = get_bucket(landing_bucket_name)
    object_summaries = landing_bucket.objects.all()
    objects = [s.Object() for s in object_summaries]
    return objects


if __name__ == "__main__":
    for obj in get_objects_to_ingest():
        ingest_object(obj)

