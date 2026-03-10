import ccxt
import talib as ta
from talib import MA_Type
import numpy as np
import time
from datetime import datetime
import pandas as pd
import mongoengine as meng
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

#NOBIOWL VERSION 0.1 --- 
#PROFESSIONAL AUTOMATED CRYPTOCURRENCY ANALYSIS WEBAPP 
#BY DAVID KYAZZE-NTWATWA 2019

xchange = ""
filename3 = ""

#---GLOBAL VARIABLE BANK#---
scoreTotal = float(0) #global var each algo can add onto, relative to active algo total
tradeSignal = "" #change to tradeTrigger?
tradeTrigger = False
algoStore = [] #current active algorithms
sleeptime = 0 #time asleep inbetween cycles

#for global getOHLCV()
openn = ""
high = ""
low = ""
close  = ""
volume = ""
#Algorithm variables
apoScore = 0 #integer based on algorithm's result, <0 bad, >0 good
apoTrade = "" #string that determines trade signal
aroonScore = 0
aroonTrade = ""
adxScore = 0 #fix
adxTrade = ""
cadScore = 0
cadTrade = ""
cmoScore = 0
cmoTrade = ""
cciScore = 0
cciTrade = ""
demaScore = 0
demaTrade = ""
dmiScore = 0
dmiTrade = ""
emaScore = 0
emaTrade = ""
kamaScore = 0
kamaTrade = ""
kdjScore = 0 #needs test
kdjTrade = ""
macdScore = 0 #needs test
macdTrade = ""
mfiScore = 0
mfiTrade = ""
mesaScore = 0
mesaTrade = ""
momiScore = 0
momiTrade = ""
ppoScore = 0
ppoTrade = ""
rocScore = 0
rocTrade = ""
rsiScore = 0
rsiTrade = ""
sarScore = 0
sarTrade = ""
smaScore = 0 
smaTrade = ""
trimaScore = 0
trimaTrade = ""
trixScore = 0
trixTrade = ""
t3score = 0
t3trade = ""
wmaScore = 0
wmaTrade = ""

class Algo(meng.DynamicDocument): #Class is MongoDB Collection db.algo.find()
    symbol = meng.StringField()
    exchange = meng.StringField()
    tframe = meng.StringField()
    tradeSignal = meng.StringField()
    scoreTotal = meng.IntField()
    high = meng.IntField()
    low = meng.IntField()
    close = meng.IntField()

