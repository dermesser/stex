#!/usr/bin/env python3

import arguments
import json
import os
import os.path as path
import sys
import urllib.parse as url
import zmq

import PyQt5.QtWidgets as wid
import PyQt5.QtCore as core
import PyQt5.QtChart as chart


class Creds:
    user = ''
    password = ''
    addr = ''
    group = ''


class ClientConfigDialog(wid.QDialog):
    addr = None
    user = None
    group = None
    password = None
    defaults = False

    def __init__(self, parent, defaults=False):
        super().__init__(parent)
        self.defaults = defaults

    def show_dialog(self):
        vbox = wid.QVBoxLayout(self)
        
        self.addr = wid.QLineEdit()
        self.addr.readOnly = False
        self.addr.setText(self.load_default('addr'))
        self.user = wid.QLineEdit()
        self.user.readOnly = False
        self.user.setText(self.load_default('user'))
        self.group = wid.QLineEdit()
        self.group.readOnly = False
        self.group.setText(self.load_default('group'))
        self.password = wid.QLineEdit()
        self.password.readOnly = False
        self.password.setText(self.load_default('password'))
        self.password.setEchoMode(wid.QLineEdit.Password)

        if self.defaults and self.addr.text() and self.user.text() and self.password.text() and self.group.text():
            self.finished.emit(1)
            self.accepted.emit()
            return

        hbox_addr = wid.QHBoxLayout()
        hbox_addr.addWidget(wid.QLabel('Address of server: '))
        hbox_addr.addWidget(self.addr)

        hbox_user = wid.QHBoxLayout()
        hbox_user.addWidget(wid.QLabel('Username: '))
        hbox_user.addWidget(self.user)

        hbox_group = wid.QHBoxLayout()
        hbox_group.addWidget(wid.QLabel('Group: '))
        hbox_group.addWidget(self.group)

        hbox_password = wid.QHBoxLayout()
        hbox_password.addWidget(wid.QLabel('Password: '))
        hbox_password.addWidget(self.password)

        ok = wid.QPushButton('OK')
        ok.clicked.connect(self.ok_clicked)
        ok.clicked.connect(super().done)
        vbox.addLayout(hbox_addr)
        vbox.addLayout(hbox_user)
        vbox.addLayout(hbox_group)
        vbox.addLayout(hbox_password)
        vbox.addWidget(ok)

        self.setVisible(True)

    default_addr_file = '.config/stex/'

    def load_default(self, id):
        try:
            home = os.environ.get('HOME')
            if not home:
                home = path.join('/home/', os.environ.get('USER'))
            with open(path.join(home, self.default_addr_file, id), 'r') as f:
                return f.readline()
        except Exception as e:
            sys.stderr.write("Couldn't read file: {}\n".format(e))
            return ''
    
    def save_default(self, id, val):
        try:
            home = os.environ.get('HOME')
            if not home:
                home = path.join('/home/', os.environ.get('USER'))
            da = path.join(home, self.default_addr_file, id)
            os.makedirs(path.dirname(da), exist_ok=True)
            f = open(da, 'w' if os.access(da, os.F_OK) else 'x')
            f.write(val)
        except Exception as e:
            sys.stderr.write("Couldn't write file: {}\n".format(e))
            return

    def ok_clicked(self):
        self.save_default('addr', self.addr.text())
        self.save_default('user', self.user.text())
        self.save_default('password', self.password.text())
        self.accepted.emit()
        self.finished.emit(1)

    def creds(self):
        creds = Creds()
        creds.user = self.user.text()
        creds.password = self.password.text()
        creds.addr = self.addr.text()
        creds.group = self.group.text()
        return creds


