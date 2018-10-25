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


class BTQException(Exception):
    pass


Creds = namedtuple('Creds', ['id', 'secret'])

ItemOption = namedtuple('ItemOption', ['id', 'name', 'isDefault'])

api_base = 'https://api-ms.beattheq.com/v2.0'

venues = {
    'regiment': 4114,
    't60': 1602,
}


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('venue', help='Venue name')
    p.add_argument('--coffee', help='Type of coffee (eg. espresso, cap)')
    p.add_argument('--double', default=False, action='store_true', help='Double shot (Extra Strength option)')
    p.add_argument('--note', help='A note to the barista', default=None)
    p.add_argument('--order', default=False, action='store_true', help='Place an order')
    p.add_argument('--search', default=False, action='store_true', help='Search the menu, do not order')
    args = p.parse_args()

    if args.coffee is None:
        print('Must specify coffee')
        sys.exit(1)
    if args.venue not in venues:
        v = ', '.join(venues.keys())
        print('Choose from venues: {}'.format(v))
        sys.exit(1)
    return args


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


def get_nonce(s):
    # Each order includes a nonce, as a string of 40 hex digits.
    # We could probably make one up but the app requests one from the API.
    r = s.get(api_base + '/nonce')
    r.raise_for_status()
    response = r.json()
    nonce = response['nonces'][0]
    return nonce


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


def filter_coffee(coffee):
    def f(item):
        return coffee.lower() in item['name'].lower()
    return f


def get_item_options(coffee, overrides=None):
    if overrides is None:
        overrides = {}
    opts = {}
    og = coffee['optionGroups']
    for g in og.values():
        for option in g:
            option_name = option['name'].lower()
            search = None
            if option_name in overrides:
                search = overrides[option_name]
            o = get_option(option, search)
            if o is not None:
                opts[option['name']] = o
    return opts


def get_option(option, search=None):
    default = None
    match = None
    if option['type'].lower() == 'radio':
        for o in option['options']:
            if o['isDefault']:
                default = o
            if search is not None and search.lower() in o['name'].lower():
                match = o
        if match is not None:
            return ItemOption(id=match['id'], name=match['name'], isDefault=match['isDefault'])
        if default is not None:
            return ItemOption(id=default['id'], name=default['name'], isDefault=default['isDefault'])
        raise BTQException('No item match')
    return None


def option_ids(options):
    return [o.id for o in options.values()]


if __name__ == '__main__':
    args = parse_args()
    creds = get_client_creds()
    s = build_session(creds)

    venue_id = venues[args.venue]
    menu = get_coffee_menu(s, venue_id)
    if args.search:
        items = ', '.join([m['name'] for m in menu])
        print('Available menu items: {}'.format(items))
        sys.exit(1)

    coffees = list(filter(filter_coffee(args.coffee), menu))
    if len(coffees) == 0:
        print('Unknown coffee: {}'.format(args.coffee))
        sys.exit(1)
    if len(coffees) > 1:
        matches = ', '.join([m['name'] for m in coffees])
        print('Multiple coffees match "{}": {}'.format(args.coffee, matches))
        sys.exit(1)
    coffee = coffees[0]

    token = get_auth_token(s, creds)
    s.headers['Authorization'] = 'Bearer {}'.format(token)
    nonce = get_nonce(s)

    order_overrides = {}
    if args.double:
        order_overrides['strength'] = 'extra shot'

    order = {
        "items": [{
            "time": int(time.time()),
            "id": coffee['id'],
            "options": option_ids(get_item_options(coffee, overrides=order_overrides)),
        }],
        "venueId": venue_id,
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

    if not args.order:
        print('Skipping order submission (use --order flag to submit). Order would be:')
        print(json.dumps(order, indent=2))
        sys.exit(0)

    print('Submitting order...')
    r = s.post(api_base + '/orders/submit', json=order)
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
        new_status = response['status']['flags'][0].lower()
        if new_status != status:
            # print response
            print('Order status now "{}"'.format(new_status))
            status = new_status
        if status == 'accepted' or status.startswith('rejected'):
            sys.exit()
        time.sleep(1)
