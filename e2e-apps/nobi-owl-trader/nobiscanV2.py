#NobiScan Version .01
import ccxt
import bs4 as bs
import numpy as np
import pandas as pd
import time
import datetime
import talib as ta
from talib import MA_Type
#import nalgoV2 as ngo
from nalgoV2 import algo_run


"""NOBISCAN TEST VERSION 2.0
ver 2.0 is more slimmed down and lets Nalgo do most of the work
PROFESSIONAL AUTOMATED CRYPTOCURRENCY TECHNICAL ANALYSIS BOT 
BY DAVID KYAZZE-NTWATWA 2019
Exchanges Available (12): gemini, livecoin, btcalpha, binance, gdax, kkex, okcoinusd, uex, poloniex, 
coinexchange, coinbasepro, bibox (beaxy later?)
Work on: logging(select path for file, to txt, , exporting to website,
Global Variables / user inputs """

print("NobiScan Has Been Started...")  
xchangename = input(str("Please Enter Exchange Name:  "))
exchangeccxt = getattr(ccxt, xchangename)
symbol = input(str("Please Enter Coin Pair:  ")) #ABC/DFG..ABC = Base Coin; DFG = Quote Coin
#ALGO GLOBAL VARIABLE BANK (flows into index.html dashboard)
scoreTotal = 0 #global var each algo can add onto
tradeSignal = ""
trend = "" #global var for uptrend(buy)/downtrend(sell)/neutral(hold)
nowTime = ""
openn = ""
high = ""
low = ""
close  = ""
volume = ""

# algoScore = overall score for indv. algo, algoTrade = buy/sell signal for algo
apoScore = 0
apoTrade = ""
aroonScore = 0
aroonTrade = ""
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
#kdjScore = 0 #needs test
#kdjTrade = ""
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
#rocScore = 0
#rocTrade = ""
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
t3Trade = ""
wmaScore = 0
wmaTrade = ""

'''
gather user inputs...
initialize/confirm inputs & create NobiScan.f market + ping OHLCV, bids/asks, or check balances
start buy or cancel if needed...
ping order status + ping prices/indicators/etc...
sell....
repeat....
'''

class NobiScan:
    #easily connect to multiple exchanges + multiple coin pairs to maximize analysis opportunities
    def __init__(self): #, symbol, xchangename
        #these variables link to the global variables 
        global nowTime

        self.symbol = symbol
        self.xchangename = xchangename #The ccxt exchange module the bot is running on
        self.exchangeccxt = exchangeccxt #links exchange to ccxt module
        self.trend = trend
        self.scoreTotal = scoreTotal #global var each algo can add onto
        self.tradeSignal = tradeSignal

        self.apoScore = 0
        self.apoTrade = ""
        self.aroonScore = 0
        self.aroonTrade = ""
        self.cadScore = 0
        self.cadTrade = ""
        self.cmoScore = 0
        self.cmoTrade = ""
        self.cciScore = 0
        self.cciTrade = ""
        self.demaScore = 0
        self.demaTrade = ""
        self.dmiScore = 0
        self.dmiTrade = ""
        self.emaScore = 0
        self.emaTrade = ""
        self.kamaScore = 0
        self.kamaTrade = ""
        #self.kdjScore = 0 #needs test
        #self.kdjTrade = ""
        self.macdScore = 0 #needs test
        self.macdTrade = ""
        self.mfiScore = 0
        self.mfiTrade = ""
        self.mesaScore = 0
        self.mesaTrade = ""
        self.momiScore = 0
        self.momiTrade = ""
        self.ppoScore = 0
        self.ppoTrade = ""
        #self.rocScore = 0
        #self.rocTrade = ""
        self.rsiScore = 0
        self.rsiTrade = ""
        self.sarScore = 0
        self.sarTrade = ""
        self.smaScore = 0 
        self.smaTrade = ""
        self.trimaScore = 0
        self.trimaTrade = ""
        self.trixScore = 0
        self.trixTrade = ""
        self.t3score = 0
        self.t3Trade = ""
        self.wmaScore = 0
        self.wmaTrade = ""

    def initialize(self): 
        #load exchange variables, api keys, global variables, etc.
        print("Creating NobiScan on the exchange {}...loading data for coin pair: {}...!".format(self.exchangeccxt, self.symbol))
        time.sleep(1)
        option = input(str("Ready to begin... 'Analyze' (to start scan), 'Algorithm' (for detailed info), or 'Exit'  "))
        print("You selected: ", option)
        time.sleep(1)
        if option == 'Analyze' or 'analyze':
            bot = NobiScan()
            bot.analyze()
        elif option == 'Algorithm' or 'algorithm':
            bot = NobiScan()
            bot.algorithm()
        elif  option == 'Exit' or 'exit':
            exit()
        else:
            print("Invalid Option")
            time.sleep(1)
            bot = NobiScan()
            bot.initialize()  

    def algorithm(self): 
    	#Gives information on algos, possibly add them into a global iterable for analyze()
        bot = ngo.Nalgo()
        info = bot.algo_info() 
        print(info)
        time.sleep(2)
        print("Going back to initialization")
        bot = NobiScan()
        bot.initialize()
        
    def analyze(self): 
        global scoreTotal
        global openn
        global high
        global low
        global close
        global volume
        print("Starting Technical Analysis...")
        sleeptime = 0 #fix
        tframe = input(str("Please enter a timeframe for OHLVC data; 1m, 5m, 15m, 30m, 1h, 2h, 3h, 4h, 1d, 1w, 1m"))
        cycle = input(str("Enter number of cycles for analysis ticker (timeframe * cycles): "))
        print("Running ticker for ", cycle, "cycles, with the interval of,", tframe)
        time.sleep(1)
