https://cmr.earthdata.nasa.gov/ingest/site/ingest_api_docs.html#create-update-collection

https://wiki.earthdata.nasa.gov/display/CMR/CMR+Data+Partner+User+Guide#CMRDataPartnerUserGuide-ToCreateaToken
https://wiki.earthdata.nasa.gov/display/CMR/CMR+Data+Partner+User+Guide#CMRDataPartnerUserGuide-ToDeletetheToken

These examples work, but curl strips newlines out of the input xml file, so things are hard to read when you request the data back out of CMR.

curl -i -XPUT -H "Content-type: application/echo10+xml" -H "Echo-Token: XXXX" https://cmr.uat.earthdata.nasa.gov/ingest/providers/ASF/collections/SENTINEL-1_INSAR_FULL_RES_WRAPPED_INTERFEROGRAM_AND_DEM -d @SENTINEL-1_INSAR_FULL_RES_WRAPPED_INTERFEROGRAM_AND_DEM.echo10

curl -i -XPUT -H "Content-type: application/echo10+xml" -H "Echo-Token: XXXX" https://cmr.uat.earthdata.nasa.gov/ingest/providers/ASF/collections/SENTINEL-1_INSAR_UNWRAPPED_INTERFEROGRAM_AND_COHERENCE_MAP -d @SENTINEL-1_INSAR_UNWRAPPED_INTERFEROGRAM_AND_COHERENCE_MAP.echo10