class Depot(core.QObject):
    """Depot contains several DepotStocks and manages buying/selling them."""
    cash = 0
    stock = {}

    priceUpdated = core.pyqtSignal(str)

    def add_stock(self, stocksym, stock):
        if stocksym not in self.stock:
            self.stock[stocksym] = stock

    def buy(self, stocksym, num):
        if stocksym not in self.stock:
            raise AttributeError('stock not found!')
        stock = self.stock[stocksym]
        price = stock.current_price
        if price == 0:
            price = 1
        if price * num > self.cash:
            return False
        self.cash -= price * num
        stock.change_hold(num)
        return True

    def sell(self, stocksym, num):
        if stocksym not in self.stock:
            raise AttributeError('stock not found!')
        stock = self.stock[stocksym]
        price = stock.current_price
        if num > stock.current_num:
            return False
        self.cash += price * num
        stock.change_hold(-num)
        return True

    def update(self, message):
        for sym, upd in message.items():
            if sym.startswith('_'):
                continue
            if sym in self.stock:
                self.stock[sym].update(upd)
                self.priceUpdated.emit(sym)

    def total_value(self):
        value = 0
        for sym, stock in self.stock.items():
            value += stock.current_num * stock.current_price
        return value

    def serialize(self):
        s = {'cash': self.cash, 'stock': {}, '_stockdepot': True}
        for sym, stock in self.stock.items():
            stock_sum = {'num': stock.current_num}
            s['stock'][sym] = stock_sum
        return json.dumps(s)


class DepotStock:
    """DepotStock is a position of stock in a single company in the depot. It
    manages its own price and volume as well as some statistics."""
    sym = ''
    mydepot = None

    current_price = -1
    total_buy_price = 0
    current_num = 0
    MAXHIST = 500
    price_history = []

    def __init__(self, sym):
        self.sym = sym

    def update(self, upd):
        """Apply an update received from the stex server.

        upd is a stock update message.
        """
        if self.current_price >= 0:
            self.price_history.append(self.current_price)
            if len(self.price_history) > self.MAXHIST:
                self.price_history = self.price_history[25:]
        self.current_price = upd['price']
        if upd['split']:
            self.current_num = self.current_num * 2

    def change_hold(self, diff):
        self.current_num += diff
        if diff > 0:
            self.total_buy_price += diff * self.current_price
        if diff < 0:
            self.total_buy_price += diff * self.avg_buy_price()

    def avg_buy_price(self):
        return self.total_buy_price / (self.current_num or 1)


class StockGraph(chart.QChartView):
    """StockGraph is a stock price graph in the UI. Its knowledge of the stock is exclusively
    updated by other objects like StockWidget."""

    sym = ''
    # Updated by StockWidget
    avg_buy_price = 0

    MAX_LEN = 500
    XAXIS = [i for i in range(0, MAX_LEN)]
    # Current position in graph.
    current = 0

    series = None
    avg_buy_series = None
    upd_series = None

    def __init__(self, sym, dim):
        super().__init__()
        super().setMinimumSize(300, 200)
        self.sym = sym
        self.series = chart.QLineSeries(self)
        self.avg_buy_series = chart.QLineSeries(self)
        self.upd_series = chart.QLineSeries(self)

        for x in self.XAXIS:
            self.series.append(x, 0)

        super().chart().setTitle(self.sym)
        super().chart().legend().hide()
        super().chart().addSeries(self.series)
        super().chart().addSeries(self.avg_buy_series)
        super().chart().addSeries(self.upd_series)
        super().chart().createDefaultAxes()

    # update_stock sets a new stock price.
    def update_stock(self, value):
        """Update data series used for plotting graphs."""
        mn, mx = 1e9, -1e9
        for v in self.series.pointsVector():
            if v.y() < mn:
                mn = v.y()
            if v.y() > mx:
                mx = v.y()

        previous, nxt = (self.current - 1) % self.MAX_LEN, (self.current + 1) % self.MAX_LEN
        self.series.replace(self.current, self.current, value)

        self.upd_series.clear()
        self.upd_series.append(self.current, 0)
        self.upd_series.append(self.current, max(mx, self.avg_buy_price))

        self.avg_buy_series.clear()
        self.avg_buy_series.append(0, self.avg_buy_price)
        self.avg_buy_series.append(self.MAX_LEN - 1, self.avg_buy_price)

        self.current += 1
        if self.current >= self.MAX_LEN:
            self.current = 0
        self.plot()

    def plot(self):
        """Updates the graph widget."""
        while super().chart().series():
            super().chart().removeSeries(super().chart().series()[0])
        super().chart().addSeries(self.upd_series)
        super().chart().addSeries(self.avg_buy_series)
        super().chart().addSeries(self.series)
        super().chart().createDefaultAxes()


