#!/usr/bin/env python3
"""The server generates stock data and distributes it to clients."""

import arguments
import json
import random
import sys
import time
 
from PyQt5.QtWidgets import QApplication, QMainWindow, QMenu, QVBoxLayout, QSizePolicy, QMessageBox, QWidget, QPushButton
from PyQt5.QtGui import QIcon

import zmq

_random = random.Random()
_random.seed(1)
# Maximum initial stock value in cents.
_maxinitvalue = 10000
_maxhistory = 100

class Stock:
    symbol = ''
    # Stock value in cents
    _current_value = 0
    _last_values = []
    
    # Random walk coefficients
    _stddev = 0

    def name():
        """Generates a stock-ticker-like name."""
        return ''.join([chr(int(_random.random()*26)+0x41) for i in range(0, 4)])

    def __init__(self, name):
        self.symbol = name
        self._stddev = _random.random() / 10
        self._current_value = _random.random() * _maxinitvalue

    def next_price(self):
        """Calculates a (random) next price based on the current price and history."""
        dev = 0.02*self._current_value or 1
        new_value = int(_random.normalvariate(self._current_value * 1.001, dev))
        new_value = abs(new_value)
        self._last_values.append(self._current_value)
        self._current_value = new_value
        if len(self._last_values) > _maxhistory:
            self._last_values = self._last_values[1:]
        return new_value

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
            next[s.symbol] = s.next_price()
        return StockData(next)


class Server(arguments.BaseArguments):
    _doc = """
    Usage:
        stex-server [options]

    Options:
        -a --address=<address>  Listen on address.
        -p --port=<port>        Listen on port.
        --stocks=<stocks>       Number of stocks to generate.
        --stocklist=<stocks>    List of ticker symbols to generate stocks for.
        --interval=<interval>   Interval in ms to publish stock data (default 500)
        --help                  Print help.
    """

    _stocks = Stocks(None)

    def __init__(self, zctx, callback=None):
        """callback is called with a StockData object every time new data are available."""
        super(arguments.BaseArguments, self).__init__(doc=self._doc)
        if self.help or None:
            print(self._doc)
            sys.exit(0)

        socket = zctx.socket(zmq.PUB)
        socket.setsockopt(zmq.IPV6, 1)
        socket.bind('tcp://{}:{}'.format(self.address or '[::]', self.port or '9988'))
        self._socket = socket
        self.init_stocks()

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
        while True:
            time.sleep(interval / 1000.)
            nextdata = self._stocks.generate()
            print("DEBUG: {}".format(nextdata))
            self._socket.send_string(nextdata.serialize())

def main():
    ctx = zmq.Context()
    s = Server(ctx)
    s.run()

if __name__ == "__main__":
    main()
