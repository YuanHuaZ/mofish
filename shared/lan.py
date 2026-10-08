# -*- coding: utf-8 -*-
"""
局域网联机（纯标准库，无额外依赖）

- 传输：TCP 长连接 + 按行分隔的 JSON 消息（一条棋一步）
- 发现：房主用 UDP 广播（含 127.0.0.1，方便同机测试）宣告房间，
  加入方监听广播即可自动列出同一局域网内的房间；也支持手动填 IP 直连
- 线程：收发都在后台线程，通过 Qt 信号回主线程，界面不会卡

消息类型：
    hello / welcome / reject      握手
    move                          走子（各游戏自定义载荷）
    undo_req / undo_ok / undo_no  悔棋请求与应答
    rematch_req / rematch_ok      再来一局
    resign                        认输
    ping / pong                   保活
    bye                           主动退出
"""
import json
import socket
import threading
import time

from PySide6.QtCore import QObject, QThread, Signal

MAGIC = "mofish-lan"
VER = 1
DEFAULT_TCP = {"gomoku": 45680, "xiangqi": 45682}
DISCOVERY_UDP = {"gomoku": 45681, "xiangqi": 45683}
BROADCAST_INTERVAL = 1.2
ROOM_TTL = 4.0
IDLE_TIMEOUT = 26.0
PING_INTERVAL = 5.0