class StockWidget(wid.QWidget):
    """StockWidget contains a stock price graph as well as buy/sell buttons and price indicators.
    """
    graph = None
    depot = None
    sym = ''
    depotstock = None

    def __init__(self, graph, depot, depotstock):
        super().__init__()
        self.graph = graph
        self.depot = depot
        self.depotstock = depotstock
        self.sym = self.depotstock.sym

        mainvbox = wid.QVBoxLayout(self)
        mainvbox.addWidget(self.graph)
        mainvbox.addLayout(self.init_buttonbox())

    def init_buttonbox(self):
        buy = wid.QPushButton('  BUY   ')
        buy.clicked.connect(self.on_buy)
        sell = wid.QPushButton('  SELL  ')
        sell.clicked.connect(self.on_sell)
        self.current_state = wid.QLineEdit()
        self.current_state.setReadOnly(True)
        self.current_state.setAlignment(core.Qt.AlignCenter)

        hbox = wid.QHBoxLayout()
        hbox.addWidget(buy)
        hbox.addWidget(sell)
        hbox.addWidget(self.current_state)
        return hbox

    def on_buy(self):
        if not self.depot.buy(self.sym, 1):
            print("Warning: couldn't buy {}".format(self.depotstock.sym))
        self.update_values()

    def on_sell(self):
        if not self.depot.sell(self.sym, 1):
            print("Warning: couldn't sell {}".format(self.depotstock.sym))
        self.update_values()

    # Triggered by the depot when there is new data for any stock (so we filter if the update is for us)
    @core.pyqtSlot(str)
    def update(self, sym):
        if sym != self.sym:
            return
        val = self.depotstock.current_price / 100
        self.graph.update_stock(val)
        self.update_values()

    def update_values(self):
        val = self.depotstock.current_price / 100
        self.graph.avg_buy_price = self.depotstock.avg_buy_price() / 100
        self.current_state.setText('{} pc / {:.2f} ø/pc / {:.2f} ø'.format(self.depotstock.current_num, val, self.depotstock.current_num * val))


class DepotWidget(wid.QWidget):
    depot = None
    hbox = None
    depot_value_widget = None

    def __init__(self, depot):
        super().__init__()
        self.depot = depot
        self.depot.priceUpdated.connect(self.on_depot_update)

        self.hbox = wid.QHBoxLayout(self)
        self.depot_value_widget = wid.QLineEdit()
        self.depot_value_widget.setReadOnly(True)
        self.depot_value_widget.setAlignment(core.Qt.AlignCenter)
        self.hbox.addWidget(wid.QLabel('Current Depot Value: '))
        self.hbox.addWidget(self.depot_value_widget)

        self.on_depot_update('')

    @core.pyqtSlot(str)
    def on_depot_update(self, sym_):
        stock = self.depot.total_value() / 100
        cash = self.depot.cash / 100
        self.depot_value_widget.setText('{:.2f} ø = {:.2f} ø (Cash) + {:.2f} ø (Stock)'.format(stock + cash, cash, stock))


class ClientSocket(core.QObject):
    zctx = None
    sock = None
    socknot = None

    on_new_message = core.pyqtSignal(dict)

    def __init__(self, zctx, creds):
        """callback is a function taking received data dicts."""
        super().__init__()

        self.zctx = zctx
        self.sock = self.zctx.socket(zmq.SUB)
        self.sock.setsockopt(zmq.IPV6, 1)
        self.sock.subscribe('')
        self.sock.setsockopt(zmq.RCVTIMEO, 0)

        self.sock.connect('tcp://{}'.format(creds.addr))
        fd = self.sock.getsockopt(zmq.FD)
        self.socknot = core.QSocketNotifier(fd, core.QSocketNotifier.Read)
        self.socknot.activated.connect(self.on_activated)

    @core.pyqtSlot(int)
    def on_activated(self, _sock):
        try:
            while True:
                msg = self.sock.recv_json()
                if '_stockdata' not in msg:
                    return
                self.on_new_message.emit(msg)
        except Exception as e:
            return

