#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# If you want to use this, set BTQ_USER and BTQ_PASS to your BeatTheQ account creds.

import argparse
from collections import namedtuple
import json
import os
import re
import requests
import sys
import time
import uuid


class BTQException(Exception):
    pass


api_base = 'https://api-ms.beattheq.com/v2.0'

venues = {
    't60': 1602,
}


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('venue', help='Venue name')
    p.add_argument('--coffee', help='Type of coffee (eg. espresso, cap)')
    p.add_argument('--note', help='A note to the barista', default=None)
    p.add_argument('--search', default=False, action='store_true', help='Search the menu, do not order')
    args = p.parse_args()
    if args.venue not in venues:
        v = ', '.join(venues.keys())
        print('Choose from venues: {}'.format(v))
        sys.exit(1)
    return args


Creds = namedtuple('Creds', ['id', 'secret'])


# There's a client id and secret embedded in the btq javascript that must
# be included in the auth request payload, and X-BTQ-Client-Id header.
def get_client_creds():
    r = requests.get('https://app.heyyou.com.au/js/btq.build.js')
    m = re.search('CLIENT_ID:"([\w\d]+)\"', r.text)
    id_ = m.groups()[0]
    m = re.search('CLIENT_SECRET:"([\w\d]+)\"', r.text)
    secret = m.groups()[0]
    return Creds(id=id_, secret=secret)


def get_auth_token(s, creds):
    data = {
        'grant_type': 'password',
        'username': os.environ['BTQ_USER'],
        'password': os.environ['BTQ_PASS'],
        'client_id': creds.id,
        'client_secret': creds.secret,
    }
    r = s.post(api_base + '/auth', json=data)
    r.raise_for_status()
    token = r.json()['access_token']
    return token


def build_session(creds):
    s = requests.Session()
    s.headers['Content-Type'] = 'application/json'
    s.headers['X-BTQ-Client-Id'] = creds.id
    return s


def get_coffee_menu(s, venue):
    r = s.get(api_base + '/venues/{venue}/menus'.format(venue=venue))
    r.raise_for_status()
    d = r.json()
    for cat in d['categories']:
        if 'coffee' in cat['name'].lower():
            return cat['items']
    raise BTQException('No coffee menu')


if __name__ == '__main__':
    args = parse_args()
    creds = get_client_creds()
    s = build_session(creds)

    menu = get_coffee_menu(s, venues[args.venue])
    if args.search:
        items = ', '.join([m['name'] for m in menu])
        print('Available menu items: {}'.format(items))
        sys.exit(1)

    coffee = None
    for item in menu:
        if args.coffee.lower() in item['name'].lower():
            coffee = item
    if coffee is None:
        print('Unknown coffee: {}'.format(args.coffee))
        sys.exit(1)

    # token = get_auth_token(s, creds)
    # s.headers['Authorization'] = 'Bearer {}'.format(token)
    # print(token)

    print(item)
    raise Exception("asdasd")


    # Each order includes a nonce, as a string of 40 hex digits.
    # We could probably make one up but the app requests one from the API.
    r = s.get(api_base + '/nonce')
    r.raise_for_status()
    response = r.json()
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
        r.raise_for_status()
        response = r.json()
    except Exception as e:
        print('Error in checkout API')
        print(r.json())
        sys.exit()

    # Submit order - note: nonce does not change when the app does this!
    # The order fields are the same, but we can also include a note
    if args.note:
        order['orderNote'] = args.note

    print('Submitting order...')
    r = s.post(api_base + '/orders/submit', data=json.dumps(order))
    try:
        r.raise_for_status()
        response = r.json()
    except Exception as e:
        print('Error in submit API')
        print(r.json())
        sys.exit()

    # print response
    order_id = response['orderId']
    print('Submitted order, id: {}'.format(response['orderId']))

    time.sleep(2)  # Avoid race between order submission and order status

    status = None
    while True:
        r = s.get(api_base + '/orders/submit/status/{}'.format(order_id))
        try:
            r.raise_for_status()
            response = r.json()
        except Exception as e:
            print('Error in status API')
            print(r.json())
            time.sleep(2)
            continue
        new_status = response['status']['flags'][0]
        if new_status != status:
            # print response
            print('Order status now {}'.format(new_status))
            status = new_status
        if status == 'ACCEPTED' or status.startswith('REJECTED'):
            sys.exit()
        time.sleep(1)
