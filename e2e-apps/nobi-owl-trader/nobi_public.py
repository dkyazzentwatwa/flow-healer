#NobiBot Version .02 Single Order LIVE Version
import ccxt
import bs4 as bs
import numpy as np
import pandas as pd
import time
import datetime
    
#NOBIBOT PUBLIC VERSION 0.1 --- 
#PROFESSIONAL AUTOMATED CRYPTOCURRENCY TRADING BOT 
#BY DAVID KYAZZE-NTWATWA 2019
""" USA Exchanges Available (6): Binance US
Kraken, coinbase(pro)
bitstamp ,gemini (small volume), poloniex
run for nalgoV2:
bot = nalgo.Nalgo()
bot.algoStart()"""


#Global Variables / user inputs
xchangename = input(str("Enter Exchange Name:  "))
mainkey = input(str("Enter your MAIN API key: "))  #BEST NOT TO HAVE KEYS IN THE CODE!
secretkey = input(str("Enter your SECRET API key: ")) 
exchangeinfo = { 'apiKey': '', 
                        'secret': '',
                        'enableRateLimit': True,  
                        'verbose': False}
exchangeinfo['apiKey'] = mainkey
exchangeinfo['secret'] = secretkey
exchangeccxt = getattr(ccxt, xchangename) #binds xchangename to ccxt module
xchange = exchangeccxt(exchangeinfo) #binds api keys to ccxt modulein Pair (ABC/DFG):  ")) #ABC/DFG..ABC = Base Coin; DFG = Quote Coin
coin1 = input(str("Please Enter Coin1(Base Coin):  ")) #Quote Coin (BASE/QUOTE) (BNB/BTC)
coin1_balance = xchange.fetchBalance()[coin1] #For Test uses static amount; Quote
coin2 = input(str("Please Enter Coin2(Quote Coin):  ")) #Base Coin (BASE/QUOTE) (BNB/BTC)
coin2_balance = xchange.fetchBalance()[coin2] #For Test uses static amount; Base
startamount = input(str("Please Enter Start Amount For Coin1:  ")) #amount to start trade, balance cannot go udner this amount
startamount2 = input(str("Please Enter Start Amount For Coin2:  "))
stop_amount = input(str("Please Enter Stop Amount For Coin1:  "))
stop_amount2 = input(str("Please Enter Stop Amount For Coin2:  "))
trade_amount = input(str("Please Enter Trade Amount For Coin1, The Constant Amount To Trade:  "))
open_order = 0 #global variable to track how many orders are open; directs loop flow so you limit max open orders.
closed_orders = 0 #global variable to track closed orders

score = 0 #global variable used to create overall score for pos/neg trade signal
profit_log = [] #global variable to track buy/sell order & profits/losses; appended to CSV
tradeTrigger = False #this is the trigger that Nalgo turns on or off via the result of the algorithms  

#Nalgo global variables
scoreTotal = 0 #global var each algo can add onto, relative to active algo total
tradeSignal = ""
trend = "" #global var for uptrend(buy)/downtrend(sell)/neutral(hold)
algoStore = []
#for global getOHLCV()
openn = ""
high = ""
low = ""
close  = ""
volume = ""

'''
basis...gather user inputs...
initialize/confirm inputs & create NobiBot...
start analysis of market + ping OHLCV, bids/asks, or check balances
start buy or cancel if needed...
ping order status + ping prices/indicators/etc...
sell....
repeat....
'''

