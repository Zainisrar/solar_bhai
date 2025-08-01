from pymongo import MongoClient

from pymongo import MongoClient
import certifi
uri = "mongodb+srv://zainisrar2003:CpDEQVfGQbPGhlbs@cluster0in.0xctwds.mongodb.net/"

client = MongoClient(uri, tlsCAFile=certifi.where())
print(client.list_database_names())
