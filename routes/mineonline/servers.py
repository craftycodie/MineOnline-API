from flask import Response, request, make_response, abort
import json
from flask_pymongo import PyMongo
from bson.objectid import ObjectId
import hashlib
from uuid import uuid4, UUID
from utils.servers import *
from datetime import datetime, timedelta, timezone
from pymongo import IndexModel, ASCENDING, DESCENDING, errors
import sys
from utils.versions import get_versions
from utils.database import getclassicservers
from uuid import uuid4, UUID
import jwt
import socket
import requests

def register_routes(app, mongo):
    @app.route("/api/servers/<uuid>", methods=["DELETE"])
    def deleteserver(uuid):
        mongo.db.classicservers.delete_one({"uuid": str(UUID(uuid))})
        return Response("ok", 200)

    @app.route("/api/servers/stats", methods=["GET"])
    def serverstats():
        servers = getclassicservers(mongo)
        servercount = len(servers)
        playercount = 0
        for server in servers:
            if "users" in server:
                playercount += int(server["users"])

        return Response(json.dumps({
            "serverCount": servercount,
            "playerCount": playercount
        }))

    @app.route("/api/servers", methods=["POST"])
    def addserver():
        port = request.json['port']
        maxUsers = request.json['max']
        name = request.json['name']
        onlinemode = request.json['onlinemode']
        md5 = request.json['md5']
        whitelisted = request.json['whitelisted']
        uuid = str(uuid4())

        players = []
        if("players" in request.json):
            players = request.json["players"]

        versionName = "Unknown Version"

        if 'ip' in request.json and request.json['ip'] != '':
            connectAddress = request.json['ip'] # new to mineonline to allow classic servers on different IPs
        else:
            connectAddress = request.remote_addr

        if connectAddress == "127.0.0.1":
            return Response("Can't list local servers.", 400)

        ip = socket.gethostbyname(connectAddress) 

        classicservers = mongo.db.classicservers

        if(port == None):
            port = "25565"

        versions = get_versions()

        for version in versions:
            if(version["md5"] == md5 and version["type"] == "server"):
                if('clientName' in version):
                    versionName = version["clientName"]
                elif('clientVersions' in version):
                    versionName = str(version["clientVersions"]).replace("'", "").replace("[", "").replace("]", "")
                else:
                    versionName = version["name"]
            pass

        try:
            # Find an existing salted server
            currentlisting = classicservers.find_one({"port": port, "ip": ip})
            expireDuration = timedelta(minutes = 2)

            # Delete existing server record
            classicservers.delete_many({"port": port, "ip": ip})

            users = request.json['users'] if 'users' in request.json else 0


            try:
                classicservers.insert_one({
                    "salt": currentlisting["salt"] if currentlisting != None and "salt" in currentlisting else None,
                    "createdAt": datetime.utcnow(),
                    "expiresAt": datetime.now(timezone.utc) + expireDuration,
                    "connectAddress": connectAddress,
                    "ip": ip,
                    "port": port,
                    "users": users,
                    "maxUsers": maxUsers,
                    "name": name,
                    "onlinemode": onlinemode,
                    "versionName": versionName,
                    "md5": md5,
                    "whitelisted": whitelisted,
                    "players": players,
                    "uuid": uuid
                })

            except:
                return Response("Something went wrong.", 500)


                        
            return make_response(json.dumps({
                "uuid": uuid
            }), 200)

        except Exception as e:
            return Response("Something went wrong.", 500)

        return Response("Something went wrong.", 500)

    @app.route("/api/servers", methods=["GET"])
    def listservers():
        mineOnlineServers = getclassicservers(mongo)
        featuredServers = list(mongo.db.featuredservers.find())
        featuredServers = [dict(server, **{'isMineOnline': False}) for server in featuredServers]
        servers = mineOnlineServers + featuredServers

        def mapServer(x): 
            if(not"md5" in x):
                return
            if(not "whitelisted" in x):
                return

            if ("public" in x and x["public"] == False):
                return

            return { 
                "createdAt": str(x["createdAt"]) if "createdAt" in x else None,
                "ip": x["connectAddress"] if "connectAddress" in x else x["ip"],
                "connectAddress": x["connectAddress"] if "connectAddress" in x else x["ip"],
                "port": x["port"],
                "users": x["users"] if "users" in x else "0",
                "maxUsers": x["maxUsers"] if "maxUsers" in x else "24",
                "name": x["name"],
                "onlinemode": x["onlinemode"],
                "md5": x["md5"],
                "isMineOnline": x["isMineOnline"] if "isMineOnline" in x else True,
                "players": x["players"] if "players" in x else []
            }

        servers = list(map(mapServer, servers))
        servers = list(filter(filterServer, servers))

        return Response(json.dumps(servers))

    @app.route("/api/getserver", methods=["GET"])
    def getserver():
        serverIP = request.args.get('serverIP')
        serverPort = request.args.get('serverPort')

        if(serverPort == None):
            serverPort = "25565"

        try:
            server = mongo.db.classicservers.find_one({"port": serverPort, "ip": serverIP})
        except:
            pass

        if server == None:
            try:
                server = mongo.db.featuredservers.find_one({"port": serverPort, "ip": serverIP})

                if server == None:
                    server = mongo.db.classicservers.find_one({"connectAddress": serverIP, "port": serverPort})
            except:
                pass

        if server == None:
            return Response("Server not found.", 404)

        if not "name" == server:
            return Response("Server not found.", 404)
        
        def mapServer(x): 
            return { 
                "createdAt": str(x["createdAt"]) if "createdAt" in x else None,
                "connectAddress": x["connectAddress"] if "connectAddress" in x else x["ip"],
                "ip": x["ip"],
                "port": x["port"],
                "users": x["users"] if "users" in x else "0",
                "maxUsers": x["maxUsers"] if "maxUsers" in x else "24",
                "name": x["name"],
                "onlinemode": x["onlinemode"],
                "md5": x["md5"],
                "isMineOnline": x["isMineOnline"] if "isMineOnline" in x else True,
                "players": x["players"] if "players" in x else []
            }

        return Response(json.dumps(mapServer(server)))

    @app.route('/api/servertoken')
    def getmojangmmpass():
        sessionId = request.args['sessionId']
        serverIP = request.args['serverIP']
        serverPort = request.args['serverPort']
        uuid = request.args['uuid']
        username = request.args['username']

        decoded = jwt.decode(sessionId, verify=False)

        if (decoded["spr"] != uuid):
            return Response("Invalid Session", 401)

        valid = requests.post("https://authserver.mojang.com/validate", json={
            "accessToken": sessionId
        })

        if valid.response_code != 200:
            return Response("Invalid Session")

        usernameCheck = requests.get("https://api.mojang.com/users/profiles/minecraft/" + username)
        
        if valid.response_code != 200:
            return Response("Bad username.")

        usernameCheck = json.loads(usernameCheck.content)

        if not "id" in usernameCheck or usernameCheck["id"] != uuid:
            return Response("Bad username.")

        try:
            server = mongo.db.classicservers.find_one({"ip": serverIP, "port": serverPort})
            if server == None:
                server = mongo.db.classicservers.find_one({"connectAddress": serverIP, "port": serverPort})

        except:
            return Response("Server not found.", 404)

        if server:
            if "salt" in server and server['salt'] != None:
                mppass = str(hashlib.md5((server['salt'] + username).encode('utf-8')).hexdigest())
                return Response(mppass)
            else:
                return Response("Classic server not found.", 404)
        else:
            return Response("Server not found.", 404)

        return Response("Something went wrong!", 500)