class NobiBot:
    #easily connect to multiple exchanges + multiple coin pairs to maximize trading opportunities
    def __init__(self, symbol, coin1, coin2, startamount, startamount2, stop_amount, stop_amount2, xchange):
        #these variables link to the global variables        
        self.symbol = symbol
        self.coin1 = coin1
        self.coin1_balance = coin1_balance
        self.coin2 = coin2
        self.coin2_balance = coin2_balance
        self.startamount = startamount #start balance of coin #1 so the bot starts with the correct balance for trading 
        self.startamount2 = startamount2 #start balance of coin #2 so the bot starts with the correct balance 
        self.stop_amount = stop_amount #coin1's balance amount you want the bot to stop at; min(protects balance from going udner!)
        self.stop_amount2 = stop_amount2 #coin2's balance amount you want the bot to stop at(protects balance from going udner!)
        self.xchange = xchange #The ccxt exchange module the bot is running on
        self.xchangename = xchangename
        self.exchangeccxt = exchangeccxt

    def initialize(self): #load exchange variables, api keys, global variables, etc.
        print("Exchange: {}...Coin pair: {}...will get balances for {} (quote coin) & {} (base coin), with starting/stoping amounts of coin1 start: {} | coin 1 stop1: {} & coin2 start: {} coin2 stop2: {}!".format(self.xchangename, self.symbol, self.coin1, self.coin2, self.startamount, self.stop_amount, self.startamount2, self.stop_amount2))
        time.sleep(1)
        print("Current Balance for Quote coin", self.coin1, "is:", self.coin1_balance, self.coin1)
        time.sleep(1)
        print("Current Balance for Base coin", self.coin2, "is:", self.coin2_balance, self.coin2)
        time.sleep(1)
        option = input(str("Ready to begin... 'Analyze', 'Balance', 'Trade', or 'Exit'  "))
        print("You selected: ", option)
        time.sleep(1)
        if option == 'Analyze':
            bot = NobiBot(symbol, coin1, coin2, startamount, startamount2, stop_amount, stop_amount2, xchange)
            bot.analyze()
        elif option == 'Balance':
            bal = NobiBot(symbol, coin1, coin2, startamount, startamount2, stop_amount, stop_amount2, xchange)
            bal.balance()
        elif option == 'Trade':
            trad = NobiBot(symbol, coin1, coin2, startamount, startamount2, stop_amount, stop_amount2, xchange)
            trad.arigato()
        elif  option == 'Exit':
            exit()
        else:
            print("Invalid Option")
            time.sleep(1)
            bot = NobiBot(symbol, coin1, coin2, startamount, startamount2, stop_amount, stop_amount2, xchange)
            bot.initialize()  


    def analyze(self): #begin pinging of stats like:OHLVC, bid/ask, etc. this gets the bot ready w/ data// 
        sleeptime = 0
        cycle = input(str("Please enter number of cycles for analysis ticker: "))
        tframe = input(str("Please enter a timeframe for OHLVC data; 1m, 5m, 1H, 1D, etc.")) #test
        print("Running ticker for ", cycle, "cycles & on timeframe of: ", tframe)
        time.sleep(1)
        for i in range(int(cycle)):
            print([i], "***ANALYSIS OF ", self.xchangename, "...", self.symbol, "****")
            orderbook= self.xchange.fetch_order_book(self.symbol)
            time.sleep(.5)
            bids = orderbook['bids'][0][0] if len (orderbook['bids']) > 0 else None
            asks = orderbook['asks'][0][0] if len (orderbook['asks']) > 0 else None
            spread = (asks - bids) if (bids and asks) else None
            columns = "time", "O", "H", "L", "C", "V"
            ohlvc = xchange.fetchOHLCV(self.symbol, 'tframe', limit=1)
            #Add Technical Indicator Values Here
            prices_df = pd.DataFrame(ohlvc, columns=columns)
            print(prices_df)
            print({'Top Bid: ' : '{:.8f}'.format(float(bids)), 'Top Ask: ' : '{:.8f}'.format(float(asks)), 'Spread: ': '{:.8f}'.format(float(spread))})    
            time.sleep(3)
        bot = NobiBot(symbol, coin1, coin2, startamount, startamount2, stop_amount, stop_amount2, xchange)
        bot.initialize()  

#ARIGATO function is the main driver, it handles the conditions & everything always loops back to here, then back to trading..
    def arigato(self):
        Order_Status = False
        global open_order
        global closed_orders
        #completed_trades = 0
        while True:
            if open_order > 1: #security to make sure there are not too many orders, and waits for sales #7
                Order_Status = True
                print("Too many orders curently active (1+)...taking a nap for 1 minute zzzz....")
                time.sleep(10)
                bot = NobiBot(symbol, coin1, coin2, startamount, startamount2, stop_amount, stop_amount2, xchange)
                bot.arigato() 
            elif open_order == 0: #if there are no orders
                Order_Status = False
                print('***Order for', symbol , 'not found...Starting auto-trading..Open Order Status: ', Order_Status) 
                time.sleep(.5)
                bot = NobiBot(symbol, coin1, coin2, startamount, startamount2, stop_amount, stop_amount2, xchange)
                bot.trade()  
            elif open_order > 0: #OR if 'open' in binance.fetchOpenOrders()['XXX/XXX'['status]] //might not be necessary; if inside arigato function the trade should be completed & open_order == 0
                Order_Status = True
                print('Order for', symbol , 'is active...Order Status: ', Order_Status, "*symbol id*") #Method to check for open order??
                if 'SELL' or 'sell' in self.xchange.fetchOpenOrders(self.symbol)[0]['side']: #tweak for test
                    print('Order for', symbol, 'waiting to be sold...')
                    time.sleep(2)
                    bot = NobiBot(symbol, coin1, coin2, startamount, startamount2, stop_amount, stop_amount2, xchange)
                    bot.arigato()  
                elif 'BUY' or 'buy' in self.xchange.fetchOpenOrders(self.symbol)[0]['side']: #tweak for test
                    print('Order for', symbol, 'waiting to be bought...')     
                    time.sleep(2)
                    bot = NobiBot(symbol, coin1, coin2, startamount, startamount2, stop_amount, stop_amount2, xchange)
                    bot.arigato()  
                else:
                    pass
            else:
                bot = NobiBot(symbol, coin1, coin2, startamount, startamount2, stop_amount, stop_amount2, xchange)
                bot.initialize() 

