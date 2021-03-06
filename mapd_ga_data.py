#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright 2012 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""The following application is based on the work from:
   http://www.ryanpraski.com/python-google-analytics-api-unsampled-data-multiple-profiles/

   This application demonstrates how to use the python client library to access
   Google Analytics data and load it to MapD's database (www.mapd.com).
"""

"""
This application demonstrates how to use the python client library to access
Google Analytics data. The sample traverses the Management API to obtain the
authorized user's first profile ID. Then the sample uses this ID to
contstruct a Core Reporting API query to return the top 25 organic search
terms.

Before you begin, you must sigup for a new project in the Google APIs console:
https://code.google.com/apis/console

Then register the project to use OAuth2.0 for installed applications.

Finally you will need to add the client id, client secret, and redirect URL
into the client_secrets.json file that is in the same directory as this sample.

Sample Usage:

  $ python hello_analytics_api_v3.py

Also you can also get help on all the command-line flags the program
understands by running:

  $ python hello_analytics_api_v3.py --help
"""

__author__ = 'veda.shankar@gmail.com (Veda Shankar)'


import argparse
import sys
import csv
import string
import os
import re
import gzip
import shutil
import pandas as pd
import numpy as np
from mapd_utils import *
import pymapd
from apiclient.errors import HttpError
from apiclient.discovery import build
from oauth2client.service_account import ServiceAccountCredentials
import httplib2
from oauth2client import client
from oauth2client import file
from oauth2client import tools

class SampledDataError(Exception):
    pass

# original set - key_dimensions=['ga:date','ga:hour','ga:minute','ga:networkLocation','ga:browserSize','ga:browserVersion']
# original set - all_dimensions=['ga:userAgeBracket','ga:userGender','ga:country','ga:countryIsoCode','ga:city','ga:continent','ga:subContinent','ga:userType','ga:sessionCount','ga:daysSinceLastSession','ga:sessionDurationBucket','ga:referralPath','ga:browser','ga:operatingSystem','ga:browserSize','ga:screenResolution','ga:screenColors','ga:flashVersion','ga:javaEnabled','ga:networkLocation','ga:mobileDeviceInfo','ga:mobileDeviceModel','ga:mobileDeviceBranding','ga:deviceCategory','ga:language','ga:adGroup','ga:source','ga:dataSource','ga:sourceMedium','ga:adSlot','ga:mobileInputSelector','ga:mobileDeviceMarketingName','ga:searchCategory','ga:searchDestinationPage','ga:interestAffinityCategory','ga:landingPagePath','ga:exitPagePath','ga:browserVersion','ga:eventLabel','ga:eventAction','ga:eventCategory','ga:hour','ga:yearMonth','ga:Month','ga:date','ga:keyword','ga:campaign','ga:adContent']


key_dimensions = ['ga:date', 'ga:hour', 'ga:minute',
                  'ga:longitude', 'ga:latitude', 'ga:landingPagePath']
#all_dimensions=['ga:networkLocation', 'ga:country', 'ga:city', 'ga:medium', 'ga:source', 'ga:sessionDurationBucket', 'ga:sessionCount', 'ga:deviceCategory', 'ga:campaign', 'ga:adContent','ga:keyword']
all_dimensions = ['ga:networkLocation', 'ga:country', 'ga:city', 'ga:medium', 'ga:source',
                  'ga:sessionDurationBucket', 'ga:sessionCount', 'ga:deviceCategory', 'ga:campaign', 'ga:adContent', 'ga:keyword']
n_dims = 7 - len(key_dimensions)


def get_service(key_file_location):
    """Get a service that communicates to a Google API.

    Args:
      api_name: The name of the api to connect to.
      api_version: The api version to connect to.
      scope: A list auth scopes to authorize for the application.
      key_file_location: The path to a valid service account JSON key file.

    Returns:
      A service that is connected to the specified API.
    """
    scope = ['https://www.googleapis.com/auth/analytics.readonly']
    api_name = 'analytics'
    api_version = 'v3'
    credentials = ServiceAccountCredentials.from_json_keyfile_name(
        key_file_location, scopes=scope)

    # Build the service object.
    service = build(api_name, api_version, credentials=credentials)

    return service

# Traverse the GA management hierarchy and construct the mapping of website
# profile views and IDs.
def traverse_hierarchy(service):
    profile_ids = {}
    accounts = service.management().accounts().list().execute()
    for account in accounts.get('items', []):
        accountId = account.get('id')
        # print('traverse_hierarchy accountId', accountId)
        webproperties = service.management().webproperties().list(
            accountId=accountId).execute()
        for webproperty in webproperties.get('items', []):
            firstWebpropertyId = webproperty.get('id')
            profiles = service.management().profiles().list(
                accountId=accountId,
                webPropertyId=firstWebpropertyId).execute()
            for profile in profiles.get('items', []):
                profileID = "%s" % (profile.get('id'))
                profileName = "%s_%s" % (
                    webproperty.get('name'), profile.get('name'))
                profile_ids[profileName] = profileID
    return profile_ids

def merge_tables(final_csv_file, csv_list):
    for i in range(0, len(csv_list), 1):
        print(csv_list[i])
        if i == (len(csv_list) - 1):
            print("exiting for loop ...")
            break

        if i == 0:
            df1 = pd.read_csv(csv_list[0])
            df2 = pd.read_csv(csv_list[1])
        else:
            df1 = pd.read_csv('./data/combo.csv')
            os.system("rm -f ./data/combo.csv")
            df2 = pd.read_csv(csv_list[i+1])

        df1 = df1.dropna(subset=['ga_longitude', 'ga_latitude'])
        df2 = df2.dropna(subset=['ga_longitude', 'ga_latitude'])
        combo = pd.merge(df1, df2, how='left')
        df = pd.DataFrame(combo)
        df = df[df.ga_pageviews != 0]
        df = df[df.ga_longitude != 0]
        df = df[df.ga_latitude != 0]
        #df['ga_pageviews'] = df['ga_pageviews'].fillna(0)
        df = df.fillna("None")
        df.to_csv('./data/combo.csv', index=False)
        del df1
        del df2
        del combo

    df = pd.read_csv('./data/combo.csv')
    #df = pd.DataFrame(df1)
    df.ga_date = df.ga_date.apply(str)
    df.ga_hour = df.ga_hour.apply(str)
    df.ga_minute = df.ga_minute.apply(str)
    df['ga_date'] = df['ga_date'].str.replace(
        r'(\d\d\d\d)(\d\d)(\d\d)', r'\2/\3/\1')
    df['ga_date'] = df['ga_date'].astype(
        str) + " " + df['ga_hour'].astype(str) + ":" + df['ga_minute'].astype(str) + ":00"
    df = df.drop('ga_hour', axis=1)
    df = df.drop('ga_minute', axis=1)
    df.to_csv(final_csv_file, index=False)
    print(df.head(3))
    print(df.isnull().sum())


def ga_query(service, profile_id, pag_index, start_date, end_date, dims):
    print('ga_query', service, profile_id, pag_index, start_date, end_date, dims)
    return service.data().ga().get(
        ids='ga:' + profile_id,
        start_date=start_date,
        end_date=end_date,
        metrics='ga:pageviews',
        dimensions=dims,
        sort='-ga:pageviews',
        samplingLevel='HIGHER_PRECISION',
        start_index=str(pag_index+1),
        max_results=str(pag_index+10000)).execute()


def build_csv_list(service, profile_id, profile, date_ranges, csv_list):
    table_names = {}
    table_filenames = {}
    writers = {}
    files = {}

    i = 0
    for dim_i in range(0, len(all_dimensions), n_dims):
        dimss = key_dimensions + all_dimensions[dim_i:dim_i+n_dims]
        dims = ",".join(dimss)
        #path = os.path.abspath('.') + '/data/'
        path = './data/'
        if not os.path.exists(path):
            os.mkdir(path, 0o755)
        file_suffix = '%s' % (all_dimensions[dim_i:dim_i+n_dims])
        file_suffix = '%s' % (file_suffix.strip('\[\'\]'))
        file_suffix = '%s' % (file_suffix[3:])
        filename = '%s_%s.csv' % (profile.lower(), file_suffix)
        filename = filename.strip()
        table_names[dims] = '%s_%s' % (profile.lower(), file_suffix)
        #table_filenames[dims] = path + '%s_%s.csv' % (profile.lower(), file_suffix)
        table_filenames[dims] = path + filename
        csv_list = csv_list + [table_filenames[dims]]
        i += 1
        files[dims] = open(path + filename, 'wt')
        writers[dims] = csv.writer(files[dims], lineterminator='\n')

    # Try to make a request to the API. Print the results or handle errors.
    if not profile_id:
        print('Could not find a valid profile for this user.')
    else:
        for start_date, end_date in date_ranges:
            for dim_i in range(0, len(all_dimensions), n_dims):
                dimss = key_dimensions + all_dimensions[dim_i:dim_i+n_dims]
                dims = ",".join(dimss)
                print(dims)
                limit = ga_query(service, profile_id, 0, start_date, end_date, dims).get('totalResults')
                print("Found " + str(limit) + " records")  # VS
                for pag_index in range(0, limit, 10000):
                    results = ga_query(service, profile_id, pag_index, start_date, end_date, dims)
                    if results.get('containsSampledData'):
                        raise SampledDataError  # VS
                    save_results(results, pag_index, start_date, end_date, date_ranges, writers[dims])
                files[dims].close()
    
    return csv_list


# Write results reported from the Core Reporting API to the CSV file
def save_results(results, pag_index, start_date, end_date, date_ranges, writer):
    # New write header
    if pag_index == 0:
        if (start_date, end_date) == date_ranges[0]:
            print('Profile Name: %s' % results.get('profileInfo').get('profileName'))
            columnHeaders = results.get('columnHeaders')
            #cleanHeaders = [str(h['name']) for h in columnHeaders]
            # writer.writerow(cleanHeaders)
            cleanHeaders_str = '%s' % [str(h['name']) for h in columnHeaders]
            cleanHeaders_str = cleanHeaders_str.replace(':', '_')
            cleanHeaders_str = cleanHeaders_str.replace('\'', '')
            cleanHeaders_str = cleanHeaders_str.replace('[', '')
            cleanHeaders_str = cleanHeaders_str.replace(']', '')
            cleanHeaders_str = cleanHeaders_str.replace(',', '')
            cleanHeaders = cleanHeaders_str.split()
            writer.writerow(cleanHeaders)
        print('Now pulling data from %s to %s.' % (start_date, end_date))

    # Print data table.
    if results.get('rows', []):
        for row in results.get('rows'):
            for i in range(len(row)):
                old, new = row[i], str()
                for s in old:
                    new += s if s in string.printable else ''
                row[i] = new
            writer.writerow(row)

    else:
        print('No Rows Found')

    limit = results.get('totalResults')
    print(pag_index, 'of about', int(round(limit, -4)), 'rows.')


def main(argv):

    if len(argv) == 0:
        key_file_location = './client_secrets.json'
        selected_profile = None
        omnisci_url = None
        date_ranges = None
    else:
        key_file_location = argv[0]
        selected_profile = argv[1]
        omnisci_url = argv[2]
        date_ranges = [(argv[3], argv[4])]

        with pymapd.connect(omnisci_url) as con:
            print('existing tables: ', [x for x in con.get_tables() if x.startswith('omnisci')])

    service = get_service(key_file_location)

    # Construct dictionary of GA website name and ids.
    profile_ids = traverse_hierarchy(service)

    # Select the GA profile view to extract data
    selection_list = [0]
    i = 1
    print('%5s %20s %5s %20s' % ("Item#", "View ID", " ", "View Name"))
    for profile in sorted(profile_ids):
        selection_list = selection_list + [profile_ids[profile]]
        print('%4s %20s %5s %20s' % (i, profile_ids[profile], " ", profile))
        i += 1

    if not selected_profile:
        print('Enter the item# of the view you would like to ingest into MapD: ')
        item = int(input())
        if item == '' or item <= 0 or item >= len(selection_list):
            print('Invalid selection - %s' % item)
            sys.exit(0)
        print('Item # %s selected' % item)
    else:
        item = selection_list.index(profile_ids[selected_profile])

    if not date_ranges:
        print('\nEnter the begin date and end date in the following format: YYYY-MM-DD YYYY-MM-DD')
        print('Or hit enter to proceed with the default which is last 30 days data')
        print('Date Range: ')
        begin_end_date = input()
        if begin_end_date == '':
            print('Extract data from today to 30 days ago')

            # date_ranges = [('2017-08-27', '2018-02-22')]
            # date_ranges = [('30daysAgo', 'today')]
            date_ranges = [('2daysAgo', 'today')]

        else:
            (begin_date, end_date) = [t(s) for t, s in zip((str, str), begin_end_date.split())]
            print('Extract data from %s to %s' % (begin_date, end_date))
            date_ranges = [(begin_date, end_date)]

    if not omnisci_url:
        print("\nEnter the OmniSci server URL if you want to upload data,\n otherwise simply hit enter to use the manual procedure to upload the data")
        print("  URL example: - omnisci://admin:HyperInteractive@omniscidb.example.com:6274/omnisci?protocol=binary")
        print('OmniSci URL: ')
        omnisci_url = input()
        if omnisci_url == '':
            print('Use MapD Immerse import user interface to load the output CSV file')
            omnisci_url = None
        print("")

    csv_list = []
    for profile in sorted(profile_ids):
        if (selection_list[item] == profile_ids[profile]):
            print('\nGoing to download data for %s (%s) ...' %
                    (profile, profile_ids[profile]))
            table_name = profile.lower()
            table_name = '%s' % (table_name.replace(' ', ''))
            final_csv_file = './data/%s.csv' % (table_name)
            final_csv_gzfile = './data/%s.csv.gz' % (table_name)
            csv_list = build_csv_list(service, profile_ids[profile], profile, date_ranges, csv_list)
            merge_tables(final_csv_file, csv_list)
    print("Download of analytics data done.")

    # TODO Lines below need to be inside the for loop above?

    # Gzip the CSV file
    if os.path.isfile(final_csv_gzfile):
        os.remove(final_csv_gzfile)
    with open(final_csv_file, 'rb') as f_in, gzip.open(final_csv_gzfile, 'wb') as f_out:
        shutil.copyfileobj(f_in, f_out)

    # Connect to MapD
    if not omnisci_url or omnisci_url == '':
        print("=======================================================================")
        print('Goto OmniSci Immerse UI and import the CSV file %s' % (final_csv_gzfile))
        print("=======================================================================")

    else:
        with pymapd.connect(omnisci_url) as con:
            load_table_mapd(con, table_name, final_csv_gzfile)

        print("=======================================================================")
        print('Goto OmniSci Immerse UI')
        print("=======================================================================")

if __name__ == "__main__":
    main(sys.argv[1:])