def local_ip():
    """取本机在局域网中的地址"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        try:
            s.close()
        except Exception:
            pass


def encode(obj):
    return (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")


class _LineReader(object):
    """把 TCP 字节流切成一行一个 JSON"""

    def __init__(self):
        self.buf = b""

    def feed(self, data):
        self.buf += data
        out = []
        while b"\n" in self.buf:
            line, self.buf = self.buf.split(b"\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line.decode("utf-8"))
            except Exception:
                continue
            if isinstance(obj, dict):
                out.append(obj)
        return out


# ------------------------------------------------------------------ 房主
class _HostThread(QThread):
    ready = Signal(int)               # 监听端口
    peerConnected = Signal(dict)      # {name, addr, seat}
    peerMessage = Signal(dict)
    peerGone = Signal(str)
    failed = Signal(str)

    def __init__(self, game, name, host_seat, parent=None):
        super().__init__(parent)
        self.game = game
        self.name = name
        self.host_seat = host_seat
        self._stop = False
        self._conn = None
        self._lock = threading.Lock()
        self._last_recv = time.time()
        self.state = "waiting"        # waiting / playing
        port = DEFAULT_TCP.get(game, 45680)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.sock.bind(("", port))
        except OSError:
            self.sock.bind(("", 0))   # 默认端口被占就随机取一个
        self.port = self.sock.getsockname()[1]
        self.sock.listen(2)
        self.sock.settimeout(0.4)

    # -------- 发送
    def send(self, obj):
        with self._lock:
            if self._conn is None:
                return False
            try:
                self._conn.sendall(encode(obj))
                return True
            except Exception:
                return False

    @property
    def peer_active(self):
        return self._conn is not None

    def run(self):
        try:
            self._run()
        except Exception as exc:          # 兜底：不让线程静默死掉
            self.failed.emit("房主线程出错：%s" % exc)

    def _run(self):
        self.ready.emit(self.port)
        bc = threading.Thread(target=self._broadcast, daemon=True)
        bc.start()
        while not self._stop:
            try:
                conn, addr = self.sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            if self._conn is not None:
                try:
                    conn.sendall(encode({"t": "reject", "reason": "房间里已经有人了"}))
                    conn.close()
                except Exception:
                    pass
                continue
            if not self._handshake(conn, addr):
                continue
            self._serve(conn, addr)
        try:
            self.sock.close()
        except Exception:
            pass

    def _handshake(self, conn, addr):
        conn.settimeout(6.0)
        reader = _LineReader()
        deadline = time.time() + 6.0
        while time.time() < deadline:
            try:
                data = conn.recv(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            if not data:
                break
            msgs = reader.feed(data)
            if not msgs:
                continue
            hello = msgs[0]
            if hello.get("t") != "hello" or hello.get("game") != self.game:
                try:
                    conn.sendall(encode({"t": "reject", "reason": "游戏类型不匹配"}))
                except Exception:
                    pass
                try:
                    conn.close()
                except Exception:
                    pass
                return False
            peer_name = str(hello.get("name") or "玩家")[:16]
            with self._lock:
                self._conn = conn
            self.state = "playing"
            self._last_recv = time.time()
            self.send({"t": "welcome", "ver": VER, "seat": 1 - self.host_seat,
                       "peer": {"name": peer_name}})
            self.peerConnected.emit({"name": peer_name, "addr": addr[0],
                                     "seat": 1 - self.host_seat})
            return True
        try:
            conn.close()
        except Exception:
            pass
        return False

    def _serve(self, conn, addr):
        reader = _LineReader()
        conn.settimeout(0.4)
        last_ping = time.time()
        while not self._stop:
            try:
                data = conn.recv(4096)
            except socket.timeout:
                data = None                      # 超时（无数据）与对端关闭要区分开
            except OSError:
                break
            if data is None:
                if time.time() - self._last_recv > IDLE_TIMEOUT:
                    self.peerGone.emit("与对手的连接超时了")
                    break
                if time.time() - last_ping > PING_INTERVAL:
                    self.send({"t": "ping"})
                    last_ping = time.time()
                continue
            if not data:
                break                            # 对端关闭了连接
            self._last_recv = time.time()
            for m in reader.feed(data):
                if m.get("t") == "ping":
                    self.send({"t": "pong"})
                elif m.get("t") != "pong":
                    self.peerMessage.emit(m)
        with self._lock:
            try:
                conn.close()
            except Exception:
                pass
            self._conn = None
        self.state = "waiting"
        if not self._stop:
            self.peerGone.emit("对手已断开连接")

    def _broadcast(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        while not self._stop:
            payload = encode({"magic": MAGIC, "ver": VER, "game": self.game,
                              "name": self.name, "port": self.port,
                              "state": self.state})
            for target in ("255.255.255.255", "127.0.0.1"):
                try:
                    s.sendto(payload, (target, DISCOVERY_UDP.get(self.game, 45681)))
                except Exception:
                    pass
            time.sleep(BROADCAST_INTERVAL)
        try:
            s.close()
        except Exception:
            pass

    def stop(self):
        self._stop = True
        self.send({"t": "bye"})
        try:
            if self._conn:
                self._conn.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass


# ------------------------------------------------------------------ 加入方
class _ClientThread(QThread):
    connected = Signal(dict)
    message = Signal(dict)
    gone = Signal(str)
    failed = Signal(str)

    def __init__(self, game, name, addr, port, parent=None):
        super().__init__(parent)
        self.game = game
        self.name = name
        self.addr = addr
        self.port = port
        self._stop = False
        self._conn = None
        self._lock = threading.Lock()
        self._last_recv = time.time()

    def send(self, obj):
        with self._lock:
            if self._conn is None:
                return False
            try:
                self._conn.sendall(encode(obj))
                return True
            except Exception:
                return False

    def run(self):
        try:
            self._run()
        except Exception as exc:          # 兜底：不让线程静默死掉
            self.failed.emit("联机线程出错：%s" % exc)

    def _run(self):
        try:
            conn = socket.create_connection((self.addr, self.port), timeout=6)
        except Exception as exc:
            self.failed.emit("连接不上 %s:%s（%s）" % (self.addr, self.port, exc))
            return
        with self._lock:
            self._conn = conn
        conn.settimeout(0.4)
        try:
            conn.sendall(encode({"t": "hello", "game": self.game, "name": self.name,
                                 "ver": VER}))
        except Exception as exc:
            self.failed.emit("发送握手失败：%s" % exc)
            return
        reader = _LineReader()
        welcome = None
        deadline = time.time() + 6.0
        while welcome is None and time.time() < deadline and not self._stop:
            try:
                data = conn.recv(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            if not data:
                break
            for m in reader.feed(data):
                if m.get("t") == "reject":
                    self.failed.emit(str(m.get("reason") or "对方拒绝了连接"))
                    self._close()
                    return
                if m.get("t") == "welcome":
                    welcome = m
                    break
        if welcome is None:
            self.failed.emit("握手失败，请确认房间还在")
            self._close()
            return
        self._last_recv = time.time()
        self.connected.emit(welcome)
        while not self._stop:
            try:
                data = conn.recv(4096)
            except socket.timeout:
                data = None                      # 超时与对端关闭要区分开
            except OSError:
                break
            if data is None:
                if time.time() - self._last_recv > IDLE_TIMEOUT:
                    self.gone.emit("与房主的连接超时了")
                    break
                if time.time() - self._last_recv > PING_INTERVAL:
                    self.send({"t": "ping"})
                continue
            if not data:
                break                            # 房主关闭了连接
            self._last_recv = time.time()
            for m in reader.feed(data):
                if m.get("t") == "ping":
                    self.send({"t": "pong"})
                elif m.get("t") != "pong":
                    self.message.emit(m)
        self._close()
        if not self._stop:
            self.gone.emit("已与房主断开连接")

    def _close(self):
        with self._lock:
            try:
                if self._conn:
                    self._conn.close()
            except Exception:
                pass
            self._conn = None

    def stop(self):
        self._stop = True
        self.send({"t": "bye"})
        self._close()


# ------------------------------------------------------------------ 房间发现
class _DiscoverThread(QThread):
    rooms = Signal(list)
    failed = Signal(str)

    def __init__(self, game, parent=None):
        super().__init__(parent)
        self.game = game
        self._stop = False

    def run(self):
        try:
            self._run()
        except Exception as exc:          # 兜底：不让线程静默死掉
            self.failed.emit("房间发现出错：%s" % exc)

    def _run(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("", DISCOVERY_UDP.get(self.game, 45681)))
        except OSError as exc:
            self.failed.emit("无法监听房间广播（%s），可手动输入对方 IP" % exc)
            return
        s.settimeout(0.5)
        seen = {}
        while not self._stop:
            try:
                data, addr = s.recvfrom(4096)
            except socket.timeout:
                data = None
            except OSError:
                break
            if data:
                try:
                    m = json.loads(data.decode("utf-8"))
                except Exception:
                    m = None
                if (isinstance(m, dict) and m.get("magic") == MAGIC
                        and m.get("game") == self.game and m.get("port")):
                    seen[addr[0]] = {"ip": addr[0],
                                     "name": str(m.get("name") or "玩家")[:16],
                                     "port": int(m["port"]),
                                     "state": str(m.get("state") or "waiting"),
                                     "t": time.time()}
            now = time.time()
            for k in [k for k, v in seen.items() if now - v["t"] > ROOM_TTL]:
                seen.pop(k, None)
            self.rooms.emit(sorted(seen.values(), key=lambda r: r["ip"]))
        try:
            s.close()
        except Exception:
            pass

    def stop(self):
        self._stop = True


# ------------------------------------------------------------------ 对外统一接口
class LanSession(QObject):
    """一个联机会话：要么当房主，要么加入别人"""

    rooms = Signal(list)
    started = Signal(dict)        # {isHost, seat, port, peer}（房主在有人加入后才发）
    message = Signal(dict)
    closed = Signal(str)
    failed = Signal(str)
    hosting = Signal(dict)        # {port, ip}

    def __init__(self, game, name="玩家", parent=None):
        super().__init__(parent)
        self.game = game
        self.name = name
        self.is_host = False
        self.seat = 0
        self.port = 0
        self.peer = {}
        self.connected = False
        self._host = None
        self._client = None
        self._disc = None
        self._want_first = True

    # -------- 房主
    def start_host(self, want_first=True):
        if self._host is not None or self._client is not None:
            return False, "已经在联机了"
        self._want_first = want_first
        self.seat = 0 if want_first else 1
        try:
            t = _HostThread(self.game, self.name, self.seat)
        except OSError as exc:
            return False, "无法监听端口：%s" % exc
        self._host = t
        self.is_host = True
        self.port = t.port
        t.peerConnected.connect(self._on_peer)
        t.peerMessage.connect(self.message)
        t.peerGone.connect(self._on_gone)
        t.failed.connect(self.failed)
        t.start()
        self.hosting.emit({"port": t.port, "ip": local_ip()})
        return True, ""

    def _on_peer(self, info):
        self.connected = True
        self.peer = info
        self.started.emit({"isHost": True, "seat": self.seat, "port": self.port,
                           "peer": info})

    def _on_gone(self, reason):
        if self.connected:
            self.connected = False
        self.closed.emit(reason)

    # -------- 加入
    def start_join(self, addr, port=None):
        if self._host is not None or self._client is not None:
            return False, "已经在联机了"
        port = int(port or DEFAULT_TCP.get(self.game, 45680))
        self.is_host = False
        t = _ClientThread(self.game, self.name, addr, port)
        self._client = t
        t.connected.connect(self._on_welcome)
        t.message.connect(self.message)
        t.gone.connect(self._on_gone)
        t.failed.connect(self.failed)
        t.start()
        return True, ""

    def _on_welcome(self, msg):
        self.connected = True
        self.seat = int(msg.get("seat") or 0)
        self.peer = msg.get("peer") or {}
        self.started.emit({"isHost": False, "seat": self.seat, "port": 0,
                           "peer": self.peer})

    # -------- 发现
    def start_discover(self):
        if self._disc is not None:
            return
        t = _DiscoverThread(self.game)
        self._disc = t
        t.rooms.connect(self.rooms)
        t.failed.connect(self.failed)
        t.start()

    def stop_discover(self):
        if self._disc is not None:
            self._disc.stop()
            self._disc.wait(800)
            self._disc = None

    # -------- 收发
    def send(self, obj):
        if self._host is not None:
            return self._host.send(obj)
        if self._client is not None:
            return self._client.send(obj)
        return False

    @property
    def active(self):
        return self._host is not None or self._client is not None

    def close(self):
        for t in (self._host, self._client):
            if t is not None:
                try:
                    t.stop()
                    t.wait(1200)
                except Exception:
                    pass
        self.stop_discover()
        self._host = self._client = None
        self.connected = False

    def status_text(self):
        if not self.active:
            return ""
        if not self.connected:
            return "联机 · 等待对手" if self.is_host else "联机 · 连接中…"
        who = "房主" if self.is_host else "加入方"
        return "联机 · %s · %s" % (who, self.peer.get("name", "对手"))
