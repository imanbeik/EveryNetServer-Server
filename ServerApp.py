from http.server import BaseHTTPRequestHandler, HTTPServer
import MySQLdb
import secrets

MYSQL_HOST = '127.0.0.1'
MYSQL_USERNAME = 'root'
MYSQL_PASSWORD = ''
MYSQL_DB_NAME = 'everynetserver'


class EveryNetServer(BaseHTTPRequestHandler):
    def get_database_connection(self):
        '''connects to the MySQL database and returns the connection'''
        return MySQLdb.connect(
            host=MYSQL_HOST,
            user=MYSQL_USERNAME,
            passwd=MYSQL_PASSWORD,
            db=MYSQL_DB_NAME,
            charset='utf8mb4'
        )

    def create_user_table_if_not_exists(self):
        mydb = self.get_database_connection()
        mycursor = mydb.cursor()
        mycursor.execute(
            f'''create table if not exists users(
                id int primary key auto_increment,
                username varchar(255),
                access_token varchar(255)
                )
            '''
        )

    def get_user(self, username):
        self.create_user_table_if_not_exists()
        # add sample user
        try:
            self.add_user("sara")
        except Exception as ex:
            print(str(type(ex)), str(ex))

        mydb = self.get_database_connection()
        mycursor = mydb.cursor()
        mycursor.execute(f"select * from users where username='{username}'")
        myresult = mycursor.fetchall()
        if myresult:
            return myresult[0]
        else:
            return None

    def add_user(self, username):
        self.create_user_table_if_not_exists()
        access_token = secrets.token_hex()
        mydb = self.get_database_connection()
        mycursor = mydb.cursor()
        mycursor.execute(f"insert into users(username, access_token) values('{username}', '{access_token}')")
        mydb.commit()
        mydb.close()

    def _set_response(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()

    def do_GET(self):
        print("path: ", self.path)
        host = self.headers.get("Host")

        if not host or host.count('.') >= 3:
            self.wfile.write("<h1> Error, requested page not found </h1>".encode("utf-8"))
        elif host.count('.') <= 1:
            self._set_response()
            self.wfile.write("<h1> EveryNetServer Homepage </h1>".encode("utf-8"))

        else:
            username = host.split('.')[0]
            print(username)
            user = self.get_user(username)
            if user:
                # trying to connect user server
                self.wfile.write(f"<h1> Test EveryNetServer server {user[1]} </h1>".encode("utf-8"))
            else:
                self.wfile.write("<h1> Error, requested server not found </h1>".encode("utf-8"))

    def do_POST(self):
        print("path: ", self.path)
        host = self.headers.get("Host")

        if not host or host.count('.') >= 3:
            self.wfile.write("<h1> Error, requested page not found </h1>".encode("utf-8"))
        elif host.count('.') == 1:
            self._set_response()
            self.wfile.write("<h1> EveryNetServer Homepage </h1>".encode("utf-8"))
        else:
            username = host.split('.')[0]
            print(username)
            user = self.get_user(username)
            if user:
                # trying to connect user server
                self.wfile.write(f"<h1> Test EveryNetServer server {user[1]} </h1>".encode("utf-8"))
            else:
                self.wfile.write("<h1> Error, requested server not found </h1>".encode("utf-8"))


if __name__ == "__main__":

    HOST = ''  # 127.0.0.1
    PORT = int(input("Enter Server Port: "))

    server_handler = HTTPServer((HOST, PORT), EveryNetServer)

    try:
        server_handler.serve_forever()
    except KeyboardInterrupt:
        pass

    server_handler.server_close()
    print("Server Stopped")