class Nalgo:
    #operates the library of algos, select active algos, & run multiple algos at once
    def __init__(self, xchangename, symbols, exchangeccxt, tframe):
        #these variables link to the global variables        
        self.symbols = symbols #ABC/DFG..ABC = Base Coin; DFG = Quote Coin
        self.xchangename = xchangename #The ccxt exchange module the bot is running on
        self.xchange = xchange #The ccxt exchange module the bot is running on
        self.exchangeccxt = exchangeccxt #links exchange to ccxt module
        self.tradeSignal = tradeSignal #change to tradeTrigger?
        self.tframe = tframe
        self.sleeptime = sleeptime
        self.algoStore = []
        self.openn = 0
        self.high = 0
        self.low = 0
        self.close = 0
        self.volume = 0
        self.algoStore = algoStore

    def algoStart(self):
        bot = Nalgo(xchangename, symbols, exchangeccxt, tframe)
        print("Current Score Total:", scoreTotal, "TradeSignal:", tradeSignal, " T-Frame:", tframe, "Symbol:", symbols, "Exchange:", xchangename, "TradeTrigger:", tradeTrigger)
        time.sleep(1)
        choice = input(str("Choose operation: 'scan', 'single', 'info', 'tframe', 'symbol', 'ohlcv', 'exchange', 'clear' or 'exit'\n "))
        if choice == 'scan':
            print("Selected (scan)")
            bot.algo_scan()
        elif choice == 'single':
            print("Selected (single)")
            bot.singleAlgo()
        elif choice == 'info':
            print("Selected (info)..")
            bot.currentInfo()
        elif choice == 'test':
            print("Selected (test)")
            bot.ohlcvTest()
        elif choice == 'tframe':
            print("Selected (tframe)")
            bot.tframeChange()
        elif choice == 'symbol':
            print("Selected (symbol)")
            bot.symbolChange()
        elif choice == 'ohlcv':
            print("Selected (ohlcv)")
            bot.quickOHLCV()
        elif choice == 'exchange':
            print("Selected (exchange)")
            bot.newExchange()
        elif choice == 'clear':
            print("Selected (clear scoreTotal)")
            bot.clearScore()
        elif choice == 'exit':
            print("Exiting the Program!")
            exit()
        else:
            print("Incorrect selection, try again!")
            bot.algoStart()
    def algo_info(self):
        print("Listing available Algorithms & basic info")
    def clearScore(self):
        #clears scoreTotal and all algo variables
        global scoreTotal
        print("Clearing the current Algo Score Total")
        scoreTotal = 0
        bot = Nalgo(xchangename, symbols, exchangeccxt, tframe)
        bot.algoStart()
    def currentInfo(self):
        global xchangename
        global symbols
        global tframe
        global scoreTotal
        global algoStore
        print("Exchange:", xchangename, "Symbol:", symbols, "T-Frame:", tframe, "ScoreTotal:", scoreTotal, "Close: ", close[99])
        print("Current algorithms are: ", algoStore)
        bot = Nalgo(xchangename, symbols, exchangeccxt, tframe)
        bot.algoStart()
    def getOHLCV(self, symbols, tframe):
        global openn
        global high
        global low
        global close 
        global volume 
        columns = "time", "O", "H", "L", "C", "V" #"time" removed
        ohlvc = self.exchangeccxt().fetchOHLCV(symbol= symbols, timeframe= str(tframe), limit=100)
        prices_df = pd.DataFrame(ohlvc, columns=columns, dtype=np.float64)
        openn = prices_df["O"]
        high = prices_df["H"]
        low = prices_df["L"]
        close = prices_df["C"]
        volume = prices_df["V"]
        return prices_df
    def newExchange(self):
        #change current exchange 
        global xchangename
        global exchangeccxt 
        xchangename = input(str("Please Enter Exchange Name (lowercase):  "))
        exchangeccxt = getattr(ccxt, xchangename)
        print("The active exchange is now: ", xchangename)
        bot = Nalgo(xchangename, symbols, exchangeccxt, tframe)
        bot.algoStart()
    def ohlcvTest(self):
        """global symbols
        global tframe"""
        global openn
        global high
        global low
        global close 
        global volume 
        columns = "time", "O", "H", "L", "C", "V"
        ohlvc = self.exchangeccxt().fetchOHLCV(symbol= symbols, timeframe= str(tframe), limit=100)
        prices_df = pd.DataFrame(ohlvc, columns=columns, dtype=np.float64)
        openn = prices_df["O"]
        high = prices_df["H"]
        low = prices_df["L"]
        close = prices_df["C"]
        volume = prices_df["V"]
        bot = Nalgo(xchangename, symbols, exchangeccxt, tframe)
        bot.ohlcvCatch()
    def ohlcvCatch(self):
        global openn
        global high
        global low
        global close 
        global volume 
        print("test")
        print(openn[99])
    def quickOHLCV(self):
        global tframe
        limits = input(str("How many rows do you want displayed? 0-100"))
        print("Listing last", limits, " OHLCV points for the tframe: ", tframe)
        columns = "time", "O", "H", "L", "C", "V"
        data = self.exchangeccxt().fetchOHLCV(symbol= symbols, timeframe= str(tframe), limit= int(limits))
        prices_df = pd.DataFrame(data, columns=columns, dtype=np.float64)
        openn = prices_df["O"]
        high = prices_df["H"]
        low = prices_df["L"]
        close = prices_df["C"]
        volume = prices_df["V"]
        today = time.asctime()
        print(prices_df)
        bot = Nalgo(xchangename, symbols, exchangeccxt, tframe)
        bot.algoStart()
    def symbolChange(self):
        global symbols
        global scoreTotal
        print("Current symbol pair is:", symbols)
        symbols = input(str("Please Enter NEW Coin Pair:  ")) #ABC/DFG..ABC = Base Coin; DFG = Quote Coin
        print("New symbol pair is:", symbols)
        scoreTotal = 0 #reset score for next iteration
        bot = Nalgo(xchangename, symbols, exchangeccxt, tframe)
        bot.algoStart()
    def tframeChange(self):
        global tframe
        global sleeptime
        global scoreTotal
        tframe = input(str("Please enter a timeframe for OHLVC data; 30s, 1m, 5m, 15m, 30m, 1h, 2h, 3h, 4h, 1d, 1w, 1m"))
        if tframe == "1m" :
            sleeptime = int(60)
        elif tframe == '30s':
            tframe = "1m"
            sleeptime = int(30)
        elif tframe == "5m" :
            sleeptime = int(300)
        elif tframe == "15m" :
            sleeptime = int(900)
        elif tframe == "30m" :
            sleeptime = int(1800)
        elif tframe == "1h" :
            sleeptime = int(3600)
        elif tframe == "2h" :
            sleeptime = int(7200)
        elif tframe == "3h" :
            sleeptime = int(10800)
        elif tframe == "4h" :
            sleeptime = int(14400)
        elif tframe == "1d" :
            sleeptime == int(86400)
        else:
            pass
        print("New timeframe is now:", tframe)
        scoreTotal = 0
        bot = Nalgo(xchangename, symbols, exchangeccxt, tframe)
        bot.algoStart()
  
    #---Technical Analysis Indicators + Algorithms:
    #Some indicators will have algorithms built from them; other indicators are for confirmation to solidify buy/sell signals
    #The determining factor for a pos/neg trade signal is based upon a unique scoring system produced from all the algorithm's results.
    #----
    def APO(self):
        #Absolute Price Oscillator (APO) // Shows difference between two EMA's,fast/slow periods(10/20day) in an absolute value
        global openn
        global high
        global low
        global close 
        global volume
        global scoreTotal
        global apoScore
        global apoTrade
        global apoNow
        apo = ta.APO(close, fastperiod=10, slowperiod=20, matype=MA_Type.EMA)
        print("APO ALGO...APO = ", apo[99])

        if apo[99] > 0:
            if apo[99] > apo[98]:
                print("APO > 0 + rising - Uptrend")
                apoScore += 1
                scoreTotal += 1
                apoTrade = "Uptrend"
            if apo[99] < apo[98]:
                print("APO > 0, + dropping - Downtrend")
                apoScore += 0.5
                scoreTotal += 0.5
                apoTrade = "Downtrend"
        if apo[99] < 0:
            if apo[99] > apo[98]:
                apoScore += 0.5
                scoreTotal += 0.5
                apoTrade = "APO < 0 + rising - Slight Uptrend"
                print("APO < 0 & is rising. Slight uptrend, still high selling pressure.")
            if apo[99] < apo[98]:
                apoScore -= 1
                scoreTotal -= 1
                apoTrade = "Downtrend"
                print("APO < 0 + falling - strong downtrend!")
        print("APO score is:", apoScore, "APO Trade Signal is:", apoTrade, "Score total is:", scoreTotal)
        apoScore = 0 #Resets score

    def AROON(self):
        #AROON Oscillator // Confirmation indicator
        global openn
        global high
        global low
        global close 
        global volume
        global aroonScore
        global aroonTrade
        global scoreTotal
        aroonosc14 = ta.AROONOSC(openn, low, timeperiod=14)
        print("Current AROON is", aroonosc14[99] )
        if aroonosc14[99] > 0:
            if aroonosc14[99] > aroonosc14[98]:
                print("Aroon Osc. > + rising - uptrend!")
                aroonScore += 1
                aroonTrade = "Uptrend"
                scoreTotal += 1
            if aroonosc14[99] < aroonosc14[98]:
                print("Aroon Osc. > + dropping - downtrend.")
                aroonScore -= 1
                aroonTrade = "Downtrend"
                scoreTotal -= 1
            if aroonosc14[99] == aroonosc14[98]:
                print("Aroon Osc. > 0 -- STALLING -- ")
                aroonScore += 0
                aroonTrade = "Neutral"
                scoreTotal += 0
        if aroonosc14[99] < 0:
            if aroonosc14[99] < aroonosc14[98]:
                print("Aroon Osc. < 0 + dropping - downtrend.")
                aroonScore -= 1
                aroonTrade = "Downtrend"
                scoreTotal -= 1
            if aroonosc14[99] > aroonosc14[98]:
                print("Aroon Osc. < 0 + rising - uptrend!")
                aroonScore += 1
                aroonTrade = "Uptrend"
                scoreTotal += 1
            if aroonosc14[99] == aroonosc14[98]:
                print("Aroon Osc. < 0 -- STALLING -- *HOLD*")
                aroonScore += 0
                aroonTrade = "Neutral"
                scoreTotal += 0
            else:
                pass
            print("AROON score is:", aroonScore, "AROON Trade Signal is:", aroonTrade, "Score total is:", scoreTotal)
            aroonScore = 0

    def ADX(self):
    #AVERAGE directional index(ADX) // *Normally paired with ADXR..
    #Try to create ratio that compares current ADX to mean of past values
        global openn
        global high
        global low
        global close 
        global volume
        global scoreTotal
        global adxScore
        global adxTrade
        adx = ta.ADX(self.high, self.low, self.close, timeperiod=14)
        print("Current ADX is", adx[99] )
        def tradeSignal():
            if adxScore >= 1:
	            tradeAction = True
	            print("Trade signal positive")
            else:
                print("Trade signal negative")
                pass
        if adx[99] > 23:
            if adx[99] > adx[98]:
                print("ADX is rising, uptrend occuring")
            if adx[99] < adx[98]:
                print("ADX is falling, downtrend occurring")
        if adx[99]:
            pass #fix 
        print("ADX score is:", adxScore, "ADX Trade Signal is:", adxTrade, "Score total is:", scoreTotal)
        tradeSignal()
        adxScore = 0        
    def ADXR(self):
    #Average Directional Index Rating // *Normally paired with ADX
        adxr = ta.ADXR(self.high, self.low, self.close, timeperiod=14)
        adx = ta.ADX(self.high, self.low, self.close, timeperiod=14)
        print("Current ADXR is", adxr[99] )

        def tradeSignal():
            if score == 2:
                pass
        if adx[99] > adxr[99]:
            print("ADX > ADXR, trend reversal starting.")
            if adx[99] > adx[98]:
                print("Trend is growing in strength.")
            if adx[99] < adx[98]:
                print("Trend is weakening.")
        if adx[99] < adxr[99]:
            print("ADX < ADXR, trend strength neutral.")
            if adx[99] > adx[98]:
                print("Trend is growing in strength.")
            if adx[99] < adx[98]:
                print("Trend is weakening even.")
            print("AROON score is:", aroonScore)
            print("ADXR Trade Signal is:", aroonTrade)
            tradeSignal()
            print("Score total is:", scoreTotal)

    def ATR(self):
    #Average True Range (ATR)
        atr14 = ta.ATR(self.high, self.low, self.close, timeperiod=14)
        current = atr[99]
        print("Current ATR is", atr[99] )

        def info():
            print("Information about algo") #tooltip info for html
        
        def tradeSignal():
            if score == 2:
                pass

        if atr14[99] > atr14[98]:
            print("ATR is rising, voltilaty is increasing.")
        if atr14[99] < atr14[98]:
            print("ATR is lowering, voltilaty is decreasing.")
        
    def BOLL(self):
    #Bollinger Bandss
        global openn
        global high
        global low
        global close 
        global volume
        upperband, middleband, lowerband = ta.BBANDS(close, timeperiod=20, nbdevup=2, nbdevdn=2, matype=0)
        print("BBANDS - UPPER:", upperband[99], "MID:", middleband[99], "LOW:", lowerband[99])

        def tradeSignal():
            if score == 2:
                pass

    def CAD(self):
    #Chalkin A/D Oscillator (Measures Momentum..aka AD or CAD) - difference between 3day ema A/D & 10day ema A/D
        global cadScore
        global cadTrade
        global scoreTotal
        global openn
        global high
        global low
        global close 
        global volume
        cad = ta.AD(high, low, close, volume)
        print("Current CAD is: ", cad[99])
        def tradeSignal():
            if cadScore >= 1:
	            tradeAction = True
	            print("Trade signal positive")
            else:
                print("Trade signal negative")
                pass

        if cad[99] > 0:
            if cad[99] > cad[98]:
                print("CAD > 0 + rising - Uptrend")
                cadScore += 1
                cadTrade = "Uptrend"
                scoreTotal += 1
            if cad[99] < cad[98]:
                print("CAD > 0 + falling - Downtrend")
                cadScore -= 1
                cadTrade = "Downtrend"
                scoreTotal -= 1
        if cad[99] < 0:
            if cad[99] > cad[98]:
                print("CAD < 0 + rising - Uptrend")
                cadScore += 1
                cadTrade = "Uptrend"
                scoreTotal += 1
            if cad[99] < cad[98]:
                print("CAD < 0 + falling - Downtrend")
                cadScore -= 1
                cadTrade = "Downtrend"
                scoreTotal -= 1
        print("CAD score is:", cadScore, "CAD Trade Signal is:", cadTrade, "Score total is:", scoreTotal)
        tradeSignal()
        cadScore = 0
    def CMO(self):
    #Chande Momentum Oscillator (CMO)// compare to 10day MA
    #if cmo > ma , uptrend. Good to confirm postive trend with mesa,   etc
        global openn
        global high
        global low
        global close 
        global volume
        global scoreTotal
        global cmoScore
        global cmoTrade
        cmo14 =  ta.CMO(close, timeperiod=14)
        print("Current CMO is: " , cmo14[99])
        def tradeSignal():
            if cmoScore >= 1:
	            tradeAction = True
	            print("Trade signal positive")
            else:
                print("Trade signal negative")
                pass        
        if cmo14[99] > 0:
            if cmo14[99] >= 20 and cmo14[99] < 50:
                if cmo14[99] > cmo14[98]:
                    print("CMO > 20 + rising - Uptrend")
                    cmoScore += 1
                    cmoTrade = "Uptrend"
                    scoreTotal += 1
                if cmo14[99] < cmo14[98]:
                    print("CMO > 20 + falling - Downtrend")
                    cmoScore -= 1
                    cmoTrade = "Downtrend"
                    scoreTotal -= 1
            if cmo14[99] >= 50:
                if cmo14[99] > cmo14[98]:
                    print("CMO > 50 + rising - Uptrend")
                    cmoScore += 1
                    cmoTrade = "Uptrend"
                    scoreTotal += 1
                if cmo14[99] < cmo14[98]:
                    print("CMO > 50 + falling - Downtrend")
                    cmoScore -= 1
                    cmoTrade = "Downtrend"
                    scoreTotal -= 1
            if cmo14[99] < 20: 
                if cmo14[99] < cmo14[98]:
                    print("CMO < 20 + falling - Downtrend")
                    cmoScore -= 1
                    cmoTrade = "Downtrend"
                    scoreTotal -= 1
                if cmo14[99] > cmo14[98]:
                    print("CMO > 50 + rising - Uptrend")
                    cmoScore += 0.5
                    cmoTrade = "Uptrend"
                    scoreTotal += 0.5
        if cmo14[99] <= 0 and cmo14[99] >= -49:
            if cmo14[99] > cmo14[98]:
                print("CMO < 0 + rising - Slight Uptrend")
                cmoScore += 0.5
                cmoTrade = "Slight Uptrend"
                scoreTotal += 0.5
            if cmo14[99] < cmo14[98]:
                print("CMO < 0 + falling - Downtrend")
                cmoScore -= 1
                cmoTrade = "Downtrend"
                scoreTotal -= 1
        if cmo14[99] <= -50:
            if cmo14[99] > cmo14[98]:
                print("CMO < -50 + rising - Slight Uptrend")
                cmoScore += 0.5
                cmoTrade = "Slight Uptrend"
                scoreTotal += 0.5
            if cmo14[99] < cmo14[98]:
                print("CMO < -50 + falling - EXTREME Downtrend")
                cmoScore -= 1
                cmoTrade = "Downtrend"
                scoreTotal -= 1
        print("CMO score is:", cmoScore, "CMO Trade Signal is:", cmoTrade, "Score total is:", scoreTotal)
        tradeSignal()
        cmoScore = 0         
    def CCI(self):
        #Commodity Channel Index (CCI) // 
        global openn
        global high
        global low
        global close 
        global volume
        global scoreTotal
        global cciScore
        global cciTrade
        cci14 = ta.CCI(high, low, close, timeperiod=14)
        print("Current CCI is: " , cci14[99])
        def tradeSignal():
            if cadScore >= 1:
	            tradeAction = True
	            print("Trade signal positive")
            else:
                print("Trade signal negative")
                pass

        if cci14[99] > 0:
            if cci14[99] > 0 and cci14[99] < 50:
                if cci14[99] > cci14[98]:
                    print("CCI < 50 + rising - Uptrend")
                    cciScore += 0.5
                    cciTrade = "Uptrend"
                    scoreTotal += 0.5
                if cci14[99] < cci14[98]:
                    print("CCI < 50 + falling - Downtrend")
                    cciScore -= 0.5
                    cciTrade = "Downtrend"
                    scoreTotal -= 0.5
            if cci14[99] < 100 and cci14[99] >= 50:
                if cci14[99] > cci14[98]:
                    print("CCI 50-100 + rising - Uptrend")
                    cciScore += 0.5
                    cciTrade = "Uptrend"
                    scoreTotal += 0.5
                if cci14[99] < cci14[98]:
                    print("CCI 50-100 + falling - Downtrend")
                    cciScore -= 0.5
                    cciTrade = "Downtrend"
                    scoreTotal -= 0.5
            if cci14[99] > 100 and cci14[99] < 200:
                    if cci14[99] > cci14[98]:
                        print("CCI 100-200 + rising - Uptrend")  
                        cciScore += 1
                        cciTrade = "Uptrend"
                        scoreTotal += 1
                    if cci14[99] < cci14[98]:
                        print("CCI 100-200 + falling - Downtrend")  
                        cciScore -= 1
                        cciTrade = "Downtrend"
                        scoreTotal -= 1
            if cci14[99] > 200:
                    if cci14[99] > cci14[98]:
                        print("CCI > 200! + rising - Super Uptrend")  
                        cciScore += 1.5
                        cciTrade = "Uptrend"
                        scoreTotal += 1.5
                    if cci14[99] < cci14[98]:
                        print("CCI > 200 + falling - Downtrend")  
                        cciScore -= 0.5
                        cciTrade = "Downtrend"
                        scoreTotal -= 0.5
        if cci14[99] < 0 and cci14[99] > -100:
            if cci14[99] > cci14[98]:
                print("CCI 0 ~ -100 + rising - Slight Uptrend")
                cciScore -= 0.5
                cciTrade = "Slight Uptrend"
                scoreTotal -= 0.5
            if cci14[99] < cci14[98]:
                print("CCI < -100 + falling - Downtrend")
                cciScore -= 1.0
                cciTrade = "Downtrend"
                scoreTotal -= 1.0
        if cci14[99] <= -100:
            if cci14[99] > cci14[98]:
                print("CCI < -100 + rising - Slight Uptrend")
                cciScore -= 1
                cciTrade = "Slight Uptrend"
                scoreTotal -= 1
            if cci14[99] < cci14[98]:
                print("CCI < -100 + falling - BIG Downtrend")
                cciScore -= 1.5
                cciTrade = "Downtrend"
                scoreTotal -= 1.5
        print("CCI score is:", cciScore, "CCI Trade Signal is:", cciTrade, "Score total is:", scoreTotal)
        tradeSignal()
        cciScore = 0
    def DEMA(self):
    #Double EMA (DEMA) (use with dema 21 vs ema21; 1m/5m for most accuracy)
        global openn
        global high
        global low
        global close 
        global volume
        global scoreTotal
        global demaScore
        global demaTrade
        dema21 = ta.DEMA(close, timeperiod=21)
        dema_ema21 = ta.DEMA(close, timeperiod=21)
        print("Current DEMA is: " , dema21[99], "DEMA/EMA is: ", dema_ema21[99])
        def tradeSignal():
            if demaScore >= 1:
	            tradeAction = True
	            print("Trade signal positive")
            else:
                print("Trade signal negative")
                pass        

        if dema21[99] > dema_ema21[99]:
            if dema21[99] > dema21[98]:
                print("DEMA > EMA + rising - Uptrend")
                demaScore += 1
                demaTrade = "Uptrend"
                scoreTotal += 1
            if dema21[99] < dema21[98]:
                print("DEMA > EMA + falling - Downtrend")
                demaScore -= 1
                demaTrade = "Downtrend"
                scoreTotal -= 1
        if dema21[99] < dema_ema21[99]:
            if dema21[99] > dema21[98]:
                print("DEMA < EMA + rising - Uptrend")
                demaScore += 1
                demaTrade = "Uptrend"
                scoreTotal += 1
            if dema21[99] < dema21[98]:
                print("DEMA < EMA + rising - Uptrend")
                demaScore -= 1
                demaTrade = "Downtrend"
                scoreTotal -= 1
        print("DEMA score is:", demaScore, "DEMA Trade Signal is:", demaTrade, "Score total is:", scoreTotal)
        tradeSignal()
        demaScore = 0
    def DMI(self):
    #Directional Movement Index - DI( + & - ) (Apart of ADX...basically same value)
        global openn
        global high
        global low
        global close 
        global volume
        global scoreTotal
        global dmiScore #the dm+ & dm- combined
        global dmiTrade
        dmi = ta.DX(high, low, close, timeperiod=14)
        minDM = ta.MINUS_DM(high, low, timeperiod=14)
        plusDM = ta.PLUS_DM(high, low, timeperiod=14)
        def tradeSignal():
            if dmiScore >= 1:
	            tradeAction = True
	            print("Trade signal positive")
            else:
                print("Trade signal negative")
                pass        
        print("Current DM(+):", plusDM[99], "DM(-): ",minDM[99], "DMI: ", dmi[99] )
        if plusDM[99] > minDM[99]:
            print("DM(+) > DM(-), uptrend occurring")
            dmiScore += 1
            dmiTrade = "Uptrend"
            scoreTotal -= 1
        if plusDM[99] < minDM[99]:
            print("DM(+) < DM(-), downtrend occurring")
            dmiScore -= 1
            dmiTrade = "Downtrend"
            scoreTotal -= 1
        print("DMI score is:", dmiScore, "DMI Trade Signal is:", dmiTrade, "Score total is:", scoreTotal)
        tradeSignal()
        dmiScore = 0
    def EMA(self):
    #Exponential Moving Average ema7 vs ema99
        global openn
        global high
        global low
        global close 
        global volume
        global scoreTotal
        global emaScore
        global emaTrade
        ema7 = ta.EMA(close, timeperiod=7)
        ema21 = ta.EMA(close, timeperiod=21)
        ema99 = ta.EMA(close, timeperiod=99)
        def tradeSignal():
            if emaScore >= 1:
	            tradeAction = True
	            print("Trade signal positive")
            else:
                print("Trade signal negative")
                pass        
        print("Current  EMA 7, 21, 99 are: ", ema7[99], ema21[99], ema99[99])
        if ema7[99] > ema99[99]:
            if ema7[99] > ema7[98]:
                print("EMA7 > EMA99 + rising - Uptrend")
                emaScore += 1
                emaTrade = "Uptrend"
                scoreTotal += 1
            if ema7[99] < ema7[98]:
                print("EMA7 > EMA99 + falling - Downtrend")
                emaScore -= 1
                emaTrade = "Downtrend"
                scoreTotal -= 1
        if ema7[99] < ema99[99]:
            if ema7[99] > ema7[98]:
                print("EMA7 < EMA99 + Rising - Slight Uptrend")
                emaScore += 0.5
                emaTrade = "Uptrend"
                scoreTotal += 0.5
            if ema7[99] < ema7[98]:
                print("EMA7 < EMA99 + FALLING - Downtrend")
                emaScore -= 1
                emaTrade = "Downtrend"
                scoreTotal -= 1
        print("EMA score is:", emaScore, "EMA Trade Signal is:", emaTrade, "Score total is:", scoreTotal)
        tradeSignal()
        emaScore = 0
    #Keltner Channel Extension
    '''
    Middle Line: 20-day exponential moving average 
    Upper Channel Line: 20-day EMA + (2 x ATR(10))
    Lower Channel Line: 20-day EMA - (2 x ATR(10))
    '''
    def KEL(self):
        global openn
        global high
        global low
        global close 
        global volume
        global scoreTotal
        atr10 = ta.ATR(high, low, close, timeperiod=10)
        midLine = ta.EMA(close, timeperiod=20) #
        upBand = (midLine + (2 * atr10) )
        lowBand = (midLine - (2 * atr10) )

        if lowBand[99] > lowBand[98]:
            pass
        if lowBand[99] > lowBand[98]:
            pass
        print("midLine:", midLine[99], "upper Band: ", upBand[99], "low Band: ", lowBand[99])
    
    def kelBOLL(self):
        #Bollinger Bands for KELTNER CHANNEL, BB(20)
        global openn
        global high
        global low
        global close 
        global volume
        upperband, middleband, lowerband = ta.BBANDS(close, timeperiod=20, nbdevup=2, nbdevdn=2, matype=0)
        print("BBANDS - UPPER:", upperband[99], "MID:", middleband[99], "LOW:", lowerband[99])  
        '''

        def tradeSignal():
            if score == 2:
                pass
        '''
    #KDJ Indicator Extension
    def KDJ(self):
        global openn
        global high
        global low
        global close 
        global volume
        global scoreTotal
        global kdjScore
        global kdjTrade
        slowk, slowd = ta.STOCH(high, low, close, fastk_period=5, slowk_period=3, slowk_matype=0, slowd_period=3, slowd_matype=0)
        J_score = (3 * slowd ) - (2 * slowk )

        print( "slowK: ", slowk[99], "slowD: ", slowd[99], "J: ", J_score[99])
    def OBVOL(self):
    #On Balance self.Volume (OBV)
        global openn
        global high
        global low
        global close 
        global volume
        global scoreTotal
        obv = ta.OBV(close, volume)
        print("Current OBV is: ", obv[99], "OBV 10 periods ago: ", obv[89] )

    def MACD(self):
    #MACD (Moving Average of Convergence / Divergence) Indicator
        global openn
        global high
        global low
        global close 
        global volume
        global scoreTotal
        global macdScore
        global macdTrade
        macd, macdSignal, macdhist = ta.MACD(close, fastperiod=12, slowperiod=26, signalperiod=9)

        def tradeSignal():
            if macdScore >= 1:
	            tradeAction = True
	            print("Trade signal positive")
            else:
                print("Trade signal negative")
                pass        

        print("Current MACD: ", macd[99], "& MACD signal: ", macdSignal[99], "MACD Hist:", macdhist[99])
        #reverse to macdHist > 0 ....etc
        if macd[99] > 0:
            if macd[99] > macdSignal[99]:
                if macdhist[99] > 0:
                    print("Macd > macd signal line & histogram > 0, uptrend occurring...")
                    macdScore += 1
                    macdTrade = "Uptrend"
                    scoreTotal += 1
                if macdhist[99] < 0:
                    print("Macd > macd signal line & histogram < 0, downtrend occurring")
                    macdScore -= 1
                    macdTrade = "Downtrend"
                    scoreTotal -= 1
            if macd[99] < macdSignal[99]:
                if macdhist[99] > 0:
                    print("Macd < macd signal line, downtrend occurring.")
                    macdScore -= 1
                    macdTrade = "Downtrend"
                    scoreTotal -= 0.5
                if macdhist[99] < 0:
                    print("Macd < macd signal line, downtrend occurring.")  
                    macdScore -= 1
                    macdTrade = "Downtrend"
                    scoreTotal -= 1
        if macd[99] < 0:
            if macd[99] > macdSignal[99]:
                    if macdhist[99] > 0:
                        print("Macd > macd signal line, histogram > 0, slight uptrend occurring...BUY!")
                    macdScore -= 0.5
                    macdTrade = "Downtrend"
                    scoreTotal -= 0.5
            if macd[99] < macdSignal[99]:
                if macdhist[99] > 0:
                    print("Macd < macd signal line, downtrend occurring...SELL/DONT BUY!")
                    macdScore -= 1
                    macdTrade = "Downtrend"
                    scoreTotal -= 1
        print("MACD score is:", macdScore, "MACD Trade Signal is:", macdTrade, "Score total is:", scoreTotal)
        tradeSignal()
        macdScore = 0
    def MFI(self):
    #Money Flow Index (MFI)
        global openn
        global high
        global low
        global close 
        global volume
        global scoreTotal
        global mfiScore
        global mfiTrade
        mfi14 = ta.MFI(high, low, close, volume, timeperiod=14)
        print("Current MFI is: ", mfi14[99] )
        if mfi14[99] >= 80:
                if mfi14[99] > mfi14[98]: 
                    print("MFI >= 80 + rising - Uptrend")
                    mfiScore += 1
                    mfiTrade = "Uptrend"
                    scoreTotal += 1
                if mfi14[99] < mfi14[98]: 
                    print("MFI >= 80 + falling - Downtrend")
                    mfiScore -= 1
                    mfiTrade = "Downtrend"
                    scoreTotal -= 1
        if mfi14[99] > 50 and mfi14[99] < 80:
                if mfi14[99] > mfi14[98]: 
                    print("MFI 50-80 + rising - Uptrend")
                    mfiScore += 1
                    mfiTrade = "Uptrend"
                    scoreTotal += 1
                if mfi14[99] < mfi14[98]: 
                    print("MFI 50-80 + falling - Downtrend")
                    mfiScore -= 1
                    mfiTrade = "Downtrend"
                    scoreTotal -= 1
        if mfi14[99] < 50 and mfi14[99] > 20:
                if mfi14[99] > mfi14[98]: 
                    print("MFI 30-50 + rising - Uptrend")
                    mfiScore += 0
                    mfiTrade = "Neutral"
                    scoreTotal += 0
                if mfi14[99] < mfi14[98]: 
                    print("MFI 50-80 + falling - Downtrend")
                    mfiScore -= 0
                    mfiTrade = "Neutral"
                    scoreTotal -= 0
        if mfi14[99] < 20:
                if mfi14[99] > mfi14[98]: 
                    print("MFI < 20 + rising - Slight Uptrend")
                    mfiScore += 0.5
                    mfiTrade = "Uptrend"
                    scoreTotal += 0.5
                if mfi14[99] < mfi14[98]: 
                    print("MFI < 20 + falling - Downtrend")
                    mfiScore -= 1
                    mfiTrade = "Downtrend"
                    scoreTotal -= 1

    def MESA(self):
    #MESA Adaptive moving Average (MAMA+FAMA) Indicator
        global openn
        global high
        global low
        global close 
        global volume
        global scoreTotal
        global mesaScore
        global mesaTrade
        mama, fama = ta.MAMA(close, fastlimit=0.5, slowlimit=0.05)
        print("Current MESA [MAMA / FAMA] is: ", mama[99], " & ", fama[99])
        def tradeSignal():
            if mesaScore >= 1:
	            tradeAction = True
	            print("Trade signal positive")
            else:
                print("Trade signal negative")
                pass        
        if mama[99] > fama[99]:
            if mama[99] > mama[98]:
                print("MAMA > FAMA & + rising - uptrend")
                mesaScore += 1
                mesaTrade = "Uptrend"
                scoreTotal += 1
            if mama[99] < mama[98]:
                print("MAMA < FAMA + falling - slight downtrend")
                mesaScore -= 1
                mesaTrade = "Downtrend"
                scoreTotal -= 1
        if mama[99] < fama[99]:
            if mama[99] > mama[98]:
                print("MAMA < FAMA + rising - downtrend")
                mesaScore += 0.5
                mesaTrade = "Uptrend"
                scoreTotal += 0.5
            if mama[99] < mama[98]:
                print("MAMA < FAMA & + decling - strong downtrend")
                mesaScore -= 0.5
                mesaTrade = "Downtrend"
                scoreTotal -= 0.5
        print("MESA score is:", mesaScore, "MESA Trade Signal is:", mesaTrade, "Score total is:", scoreTotal)
        tradeSignal()
        mesaScore = 0
    def KAMA(self):
    #Kaufman Adaptive Moving Average (KAMA); use against FAMA(MESA)
        global openn
        global high
        global low
        global close 
        global volume
        global scoreTotal
        global kamaScore
        global kamaTrade
        kama30 = ta.KAMA(close, timeperiod=30)
        mama, fama = ta.MAMA(close, fastlimit=0.5, slowlimit=0.05)
        print("Current KAMA & FAMA is: ", kama30[99], " & ", fama[99])
        def tradeSignal():
            if kamaScore >= 1:
	            tradeAction = True
	            print("Trade signal positive")
            else:
                print("Trade signal negative")
                pass        
        if kama30[99] > fama[99]:
            if kama30[99] > kama30[98]:
                print("KAMA > FAMA + rising - Uptrend")
                kamaScore += 1
                kamaTrade ="Uptrend"
                scoreTotal += 1
            if kama30[99] < kama30[98]:
                print("KAMA > FAMA + falling - downtrend")
                kamaScore -= 1
                kamaTrade ="Downtrend"
                scoreTotal -= 1
        if kama30[99] < fama[99]:
            if kama30[99] > kama30[98]:
                print("KAMA < FAMA + rising - Slight Uptrend")
                kamaScore += 0.5
                kamaTrade ="Uptrend"
                scoreTotal += 0.5
            if kama30[99] < kama30[98]:
                print("KAMA > FAMA + falling - downtrend")
                kamaScore -= 0.5
                kamaTrade ="Downtrend"
                scoreTotal -= 0.5
        print("KAMA score is:", kamaScore, "KAMA Trade Signal is:", kamaTrade, "Score total is:", scoreTotal)
        tradeSignal()
        kamaScore = 0
    def MOMI(self):
    #Momentum Indicator (MOM)
        global openn
        global high
        global low
        global close 
        global volume
        global scoreTotal
        global momiScore
        global momiTrade
        mom14 = ta.MOM(close, timeperiod=14)
        print("Current MOM indicator is: ", mom14[99])
        def tradeSignal():
            if momiScore >= 1:
	            tradeAction = True
	            print("Trade signal positive")
            else:
                print("Trade signal negative")
                pass        

        if mom14[99] > 0:
            if mom14[99] > mom14[98]:
                print("MOM > 0 & rising, price uptrend!")
                momiScore += 1
                momiTrade = "Uptrend"
                scoreTotal += 1
            if mom14[99] < mom14[98]:
                print("MOM > 0, but declining, downtrend")
                momiScore += 0.5
                momiTrade = "Downtrend"
                scoreTotal += 0.5
        if mom14[99] < 0:
            if mom14[99] > mom14[98]:
                print("MOM < 0 but rising; slight uptrend")
                momiScore += 0.5
                momiTrade = "Uptrend"
                scoreTotal += 0.5
            if mom14[99] < mom14[98]:
                print("MOM < 0 & declining, downtrend!")
                momiScore -= 0.5
                momiTrade = "Downtrend"
                scoreTotal -= 0.5
        print("MOMI score is:", momiScore, "MOMI Trade Signal is:", momiTrade, "Score total is:", scoreTotal)
        tradeSignal()
        momiScore = 0            
    def PPO(self):
    #Price Percentage Oscillator
        global openn
        global high
        global low
        global close 
        global volume
        global scoreTotal
        global ppoScore
        global ppoTrade
        ppo = ta.PPO(close, fastperiod=12, slowperiod=26, matype=0)
        print("Current PPO is: ", ppo[99])    
        def tradeSignal():
            if ppoScore >= 1:
	            tradeAction = True
	            print("Trade signal positive")
            else:
                print("Trade signal negative")
                pass        
        if ppo[99] > 0:
            if ppo[99] > ppo[98]:
                print("PPO > 0 + rising - uptrend")
                ppoScore += 0.5
                ppoTrade = "Uptrend"
                scoreTotal += 0.5
            if ppo[99] < ppo[98]:
                print("PPO > 0 + declining - downtrend")
                ppoScore -= 0.5
                ppoTrade = "Downtrend"
                scoreTotal -= 0.5
        if ppo[99] < 0:
            if ppo[99] > ppo[98]:
                print("PPO < 0 + rising - uptrend")
                ppoScore += 0.5
                ppoTrade = "Uptrend"
                scoreTotal += 0.5
            if ppo[99] < ppo[98]:
                print("PPO < 0 + declining - downtrend")
                ppoScore -= 1  
                ppoTrade = "Downtrend"
                scoreTotal -= 1
        print("PPO score is:", ppoScore, "PPO Trade Signal is:", ppoTrade, "Score total is:", scoreTotal)
        tradeSignal()
        ppoScore = 0        
    def ROC(self):
    #Price Rate of Change (ROC)
        global openn
        global high
        global low
        global close 
        global volume
        global scoreTotal
        global rocScore
        global rocTrade
        roc14 = ta.ROC(self.close, timeperiod =14)
        print("ROC is: ", roc14[99])
        def tradeSignal():
            if rocScore >= 1:
	            tradeAction = True
	            print("Trade signal positive")
            else:
                print("Trade signal negative")
                pass        
        if roc14[99] > 0: #work on velocity of change
            if roc14[99] > roc14[98]:
                print("ROC > 0 + rising - uptrend")
                rocScore += 0.5
                rocTrade = "Uptrend"
                scoreTotal += 0.5
            if roc14[99] < roc14[98]:
                print("ROC > 0 + declining - downtrend")
                rocScore -= 0.5
                rocTrade = "Downtrend"
                scoreTotal -= 0.5
        if roc14[99] < 0: #work on velocity of change
            if roc14[99] > roc14[98]:
                print("ROC < 0, but rising; uptrend")
                rocScore += 0.5
                rocTrade = "Uptrend"
                scoreTotal += 0.5
            if roc14[99] < roc14[98]:
                print("ROC < 0 & declining, downtrend")
                rocScore -= 0.5
                rocTrade = "Downtrend"
                scoreTotal -= 0.5
        tradeSignal()
        rocScore = 0

    def RSI(self):
    #Relative Strength Indicator (RSI) 50: trend change, 0:50 downtrend, 
        global openn
        global high
        global low
        global close 
        global volume
        global scoreTotal
        global rsiScore
        global rsiTrade
        rsi16 = ta.RSI(close, timeperiod=16)
        print("RSI is: ", rsi16[99])
        def tradeSignal():
            if rsiScore >= 1:
	            print("Trade signal positive")
            else:
                print("Trade signal negative")
                pass        
        if rsi16[99] <= 37: #deciding on rsi 30-38~ for lowpoint
            if rsi16[99] > rsi16[99]:
                print("RSI < 37 + rising - slight uptrend")
                rsiScore += 0.5
                rsiTrade = "Slight Uptrend"
                scoreTotal += 0.5
            if rsi16[99] < rsi16[98]:
                print("RSI < 37 + falling - DOWNTREND")
                rsiScore -= 1
                rsiTrade = "Downtrend" 
                scoreTotal -= 1
        if rsi16[99] >= 38 and rsi16[99] < 50:
            if rsi16[99] > rsi16[99]:
                print("RSI 38-50 + rising - slight uptrend")
                rsiScore += 0.5
                rsiTrade = "Slight Uptrend"
                scoreTotal += 0.5
            if rsi16[99] < rsi16[98]:
                print("RSI 38-50 + falling - downtrend")
                rsiScore -= 0.5
                rsiTrade = "Downtrend"     
                scoreTotal -= 0.5         
        if rsi16[99] >= 50 and rsi16[99] < 70:
            if rsi16[99] > rsi16[99]:
                print("RSI 50-70 + rising - uptrend")
                rsiScore += 1
                rsiTrade = "Uptrend"
                scoreTotal += 1
            if rsi16[99] < rsi16[98]:
                print("RSI 50-70 + falling - downtrend")
                rsiScore -= 0.5
                rsiTrade = "Downtrend"  
                scoreTotal -= 0.5            
        if rsi16[99] >= 70:
            print("RSI is > 70, extremely overbought!")
            if rsi16[99] > rsi16[99]:
                print("RSI > 70 + rising - uptrend")
                rsiScore += 1
                rsiTrade = "Uptrend"
                scoreTotal += 1
            if rsi16[99] < rsi16[98]:
                print("RSI > 70 + falling - downtrend")
                rsiScore -= 1
                rsiTrade = "Downtrend" 
                scoreTotal -= 1           
        print("RSI score is:", rsiScore, "RSI Trade Signal is:", rsiTrade, "Score total is:", scoreTotal)
        tradeSignal()
        rsiScore = 0
    def SAR(self):
        #Parabolic SAR
        global openn
        global high
        global low
        global close 
        global volume
        global scoreTotal
        global sarScore
        global sarTrade
        psar = ta.SAR(high, low, acceleration=0.02, maximum=0.2)
        print("SAR is: ", psar[99] )
        def tradeSignal():
            if sarScore >= 1:
	            tradeAction = True
	            print("Trade signal positive")
            else:
                print("Trade signal negative")
                pass        
        if psar[99] < high[99]:
            if psar[99] > psar[98]:
                print("SAR < High + Rising - Uptrend")
                sarScore += 1
                sarTrade = "SAR < High"
                scoreTotal += 1
            if psar[99] < psar[98]:
                print("SAR < High + Falling - Downtrend")
                sarScore -= 1
                sarTrade = "SAR < High"
                scoreTotal -= 1
        if psar[99] > high[99]:
            if psar[99] > psar[98]:
                print("SAR > High + Rising - Uptrend")
                sarScore += 1
                sarTrade = "SAR < High"
                scoreTotal += 1
            if psar[99] < psar[98]:
                print("SAR > High + Falling - Downtrend")
                sarScore -= 1
                sarTrade = "SAR < High"
                scoreTotal -= 1
        print("SAR score is:", sarScore, " - SAR Trade Signal is:", sarTrade, " - Score total is:", scoreTotal)
        tradeSignal()
        sarScore = 0
    def SMA(self):
    #Small Moving Average
        global openn
        global high
        global low
        global close 
        global volume
        global scoreTotal
        global smaScore #value that determines up/downtrend
        global smaTrade #str for buy/sell/hold signal
        sma7 = ta.SMA(close, timeperiod=7)
        sma99 = ta.SMA(close, timeperiod=99)
        print("Current SMA 7d & 99d is: ", sma7[99], " & ", sma99[99] )
        def tradeSignal():
            if smaScore >= 1:
	            tradeAction = True
	            print("Trade signal positive")
            else:
                print("Trade signal negative")
                pass        
        if sma7[99] > sma99[99]:
            if sma7[99] > sma7[98]:
                print("SMA7 > SMA99 + rising - uptrend" )
                smaScore += 1
                smaTrade = "Uptrend"
                scoreTotal += 1
            if sma7[99] < sma7[98]:
                print("SMA7 > SMA99 + falling - downtrend" )
                smaScore -= 1
                smaTrade = "Downtrend"
                scoreTotal -= 1
        if sma7[99] < sma99[99]:
            if sma7[99] > sma7[98]:
                print("SMA7 < SMA99 + rising - uptrend" )
                smaScore += 0.5
                smaTrade = "Uptrend"
                scoreTotal += 0.5
            if sma7[99] < sma7[98]:
                print("SMA7 < SMA99 + falling - downtrend" )
                smaScore -= 1
                smaTrade = "Downtrend"
                scoreTotal -= 1
        print("SMA score is:", smaScore, "SMA Trade Signal is:", smaTrade, "Score total is:", scoreTotal)
        tradeSignal()
        smaScore = 0
    def STOCH(self):
    #STOCH
        slowk, slowd = ta.STOCH(self.high, self.low, self.close, fastk_period=5, slowk_period=3, slowk_matype=0, slowd_period=3, slowd_matype=0)
        pass

    def TRIMA(self):
        #Triangular Moving Average (trima or tema) - Use with TRIMA vs EMA & TRIMA vs FAMA (more accurate?)
        global openn
        global high
        global low
        global close 
        global volume
        global scoreTotal
        global trimaScore
        global trimaTrade
        trima25 = ta.TRIMA(close, timeperiod=25)
        ema_T = ta.EMA(close, timeperiod=25)
        mama, fama = ta.MAMA(close, fastlimit=0.5, slowlimit=0.05)
        print("Current TRIMA(25):", trima25[99], "EMA(trima):", ema_T[99], "FAMA: ", fama[99])
        def tradeSignal():
            if trimaScore >= 1:
	            tradeAction = True
	            print("Trade signal positive")
            else:
                print("Trade signal negative")
                pass        

        if trima25[99] > ema_T[99]:
            if trima25[99] > trima25[98]:
                print("TRIMA > EMA + rising - Uptrend")
                trimaScore += 1
                trimaTrade = "Uptrend"
                scoreTotal += 1
            if trima25[99] < trima25[98]:
                print("TRIMA > EMA + Falling - Downtrend")
                trimaScore -= 1
                trimaTrade = "Downtrend"
                scoreTotal -= 1
        if trima25[99] < ema_T[99]:
            if trima25[99] > trima25[98]:
                print("TRIMA < EMA + Rising - Uptrend")
                trimaScore += 1
                trimaTrade = "Uptrend"
                scoreTotal += 1
            if trima25[99] < trima25[98]:
                print("TRIMA < EMA + Falling - Downtrend")
                trimaScore -= 1
                trimaTrade = "Downtrend"
                scoreTotal -= 1
        if trima25[99] > fama[99]:
            if trima25[99] > trima25[98]:
                print("TRIMA > FAMA + Rising - Uptrend")
                trimaScore += 1
                trimaTrade = "Uptrend"
                scoreTotal -= 1
            if trima25[99] < trima25[98]:
                print("TRIMA < FAMA + Falling - Downtrend")
                trimaScore -= 1
                trimaTrade = "Downtrend"
                scoreTotal -= 1
        if trima25[99] < fama[99]:
            if trima25[99] > trima25[98]:
                print("TRIMA < FAMA + Rising - Uptrend")
                trimaScore += 1
                trimaTrade = "Uptrend"
                scoreTotal += 1
            if trima25[99] < trima25[98]:
                print("TRIMA < FAMA + Falling - Downtrend")
                trimaScore -= 1
                trimaTrade = "Downtrend"
                scoreTotal -= 1
        print("TRIMA score is:", trimaScore, "TRIMA Trade Signal is:", trimaTrade, "Score total is:", scoreTotal)
        tradeSignal()
        trimaScore = 0        
    def TRIX(self):
    #Triple Exponential Average Indicator (TRIX)
        global openn
        global high
        global low
        global close 
        global volume
        global scoreTotal
        global trixScore
        global trixTrade
        trix9 = ta.TRIX(close, timeperiod=9)
        ema_trix = ta.EMA(trix9, timeperiod=9)
        print("Current TRIX is", trix9[99], "and ema_trix is: ", ema_trix[99], "*")
        def tradeSignal():
            if trixScore >= 1:
	            tradeAction = True
	            print("Trade signal positive")
            else:
                print("Trade signal negative")
                pass        
        if trix9[99] > 0:
            if trix9[99] > ema_trix[99]:
                if trix9[99] > trix9[98]:
                    print("TRIX > EMA + > 0 - Rising - Big Uptrend")
                    trixScore += 1
                    trixTrade = "Uptrend"
                    scoreTotal += 1
                if trix9[99] < trix9[98]:
                    print("TRIX > EMA + > 0 - Falling - Slight Downtrend")
                    trixScore -= 1
                    trixTrade = "Downtrend"
                    scoreTotal -= 1
            if trix9[99] < ema_trix[99]:
                if trix9[99] > trix9[98]:
                    print("TRIX < EMA + > 0 - Rising - Uptrend")
                    trixScore += 1
                    trixTrade = "Uptrend"
                    scoreTotal += 1
                if trix9[99] < trix9[98]:
                    print("TRIX < EMA + > 0 - Falling - Downtrend")
                    trixScore -= 1
                    trixTrade = "Downtrend"
                    scoreTotal -= 1
        if trix9[99] < 0:
            if trix9[99] > ema_trix[99]:
                if trix9[99] > trix9[98]:
                    print("TRIX > EMA + < 0 - Rising - Uptrend")
                    trixScore += 1
                    trixTrade = "Uptrend"
                    scoreTotal += 1
                if trix9[99] < trix9[98]:
                    trixScore -= 1
                    trixTrade = "Downtrend"
                    scoreTotal -= 1
            if trix9[99] < ema_trix[99]:
                if trix9[99] > trix9[98]:
                    print("TRIX > EMA + < 0 - Rising - Slight Uptrend")
                    trixScore += 1
                    trixTrade = "Uptrend"
                    scoreTotal += 1
                if trix9[99] < trix9[98]:
                    print("TRIX > EMA + < 0 - Falling - Big Downtrend")
                    trixScore -= 1
                    trixTrade = "Downtrend"
                    scoreTotal -= 1
        print("TRIX score is:", trixScore, "TRIX Trade Signal is:", trixTrade, "Score total is:", scoreTotal)
        tradeSignal()
        trixScore = 0
    def T3(self):
    #T3 - Triple Exponential Moving Average (Use with FAMA (from MESA indicator))
        global openn
        global high
        global low
        global close 
        global volume
        global scoreTotal
        global t3score
        global t3trade
        t3 = ta.T3(close, timeperiod=5, vfactor=0.7)
        mama, fama = ta.MAMA(close, fastlimit=0.5, slowlimit=0.05)
        print("Current T3:", t3[99], "FAMA: ", fama[99])
        def tradeSignal():
            if t3score >= 1:
	            tradeAction = True
	            print("Trade signal positive")
            else:
                print("Trade signal negative")
                pass        
        if t3[99] > fama[99]:
            if t3[99] > t3[98]:
                print("T3 > FAMA + rising - Uptrend")
                t3score += 1
                t3trade = "Uptrend"
                scoreTotal += 1
            if t3[99] < t3[98]:
                print("T3 > FAMA + falling - Slight Downtrend")
                t3score -= 1
                t3trade = "Downtrend"
                scoreTotal -= 1
        if t3[99] < fama[99]:
            if t3[99] > t3[98]:
                print("T3 < FAMA + rising - Uptrend")
                t3score += 0.5
                t3trade = "Uptrend"
                scoreTotal += 0.5
            if t3[99] < t3[98]:
                print("T3 < FAMA + falling - Downtrend")
                t3score -= 1
                t3trade = "Downtrend"
                scoreTotal -= 1
        print("T3 score is:", t3score, "T3 Trade Signal is:", t3trade, "Score total is:", scoreTotal)
        tradeSignal()
        t3score = 0
    def WMA(self):
    #Weighted Moving Average (WMA) wma vs FAMA line
        global openn
        global high
        global low
        global close 
        global volume
        global scoreTotal
        global wmaScore
        global wmaTrade
        wma9 = ta.WMA(close, timeperiod=9)
        mama, fama = ta.MAMA(close, fastlimit=0.5, slowlimit=0.05)
        print("Current WMA:", wma[99], "FAMA: ", fama[99])  
        def tradeSignal():
            if wmaScore >= 1:
	            tradeAction = True
	            print("Trade signal positive")
            else:
                print("Trade signal negative")
                pass        

        if wma9[99] > fama[99]:
            if wma9[99] > wma9[98]:
                print("WMA > FAMA + rising - Uptrend")
                wmaScore += 0.5
                wmaTrade = "Uptrend"
                scoreTotal += 0.5
            if wma9[99] < wma9[98]:
                print("WMA > FAMA + falling - Slight Downtrend")
                wmaScore -= 0.5
                wmaTrade = "Downtrend"
                scoreTotal -= 0.5
        if wma9[99] < fama[99]:
            if wma9[99] > wma9[98]:
                print("WMA < FAMA + rising - Uptrend")
                wmaScore += 0.5
                wmaTrade = "Uptrend"
                scoreTotal += 0.5
            if wma9[99] < wma9[98]:
                print("WMA < FAMA + falling - Slight Downtrend")
                wmaScore -= 0.5
                wmaTrade = "Downtrend"
                scoreTotal -= 0.5
        print("WMA score is:", wmaScore, "WMA Trade Signal is:", wmaTrade, "Score total is:", scoreTotal)
        tradeSignal()
        wmaScore = 0

    def singleAlgo(self):
        #Used to test a single algorithm
        global algoStore 
        global scoreTotal
        global tradeSignal
        global openn
        global high
        global low
        global close 
        global volume 
        bot = Nalgo(xchangename, symbols, exchangeccxt, tframe)
        bot.getOHLCV(self.symbols, self.tframe)
        print("Cycling through 1 algo...")
        self.algoStore = [bot.DMI()] #manually add active algos
        if scoreTotal > 13:
            tradeSignal = "Uptrend"
        elif scoreTotal > 5 and scoreTotal < 12:
            tradeSignal = "Hold"
        elif scoreTotal < 5:
                tradeSignal = "Downtrend"
        else:
            pass
        print("Iteration complete, scoreTotal =", scoreTotal, "Trade Signal:", tradeSignal)
        bot.algoStart()

    def algo_scan(self): 
        #this is used for the analysis function
        global algoStore 
        global scoreTotal
        global tradeSignal
        global tradeTrigger
        global openn
        global high
        global low
        global close 
        global volume 
        global sleeptime
        global filename3
        global scoreTotal
        global symbol
        global xchangename
        scoreTotal = 0 #reset score for next iteration
        bot = Nalgo(xchangename, symbols, exchangeccxt, tframe)
        nowTime = time.asctime().replace(" ", "")
        #file naming & restructuring
        fileName = "SCAN-" + self.xchangename + "-" + self.symbols + "-" + tframe + "-" + nowTime + ".csv" #unique file name
        #for JSON storage
        """jsonName = "SCAN-" + self.xchangename + "-" + self.symbols + "-" + tframe + "-" + nowTime + ".JSON" #unique file name
        jsonName2 = jsonName.replace("/", "")
        jsonName3 = jsonName2.replace(":", "")"""
        filename2 = fileName.replace("/", "")
        filename3 = filename2.replace(":", "")
        cycle = input(str("Enter number of cycles for analysis ticker (timeframe * cycles): "))
        print("Running ticker for ", cycle, "cycles, with the interval of,", tframe, "---CTRL+C TO EXIT")
        time.sleep(1)
        #creating mongoDB collection db.algo.find()
        class Algo(meng.Document):
            symbol = meng.StringField()
            exchange = meng.StringField()
            tframe = meng.StringField()
            tradeSignal = meng.StringField()
            tradeTrigger = meng.StringField()
            scoreTotal = meng.FloatField()
            high = meng.FloatField()
            low = meng.FloatField()
            close = meng.FloatField()
            currentTime = meng.StringField()
            timeName = meng.StringField()
        try:
            for i in range(int(cycle)): 
                print("Run #", [i], "***ANALYSIS OF ", self.xchangename, "...", self.symbols, "****")
                theTime = time.asctime()
                timedName = "CurrentTime"
                scoreTotal = 0 #reset score for next iteration
                print("Cycling through active algos...")
                nowTime = time.asctime().replace(" ", "")
                bot.getOHLCV(self.symbols, self.tframe)
                self.algoStore = [bot.APO(), bot.AROON(), bot.CAD(), bot.CMO(), bot.CCI(), bot.DEMA(), bot.EMA(), bot.MACD(), bot.MFI(), bot.MESA(), bot.KAMA(), bot.MOMI(), bot.PPO(), bot.RSI(), bot.SAR(), bot.SMA(), bot.TRIMA(), bot.TRIX(), bot.T3()] #manually add active algos
                if scoreTotal >= 7:
                    tradeSignal = "Uptrend"
                    tradeTrigger = True
                    #bot = Nalgo(xchangename, symbols, exchangeccxt, tframe)
                    #bot.trade or bot.tradeTest
                elif scoreTotal >= 3 and scoreTotal < 6.5:
                    tradeSignal = "Neutral"
                    tradeTrigger = False
                elif scoreTotal < 3 and scoreTotal > 0:
                    tradeSignal = "Downtrend"
                    tradeTrigger = False
                elif scoreTotal <= 0 :
                    tradeSignal = "Downtrend"
                    tradeTrigger = False
                else:
                    pass
                #Add to mongoDB here
                time.sleep(1)     
                if Algo.objects(exchange=self.xchangename, symbol=self.symbols).count() > 0: #checks if there are documents for current symbol & exchange
                    update1 = Algo.objects(symbol=self.symbols, exchange=self.xchangename)
                    update1.update(set__tframe=self.tframe, set__tradeSignal=tradeSignal, set__tradeTrigger=str(tradeTrigger), set__scoreTotal=float(scoreTotal), set__high=high[99], set__low=low[99], set__close=float(close[99]))
                    timeUpdate = Algo.objects(timeName=timedName)
                    timeUpdate.update(set__currentTime=theTime)
                    print("Updating old documents for ", self.symbols , "on", self.xchangename)
                else:
                    results = Algo(symbol=self.symbols, exchange=self.xchangename, tframe=self.tframe, tradeSignal=tradeSignal, scoreTotal=scoreTotal, high=high[99], low=low[99], close=close[99])
                    results.save()
                    timeUpdate = Algo.objects(timeName=timedName)
                    timeUpdate.update(set__currentTime=theTime)
                    print("Created new document for ", self.symbols , "on", self.xchangename)
                    pass
                
                #MONGODB Entry
                '''
                update1 = Algo.objects(symbol=self.symbols, exchange=self.xchangename)
                update1.update(set__tframe=self.tframe, set__tradeSignal=tradeSignal, set__tradeTrigger=str(tradeTrigger), set__scoreTotal=float(scoreTotal), set__high=high[99], set__low=low[99], set__close=float(close[99]))
                timeUpdate = Algo.objects(timeName=timedName)
                timeUpdate.update(set__currentTime=theTime)
                #timeUpdate.reload()
                #results2 = Algo(symbol=self.symbols, exchange=self.xchangename, tframe=self.tframe, tradeSignal=tradeSignal, tradeTrigger=str(tradeTrigger), scoreTotal=float(scoreTotal), high=high[99], low=low[99], close=float(close[99]))
                #results2.save()
                #timeResult = Algo(currentTime=theTime, timeName=timedName )
                #timeResult.save()
                print("Document saved to MongoDB database!")
                '''
                time.sleep(3)
                print(Algo.objects.count())
                
                #console summary in JSON format
                data = {
                    'symbol' : self.symbols,
                    'exchange' : self.xchangename,
                    'tframe' : self.tframe,
                    'tradeSignal' : tradeSignal,
                    'tradeTrigger' : tradeTrigger,
                    'scoreTotal' : float(scoreTotal),
                    'time' : nowTime,
                    'close' : float(close[99]),
                }
                columns = ["symbol", "exchange", "tframe", "tradeSignal", "tradeTrigger", "scoreTotal", "time", "close"]
                scan_df = pd.DataFrame(data, index= [i], columns=columns)
                scan_df.to_csv(filename3, mode= "a", header=True)
                #for json
                #scan_df.to_json(path_or_buf= jsonName3, orient='records') #saves to json file.
                print("Iteration complete", data)
                print("Next analysis will be in ", self.sleeptime , "seconds")
                time.sleep(self.sleeptime)
        except ccxt.NetworkError as e:
            print('network error:', str(e))
            bot.algoStart()
        except ccxt.ExchangeError as e:
            print('exchange error:', str(e))
            bot.algoStart()
        except Exception as e:
            print('failed with:', str(e))
        except KeyboardInterrupt:
            print("Loop exited! Returning to Initialization")
            bot.algoStart()
        bot.algoStart()
        #bot.logData(xchangename, symbols, tframe, scoreTotal, trend, tradeSignal, openn, high, low, close, volume)

