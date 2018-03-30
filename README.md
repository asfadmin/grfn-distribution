# About

The Getting Ready for NISAR (GRFN) project was designed to experiment with the functional architecture of Amazon Web Services cloud computing environment for the processing, distribution and archival of Synthetic Aperture Radar data in preparation for the [NASA-ISRO SAR Mission (NISAR)](https://nisar.jpl.nasa.gov/). The grfn-ingest pipeline is designed to manage large volumes of data at high rates (up to 50 Gbps), to simulate the data volumes anticipated for transfer and archival during the NISAR mission.

This repository contains the code developed and used by the [Alaska Satellite Facility (ASF)](https://www.asf.alaska.edu) to distribute data that was stored in the Amazon Glacier storage facility.  Glacier is a slower but cheaper option for long-term storage of data.  However, as it is asynchronous, user notifications are used to help improve the user experience.

# Architecture

![Email Process](/doc/EmailArchitecture.jpg)

# Components

* **door:** Door is the main GRFN data distribution point.
* **glacier-availability:** Requests data from Glacier if the data is not available for immediate download from S3.
* **glacier-notifications:** Sends email to users if activity has occurred that a user is interested in.  Sends an acknowledgement email when the user requests data that is stored in Glacier.  It also sends an email when the entirety of a user's requests is retrieved.  
* **glacier-requests:**  Retrieves the user's requested data from Amazon Glacier.
* **glacier-status:**  The status web page that provides a user an overview of the status of their recent requests for GRFN data that was stored in Glacier.


# Build and Deployment Instructions

1. Run steps in buildspec.yaml
2. Deploy cloudformation-final.yaml

# Top Level Inputs and Outputs

## Runtime Inputs

## Outputs

# Credits

## ASF

GRFN-distribution was written by the Alaska Satellite Facility.  The Alaska Satellite Facility downlinks, processes, archives, and distributes remote-sensing data to scientific users around the world. ASF's mission is to make remote-sensing data accessible.

### GRFN Team at ASF

The GRFN team at ASF that directly contributed to this project consists of:

  * Jessica Garron, Product Owner
  * Andrew Johnston, Scrum Master and developer
  * Ian Dixon, developer
  * David Matz, developer

## NASA

ASF gratefully acknowledges the sponsorship of the National Aeronautics and Space Administration for this work.
