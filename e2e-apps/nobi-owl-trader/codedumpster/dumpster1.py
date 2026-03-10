    

def buy(self):
        if open_orders == 0 and open_orders < 6: #OR if len(binance.fetchOpenOrders("XXX/XXX")) == 0 AND < 6:
            buy_amount = xchange.fetch_balance()[coin1]['free'] #uses free amount; multiply by XXX% if you dont want to use everything.
            buy_price = ( bchbtc_binance_ob['bids'][0][0] + (spread_bchbtc_binance / 2) ) #or spread/4    
            params = {
                'stopPrice': (buy_price - (buy_price *.0005)), # stop price is a safety net incase price plummets
                'type': 'stopLimit',
            }
            xchange.create_limit_buy_order(self.symbol, buy_amount, buy_price, params)
            open_orders += 1
            time.sleep(2)
            symbol_id = xchange.fetchOpenOrders("BCH/BTC")[0]['id']
            order_receipt = {'symbol': ' ', 'id': ' '}
            order_receipt['symbol'] = symbol
            order_receipt['id'] = symbol_id
            print("***ORDER HAS BEEN PLACED,", order_receipt, buy_amount, buy_price)
        #SELL
        if open_orders > 0 and open_orders <= 5:
            sellprice = ( "createBuy.buy_price" + .00001 )
            sell_amount = xchange.fetch_balance()['coin2']['free'] #uses free amount; multiply by XXX% if you dont want to use everything.
            params = {
                'stopPrice': sellprice, # your stop price
                'type': 'stopLimit',
            }
            xchange.create_limit_sell_order (symbol, sell_amount, sellprice, params)
            open_orders -= 1
            print('***SALE HAS BEEN PLACED')
            completed_trades += 1
        else: 
            pass           
        #CANCEL ORDER
        def cancel(self):
            xchange.cancel_order (symbol_id) # replace with your order id here (a string)

def OrderStat(symbol):
    Order_Status = True
    if 'open' or 'NEW' in xchange.fetchOpenOrders(symbol)[0]['status']: #OR if 'open' in binance.fetchOpenOrders()['XXX/XXX'['status]]
        Order_Status = True
        print('Order for', symbol , 'still active')
        time.sleep(2)
    if 'open' not in xchange.fetchOpenOrders()[symbol]['status']:
        print('Order for', symbol , 'not found.')
        Order_Status = False
