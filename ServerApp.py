import cgi
import time
import traceback
from urllib.parse import urlparse, parse_qs
import MySQLdb
import secrets
import json
import os
import asyncio
import websockets
import threading
import datetime
import base64
import config
from aiohttp import web


onlineUsers = set()
response_dict = {}


class User:
    def __init__(self, ws, username, access_token):
        self.ws = ws
        self.username = username
        self.access_token = access_token


async def websocket_handler(websocket):
    global onlineUsers

    token = websocket.request.headers.get('access_token')
    user = None
    if token:
        user = get_user_by_token(token)
        if user:
            print(user[1], "Connected.")
            await websocket.send(json.dumps({"type": "alert",
                                             "data": f"You are successfully connected, your site is available on: 'http://{user[1]}.{config.SERVER_DOMAIN}'"}))
            onlineUsers.add(User(websocket, user[1], user[2]))
        async for message in websocket:
            response_json = message
            response = json.loads(response_json)
            response_dict[response["id"]] = response

    if not token or not user:
        await websocket.send(json.dumps({"type": "alert", "data": "You are disconnected!"}))

    # remove user after disconnect
    for user in onlineUsers:
        if user.ws == websocket:
            onlineUsers.remove(user)
            break


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
        host=config.MYSQL_HOST,
        user=config.MYSQL_USERNAME,
        passwd=config.MYSQL_PASSWORD,
        db=config.MYSQL_DB_NAME,
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
    return access_token


async def catch_all(request):
    host = request.headers.get("Host", "")
    print("HostPath: ", f"{host}{request.path}")

    # Serve signup page or handle sign-up logic
    if not host:
        return web.Response(text="<h1> Error, requested page not found </h1>", content_type="text/html")

    elif host.count('.') <= 1:
        if request.method == "GET":
            if request.path == "/":
                signup_html = os.path.join(os.path.dirname(__file__), "signup.html")
                content = file_get_contents(signup_html)
                return web.Response(text=content, content_type="text/html")

            elif "/sign-up" in request.path:
                query_components = parse_qs(urlparse(request.path).query)
                username = query_components.get('username', [''])[0]
                print("Register for", username)
                try:
                    token = add_user(username)
                    return web.Response(text=f"<h1> Successfully created! your token: <br> {token} </h1>", content_type="text/html")
                except Exception as ex:
                    print("Error:", str(type(ex)), str(ex))
                    return web.Response(text="<h1 style='color: red'> Error in user creation :( </h1>", content_type="text/html")

        elif request.method == "POST":
            signup_html = os.path.join(os.path.dirname(__file__), "signup.html")
            content = file_get_contents(signup_html)
            return web.Response(text=content, content_type="text/html")

    else:
        try:
            username = host.split('.')[-3]
            user = get_online_user(username)
        except IndexError:
            return web.Response(text="<h1> Error, requested server not found </h1>", content_type="text/html")

        if user:
            full_request = {
                "headers": dict(request.headers),
                "path": request.path,
                "method": request.method
            }

            # Handle POST body if needed
            if request.method == "POST":
                try:
                    content_type = request.headers.get("Content-Type", "")
                    if "application/x-www-form-urlencoded" in content_type:
                        data = await request.post()
                        full_request["params"] = dict(data)
                    elif "multipart/form-data" in content_type:
                        reader = await request.multipart()
                        params = {}
                        async for part in reader:
                            if part.name:
                                params[part.name] = await part.text()
                        full_request["params"] = params
                except Exception as e:
                    print("Error parsing POST data:", e)
                    full_request["params"] = {}

            rid = secrets.token_hex()
            full_request["id"] = rid
            full_request_json = json.dumps({"type": "request", "data": full_request})

            try:
                await user.ws.send(full_request_json)
                now = datetime.datetime.now()

                # Wait for response with timeout
                for _ in range(50):  # 5 seconds max
                    await asyncio.sleep(0.1)
                    if rid in response_dict:
                        break
                else:
                    raise Exception("Not responding")

                resp_data = response_dict[rid]
                headers = resp_data["headers"]
                body = base64.b64decode(resp_data["content"].encode("ascii"))
                del response_dict[rid]

                return web.Response(
                    status=resp_data["code"],
                    headers=headers,
                    body=body
                )

            except Exception as ex:
                print("Error:", str(type(ex)) + " " + str(ex))
                return web.Response(text=f"<h1> There is a problem in {user.username} </h1>", content_type="text/html")

        else:
            return web.Response(text="<h1> Error, requested server not found </h1>", content_type="text/html")


async def websocket_starter():
    try:
        async with websockets.serve(websocket_handler, "", 8080):
            print("WebSocket server started on port 8080")
            await asyncio.Future()  # Keep the server running forever
    except:
        print(traceback.format_exc())
    

def websocket_thread_handler():
    asyncio.run(websocket_starter())

if __name__ == "__main__":

    threading.Thread(target=websocket_thread_handler).start()
    
    app = web.Application()
    app.router.add_route('*', '/{tail:.*}', catch_all)
    web.run_app(app, host='0.0.0.0', port=80)
    
