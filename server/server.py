#!/usr/bin/env python3
"""The server generates stock data and distributes it to clients."""

import arguments
import json
import random
import sys
import time

import zmq

_random = random.SystemRandom()
# Maximum initial stock value in cents.
_maxinitvalue = 10000
_splitvalue = 20000
_maxhistory = 100

class Log:
    def __init__(self, file=sys.stderr):
        self.out = file

    def log(self, *kwargs):
        print(*kwargs, file=self.out, flush=True)

LOG = None

class Groups:
    """Groups manages depot subscriptions for groups."""
    groups = {}

    def update(self, group, user, info):
        """updates user info in a group. info is a dict containing the fields 'cash'."""
        if not (group and user and info):
            return
        LOG.log('updated ', group, user, info)
        self.groups[group] = {} if group not in self.groups else self.groups[group]
        self.groups[group][user] = info

    def get(self, group):
        """gets a dict with 'user' -> {'depot': _} mapping."""
        return self.groups.get(group, None)

_groups = Groups()

class Stock:
        symbol = ''
        # Stock value in cents
        _current_value = 0
        _last_values = []
        
        # Random walk coefficients
        _stddev = 0

        def name():
            """Generates a stock-ticker-like name."""
            return ''.join([chr(int(_random.random() * 26) + 0x41) for i in range(0, 4)])

        def __init__(self, name):
            self.symbol = name
            self._stddev = _random.random() / 10
            self._current_value = _random.random() * _maxinitvalue

        def next_price(self):
            """Calculates a (random) next price based on the current price and history. Returns a dict suitable for inclusion in a _stockdata object."""
            dev = 0.02 * self._current_value or 1
            new_value = int(_random.normalvariate(self._current_value * 1.0005, dev))
            new_value = abs(new_value)
            split = False

            if new_value > _splitvalue:
                new_value = new_value / 2
                split = True

            self._last_values.append(self._current_value)
            self._current_value = new_value
            if len(self._last_values) > _maxhistory:
                self._last_values = self._last_values[1:]

            return {'price': new_value, 'split': split, '_stockupdate': True}

        def current_value(self):
            return self._current_value


class StockData:
        _data = {}

        def __init__(self, data):
            self._data = data
            self._data['_stockdata'] = True

        def data(self):
            return self._data

        def serialize(self):
            return json.dumps(self._data)

        def write(self, dst):
            return json.dump(self._data, dst)

        def deserialize_from(jsondata):
            """Parse StockData from JSON data. Raises an exception if JSON is invalid or the object is malformed."""
            data = json.loads(jsondata)
            if data is not dict or '_stockdata' not in data:
                raise ValueError('JSON object is not a valid StockData serialization')
            _data = data


class Stocks:
        _stocks = []

        def __init__(self, stocks=None):
            """Takes [Stock]."""
            self._stocks = stocks

        def generate(self):
            next = {}
            for s in self._stocks:
                nextprice = s.next_price()
                next[s.symbol] = nextprice
            return StockData(next)


class Server(arguments.BaseArguments):
        _doc = """
    Usage:
        stex-server [options]

    Options:
        -a --address=<address>  Listen on address.
        -p --port=<port>        Listen on port (the port directly above will also be used)
        --stocks=<stocks>       Number of stocks to generate.
        --stocklist=<stocks>    List of ticker symbols to generate stocks for.
        --interval=<interval>   Interval in ms to publish stock data (default 500)
        --log=<file>            Log file.
        --help                  Print help.
    """

        _stocks = Stocks(None)

        def __init__(self, zctx, callback=None):
            """callback is called with a StockData object every time new data are available."""
            super(arguments.BaseArguments, self).__init__(doc=self._doc)
            self.setup_log()
            if self.help or None:
                print(self._doc)
                sys.exit(0)

            port = self.port or '9988'

            interactivesocket = zctx.socket(zmq.ROUTER)
            interactivesocket.setsockopt(zmq.IPV6, 1)
            interactivesocket.bind('tcp://{}:{}'.format(self.address or '[::]', int(port) + 1 if self.port else '9989'))
            interactivesocket.setsockopt(zmq.RCVTIMEO, 0)
            self.interactivesocket = interactivesocket

            pubsocket = zctx.socket(zmq.PUB)
            pubsocket.setsockopt(zmq.IPV6, 1)
            pubsocket.bind('tcp://{}:{}'.format(self.address or '[::]', port))
            self.pubsocket = pubsocket
            self.init_stocks()

        def setup_log(self):
            if self.log is not None:
                # Attempt to create file if it doesn't exist.
                try:
                    with open(self.log, mode='x') as f:
                        pass
                except:
                    pass
                log = open(self.log, mode='a')
                global LOG
                LOG = Log(log)
            else:
                LOG = Log()

        def init_stocks(self):
            stocklist = []
            if self.stocklist:
                stocklist = self.stocklist.split(',')
            elif self.stocks and int(self.stocks) > 0:
                stocklist = [Stock.name() for _ in range(0, self.stocks)]
            else:
                stocklist = [Stock.name() for _ in range(0, 10)]

            stocklist = [Stock(name=s) for s in stocklist]
            self._stocks = Stocks(stocklist)

        def run(self):
            interval = int(self.interval or 500)
            nextinterval = interval

            p = zmq.Poller()
            p.register(self.interactivesocket, zmq.POLLIN)
            while True:
                before = time.clock_gettime_ns(time.CLOCK_MONOTONIC)
                events = p.poll(nextinterval)

                if len(events) > 0:
                    self.handle_calls(events)
                    diff = (time.clock_gettime_ns(time.CLOCK_MONOTONIC) - before) / 1e6
                    remaining = nextinterval - diff
                    nextinterval = remaining if remaining > 0 else 0
                else:  # Timeout
                    nextdata = self._stocks.generate()
                    self.pubsocket.send_string(nextdata.serialize())
                    nextinterval = interval

        groups = Groups()

        # Handle callbacks from clients.
        def handle_calls(self, events):
            for (sock, ev) in events:
                if not (ev | zmq.POLLIN):
                    continue
                try:
                    msgs = sock.recv_multipart()
                    assert len(msgs) > 2
                    msg = json.loads(msgs[2].decode())
                    LOG.log('Client {}: {} {}'.format(msgs[0].hex(), msgs[1].decode(), msg))

                    custom_msg = msg.get('msg', {})
                    resp = self.handle_message(msg['user'], msg['group'], msg['password'], custom_msg)
                    sock.send_multipart([msgs[0], msgs[1], bytes(json.dumps(resp), 'utf-8')])
                except Exception as e:
                    raise e

        def handle_message(self, user, group, password, message):
            """Returns the complete response to send to a client."""
            if '_stocklogin' in message:
                return {}
            if '_stockdepot' in message:
                groupinfo = {'cash': message.get('cash', -1), 'value': message.get('value', -1)}
                _groups.update(group, user, groupinfo)
                return {'_stockresp': True, 'ok': True, 'groupinfo': _groups.get(group)}
def main():
        ctx = zmq.Context()
        s = Server(ctx)
        s.run()


if __name__ == "__main__":
        main()
