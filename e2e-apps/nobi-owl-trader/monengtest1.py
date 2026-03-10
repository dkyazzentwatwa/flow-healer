#from mongoengine import *
import mongoengine as meng
from datetime import datetime

#connect to database

#Class is Collection

class Ohclv(meng.EmbeddedDocument):
    openn = meng.IntField()
    high = meng.IntField()
    low = meng.IntField()
    close = meng.IntField()
    volume = meng.IntField()

class Algo(meng.Document):
    symbol = meng.StringField()
    exchange = meng.StringField()
    tframe = meng.StringField()
    tradeSignal = meng.StringField()
    scoreTotal = meng.IntField()
    time = meng.DateTimeField(default=datetime.utcnow)
    ohclv = meng.DictField(Ohclv)

'''
adding to db
results = Algo(symbol=symbols, exchange=xchangename, tframe=tframe, tradeSignal=tradeSignal, 
    scoreTotal=scoreTotal, ohlcv=ohlcv).save()
print(results.toJson())
resID = results.id
print(resID)

(database) -- nobi
    (collection) -- coin 
        (document) --- results

'''

"""
basic schema
{
    symbol : "BTC/USDT"
    exchange : "binance"
    tframe : "15m"
    tradeSignal : "Uptrend"
    scoreTotal : 12
    time : datetime.datetime
    ohclv {
        openn :
        high : 
        close : 
        low :
        volume :
    }
    algo {
        APO : "+"
        ... : "+"
    }
}


"""
