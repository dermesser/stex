#!/usr/bin/env python3

import arguments
import os
import os.path as path
import sys
import zmq

import PyQt5.QtWidgets as wid
import PyQt5.QtCore as core
import PyQt5.QtChart as chart

class Creds:
    user = ''
    password = ''
    addr = ''

class ClientConfigDialog(wid.QDialog):
    addr = None
    user = None
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
        self.password = wid.QLineEdit()
        self.password.readOnly = False
        self.password.setText(self.load_default('password'))
        self.password.setEchoMode(wid.QLineEdit.Password)

        if self.defaults and self.addr.text() and self.user.text() and self.password.text():
            self.finished.emit(1)
            self.accepted.emit()
            return

        hbox_addr = wid.QHBoxLayout()
        hbox_addr.addWidget(wid.QLabel('Address of server: '))
        hbox_addr.addWidget(self.addr)

        hbox_user = wid.QHBoxLayout()
        hbox_user.addWidget(wid.QLabel('Username: '))
        hbox_user.addWidget(self.user)

        hbox_password = wid.QHBoxLayout()
        hbox_password.addWidget(wid.QLabel('Password: '))
        hbox_password.addWidget(self.password)

        ok = wid.QPushButton('OK')
        ok.clicked.connect(self.ok_clicked)
        ok.clicked.connect(super().done)
        vbox.addLayout(hbox_addr)
        vbox.addLayout(hbox_user)
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
        return creds

class StockGraph(chart.QChartView):
    sym = ''

    MAX_LEN = 500
    XAXIS = [i for i in range(0, MAX_LEN)]
    # Current position in graph.
    current = 0

    series = None
    min, max = 1e9, -1e9

    def __init__(self, sym, dim):
        super().__init__()
        super().setMinimumSize(300,300)
        self.sym = sym
        self.series = chart.QLineSeries(self)
        for x in self.XAXIS:
            self.series.append(x, 0)

        super().chart().setTitle(self.sym)
        super().chart().legend().hide()
        super().chart().addSeries(self.series)
        super().chart().createDefaultAxes()

    def update_stock(self, value):
        if value < self.min:
            self.min = value
        if value > self.max:
            self.max = value

        previous, nxt = (self.current-1)%self.MAX_LEN, (self.current+1)%self.MAX_LEN
        # Shift graph to the left
        self.series.replace(self.current, self.current, value)

        self.current += 1
        if self.current >= self.MAX_LEN:
            self.current = 0
        self.plot()

    def plot(self):
        super().chart().removeSeries(super().chart().series()[0])
        super().chart().addSeries(self.series)
        super().chart().createDefaultAxes()

class StockWidget(wid.QWidget):
    graph = None

    def __init__(self, graph):
        super().__init__()
        self.graph = graph

        mainvbox = wid.QVBoxLayout(self)
        mainvbox.addWidget(self.graph)
        mainvbox.addLayout(self.init_buttonbox())

    def init_buttonbox(self):
        buy = wid.QPushButton('  BUY   ')
        sell = wid.QPushButton('  SELL  ')
        self.current_state = wid.QLineEdit()
        self.current_state.setReadOnly(True)
        self.current_state.setAlignment(core.Qt.AlignCenter)

        hbox = wid.QHBoxLayout()
        hbox.addWidget(buy)
        hbox.addWidget(sell)
        hbox.addWidget(self.current_state)
        return hbox

    def update(self, val):
        self.graph.update_stock(val/100)
        self.current_state.setText('{} pc / {} ø/pc / {} ø'.format('?', val/100, val/100))

class ClientSocket(core.QObject):
    zctx = None
    sock = None
    socknot = None

    on_new_message = core.pyqtSignal(dict)

    def __init__(self, creds):
        """callback is a function taking received data dicts."""
        super().__init__()

        self.zctx = zmq.Context()
        self.sock = self.zctx.socket(zmq.SUB)
        self.sock.setsockopt(zmq.IPV6, 1)
        self.sock.subscribe('')
        self.sock.connect('tcp://{}'.format(creds.addr))
        self.sock.setsockopt(zmq.RCVTIMEO, 0)
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
        except Exception:
            return

class Client(arguments.BaseArguments, wid.QWidget):
    _doc = """
    Usage:
        stex [options]

    Options
        --defaults      Use cached defaults if available.
    """

    creds = Creds()

    def __init__(self):
        super(wid.QWidget, self).__init__()
        super(arguments.BaseArguments, self).__init__(doc=self._doc)

        ccd = ClientConfigDialog(self, defaults=self.defaults)
        ccd.accepted.connect(lambda: self.set_creds(ccd.creds()))
        ccd.accepted.connect(self.start_wait_window)
        ccd.show_dialog()

    def set_creds(self, creds):
        self.creds = creds

    def start_wait_window(self):
        self.sock = ClientSocket(self.creds)
        self.sock.on_new_message.connect(self.on_new_data)

        self.start_main_window()
        self.waiting = wid.QLabel("Waiting for incoming stock data - hang tight!", self)
        self.mainvbox.addWidget(self.waiting)

    stock_widgets = {}

    @core.pyqtSlot(dict)
    def on_new_data(self, stockdata):
        self.waiting.hide()
        for sym, val in sorted(stockdata.items()):
            if sym in self.stock_widgets:
                self.stock_widgets[sym].update(val)
            elif sym != '_stockdata':
                sg = StockGraph(sym, None)
                sw = StockWidget(sg)
                self.stock_widgets[sym] = sw
                self.add_stock_widget(sw)

    mainvbox = None
    hboxes = []
    widgets_per_hbox = 2

    def add_stock_widget(self, sw):
        print(self.hboxes)
        if len(self.hboxes) == 0 or self.hboxes[-1].count() >= self.widgets_per_hbox:
            hbox = wid.QHBoxLayout()
            hbox.addWidget(sw)
            self.hboxes.append(hbox)
            self.mainvbox.addLayout(hbox)
        else:
            self.hboxes[-1].addWidget(sw)
        return

    def start_main_window(self):
        self.mainvbox = wid.QVBoxLayout(self)
        self.main_window_active = True
        self.show()

def main():
    app = wid.QApplication(sys.argv)
    client = Client()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
