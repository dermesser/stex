#!/usr/bin/env python3

import zmq

ctx = zmq.Context()
sock = ctx.socket(zmq.SUB)
sock.setsockopt(zmq.IPV6, 1)
sock.connect('tcp://borgac.net:8080')
sock.setsockopt_string(zmq.SUBSCRIBE, '')

history = {}
i = 0

while True:
    i += 1
    msg = sock.recv_json()
    msg.pop('_stockdata')
    for sym, val in sorted(msg.items()):
        if 'price' not in val:
            print('invalid item: ', val)
        price = val['price']
        print(' {}: {:.2f}'.format(sym, price / 100.))
        if sym in history:
            history[sym].append(price/100.)
            if len(history[sym]) > 500:
                history[sym] = history[sym][1:]
        else:
            history[sym] = [price/100.]
    print('')

