import boto3
import zipfile
import os.path


landing_bucket_name = 'grfn-d-a4d38f59-5e57-590c-a2be-58640db02d91'
content_bucket_name = 'grfn-d-fe9f1b34-1425-56b9-939f-5f1431a6d1de'
working_directory = '/tmp/'

s3 = boto3.resource('s3')


def process_object(s3_object):
    #sanity check
    local_zip_file = os.path.join(working_directory, s3_object.key)
    s3_object.download_file(local_zip_file)
    with zipfile.ZipFile(local_zip_file, 'r') as zip_ref:
        zip_ref.extractall()
    # reorganize
    # zip
    distribution_zip = local_zip_file
    s3.Bucket(content_bucket_name).upload_file(distribution_zip)
    #s3_object.delete()


landing_bucket = s3.Bucket(landing_bucket_name)
for object in landing_bucket.objects.all():
    process_object(object)

