import cgi
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
import MySQLdb
import secrets
import json
import os
import asyncio
import websockets
import threading
import datetime

MYSQL_HOST = '127.0.0.1'
MYSQL_USERNAME = 'root'
MYSQL_PASSWORD = ''
MYSQL_DB_NAME = 'everynetserver'
onlineUsers = set()
response_dict = {}


class User:
    def __init__(self, ws, username, access_token):
        self.ws = ws
        self.username = username
        self.access_token = access_token


async def websocket_handler(websocket, path):
    global onlineUsers

    token = websocket.request_headers.get('access_token')
    user = None
    if token:
        user = get_user_by_token(token)
        if user:
            await websocket.send(json.dumps({"type": "alert",
                                             "data": f"You are successfully connected, your site is available on: 'http://{user[1]}.everynetserver.ga''"}))
            onlineUsers.add(User(websocket, user[1], user[2]))
        async for message in websocket:
            response_json = message
            response = json.loads(response_json)
            response_dict[response[id]] = response

    if not token or not user:
        await websocket.send(json.dumps({"type": "alert", "data": "You are disconnected!"}))

    # remove user after disconnect
    onlineUsers = [user for user in onlineUsers if user.ws != websocket]


def get_online_user(name):
    for user in onlineUsers:
        if user.username == name:
            return user
    return None


def file_get_contents(name):
    with open(name, encoding="utf-8") as f:
        return f.read()


def get_database_connection():
    '''connects to the MySQL database and returns the connection'''
    return MySQLdb.connect(
        host=MYSQL_HOST,
        user=MYSQL_USERNAME,
        passwd=MYSQL_PASSWORD,
        db=MYSQL_DB_NAME,
        charset='utf8mb4'
    )


def create_user_table_if_not_exists():
    mydb = get_database_connection()
    mycursor = mydb.cursor()
    mycursor.execute(
        f'''create table if not exists users(
            id int primary key auto_increment,
            username varchar(255) not null unique,
            access_token varchar(255)
            )
        '''
    )


def get_user(username):
    create_user_table_if_not_exists()
    mydb = get_database_connection()
    mycursor = mydb.cursor()
    mycursor.execute(f"select * from users where username='{username}'")
    myresult = mycursor.fetchall()
    if myresult:
        return myresult[0]
    else:
        return None


def get_user_by_token(token):
    create_user_table_if_not_exists()
    mydb = get_database_connection()
    mycursor = mydb.cursor()
    mycursor.execute(f"select * from users where access_token='{token}'")
    myresult = mycursor.fetchall()
    if myresult:
        return myresult[0]
    else:
        return None


def add_user(username):
    create_user_table_if_not_exists()
    access_token = secrets.token_hex()
    mydb = get_database_connection()
    mycursor = mydb.cursor()
    mycursor.execute(f"insert into users(username, access_token) values('{username}', '{access_token}')")
    mydb.commit()
    mydb.close()


class EveryNetServer(BaseHTTPRequestHandler):

    def _set_response(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()

    def do_GET(self):
        print("path: ", self.path)
        host = self.headers.get("Host")

        if not host:
            self.wfile.write("<h1> Error, requested page not found </h1>".encode("utf-8"))

        elif host.count('.') <= 1:
            if self.path == "/":
                self._set_response()
                signup_html = os.path.dirname(__file__) + "/signup.html"
                self.wfile.write(file_get_contents(signup_html).encode("utf-8"))
            elif "/sign-up" in self.path:
                query_components = parse_qs(urlparse(self.path).query)
                username = query_components['username'][0]
                print(username)
                try:
                    add_user(username)
                    self._set_response()
                    self.wfile.write("<h1> Successfully created! </h1>".encode("utf-8"))
                except Exception as ex:
                    print(str(type(ex)), str(ex))
                    self._set_response()
                    self.wfile.write("<h1 style='color: red'> Error in user creation :( </h1>".encode("utf-8"))
        else:
            username = host.split('.')[-3]
            print(username)
            user = get_online_user(username)
            if user:
                full_request = {}
                headers = {}
                print(str(type(self.headers)))
                for k, v in self.headers.items():
                    headers[k] = v
                full_request["headers"] = headers
                full_request["path"] = self.path
                full_request["method"] = "GET"
                rid = secrets.token_hex()
                full_request["id"] = rid
                full_request_json = json.dumps({"type": "request", "data": full_request})
                try:
                    asyncio.run(user.ws.send(full_request_json))
                    now = datetime.datetime.now()
                    while True:
                        if response_dict.get(rid):
                            break
                        if (datetime.datetime.now() - now).seconds > 2:
                            raise Exception("Not responding")
                    # self.send_response(response_dict[rid]["code"])
                    # for header in response_dict[rid]["headers"]:
                    #     self.send_header(header)
                    # self.end_headers()
                    self._set_response()
                    self.wfile.write(response_dict[rid]["text"])
                    del response_dict[rid]
                except:
                    self.wfile.write(f"<h1> There is a problem in {user.username} </h1>".encode("utf-8"))
            else:
                self.wfile.write("<h1> Error, requested server not found </h1>".encode("utf-8"))

    def do_POST(self):
        print("path: ", self.path)
        host = self.headers.get("Host")

        if not host:
            self.wfile.write("<h1> Error, requested page not found </h1>".encode("utf-8"))
        elif host.count('.') <= 1:
            self._set_response()
            self.wfile.write(file_get_contents("./signup.html").encode("utf-8"))
        else:
            username = host.split('.')[-3]
            print(username)
            user = get_online_user(username)
            if user:
                full_request = {}
                headers = {}
                params = {}
                print(str(type(self.headers)))
                for k, v in self.headers.items():
                    headers[k] = v
                full_request["headers"] = headers
                full_request["path"] = self.path
                full_request["method"] = "POST"

                ctype, pdict = cgi.parse_header(self.headers.get('content-type'))
                if ctype == 'multipart/form-data':
                    params = cgi.parse_multipart(self.rfile, pdict)
                elif ctype == 'application/x-www-form-urlencoded':
                    length = int(self.headers.get('content-length'))
                    params = cgi.parse(self.rfile.read(length))
                full_request["params"] = params
                rid = secrets.token_hex()
                full_request["id"] = rid
                full_request_json = json.dumps({"type": "request", "data": full_request})
                try:
                    asyncio.run(user.ws.send(full_request_json))
                    now = datetime.datetime.now()
                    while True:
                        if response_dict.get(rid):
                            break
                        if (datetime.datetime.now() - now).seconds > 2:
                            raise Exception("Not responding")
                    # self.send_response(response_dict[rid]["code"])
                    # for header in response_dict[rid]["headers"]:
                    #     self.send_header(header)
                    # self.end_headers()
                    self._set_response()
                    self.wfile.write(response_dict[rid]["text"])
                    del response_dict[rid]
                except:
                    self.wfile.write(f"<h1> There is a problem in {user.username} </h1>".encode("utf-8"))

            else:
                self.wfile.write("<h1> Error, requested server not found </h1>".encode("utf-8"))


def start_http():
    server_handler = HTTPServer(('', 80), EveryNetServer)
    try:
        print("HttpServer Started")
        server_handler.serve_forever()
    except KeyboardInterrupt:
        pass

    server_handler.server_close()
    print("Server Stopped")


if __name__ == "__main__":
    threading.Thread(target=start_http).start()
    start_server = websockets.serve(websocket_handler, '', 8924)
    asyncio.get_event_loop().run_until_complete(start_server)
    asyncio.get_event_loop().run_forever()
