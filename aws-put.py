#!/usr/bin/env python3

# aws-put.py: Simple script to push a file to AWS.

import sys
import os.path
import optparse
import configparser

import boto3

popt = optparse.OptionParser(usage='aws-put.py filename bucket')

popt.add_option('--stdin',
                action='store_true', dest='stdin',
                help='upload data streamed from stdin (the filename is still needed for the S3 side)')

popt.add_option('--config',
                action='store', dest='config', metavar='PATH',
                help='config file (default: $HOME/.aws/credentials)')

(opts, args) = popt.parse_args()

if len(args) < 2:
    print('usage: aws-put.py filename bucket')
    sys.exit(0)

filename = args[0]
bucket = args[1]

cliargs = {}

if opts.config:
    config = configparser.ConfigParser()
    config.read(opts.config)
    if config.has_section('AWSStorage'):
        map = config['AWSStorage']
    elif config.has_section('default'):
        map = config['default']
    else:
        raise Exception('config file does not have credentials')
    cliargs['aws_access_key_id'] = map['aws_access_key_id']
    cliargs['aws_secret_access_key'] = map['aws_secret_access_key']

s3client = boto3.client('s3', **cliargs)

if opts.stdin:
    destfile = os.path.basename(filename)
    print('Uploading stdin as %s...' % (destfile,))
    infl = sys.stdin.buffer
else:
    destfile = os.path.basename(filename)
    print('Uploading file as %s...' % (destfile,))
    infl = open(filename, 'rb')

res = s3client.upload_fileobj(infl, bucket, destfile)

if res is not None:
    print(res)

