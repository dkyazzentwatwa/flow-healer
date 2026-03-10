    
    
def logData(self, xchangename, symbols, tframe, scoreTotal, trend, tradeSignal, openn, high, low, close, volume):
    #make a unique conditional for each symbol+exchange? :
    if self.base == "ETH":
        if xchangename == "binance":
            with open('/Users/owner/Desktop/Coding/ccxt1/webapp/index.html', "r+") as inf:
                    txt = inf.read()
                    soup = bs.BeautifulSoup(txt, features="lxml")
            with open('/Users/owner/Desktop/Coding/ccxt1/webapp/index.html', "w") as outf:
                for tag in soup.findAll(attrs={'class': 'eth-bin'}):
                    #while tag is not None:
                    new_tag = soup.new_tag("td")
                    tag.append(new_tag, xchangename)
                    tag.append(new_tag, tframe)
                    tag.append(new_tag, scoreTotal)
                    tag.append(new_tag, trend)
                    tag.append(new_tag, tradeSignal)
                    tag.append(new_tag, openn)
                    tag.append(new_tag, high)
                    tag.append(new_tag, low)
                    tag.append(new_tag, close)
                    tag.append(new_tag, apoTrade)
                    tag.append(new_tag, aroonTrade)
                    tag.append(new_tag, cadTrade)
                    tag.append(new_tag, cmoTrade)
                    tag.append(new_tag, cciTrade)
                    tag.append(new_tag, demaTrade)
                    tag.append(new_tag, emaTrade)
                    tag.append(new_tag, macdTrade)
                    tag.append(new_tag, mfiTrade)
                    tag.append(new_tag, mesaTrade)
                    tag.append(new_tag, kamaTrade)
                    tag.append(new_tag, momiTrade)
                    tag.append(new_tag, ppoTrade)
                    tag.append(new_tag, rsiTrade)
                    tag.append(new_tag, sarTrade)
                    tag.append(new_tag, smaTrade)
                    tag.append(new_tag, trimaTrade)
                    tag.append(new_tag, trixTrade)
                    tag.append(new_tag, t3trade)
                    tag.append(new_tag, wmaTrade)


        elif xchangename == "bitfinex":
            pass
        elif xchangename == "bittrex":
            pass
        elif xchangename == "coinbasepro":
            pass
    if base == "BNB":
        if xchangename == "binance":
            pass







"""
def one():
    print("one")
def two():
    print("two")
def three():
    print("three")
list = [one, two, three]

for fn in list:
    fn()
"""

"""
    def logData(self, xchangename, symbols, tframe, scoreTotal, trend, tradeSignal, openn, high, low, close, volume):
        #make a unique conditional for each symbol+exchange? :
        if self.base == "ETH":
            if xchangename == "binance":
                with open('/Users/owner/Desktop/Coding/ccxt1/webapp/index.html', "r+") as inf:
                        txt = inf.read()
                        soup = bs.BeautifulSoup(txt, features="lxml")
                with open('/Users/owner/Desktop/Coding/ccxt1/webapp/index.html', "w") as outf:
                    for tag in soup.findAll(attrs={'class': 'eth-bin'}):
                        #while tag is not None:
                        tag["ebexc"] = xchangename
                        tag["ebtf"] = tframe
                        tag["ebsc"] = scoreTotal
                        tag["ebtr"] = trend
                        tag["ebsig"] = tradeSignal
                        tag["ebopen"] = openn
                        tag["ebhigh"] = high
                        tag["eblow"] = low
                        tag["ebclose"] = close
                        tag["ebapo"] = apoTrade
                        tag["ebaroon"] = aroonTrade
                        tag["ebcad"] = cadTrade
                        tag["ebcmo"] = cmoTrade
                        tag["ebcci"] = cciTrade
                        tag["ebdema"] = demaTrade
                        tag["ebema"] = emaTrade
                        tag["ebmacd"] = macdTrade
                        tag["ebmfi"] = mfiTrade
                        tag["ebmesa"] = mesaTrade
                        tag["ebkama"] = kamaTrade
                        tag["ebmomi"] = momiTrade
                        tag["ebppo"] = ppoTrade
                        tag["ebrsi"] = rsiTrade
                        tag["ebsar"] = sarTrade
                        tag["ebsma"] = smaTrade
                        tag["ebtrima"] = trimaTrade
                        tag["ebtrix"] = trixTrade
                        tag["ebt3"] = t3trade
                        tag["ebwma"] = wmaTrade


            elif xchangename == "bitfinex":
                pass
            elif xchangename == "bittrex":
                pass
            elif xchangename == "coinbasepro":
                pass
        if base == "BNB":
            if xchangename == "binance":
                pass

"""