class CallbackSocket(core.QObject):
    """CallbackSocket sends messages to the stex server and receives responses."""
    creds = None
    socket = None
    waiting = False
    queue = []

    def __init__(self, zctx, creds):
        super().__init__()
        self.creds = creds
        socket = zctx.socket(zmq.REQ)
        socket.setsockopt(zmq.IPV6, 1)
        socket.setsockopt(zmq.RCVTIMEO, 0)
        socket.setsockopt(zmq.SNDTIMEO, 10)
        
        u = url.urlparse(creds.addr)
        hostport = u.netloc or u.path
        (host, _, port) = hostport.partition(':')
        socket.connect('tcp://{}:{}'.format(host, int(port if port else '9988') + 1))
        self.socket = socket

        fd = self.socket.getsockopt(zmq.FD)
        self.socknot = core.QSocketNotifier(fd, core.QSocketNotifier.Read)
        self.socknot.activated.connect(self.on_reply)

    def login(self):
        self.try_send({'_stocklogin': True})

    def send_depot(self, depot):
        summary = depot.serialize()
        self.try_send(summary)

    def wrap(self, msg):
        return json.dumps({
            '_stockcallback': True,
            'user': self.creds.user,
            'password': self.creds.password,
            'group': self.creds.group,
            'msg': msg,
        })

    def try_send(self, msg):
        msg = self.wrap(msg)
        if self.waiting:
            self.queue.append(msg)
        else:
            try:
                self.socket.send_string(msg)
                self.waiting = True
            except Exception as e:
                print ('DEBUG: Send failed on REQ socket: ', e)
                self.queue.append(msg)
        assert len(self.queue) < 5

    @core.pyqtSlot(int)
    def on_reply(self, _sock):
        try:
            msg = self.socket.recv_json()
            print('DEBUG: Received response: {}'.format(msg))
            self.waiting = False

            # Try sending oldest message.
            if len(self.queue) > 0:
                self.try_send(self.queue.pop(0))
        except Exception as e:
            print ('DEBUG: RECV failed on REQ socket: ', e)


class Client(arguments.BaseArguments, wid.QWidget):
    _doc = """
    Usage:
        stex [options]

    Options
        --defaults      Use cached defaults if available.
    """

    creds = Creds()
    depot = Depot()
    depot_widget = None
    zctx = zmq.Context()
    timer = None
    callback_sock = None

    def __init__(self):
        super(wid.QWidget, self).__init__()
        super(arguments.BaseArguments, self).__init__(doc=self._doc)

        self.depot_widget = DepotWidget(self.depot)
        self.depot.cash = 1000000

        ccd = ClientConfigDialog(self, defaults=self.defaults)
        ccd.accepted.connect(lambda: self.set_creds(ccd.creds()))
        ccd.accepted.connect(self.start_wait_window)
        ccd.show_dialog()

        self.timer = core.QTimer(self)
        self.timer.setInterval(1500)
        self.timer.timeout.connect(self.on_periodic_timer)
        self.timer.start()

    def set_creds(self, creds):
        self.creds = creds

    def start_wait_window(self):
        self.mainvbox = wid.QVBoxLayout(self)
        self.waiting = wid.QLabel("Waiting for incoming stock data - hang tight!", self)
        self.mainvbox.addWidget(self.depot_widget)
        self.mainvbox.addWidget(self.waiting)
        self.show()
        
        self.sock = ClientSocket(self.zctx, self.creds)
        self.sock.on_new_message.connect(self.on_new_data)
        self.callback_sock = CallbackSocket(self.zctx, self.creds)
        self.callback_sock.login()

    stock_widgets = {}

    @core.pyqtSlot(dict)
    def on_new_data(self, stockdata):
        self.waiting.hide()
        self.depot.update(stockdata)
        for sym, upd in sorted(stockdata.items()):
            if sym != '_stockdata' and sym not in self.stock_widgets:
                depotstock = DepotStock(sym)
                sg = StockGraph(sym, None)
                sw = StockWidget(sg, self.depot, depotstock)
                self.stock_widgets[sym] = sw
                self.add_stock_widget(sw)
                self.depot.add_stock(sym, depotstock)
                self.depot.priceUpdated.connect(sw.update)

    @core.pyqtSlot()
    def on_periodic_timer(self):
        print('DEBUG: timer expired!')
        if not self.callback_sock:
            return
        self.callback_sock.send_depot(self.depot)
    
    mainvbox = None
    hboxes = []
    widgets_per_hbox = 2

    def add_stock_widget(self, sw):
        if len(self.hboxes) == 0 or self.hboxes[-1].count() >= self.widgets_per_hbox:
            hbox = wid.QHBoxLayout()
            hbox.addWidget(sw)
            self.hboxes.append(hbox)
            self.mainvbox.addLayout(hbox)
        else:
            self.hboxes[-1].addWidget(sw)
        return


def main():
    app = wid.QApplication(sys.argv)
    client = Client()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
