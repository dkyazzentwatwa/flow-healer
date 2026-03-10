import mongoengine as meng
from datetime import datetime

#connect to database
meng.connect('testdb')

#Class is Collection

class User(meng.Document)