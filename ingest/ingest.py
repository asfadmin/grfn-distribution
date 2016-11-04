#!/usr/bin/python

import boto3
import zipfile
import os
import time


landing_bucket_name = 'grfn-d-a4d38f59-5e57-590c-a2be-58640db02d91'
content_bucket_name = 'grfn-d-fe9f1b34-1425-56b9-939f-5f1431a6d1de'
working_directory = '/tmp/'
sleep_time_in_seconds = 30

output_files = [
    {
        'extension': '.unw_geo.zip',
        'files': [
            {'source': 'fine_interferogram.xml', 'dest': 'fine_interferogram.xml'},
            {'source': 'merged/filt_topophase.unw.geo', 'dest': 'filt_topophase.unw.geo'},
            {'source': 'merged/filt_topophase.unw.geo.hdr', 'dest': 'filt_topophase.unw.geo.hdr'},
            {'source': 'merged/filt_topophase.unw.geo.vrt', 'dest': 'filt_topophase.unw.geo.vrt'},
            {'source': 'merged/filt_topophase.unw.geo.xml', 'dest': 'filt_topophase.unw.geo.xml'},
            {'source': 'merged/phsig.cor.geo', 'dest': 'phsig.cor.geo'},
            {'source': 'merged/phsig.cor.geo.hdr', 'dest': 'phsig.cor.geo.hdr'},
            {'source': 'merged/phsig.cor.geo.vrt', 'dest': 'phsig.cor.geo.vrt'},
            {'source': 'merged/phsig.cor.geo.xml', 'dest': 'phsig.cor.geo.xml'},
        ],
    },
    {
        'extension': '.full_res.zip',
        'files': [
            {'source': 'fine_interferogram.xml', 'dest': 'fine_interferogram.xml'},
            {'source': 'merged/filt_topophase.flat', 'dest': 'filt_topophase.flat'},
            {'source': 'merged/filt_topophase.flat.hdr', 'dest': 'filt_topophase.flat.hdr'},
            {'source': 'merged/filt_topophase.flat.vrt', 'dest': 'filt_topophase.flat.vrt'},
            {'source': 'merged/filt_topophase.flat.xml', 'dest': 'filt_topophase.flat.xml'},
            {'source': 'merged/dem.crop', 'dest': 'dem.crop'},
            {'source': 'merged/dem.crop.hdr', 'dest': 'dem.crop.hdr'},
            {'source': 'merged/dem.crop.vrt', 'dest': 'dem.crop.vrt'},
            {'source': 'merged/dem.crop.xml', 'dest': 'dem.crop.xml'},
        ]
    },
    {
        'extension': '.5cm_browse.zip',
        'files': [
            {'source': 'fine_interferogram.xml', 'dest': 'fine_interferogram.xml'},
            {'source': 'unw.geo_5cm.browse.png', 'dest': 'unw.geo_5cm.browse.png'},
            {'source': 'unw.geo_5cm.browse_small.png', 'dest': 'unw.geo_5cm.browse_small.png'},
        ]
    },
]


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


def process_output_file(output_file, input_file_name):
    output_file_name = os.path.splitext(input_file_name)[0] + output_file['extension']
    create_output_zip(input_file_name, output_file_name, output_file['files'])
    upload_object(content_bucket_name, os.path.split(output_file_name)[1], output_file_name)
    os.remove(output_file_name)


def ingest_object(obj):
    local_file = os.path.join(working_directory, obj.key)
    obj.download_file(local_file)
    for output_file in output_files:
        process_output_file(output_file, local_file)
    upload_object(content_bucket_name, obj.key, local_file)
    os.remove(local_file)
    obj.delete()


def get_objects_to_ingest():
    landing_bucket = get_bucket(landing_bucket_name)
    object_summaries = landing_bucket.objects.all()
    objects = [s.Object() for s in object_summaries]
    return objects


if __name__ == "__main__":
    while True:
        for obj in get_objects_to_ingest():
            print('Processing {0}'.format(obj.key))
            ingest_object(obj)
            print('Done processing {0}'.format(obj.key))
        time.sleep(sleep_time_in_seconds)