#TRADE FUNCTION FOR BUY/SELL/CANCEL..RETURNS TO ARIGATO LOOP // a coroutine to buy/sell a coin 
#BUY 
    def trade(self):
        global open_order
        global closed_orders
        global profit_log
        global trade_amount
        global tradeTrigger #added 1/11/21
        global openn
        global high
        global low
        global close 
        global volume 
        global scoreTotal
        global tradeSignal
        global trend
        #nalgo.Nalgo.getOHLCV()

        nowtime = time.asctime().replace(" ", "")
        fileName = coin1 + coin2 + str(closed_orders) + "-" +  nowtime #unique file name
        time.sleep(.5)
        """
        buyprice = input(float("Insert buy amount"))
        """
        print("Starting Auto-Trading...NobiBot Wishes You Good Luck & Success!!")
        print(closed_orders, "orders completed so far.")
        if float(xchange.fetchBalance()[coin2]['free']) < float(self.stop_amount2): #if QUOTE amount(Base/Quote) is less than stop amount. 
            print("Returning to Initialization, make sure your account is ready before you begin again!")
            bot = NobiBot(symbol, coin1, coin2, startamount, startamount2, stop_amount, stop_amount2, xchange)
            bot.initialize()   
        else:
            pass
        time.sleep(.5)
        #add algorithm script here?
        '''
        while numberTrigger < 2:
            bot = Nalgo(xchangename, symbols, exchangeccxt, tframe)
            bot.algo_run()
            if numberTrigger == 2: 
                print("conditions met")
                continue #to instantly jump out of loop & start trade...vs wait for another 'true' value
            else:
                print("conditions not met, looping..")
                pass
            print(triggerList, 'ScoreTotals:', scoreList, "waitng to buy...")
            print("resting for", self.sleeptime , "seconds..zzz..")
            time.sleep(self.sleeptime)
        else:
        '''
        #------------
        #BUY SECTION ----
        #------------
        orderbook= self.xchange.fetch_order_book(self.symbol)
        time.sleep(1)
        bids = orderbook['bids'][0][0] if len (orderbook['bids']) > 0 else None
        asks = orderbook['asks'][0][0] if len (orderbook['asks']) > 0 else None
        spread = (asks - bids) if (bids and asks) else None
        #Insert Technical Analysis Indicator Algorithm Here
        buyprice = bids + (spread / 2) #in quote coin...BNB/BTC; BTC is quote // *value is computed by current algorithm
        buyamount = float(trade_amount) #buy base coin with quote coin (BASE/QUOTE) /// #self.xchange.fetch_balance()[self.coin1]['free'] or int(self.xchange.fetch_balance()[self.coin1]['free'])*.90 (percentage)
        self.xchange.create_limit_buy_order(self.symbol, buyamount, buyprice)
        time.sleep(2)
        while len(self.xchange.fetchOpenOrders(self.symbol)) == 0:
            print("Buy Order waiting to be placed...hold on..")
            time.sleep(1)
        else:
            buy_symbol_id =  self.xchange.fetchOpenOrders(self.symbol)[0]['id'] #'1234567890' Static for test
        order_receipt = {'time': ' ', 'symbol': ' ', 'id': ' ', 'buy amount': ' ', 'buy price': ' '} #add timestamp
        order_receipt['symbol'] = self.symbol
        order_receipt['id'] = buy_symbol_id #ID number for order
        order_receipt['buy amount'] = buyamount
        order_receipt['buy price'] = buyprice
        order_receipt['time'] = str(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        print("***BUY ORDER HAS BEEN PLACED,", order_receipt)
        open_order += 1 #this variable logs the current # of open order; directs the loop flow
        time.sleep(.5)
        while buy_symbol_id in str(xchange.fetchOpenOrders(symbol)):
            print('Order for ', symbol, buy_symbol_id, 'waiting to be bought...')
            time.sleep(1)
        else:
            print('***Order for ', buy_symbol_id, symbol, buyprice, buyamount, ' has been bought..starting sell order***')
        time.sleep(.5)
        #------------
        #SELL SECTION ----
        #------------
        if float(xchange.fetchBalance()[coin1]['free']) < float(self.stop_amount):
            print("NobiBot will not continue if coin1 balance drops below coin 1 stop_amount: ", self.stop_amount, self.coin1, "Funds are SAFU!" ) #create iteration of openorders to gather all ids & cancel them all #8
            exit()          
        else:
            pass
        #Insert Technical Analysis Algorithm Values Here
        '''
        tradeTrigger = False
        while tradeTrigger == False:
            bot = nalgo.Nalgo()
            bot.algo_run()
            if tradeSignal ==  #or if scoreTotal >= ..
        '''
        orderbook2= self.xchange.fetch_order_book(self.symbol) #new orderbook to get correct sell price
        time.sleep(1)
        bids2 = orderbook2['bids2'][0][0] if len (orderbook2['bids2']) > 0 else None
        asks2 = orderbook2['asks2'][0][0] if len (orderbook2['asks2']) > 0 else None
        spread = (asks2 - bids2) if (bids2 and asks2) else None
        sellprice = (asks2 + (spread / 4 )) 
        sell_amount = float(trade_amount) #sell base coin for quote coin #self.xchange.fetch_balance()[self.coin2]['free'] // or use % of balance int(balance)*.90
        self.xchange.create_limit_sell_order (self.symbol, sell_amount, sellprice)
        while len(self.xchange.fetchOpenOrders(self.symbol)) == 0:
            print("Sell Order waiting to be placed...hold on..")
            time.sleep(1)
        else:
            sell_symbol_id = self.xchange.fetchOpenOrders(self.symbol)[0]['id'] #'987654321'
        time.sleep(1)
        sell_order_receipt = {'symbol': ' ', 'id': ' ', 'sell amount: ': '', "sell price: ": "" }
        sell_order_receipt['symbol'] = self.symbol
        sell_order_receipt['id'] = sell_symbol_id
        sell_order_receipt['sell amount: '] = sell_amount
        sell_order_receipt['sell price: '] = sellprice
        print("***SELL ORDER HAS BEEN PLACED,", sell_order_receipt)
        time.sleep(.5)
        while sell_symbol_id in str(xchange.fetchOpenOrders(symbol)):
            print('Order for ', symbol, sell_symbol_id, 'waiting to be sold...')
            time.sleep(1)
        else:
            print('Order for ', symbol, sell_symbol_id, 'has been sold for: ', sellprice, self.coin2, '! Returning to main loop...')
            open_order -= 1
            closed_orders += 1
            #LOGGING ORDER OUTPUT TO CSV ---------------------------------
            order_output = {"time": "", "symbol": "", "amount": "", "buy": "", "sold": "", "profit": ""}
            order_output["time"] = "{:.8f}".format(time.strftime("%b%d%Y%H%M%S"))
            order_output["symbol"] = self.symbol
            order_output["amount"] = "{:.8f}".format(float(buyamount))
            order_output["buy"] = "{:.8f}".format(float(buyprice))
            order_output["sold"]= "{:.8f}".format(float(sellprice))
            order_output["profit"]= "{:.8f}".format(float((sellprice - buyprice)*sell_amount))
            columns = ["time", "symbol", "amount", "buy", "sold", "profit"]
            profit_log_df = pd.DataFrame(order_output, index=[0], columns=columns)
            profit_log_df.to_csv(fileName, mode= "a", header=True)
            #LOGGING DONE // returning to loop ---------------------------
            bot = NobiBot(symbol, coin1, coin2, startamount, startamount2, stop_amount, stop_amount2, xchange)
            bot.arigato()

#Balance
    def balance(self):
        print("Current balance for coin1,", self.coin1, " is: ", xchange.fetchBalance()[self.coin1])
        time.sleep(1)
        print("Coin2, ", self.coin2, " is: ", xchange.fetchBalance()[self.coin2])
        time.sleep(1)
        balinit = NobiBot(symbol, coin1, coin2, startamount, startamount2, stop_amount, stop_amount2, xchange)
        balinit.initialize()

run = NobiBot(symbol, coin1, coin2, startamount, startamount2, stop_amount, stop_amount2, xchange)
run.initialize()

#extra code
''' line 206orderbook= self.xchange.fetch_order_book(self.symbol)
asks = orderbook['asks'][0][0] if len (orderbook['asks']) > 0 else None
if asks < buyprice: #cancel order since bid order will not be met as price drops ; slippage protection
    print('***cancel order action; Current ask price less than your buy price!***') 
    self.xchange.cancel_order(buy_symbol_id, self.symbol) # ('12345678', 'BNB/BTC')
    time.sleep(1)
    open_order -= 1
    bot = NobiBot(symbol, coin1, coin2, startamount, startamount2, stop_amount, stop_amount2, xchange)
    bot.arigato()  
else:
    pass'''