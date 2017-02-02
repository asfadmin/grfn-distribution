# utility script to trigger grfn-echo10-construction for an arbitrary list of granules
# not production quality, use at your own risk

import boto3
import json
import time
import re

lambda_arn = 'arn:aws:lambda:us-west-2:765666652335:function:grfn-echo10-construction:DEV'
private_bucket = 'grfn-d-fe9f1b34-1425-56b9-939f-5f1431a6d1de'
public_bucket = 'grfn-d-b6710a78-8fc7-5e52-bdc3-b7ea3b691575'
sleep_time_in_seconds = 20
pause_every_x_items = None  # None to disable

# Ususally the same as Private bucket, set to False to prevent bucket-based reprocessing
reprocess_bucket = private_bucket
reprocess_product_regex = "(?P<product_name>S1-\w+_\w+_\w+_\w+-\w+_\w+-\w+-v\d+\.\d+\.\d+)\.zip"

# Which types to send to CMR
process_cmr_for = { 'unw_geo': False, 'full_res': False, 'all_prods': True}

granules = [
'S1-IFG_STCM1S1_TN035_20161208T020720-20170101T020747_s2-resorb-v1.0.1',
'S1-IFG_STCM1S1_TN035_20161208T020720-20170101T020747_s3-resorb-v1.0.1',
'S1-IFG_STCM1S1_TN064_20161210T014940-20170103T015006_s1-resorb-v1.0.1',
]

# Comment this line out process list of granules with, or without bucket-based reprocessing
granules = None

def unw_geo_payload(granule):
    return {
      'collection': 'Sentinel-1 Unwrapped Interferogram and Coherence Map (BETA)',
      'zip': {
          'key': granule + '.unw_geo.zip',
          'bucket': private_bucket,
       },
       'browse': {
          'key': granule + '.unw_geo.browse.png',
          'bucket': public_bucket,
       },
       'log': {
          'key': granule + '.isce.log',
          'bucket': private_bucket,
       }
    }


def full_res_payload(granule):
    return {
      'collection': 'Sentinel-1 Full Resolution Wrapped Interferogram and DEM (BETA)',
      'zip': {
          'key': granule + '.full_res.zip',
          'bucket': private_bucket,
       },
       'browse': {
          'key': granule + '.full_res.browse.png',
          'bucket': public_bucket,
       },
       'log': {
          'key': granule + '.isce.log',
          'bucket': private_bucket,
       }
    }

def all_products_payload(granule):
    return {
      'collection': 'Sentinel-1 All Interferometric Products (BETA)',
      'zip': {
          'key': granule + '.zip',
          'bucket': private_bucket,
       },
       'browse': {
          'key': granule + '.unw_geo.browse.png',
          'bucket': public_bucket,
       },
       'log': {
          'key': granule + '.isce.log',
          'bucket': private_bucket,
       }
    }

def get_products_from_bucket( reprocess_bucket, product_regex ):
    bucket = boto3.resource('s3').Bucket(reprocess_bucket)
    regex = re.compile(product_regex)
    products = []

    for obj in bucket.objects.all(): 
        search = regex.search( obj.Object().key ) 
        if search:
            print "Added " + search.group('product_name')
            products.append(search.group('product_name'))

    return products

def invoke_lambda(lambda_arn, payload):
    region_name = lambda_arn.split(':')[3]
    lambda_client = boto3.client('lambda', region_name=region_name)
    lambda_client.invoke(FunctionName=lambda_arn, InvocationType='Event', Payload=json.dumps(payload))


if __name__ == "__main__":

    if granules is None:
        granules = [] 
    if reprocess_bucket is not False:
        granules += get_products_from_bucket( reprocess_bucket, reprocess_product_regex )

    cnt = 0
    for granule in granules:
        print("Submitting {0} to CMR".format(granule))
        if process_cmr_for['unw_geo']:
            payload = unw_geo_payload(granule)
            invoke_lambda(lambda_arn, payload)
        if process_cmr_for['full_res']:
            payload = full_res_payload(granule)
            invoke_lambda(lambda_arn, payload)
        if process_cmr_for['all_prods']:
            payload = all_products_payload(granule)
            invoke_lambda(lambda_arn, payload)
        time.sleep(sleep_time_in_seconds)
 
        cnt += 1
        if pause_every_x_items and (cnt % pause_every_x_items == 0):
            raw_input("Press Enter to continue...")

    print ("Submitted {0} products to CMR".format(len(granules)))

