#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# If you want to use this, set BTQ_USER and BTQ_PASS to your BeatTheQ account creds.

import argparse
import json
import os
import requests
import sys
import time
import uuid


order_items = {
    "espresso": {
        "name": "Espresso",
        "id": "11867",
        # 283373 => House Blend (coffee type)
        # 120959 => Regular strength
        # 120960 => Normal hotness
        # 120953 => no sugar
        # 120962 => no artificial sweetener
        "options": [120953, 120962, 283373, 120959, 120960],
    },
    "fw": {
        "name": "Flat White",
        "id": "11864",
        # 283364 => House Blend (coffee type)
        # 120917 => Regular strength
        # 120919 => Normal hotness
        # 120909 => no sugar
        # 120925 => no artificial sweetener
        # 121330 => small size
        # 120908 => full cream milk
        "options": [283364, 120917, 120919, 120909, 120925, 121330, 120908],
    },
}


def valid_response_or_raise(r):
    print r.text
    response = r.json()
    if not r.ok:
        raise Exception('Uh-oh. Bad http status: {}'.format(r.status_code))
    if response['status']['code'] != 0:
        raise Exception('Bad status code from API: {}'.format(response['status']['code']))
    return response


def parse_args():
    coffee_types = ', '.join(order_items.keys())
    p = argparse.ArgumentParser()
    p.add_argument('coffee_type', help=coffee_types)
    p.add_argument('--note', help='A note to the barista', default=None)
    args = p.parse_args()
    if args.coffee_type not in order_items:
        print 'Choose from coffee types:', coffee_types
        sys.exit(1)
    return args


args = parse_args()
chosen_coffee = order_items[args.coffee_type]

api_base = 'https://app.heyyou.com.au/proxy/btq/api'

s = requests.Session()
s.headers['Content-Type'] = 'application/json'
s.headers['X-BTQ-Client-Id'] = 'a796320ec3f35d3c8e2226f8148a9cc093dc715d'

data = {
    'grant_type': 'password',
    'username': os.environ['BTQ_USER'],
    'password': os.environ['BTQ_PASS'],
    'client_id': s.headers['X-BTQ-CLient-Id'],
    'client_secret': '314dd7980df485897230e2880436c73488eb3c6e',
}

r = s.post(api_base + '/auth', data=json.dumps(data))
response = valid_response_or_raise(r)
token = response['access_token']
print token
raise Exception("asdasd")
s.headers['Authorization'] = 'Bearer {}'.format(token)

# Each order includes a nonce, as a string of 40 hex digits.
# We could probably make one up but the app requests one from the API.
r = s.get(api_base + '/nonce')
response = valid_response_or_raise(r)
nonce = response['nonces'][0]

order = {
    "items": [{
        "time": int(time.time()),
        "id": chosen_coffee['id'],
        "options": chosen_coffee['options'],
    }],
    # "deviceId": str(uuid.uuid4()),  # I actually use the real uuid the app uses
    "venueId": "208",  # Double Barrel
    "serviceType": "takeaway",
    "nonce": nonce,
}

r = s.post(api_base + '/orders/checkout', data=json.dumps(order))
try:
    response = valid_response_or_raise(r)
except Exception as e:
    print 'Error in checkout API'
    print r.json()
    sys.exit()

# Submit order - note: nonce does not change when the app does this!
# The order fields are the same, but we can also include a note
if args.note:
    order['orderNote'] = args.note

print 'Submitting order...'
r = s.post(api_base + '/orders/submit', data=json.dumps(order))
try:
    response = valid_response_or_raise(r)
except Exception as e:
    print 'Error in submit API'
    print r.json()
    sys.exit()

# print response
order_id = response['orderId']
print 'Submitted order, id: {}'.format(response['orderId'])

time.sleep(2)  # Avoid race between order submission and order status

status = None
while True:
    r = s.get(api_base + '/orders/submit/status/{}'.format(order_id))
    try:
        response = valid_response_or_raise(r)
    except Exception as e:
        print 'Error in status API'
        print r.json()
        time.sleep(2)
        continue
    new_status = response['status']['flags'][0]
    if new_status != status:
        # print response
        print 'Order status now {}'.format(new_status)
        status = new_status
    if status == 'ACCEPTED' or status.startswith('REJECTED'):
        sys.exit()
    time.sleep(1)
