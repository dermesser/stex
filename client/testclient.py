#!/usr/bin/env python3

import zmq

from matplotlib import figure
from matplotlib.backends import backend_cairo

ctx = zmq.Context()
sock = ctx.socket(zmq.SUB)
sock.setsockopt(zmq.IPV6, 1)
sock.connect('tcp://[::1]:9988')
sock.setsockopt_string(zmq.SUBSCRIBE, '')

history = {}
i = 0


def draw_symbols():
    for sym, hist in history.items():
        fig = figure.Figure()
        ax = fig.add_subplot(111)
        ax.grid(True)
        ax.set_xlim(0, len(hist))
        ax.set_ybound(0, 100)
        ax.plot([i for i in range(0, len(hist))], hist)
        backend_cairo.FigureCanvas(fig).print_png('{}.png'.format(sym))

while True:
    i += 1
    msg = sock.recv_json()
    msg.pop('_stockdata')
    for sym, val in sorted(msg.items()):
        print(' {}: {:.2f}'.format(sym, val / 100.))
        if sym in history:
            history[sym].append(val/100.)
            if len(history[sym]) > 500:
                history[sym] = history[sym][1:]
        else:
            history[sym] = [val/100.]
    print('')

    if i > 25:
        draw_symbols()
        i = 0

