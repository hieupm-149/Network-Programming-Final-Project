import socket
import threading
import sys

class LobbyClient:
    def __init__(self, host='26.243.99.186', port=5555):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)         
        try:
            self.sock.connect((host, port))             
            print("[✓] Connected to server.")
        except Exception as e:
            print(f"[✗] Connection failed: {e}")
            sys.exit()
        self.running = True

    def receive(self):                              
        while self.running:
            try:
                data = self.sock.recv(1024).decode()
                if not data:
                    print("Disconnected from server.")
                    break
                print(data, end='')
            except:
                break

    def send(self):                         
        while self.running:             
            try:
                msg = input()
                if msg.strip() == "/quit":
                    self.running = False
                self.sock.send(msg.encode())
            except:
                break

    def start(self):
        threading.Thread(target=self.receive, daemon=True).start()      
        self.send()                                                     
        self.sock.close()

if __name__ == "__main__":
    client = LobbyClient()
    client.start()