#Analysis loop begins here
	#try: #for error handling
        for i in range(int(cycle)): 
            print("Run #", [i], "***ANALYSIS OF ", self.xchangename, "...", self.symbol, "****")
            '''
            nowtime = time.asctime().replace(" ", "")
            fileName = "SCAN-" + self.xchangename + "-" + self.symbol + "-" +  nowTime + ".csv" #unique file name
            filename2 = fileName.replace("/", "")
            filename3 = filename2.replace(":", "")
            #sessionName = "SCAN" + self.xchangename + "-", self.symbol + "-" +  nowtime #unique file name
            '''
            orderbook= self.xchangename.fetch_order_book(self.symbol)
            time.sleep(.5)
            bids = orderbook['bids'][0][0] if len (orderbook['bids']) > 0 else None
            asks = orderbook['asks'][0][0] if len (orderbook['asks']) > 0 else None
            spread = (asks - bids) if (bids and asks) else None
            print({'Top Bid: ' : '{:.8f}'.format(float(bids)), 'Top Ask: ' : '{:.8f}'.format(float(asks)), 'Spread: ': '{:.8f}'.format(float(spread)), 'Open: ' : openn, 'High: ' : high, 'Low: ' : low, 'Close: ' : close, 'Volume' : volume})
            """
            columns = "xchange", "time", "O", "H", "L", "C", "V"
            ohlvc = exchangeccxt.fetchOHLCV(self.symbol, str(tframe), limit=1)
            prices_df = pd.DataFrame(ohlvc, columns=columns)
            #Variables for TA:
            openn = prices_df["O"]
            high = prices_df["H"]
            low = prices_df["L"]
            close = prices_df["C"]
            volume = prices_df["V"]
            #print(prices_df)
            """
	        # Call T.A. functions here? Using loop from algorun
            #ngo.Nalgo().algo_run()
            algo_run()
            #logging, or just have nalgo log
            """
            scan_df = pd.DataFrame(data, index=[0], columns=columns)
            scan_df.to_csv(filename3, mode= "w", header=True)
            """
            print("Next analysis will be in ", sleeptime , "seconds")
            self.scoreTotal = 0 #reset score for next iteration
            time.sleep(sleeptime)
        bot = NobiScan()
        bot.initialize()  
    """except KeyboardInterrupt:
        print('exiting...')"""

run = NobiScan()
run.initialize()




