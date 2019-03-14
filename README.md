# stex

stex (**st**ock **ex**change) is another stock market simulator game like there have been many of before. This one
featGures client/server mode in which several clients can play on identical, synchronous stock exchange data (randomly
generated, just to be clear). More features are planned, but as of now, clients will already see the wealth of
other players in the same group in their game window.

# Dependencies

These can be installed via `pip3` or your system's package manager:

* `PyQt5` (>= 5.11)
* `PyQtChart`
* `pyzmq`
* `arguments`

# Usage

Run `server/server.py` on one computer. Use `--help` to see options. Once started, it will produce a feed of arbitrarily
many stocks, distributed as JSON objects in ZeroMQ messages. The default port is `9988`, and will be used if you do not
specify a different one.

On any client, run `client/client.py`. You can again use `--help` for an overview of the available options. The client
will store the information you enter in the client window so that you don't have to enter them every time. Note that
the `Password` is not used anywhere so far -- it is meaningless. `Group` determines whose wealth numbers you see, so if
you play with others you should choose the same group name here.
