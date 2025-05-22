import socket
import threading
import random
import string

class LobbyServer:
    def __init__(self, host='0.0.0.0', port=5555):
        self.host = host
        self.port = port
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)

        self.clients = {}  # username -> {socket, room, status}
        self.rooms = {}    # room_code -> {players: [usernames]}
        self.users = {}    # username -> password
        self.lock = threading.Lock()

    def generate_room_code(self):
        while True:
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            if code not in self.rooms:
                return code

    def handle_client(self, client_socket):
        username = None
        try:
            client_socket.send("Welcome! Use /register <user> <pass> or /login <user> <pass>\n".encode())
            
            # Authentication loop
            while True:
                data = client_socket.recv(1024).decode().strip()
                if not data:
                    return

                if data.startswith('/register'):
                    _, uname, pwd = data.split(maxsplit=2)
                    with self.lock:
                        if uname in self.users:
                            client_socket.send("Username exists.\n".encode())
                        else:
                            self.users[uname] = pwd
                            client_socket.send("Registered successfully! Please /login.\n".encode())

                elif data.startswith('/login'):
                    _, uname, pwd = data.split(maxsplit=2)
                    with self.lock:
                        if self.users.get(uname) == pwd:
                            if uname in self.clients:
                                client_socket.send("Already logged in.\n".encode())
                            else:
                                username = uname
                                self.clients[username] = {'socket': client_socket, 'room': None, 'status': 'online'}
                                client_socket.send(f"Logged in as {username}.\n".encode())
                                break
                        else:
                            client_socket.send("Invalid credentials.\n".encode())

                else:
                    client_socket.send("Invalid command.\n".encode())

            # Main command loop
            while True:
                data = client_socket.recv(1024).decode().strip()
                if not data:
                    break

                if data.startswith('/'):
                    parts = data.split()
                    cmd = parts[0][1:]

                    if cmd == 'create_room':
                        code = self.generate_room_code()
                        with self.lock:
                            self.rooms[code] = {'players': [username]}
                            self.clients[username]['room'] = code
                            self.clients[username]['status'] = 'in game'
                        client_socket.send(f"Room created! Code: {code}\n".encode())
                        self.broadcast_room(code, f"{username} created the room.")

                    elif cmd == 'join_room' and len(parts) > 1:
                        code = parts[1]
                        with self.lock:
                            if code not in self.rooms:
                                client_socket.send("Invalid code.\n".encode())
                                continue

                            prev = self.clients[username]['room']
                            if prev == code:
                                client_socket.send("Already in this room.\n".encode())
                                continue

                            if prev:
                                self.rooms[prev]['players'].remove(username)
                                self.broadcast_room(prev, f"{username} left the room.")
                                if not self.rooms[prev]['players']:
                                    del self.rooms[prev]

                            self.rooms[code]['players'].append(username)
                            self.clients[username]['room'] = code
                            self.clients[username]['status'] = 'in game'

                        client_socket.send(f"Joining room {code}...\n".encode())
                        others = [p for p in self.rooms[code]['players'] if p != username]
                        client_socket.send(f"You have joined the room. {len(others)} other players present.\n".encode())
                        self.broadcast_room(code, f"{username} joined the room.")

                    elif cmd == 'list_rooms':
                        with self.lock:
                            if not self.rooms:
                                client_socket.send("No active rooms.\n".encode())
                            else:
                                room_list = "\n".join([f"{code}: {len(info['players'])} players" for code, info in self.rooms.items()])
                                client_socket.send((room_list + "\n").encode())

                    elif cmd == 'leave_room':
                        with self.lock:
                            room = self.clients[username]['room']
                            if room:
                                self.rooms[room]['players'].remove(username)
                                self.broadcast_room(room, f"{username} left the room.")
                                if not self.rooms[room]['players']:
                                    del self.rooms[room]
                                self.clients[username]['room'] = None
                                self.clients[username]['status'] = 'online'
                                client_socket.send("You left the room.\n".encode())
                            else:
                                client_socket.send("You are not in a room.\n".encode())

                    elif cmd == 'status' and len(parts) > 1:
                        new_status = parts[1]
                        with self.lock:
                            self.clients[username]['status'] = new_status
                        msg = f"[STATUS] {username} is now {new_status}"
                        room = self.clients[username]['room']
                        if room:
                            self.broadcast_room(room, msg)
                        else:
                            self.broadcast_lobby(msg)
                        client_socket.send(f"Status updated: {new_status}\n".encode())

                    elif cmd == 'whois':
                        with self.lock:
                            room = self.clients[username]['room']
                            targets = self.rooms[room]['players'] if room else [u for u in self.clients if not self.clients[u]['room']]
                            info = "\n".join([f"{p} ({self.clients[p]['status']})" for p in targets])
                            client_socket.send(f"Current players:\n{info}\n".encode())

                    elif cmd == 'quit':
                        client_socket.send("Goodbye!\n".encode())
                        break

                    else:
                        client_socket.send("Unknown command.\n".encode())
                else:
                    room = self.clients[username]['room']
                    msg = f"{username}: {data}"
                    if room:
                        self.broadcast_room(room, msg)
                    else:
                        self.broadcast_lobby(msg)

        except Exception as e:
            print(f"[ERROR] {e}")

        finally:
            with self.lock:
                if username and username in self.clients:
                    room = self.clients[username]['room']
                    if room and username in self.rooms.get(room, {}).get('players', []):
                        self.rooms[room]['players'].remove(username)
                        self.broadcast_room(room, f"{username} disconnected.")
                        if not self.rooms[room]['players']:
                            del self.rooms[room]
                    del self.clients[username]
            client_socket.close()

    def broadcast_room(self, code, msg):
        with self.lock:
            if code in self.rooms:
                for player in self.rooms[code]['players']:
                    sock = self.clients[player]['socket']
                    try:
                        sock.send((msg + "\n").encode())
                    except:
                        continue

    def broadcast_lobby(self, msg):
        with self.lock:
            for user, data in self.clients.items():
                if data['room'] is None:
                    try:
                        data['socket'].send((msg + "\n").encode())
                    except:
                        continue

    def start(self):
        print(f"[SERVER] Listening on {self.host}:{self.port}")
        while True:
            client_sock, _ = self.server_socket.accept()
            threading.Thread(target=self.handle_client, args=(client_sock,), daemon=True).start()

if __name__ == "__main__":
    LobbyServer().start()
