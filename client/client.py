#!/usr/bin/env python3

import arguments
import os
import os.path as path
import sys

import PyQt5.QtWidgets as wid
import PyQt5.QtCore as core

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

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

    def creds(self):
        creds = Creds()
        creds.user = self.user.text()
        creds.password = self.password.text()
        creds.addr = self.addr.text()
        return creds

class StockGraph(FigureCanvas):
    fig = None
    axes = None
    sym = ''

    MAX_LEN = 500
    XAXIS = [i for i in range(0, MAX_LEN)]
    history = [0 for i in range(0, MAX_LEN)]

    def __init__(self, sym, dim):
        self.sym = sym
        self.fig = Figure(figsize=(dim or (200,100)))
        self.axes = self.fig.add_subplot(111)
        self.axes.grid(True)
        self.axes.set_xlim(0, self.MAX_LEN)

        super().__init__(self.fig)
        super().setSizePolicy(wid.QSizePolicy.Expanding, wid.QSizePolicy.Expanding)
        super().updateGeometry()

    def update_stock(self, value):
        self.history.append(value)
        self.history[0:] = self.history[1:]
        self.plot()

    def plot(self):
        self.axes.set_title(self.sym)
        self.axes.plot(self.XAXIS, self.history)
        self.draw()

class StockWidget(wid.QWidget):
    graph = None

    def __init__(self, graph):
        super().__init__()
        self.graph = graph

        mainvbox = wid.QVBoxLayout(self)
        mainvbox.addWidget(self.graph)
        mainvbox.addLayout(self.init_buttonbox())
        self.update(5000)
        self.show()

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
        self.graph.update_stock(val)
        self.current_state.setText('{} pc / {} ø/pc / {} ø'.format('?', val/100, val/100))

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
        ccd.accepted.connect(self.start_main_window)
        ccd.show_dialog()

    def set_creds(self, creds):
        self.creds = creds

    def start_main_window(self):
        mainvbox = wid.QVBoxLayout(self)

        hbox1 = wid.QHBoxLayout()
        sg1 = StockWidget(StockGraph('ABCD', None))
        sg2 = StockWidget(StockGraph('EFGH', None))
        hbox1.addWidget(sg1)
        hbox1.addWidget(sg2)

        hbox2 = wid.QHBoxLayout()
        sg3 = StockWidget(StockGraph('ABCD', None))
        sg4 = StockWidget(StockGraph('ABCD', None))
        hbox2.addWidget(sg3)
        hbox2.addWidget(sg4)

        mainvbox.addLayout(hbox1)
        mainvbox.addLayout(hbox2)

        self.show()


def main():
    app = wid.QApplication(sys.argv)
    client = Client()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