if __name__ == '__main__':
    #run as script starts
    print("Running nalgoV2!")
    pd.set_option('display.max_columns', None)
    pd.set_option('display.max_rows', None)
    xchangename = input(str("Please Enter Exchange Name (lowercase): \n"))
    exchangeccxt = getattr(ccxt, xchangename) #add exchange to ccxt module
    symbols = input(str("Please Enter Coin Pair:  \n")) #ABC/DFG..ABC = Base Coin; DFG = Quote Coin
    tframe = input(str("Please enter a timeframe for OHLVC data; 30s, 1m, 5m, 15m, 30m, 1h, 2h, 3h, 4h, 1d, 1w, 1m  \n"))
    if tframe == "1m" :
        sleeptime = int(60) 
    elif tframe == "30s":
        tframe = "1m"
        sleeptime = int(30)
    elif tframe == "5m" :
        sleeptime = int(300)
    elif tframe == "15m" :
        sleeptime = int(900)
    elif tframe == "30m" :
        sleeptime = int(1800)
    elif tframe == "1h" :
        sleeptime = int(3600)
    elif tframe == "2h" :
        sleeptime = int(7200)
    elif tframe == "3h" :
        sleeptime = int(10800)
    elif tframe == "4h" :
        sleeptime = int(14400)
    elif tframe == "1d" :
        sleeptime == int(86400)
    else:
        pass
    #---Connect to database---#
    mongodb_uri = os.getenv('MONGODB_URI')
    dbname = os.getenv('MONGODB_DB_NAME', 'nobi')
    if mongodb_uri:
        meng.connect(host=mongodb_uri)
        print(f"Connected to MongoDB database: {dbname}")
    else:
        print("Warning: MONGODB_URI not set. Database features disabled.")
    time.sleep(8)
    print("connected to" ,dbname, "database!")
    bot = Nalgo(xchangename, symbols, exchangeccxt, tframe)
    print("Starting Analysis Bot...")
    bot.algoStart()
else:
    print("Starting Bot as import...")
    pass




#EXTRA


"""
#from sklearn.linear_model import LinearRegression

    def squeeze(self):
        global openn
        global high
        global low
        global close 
        global volume
        
        max1 = max(high[:19])
        min1 = min(low[:19])
        sma1 = ta.SMA(close, timeframe=20)
        #Linear

        linReg = ta.LINEARREG(close, timeperiod=14)
        #squeezey = linReg * (close - stat.mean ( stat.mean ( max ( high, 20), min(low, 20) ), sma1 ), 20, 0 ) 

        squeezeTrigger = False
        if (lowerBB > lowerKC) and (upperBB < upperKC):
            squeezeTrigger = True
        else:
            squeezeTrigger = False
        return squeezeTrigger
"""
'''
adding to db
results = Algo(symbol=symbols, exchange=xchangename, tframe=tframe, tradeSignal=tradeSignal, 
    scoreTotal=scoreTotal, ohlcv=ohlcv).save()
print(results.toJson())
resID = results.id
print(resID)

(database) -- nobi
    (collection) -- algo 
        (document) --- results

'''

"""with open(fileName, 'w') as f: #create variable for unique file name
    scan_df.to_csv(f, header=True)"""