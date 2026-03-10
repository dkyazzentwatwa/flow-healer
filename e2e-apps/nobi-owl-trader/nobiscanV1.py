#NobiScan Version .01
import ccxt
import bs4 as bs
import numpy as np
import pandas as pd
import time
import datetime
import talib as ta
from talib import MA_Type
import nalgoV2 as ngo

"""NOBISCAN TEST VERSION 0.1 
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
#ALGO GLOBAL VARIABLE BANK
score = 0 #global variable used to create overall score for pos/neg trade signal
scoreTotal = 0 #global var each algo can add onto
tradeSignal = ""
trend = "" #global var for uptrend(buy)/downtrend(sell)/neutral(hold)

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
t3Trade = ""
wmaScore = 0
wmaTrade = ""

algoStore = [] #global var for current algorthms being used
#mainkey = input(str("Please enter your MAIN API key: "))  #BEST NOT TO HAVE KEYS IN THE CODE!
#secretkey = input(str("Please enter your SECRET API key: ")) 
"""exchangeinfo = { 'apiKey': '', 
                        'secret': '',
                        'enableRateLimit': True,  
                        'verbose': False}"""
#exchangeinfo['apiKey'] = mainkey
#exchangeinfo['secret'] = secretkey
#xchange = exchangeccxt(exchangeinfo)

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
        self.symbol = symbol
        self.xchangename = xchangename #The ccxt exchange module the bot is running on
        self.exchangeccxt = exchangeccxt #links exchange to ccxt module
        self.scoreTotal = 0 #global var each algo can add onto
        self.trend = trend
        self.scoreTotal = scoreTotal
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
        self.kdjScore = 0 #needs test
        self.kdjTrade = ""
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
        self.rocScore = 0
        self.rocTrade = ""
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
        print("Starting Technical Analysis...")
        sleeptime = 0
        cycle = input(str("Enter number of cycles for analysis ticker (timeframe * cycles): "))
        #remove tframe since it is in Nalgo module?
        tframe = input(str("Please enter a timeframe for OHLVC data; 1m, 5m, 1H, 2H, 1D, etc."))
        #algo_sel = input
        if tframe == "1m" :
            sleeptime = int(60)
        elif tframe == "5m" :
            sleeptime = int(300)
        elif tframe == "15m" :
            sleeptime = int(900)
        elif tframe == "30m" :
            sleeptime = int(1800)
        elif tframe == "1H" :
	        sleeptime = int(3600)
        elif tframe == "2H" :
            sleeptime = int(7200)
        elif tframe == "3H" :
            sleeptime = int(10800)
        elif tframe == "4H" :
            sleeptime = int(14400)
        else:
            pass
        print("Running ticker with the timeframe of", tframe , "for ", cycle, "cycles.")
        time.sleep(1)
        #end of tframe remove
#Analysis loop begins here
	#try: #for error handling
        for i in range(int(cycle)): 
            currentTime = time.asctime()
            fileName = symbol + currentTime
            fileName.replace(" ", "")
            algo = ngo.Nalgo()
            print("Run #", [i], "***ANALYSIS OF ", self.xchangename, "...", self.symbol, "****")
            orderbook= self.xchangename.fetch_order_book(self.symbol)
            time.sleep(.5)
            bids = orderbook['bids'][0][0] if len (orderbook['bids']) > 0 else None
            asks = orderbook['asks'][0][0] if len (orderbook['asks']) > 0 else None
            spread = (asks - bids) if (bids and asks) else None
            columns = "xchange", "time", "O", "H", "L", "C", "V"
            ohlvc = exchangeccxt.fetchOHLCV(self.symbol, str(tframe), limit=1)
            prices_df = pd.DataFrame(ohlvc, columns=columns)
            #Variables for TA:
            #ctime = prices_df["time"] 
            openn = prices_df["O"]
            high = prices_df["H"]
            low = prices_df["L"]
            close = prices_df["C"]
            volume = prices_df["V"]
            print(prices_df)
            print({'Top Bid: ' : '{:.8f}'.format(float(bids)), 'Top Ask: ' : '{:.8f}'.format(float(asks)), 'Spread: ': '{:.8f}'.format(float(spread)), 'Open: ' : openn, 'High: ' : high, 'Low: ' : low, 'Close: ' : close,})
	        # Call T.A. functions here? Using loop from algobank
            algo.Nalgo.algoRun()

            """
            #df outline for logging to Nobi dashboard
            scan_output = {"exchange": "", "symbol": "", "scoreTotal": "", "signal": "", "trend": "", "O": "", "H": "", "L": "", "C": "", "V": "", "APO": "", "AROON": "", "CAD": "", "CMO": "", "CCI": "", "DEMA": "", "DMI": "", "EMA": "", "KAMA": "", "KDJ": "", "MACD": "", "MFI": "", "MESA": "", "MOMI": "", "PPO": "", "RSI": "", "SAR": "", "SMA": "", "TRIMA": "", "TRIX": "", "WMA": ""}
            scan_output["exchange"] = self.exchange
            scan_output["symbol"] = self.symbol
            scan_output["scoreTotal"] = self.scoreTotal
            scan_output["signal"] = self.signal
            scan_output["trend"] = self.trend
            scan_output["O"] = openn
            scan_output["H"] = high
            scan_output["L"] = low
            scan_output["C"] = close
            scan_output["V"] = volume
            scan_output["APO"] = APO
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
            columns = ["Exchange", "Score", "Trend", "Signal", "O", "H", "L", "C", "V", "APO", "AROON", "CAD", "CMO", "CCI", "DEMA", "DMI", "EMA", "KDJ", "MACD", "MFI", "MESA", "KAMA", "MOMI", "PPO", "RSI", "SMA", "TRIMA", "TRIX", "T3", "WMA"]
            scanLog_df = pd.DataFrame(scan_output, index=[0], columns=columns)
            dframe_html = scanLog_df(escape=False)
            dframe_html2 = dframe_html.strip('<table border="1" class="dataframe">, </table>')
            
            with open('/index.html') as inf:
                    txt = inf.read()
                    soup = bs4.BeautifulSoup(txt, features="lxml")
            for tag in soup.findAll(attrs={'class':'auscrime'}):
                    tag.clear()
                    tag.append(dframe_html2)
            with open('/index.html', "w") as outf:
                    outf.write(unescape(str(soup))
            #use bs4 to update currentTime for "Updated on: " in html
            #use bs4 to update background color of <td> element to determine pos/neg signal (red/green)
            """
            print("Next analysis will be in ", sleeptime , "seconds")
            self.scoreTotal = 0
            time.sleep(sleeptime)
        bot = NobiScan()
        bot.initialize()  
    """except KeyboardInterrupt:
        print('exiting...')"""
        

run = NobiScan()
run.initialize()