"""
#df outline for logging to Nobi dashboard
scan_output = {"exchange": "", "symbol": "", "tframe": "", "scoreTotal": "", "signal": "", "trend": "", "O": "", "H": "", "L": "", "C": "", "V": "", "APO": "", "AROON": "", "CAD": "", "CMO": "", "CCI": "", "DEMA": "", "DMI": "", "EMA": "", "KAMA": "", "KDJ": "", "MACD": "", "MFI": "", "MESA": "", "MOMI": "", "PPO": "", "RSI": "", "SAR": "", "SMA": "", "TRIMA": "", "TRIX": "", "WMA": ""}
scan_output["exchange"] = self.exchange
scan_output["symbol"] = self.symbol
scan_output["tframe"] = self.tframe
scan_output["scoreTotal"] = self.scoreTotal
scan_output["signal"] = self.signal
scan_output["trend"] = self.trend
scan_output["O"] = openn
scan_output["H"] = high
scan_output["L"] = low
scan_output["C"] = close
scan_output["V"] = volume
scan_output["APO"] = apo[99]
scan_output["AROON"] = AROON
scan_output["CAD"] = CAD
scan_output["CMO"] = CMO
scan_output["CCI"] = CCI
scan_output["DEMA"] = DEMA
scan_output["DMI"] = DMI
scan_output["EMA"] = EMA
scan_output["KDJ"] = KDJ
scan_output["MACD"] = MACD
scan_output["MFI"] = MFI
scan_output["MESA"] = MESA
scan_output["KAMA"] = KAMA
scan_output["MOMI"] = MOMI
scan_output["PPO"] = PPO
scan_output["RSI"] = RSI
scan_output["SMA"] = SMA
scan_output["TRIMA"] = TRIMA
scan_output["TRIX"] = TRIX
scan_output["T3"] = T3
scan_output["WMA"] = WMA
columns = ["Exchange", "T-Frame", "Score", "Trend", "Signal", "O", "H", "L", "C", "V", "APO", "AROON", "CAD", "CMO", "CCI", "DEMA", "DMI", "EMA", "KDJ", "MACD", "MFI", "MESA", "KAMA", "MOMI", "PPO", "RSI", "SMA", "TRIMA", "TRIX", "T3", "WMA"]
scanLog_df = pd.DataFrame(scan_output, index=[0], columns=columns)
print(scanLog_df)
dframe_html = scanLog_df(escape=False)
dframe_html2 = dframe_html.strip('<table border="1" class="dataframe">, </table>')

with open('/index.html') as inf:
        txt = inf.read()
        soup = bs.BeautifulSoup(txt, features="lxml")
for tag in soup.findAll(attrs={'class': 'auscrime'}):
        tag.clear()
        tag.append(dframe_html2)
with open('/index.html', "w") as outf:
        outf.write(unescape(str(soup))
#use bs4 to update currentTime for "Updated on: " in html
#use bs4 to update background color of <td> element to determine pos/neg signal (red/green)

----------------------
make a unique conditional for each symbol+exchange? :
if symbol == "ETH/BTC":
if exchange == "binance"
with open('/index.html', "w") as inf:
        txt = inf.read()
        soup = bs.BeautifulSoup(txt, features="lxml")
for tag in soup.findAll(attrs={'class': 'ethbtc'}):
    tag["ebsc"] = self.scoreTotal
    tag["ebtf"] = self.tframe
    tag.append(dframe_html2)
elif exchange == "kraken"
...
if symbol == "BNB/BTC":
if exchange == "binance":
... 
-------------------------- 
def changeBG(self, algo):

for changing CSS selector for algo value (red,green,yellow)
changeBG(apo)
if algo > 1:
    with open('/index.html') as inf:
            txt = inf.read()
            soup = bs.BeautifulSoup(txt, features="lxml")
    for tag in soup.findAll(attrs={'class': algo }):
            tag['id'] = "pos-bg"
elif algo < 1:
    with open('/index.html') as inf:
            txt = inf.read()
            soup = bs.BeautifulSoup(txt, features="lxml")
    for tag in soup.findAll(attrs={'class': algo }):
            tag['id'] = "neg-bg"
else:
    with open('/index.html') as inf:
            txt = inf.read()
            soup = bs.BeautifulSoup(txt, features="lxml")
    for tag in soup.findAll(attrs={'class': algo }):
            tag['id'] = "neu-bg"

"""
