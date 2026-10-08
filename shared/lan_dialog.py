# -*- coding: utf-8 -*-
"""
局域网联机对话框：左边创建房间，右边发现并加入房间

对外入口：
    info, session = ask_lan(parent, game, "黑方", "白方")
连接成功后 info = {"isHost":bool, "seat":0/1, "peer":{"name":..}}，
session 需要由调用方保管，游戏结束时 session.close()。
"""
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                               QLineEdit, QComboBox, QListWidget, QListWidgetItem,
                               QFrame)

from shared.common import (C_BG, C_PANEL, C_PANEL2, C_LINE, C_TEXT, C_DIM,
                           C_FAINT, C_ACCENT, C_OK, C_DANGER, C_GOLD, rgba,
                           mk_button)
from shared.lan import LanSession, DEFAULT_TCP


def default_name():
    n = os.environ.get("USERNAME") or os.environ.get("USER") or "玩家"
    return str(n)[:12]


class LanDialog(QDialog):
    def __init__(self, parent, game, first_name="先手", second_name="后手",
                 title="局域网联机"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(680, 540)
        self.game = game
        self.info = None
        self.session = None
        self.rooms = {}
        self.setStyleSheet("QDialog{background:%s;}QLabel{color:%s;}" % (C_BG, C_TEXT))
        self._build(first_name, second_name)
        # 自动开始搜索房间
        self.session = LanSession(self.game, default_name())
        self._wire()
        self.session.start_discover()

    # -------- UI
    def _build(self, first_name, second_name):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(12)

        head = QHBoxLayout()
        t = QLabel("局域网联机")
        t.setStyleSheet("font-size:18px;font-weight:800;")
        head.addWidget(t)
        head.addStretch(1)
        head.addWidget(QLabel("我的昵称"))
        self.ed_name = QLineEdit(default_name())
        self.ed_name.setFixedWidth(140)
        self.ed_name.setStyleSheet(self._qss_input())
        head.addWidget(self.ed_name)
        root.addLayout(head)

        cols = QHBoxLayout()
        cols.setSpacing(14)
        cols.addWidget(self._host_panel(first_name, second_name), 1)
        cols.addWidget(self._join_panel(), 1)
        root.addLayout(cols, 1)

        self.lb_msg = QLabel("提示：同一局域网内会自动出现在右侧列表；"
                             "首次运行请允许 Windows 防火墙访问")
        self.lb_msg.setWordWrap(True)
        self.lb_msg.setStyleSheet("color:%s;font-size:12px;" % C_DIM)
        root.addWidget(self.lb_msg)

        row = QHBoxLayout()
        row.addStretch(1)
        self.btn_cancel = mk_button("取消", parent=self)
        self.btn_cancel.clicked.connect(self.reject)
        row.addWidget(self.btn_cancel)
        root.addLayout(row)

    def _card(self, title):
        f = QFrame()
        f.setStyleSheet("QFrame{background:%s;border:1px solid %s;border-radius:12px;}"
                        % (C_PANEL, C_LINE))
        lay = QVBoxLayout(f)
        lay.setContentsMargins(14, 12, 14, 14)
        lay.setSpacing(9)
        lb = QLabel(title)
        lb.setStyleSheet("color:%s;font-size:12px;font-weight:700;" % C_FAINT)
        lay.addWidget(lb)
        return f, lay

    def _qss_input(self):
        return ("QLineEdit{background:%s;color:%s;border:1px solid %s;border-radius:9px;"
                "padding:5px 9px;font-size:13px;}"
                "QLineEdit:focus{border-color:%s;}" % (C_PANEL2, C_TEXT, C_LINE, C_ACCENT))

    def _host_panel(self, first_name, second_name):
        f, lay = self._card("① 创建房间")
        self.cmb_side = QComboBox()
        self.cmb_side.addItems(["我执%s（先手）" % first_name, "我执%s（后手）" % second_name])
        self.cmb_side.setStyleSheet(
            "QComboBox{background:%s;color:%s;border:1px solid %s;border-radius:9px;"
            "padding:6px 10px;font-size:13px;}"
            "QComboBox QAbstractItemView{background:%s;color:%s;"
            "selection-background-color:%s;outline:none;}"
            % (C_PANEL2, C_TEXT, C_LINE, C_PANEL2, C_TEXT, C_ACCENT))
        lay.addWidget(self.cmb_side)
        self.btn_host = mk_button("创建房间", "primary", parent=self)
        self.btn_host.clicked.connect(self._do_host)
        lay.addWidget(self.btn_host)
        self.lb_host = QLabel("创建后，右侧会自动把你的房间广播给同一局域网的人")
        self.lb_host.setWordWrap(True)
        self.lb_host.setStyleSheet("color:%s;font-size:12px;" % C_DIM)
        lay.addWidget(self.lb_host)
        lay.addStretch(1)
        return f

    def _join_panel(self):
        f, lay = self._card("② 加入房间")
        self.lst = QListWidget()
        self.lst.setMinimumHeight(150)
        self.lst.itemDoubleClicked.connect(lambda _i: self._do_join_selected())
        self.lst.setStyleSheet(
            "QListWidget{background:%s;color:%s;border:1px solid %s;border-radius:9px;"
            "font-size:13px;outline:none;}"
            "QListWidget::item{padding:7px 9px;}"
            "QListWidget::item:selected{background:%s;color:%s;}"
            % (C_PANEL2, C_TEXT, C_LINE, rgba(C_ACCENT, 0.35), C_TEXT))
        lay.addWidget(self.lst, 1)
        self.btn_join = mk_button("加入选中的房间", parent=self)
        self.btn_join.clicked.connect(self._do_join_selected)
        lay.addWidget(self.btn_join)

        man = QHBoxLayout()
        man.setSpacing(7)
        self.ed_ip = QLineEdit()
        self.ed_ip.setPlaceholderText("或手动输入 IP，如 192.168.1.29")
        self.ed_ip.setStyleSheet(self._qss_input())
        self.ed_ip.returnPressed.connect(self._do_join_manual)
        man.addWidget(self.ed_ip, 1)
        b = mk_button("加入", parent=self)
        b.clicked.connect(self._do_join_manual)
        man.addWidget(b)
        lay.addLayout(man)
        return f

    # -------- 信号
    def _wire(self):
        s = self.session
        s.rooms.connect(self._on_rooms)
        s.started.connect(self._on_started)
        s.failed.connect(self._on_failed)
        s.hosting.connect(self._on_hosting)

    def _on_rooms(self, rooms):
        keys = []
        for r in rooms:
            key = "%s:%s" % (r["ip"], r["port"])
            keys.append(key)
            state = "可加入" if r.get("state") != "playing" else "对局中"
            text = "  %-15s  %-12s  %s" % (r["ip"], r["name"], state)
            if key not in self.rooms:
                it = QListWidgetItem(text)
                it.setData(Qt.UserRole, (r["ip"], r["port"], r.get("state")))
                if r.get("state") == "playing":
                    it.setForeground(Qt.gray)
                self.lst.addItem(it)
                self.rooms[key] = it
            else:
                it = self.rooms[key]
                it.setText(text)
                it.setData(Qt.UserRole, (r["ip"], r["port"], r.get("state")))
        for key in list(self.rooms):
            if key not in keys:
                it = self.rooms.pop(key)
                self.lst.takeItem(self.lst.row(it))

    def _on_hosting(self, info):
        self.lb_host.setText(
            "房间已创建\n本机地址：%s:%d\n把地址告诉朋友，或让他在右侧列表里点你的房间。\n"
            "等待对手加入…" % (info["ip"], info["port"]))
        self.lb_host.setStyleSheet("color:%s;font-size:12.5px;font-weight:600;" % C_OK)
        self.btn_host.setEnabled(False)

    def _on_started(self, info):
        self.info = info
        self.session.stop_discover()
        self.accept()

    def _on_failed(self, msg):
        self.lb_msg.setText("⚠ " + str(msg))
        self.lb_msg.setStyleSheet("color:%s;font-size:12px;" % C_DANGER)
        self.btn_host.setEnabled(True)

    # -------- 操作
    def _do_host(self):
        self.session.name = self.ed_name.text().strip() or "玩家"
        want_first = self.cmb_side.currentIndex() == 0
        ok, err = self.session.start_host(want_first)
        if not ok:
            self._on_failed(err)
            return
        self.lb_msg.setText("房间已建好，等待对手加入…（首次运行请允许防火墙访问）")
        self.lb_msg.setStyleSheet("color:%s;font-size:12px;" % C_GOLD)

    def _do_join_selected(self):
        it = self.lst.currentItem()
        if it is None:
            self._on_failed("先在列表里选一个房间，或手动输入对方 IP")
            return
        ip, port, state = it.data(Qt.UserRole)
        if state == "playing":
            self._on_failed("这个房间正在对局中")
            return
        self._join(ip, port)

    def _do_join_manual(self):
        text = self.ed_ip.text().strip()
        if not text:
            self._on_failed("请输入对方 IP，例如 192.168.1.29 或 192.168.1.29:45680")
            return
        if ":" in text:
            ip, _, por = text.partition(":")
            try:
                port = int(por)
            except ValueError:
                self._on_failed("端口号不对：%s" % por)
                return
        else:
            ip, port = text, DEFAULT_TCP.get(self.game, 45680)
        self._join(ip, port)

    def _join(self, ip, port):
        self.session.name = self.ed_name.text().strip() or "玩家"
        self.lb_msg.setText("正在连接 %s:%s …" % (ip, port))
        self.lb_msg.setStyleSheet("color:%s;font-size:12px;" % C_DIM)
        ok, err = self.session.start_join(ip, port)
        if not ok:
            self._on_failed(err)

    # -------- 关闭
    def _cleanup(self):
        if self.session is not None and self.info is None:
            self.session.close()

    def reject(self):
        self._cleanup()
        super().reject()

    def closeEvent(self, ev):
        self._cleanup()
        super().closeEvent(ev)


def ask_lan(parent, game, first_name="先手", second_name="后手", title="局域网联机"):
    """弹出联机对话框；成功返回 (info, session)，取消返回 (None, None)"""
    dlg = LanDialog(parent, game, first_name, second_name, title)
    if dlg.exec() == QDialog.Accepted and dlg.info:
        return dlg.info, dlg.session
    return None, None
