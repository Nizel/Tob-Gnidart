import urllib
import urllib2
import time
import httplib
import hashlib
import ConfigParser
import hmac
import threading
import smtplib
import sys
import json
import datetime
import sqlite3
import socket
from optparse import OptionParser
import logging
import os
from signal import SIGTERM 

try:
    import daemon
except ImportError, e:
    print "You need python-daemon to run this script."
    print e
    sys.exit(0)
    
try:
    import lockfile
except ImportError, e:
    print "You need lockfile to run this script. Install using pip install python-daemon"
    print e
    sys.exit(0)

log = logging.getLogger("root")
handler = logging.StreamHandler()
formatter = logging.Formatter(fmt="[%(levelname)s] [%(asctime)s] [Function: %(funcName)s] [Line: %(lineno)d] %(message)s", datefmt="%H:%M:%S")
handler.setFormatter(formatter)
handlerLogFile = logging.FileHandler("./logs/output.log")
handlerLogFile.setFormatter(formatter)
log.addHandler(handler)
log.addHandler(handlerLogFile)

rootLogLvl = logging.INFO
validityLogLvl = logging.DEBUG
orderLogLvl = logging.DEBUG
monitorLogLvl = logging.INFO
checkLogLvl = logging.INFO

log.setLevel(rootLogLvl)

config = ConfigParser.RawConfigParser()

try:
    config.readfp(open('bot.conf'))
except Exception, e:
    log.exception(e)
    sys.exit(1)

BTC_api_key = str(config.get('API', 'key'))
if BTC_api_key == "":
    log.critical("Please put your API Key into the config file!")
    sys.exit(1)

BTC_api_secret = str(config.get('API', 'secret'))
if BTC_api_secret == "":
    log.critical("Please put your API Secret Key into the config file!")
    sys.exit(1)

if config.get('ABILITY', 'trade') == "False":
    tradeAllowed = False
else:
    tradeAllowed = True

gmailUsername = str(config.get('LOGIN', 'username'))
gmailPassword = str(config.get('LOGIN', 'password'))
if gmailUsername == "":
    log.critical("Error, you must enter a valid GMail username into the config file!")
    sys.exit(1)
if gmailPassword == "":
    log.critical("Oh come on, we know your password isn't '', so change it in the config file!")
    sys.exit(1)

phoneNumber = str(config.get('SMS', 'number'))
phoneProvider = str(config.get('SMS', 'provideremail'))
if phoneNumber == "5555555555":
    log.critical("Error, must enter a valid phone number into the config file!")
    sys.exit(1)
   
maxFunds = 0
btcMaxFunds = 0
    
pairs = ["btc_usd",
        "ltc_btc",
        "ltc_usd",
        "trc_btc",
        "nvc_btc",
        "nmc_btc",
        "ppc_btc"]
        
rounding = {"btc":3,
            "ltc":3,
            "usd":3,
            "trc":3,
            "nvc":3,
            "nmc":3,
            "ppc":3}

def nonce():#extra=None):
    nonce = int(config.get('POST', 'nonce'))
    if not nonce > 0:
        nonce = 1
    config.set('POST', 'nonce', str(nonce+1))
    with open('./bot.conf', 'wb') as configfile:
        config.write(configfile)
    return nonce
    
def isValidTrade(params):
    validityLog = logging.getLogger("root.validity")
    validityLog.setLevel(validityLogLvl)
    if tradeAllowed == False:
        validityLog.debug("Trade failed because of config file")
        return False

    pair = params['pair']
    tradeType = params['type']
    rate = params['rate']
    amount = params['amount']
    reserveMoney = float(0)
    o = Order()
    
    if pair not in pairs:
        validityLog.debug("Pair not in pairs: %s" % pair)
        return False

    #if tradeType == "buy":
        #reserveMoney = o.getinfo()['funds'][pair[4:]]
    #elif tradeType == "sell":
        #reserveMoney = o.getinfo()['funds'][pair[:3]]
    #if amount > rate*reserveMoney:
        #return False
    return True
    
def totalFunds(tradeData=None, returnBTC=False):
    global maxFunds
    sumFunds = float(0)
    btcSumFunds = float(0)
    o = Order()
    funds = o.getinfo()['funds']
    log.debug(funds)
    if tradeData:
        for datum in tradeData.iterkeys():
            funds[datum] = tradeData[datum]
    log.debug(funds)
    for fund in funds.iterkeys():
        log.debug(fund)
        if str(fund) != 'usd' and str(fund) != 'rur' and str(fund) != 'eur':
            if str(fund) == 'btc' or str(fund) == 'ltc':
                conn = urllib2.urlopen("https://btc-e.com/api/2/%s_usd/ticker" % fund)
                data = json.load(conn)
                log.debug(data)
                sellRate = float(data['ticker']['sell'])
                sumFunds+=sellRate*funds[fund]
                if str(fund) == "btc":
                    btcSumFunds+=funds[fund]
                else:
                    conn2 = urllib2.urlopen("https://btc-e.com/api/2/%s_btc/ticker" % fund)
                    data2 = json.load(conn2)
                    log.debug(data2)
                    sellRate2 = float(data2['ticker']['sell'])
                    log.debug("LTC to BTC "+str(sellRate2*funds[fund]))
                    btcSumFunds+=sellRate2*funds[fund]
            else:
                try:
                    conn = urllib2.urlopen("https://btc-e.com/api/2/%s_btc/ticker" % fund)
                except Exception, ex:
                    if "Connection refused>" in str(ex):
                        log.warning("Connection refused at "+fund+"_btc")
                    else:
                        log.exception(ex)
                    return 0
                data = json.load(conn)
                sellToBTCRate = float(data['ticker']['sell'])
                tempBTCSum = funds[fund]*sellToBTCRate
                log.debug("BTC TEMP SUM "+str(tempBTCSum))
                btcSumFunds+=tempBTCSum
                try:
                    conn2 = urllib2.urlopen("https://btc-e.com/api/2/btc_usd/ticker")
                except Exception, ex:
                    if "Connection refused>" in str(ex):
                        log.warning("Connection refused at btc_usd")
                    else:
                        log.exception(ex)
                    return 0
                sellRate = float(json.load(conn2)['ticker']['sell'])
                sumFunds+=sellRate*tempBTCSum
    sumFunds+=float(funds['usd'])
    if not tradeData and sumFunds > maxFunds:
        config.set('FUNDS', 'worth', str(sumFunds))
        with open('bot.conf', 'wb') as configfile:
            config.write(configfile)
        maxFunds = sumFunds
    if not tradeData and btcSumFunds > btcMaxFunds:
        config.set('FUNDS', 'btc', str(btcSumFunds))
        with open('bot.conf', 'wb') as configfile:
            config.write(configfile)
    log.debug(sumFunds)
    log.debug(btcSumFunds)
    if returnBTC == True:
        return btcSumFunds
    return sumFunds
    
class SMS(object):
    def send(self, message):
        server = smtplib.SMTP( "smtp.gmail.com", 587 )
        server.starttls()
        server.login( gmailUsername, gmailPassword )
        message = "\n["+str(datetime.datetime.today().strftime("%H:%M:%S"))+"] "+message
        server.sendmail('testing', phoneNumber+"@"+phoneProvider, message)
    
class POST(object):
    def getinfo(self):
        params = {"method":"getInfo",
          "nonce": nonce()}
        return urllib.urlencode(params)
        
    def transhistory(self, count=None, order=None):
        params = {"method":"TransHistory",
            "nonce":nonce()}
        if count:
            params['count'] = count
        if order:
            params['prder'] = order
        return urllib.urlencode(params)
        
    def tradehistory(self, count=None, order=None, pair=None):
        params = {"method":"TradeHistory",
            "nonce":nonce()}
        if count:
            params['count'] = count
        if order:
            params['prder'] = order
        if pair:
            if pair[3] != "_":
                params['pair'] = "btc_usd"
            else:
                params['pair'] = pair
        return urllib.urlencode(params)
    
    def orderlist(self, count=None, order=None, pair=None, active=None):
        params = {"method":"OrderList",
            "nonce":nonce()}
        if count:
            params['count'] = count
        if order:
            params['prder'] = order
        if pair:
            if pair[3] != "_":
                params['pair'] = "btc_usd"
            else:
                params['pair'] = pair
        if active:
            params['active'] = str(active)
        return urllib.urlencode(params)
        
    def trade(self, pair, tradeType, rate, amount):
        params = {"method":"Trade",
            "nonce":nonce(),
            "pair":pair,
            "type":tradeType,
            "rate":rate,
            "amount":amount}
        log.debug(tradeAllowed)
        if tradeAllowed == False:
            SMS().send("We tried to "+str(tradeType)+" "+str(amount)+" "+str(pair)+" at "+str(rate))
        if not isValidTrade(params):
            return -1
        params['nonce'] = nonce()
        return urllib.urlencode(params)
        
class Header(object):
    def hashParams(self, params):
        H = hmac.new(BTC_api_secret, digestmod=hashlib.sha512)
        H.update(params)
        return H.hexdigest()
        
class Order(object):
    def __init__(self):
        self.orderLog = logging.getLogger("root.order")
        self.orderLog.setLevel(orderLogLvl)
        
    def getinfo(self):
        params = POST().getinfo()
        return self.makeOrder(params)
    
    def trade(self, pair, tradeType, rate, amount):
        self.orderLog.debug(pair+" "+tradeType+" "+str(rate)+" "+str(amount))
        params = POST().trade(pair, tradeType, rate, amount)
        if params == -1:
            self.orderLog.error("Error with trade parameters")
            self.orderLog.error("Pair: %s" % pair)
            self.orderLog.error("Type: %s" % tradeType)
            self.orderLog.error("Rate: %s" % rate)
            self.orderLog.error("Amount: %s" % amount)
            return -1
        return self.makeOrder(params)
        
    def tradeHistory(self, pair=None, count=None, order=None):
        self.orderLog.debug("Pair: "+pair+" Count: "+count+" Order: "+order)
        if pair and pair not in pairs:
            self.orderLog.error("Invalid pair: "+pair)
            return
        if count and count < 1:
            self.orderLog.error("Invalid count: "+count)
            return
        if order and order != "desc" or order != "asc":
            self.orderLog.error("Invalid order: "+order)
            return
		   
    def makeOrder(self, params):
        h = Header()
        signHeader = h.hashParams(params)
        headers = {"Content-type": "application/x-www-form-urlencoded",
		   "Key":BTC_api_key,
		   "Sign":signHeader}
        conn = httplib.HTTPSConnection("btc-e.com")
        try:
            conn.request("POST", "/tapi", params, headers)
            response = conn.getresponse()
            data = json.load(response)
            conn.close()
            if "method=Trade" in params.split("&"):
                self.orderLog.debug(data)
            if int(data['success']) == 1:
                if "method=Trade" in params.split("&"):
                    totalFunds()
                return data['return']
            else:
                self.orderLog.error("Error, %s" % data['error'])
        except Exception, e:
            if "Connection refused" in str(e):
                self.orderLog.warning("Connection refused")
            else:
                self.orderLog.exception(e)
        
class MonitorTicker(object):
    def __init__(self):
        self.monitorLog = logging.getLogger("root.monitor")
        self.monitorLog.setLevel(monitorLogLvl)
        self.monitorHandler = logging.StreamHandler()
        monitorFormatter = logging.Formatter(fmt="[%(levelname)s] [%(asctime)s] %(message)s", datefmt="%H:%M:%S")
        self.monitorHandler.setFormatter(monitorFormatter)
        self.monitorLog.propagate = False
        self.monitorLog.addHandler(self.monitorHandler)
        self.monitorFileHandler = handlerLogFile
        self.monitorFileHandler.setFormatter(monitorFormatter)
        self.monitorLog.addHandler(self.monitorFileHandler)
        
        self.stdin_path = '/dev/null'
        self.stdout_path = '/dev/tty'
        self.stderr_path = '/dev/tty'
        self.pidfile_path =  os.path.abspath('./logs/bot.pid')
        self.pidfile_timeout = 5
        
    def run(self):
        self.allcoins()

    def allcoins(self):
        while True:
            tradeAbility = self.checkTradeAbility()
            if tradeAbility == True:
                for pair in pairs:
                    try:
                        url = "https://btc-e.com/api/2/%s/ticker" % pair
                        response = urllib2.urlopen(url)
                        data = json.load(response)
                        self.monitorLog.debug(data)
                        try:
                            self.check(data['ticker'], pair)
                        except Exception, e:
                            self.monitorLog.exception(e)
                    except Exception, e:
                        self.monitorLog.exception(e)
            else:
                self.monitorLog.warning("We don't have the trading ability as of yet.\nMake sure to enable bot trading on the API page!")
            self.monitorLog.info("Check round completed.\n")
            time.sleep(150)
    
    def check(self, data, pair):
        checkLog = logging.getLogger("root.monitor.check")
        checkLog.propagate = False
        checkLog.addHandler(handler)
        #checkLog.addHandler(handlerLogFile)
        checkLog.setLevel(checkLogLvl)
        
        conn = sqlite3.connect('trading.db', timeout=30)
        c = conn.cursor()
        try:
            c.execute("SELECT * FROM btc_usd LIMIT 5").fetchall()
        except sqlite3.OperationalError, e:
            if "btc_usd" in str(e):
                for paird in pairs:
                    c.execute('''CREATE table %s (type TEXT, time INTEGER PRIMARY KEY)''' % paird)
                conn.commit()
            pass
        
        o = Order()
        
        checkLog.debug(data)
        dayRange = float(data['high']) - float(data['low'])
        buyPrice = (float(data['avg']) + float(data['low'])) / 2# * 0.99
        sellPrice = (float(data['avg']) + float(data['high'])) / 2# * 1.01
        
        checkLog.debug(str(pair)+" "+str(buyPrice))
        checkLog.debug(str(pair)+" "+str(sellPrice))
        
        try:
            buyReserve = float(o.getinfo()['funds'][pair[4:]])
            sellReserve = float(o.getinfo()['funds'][pair[:3]])
        except Exception, e:
            checkLog.exception(e)
            buyReserve = float(0)
            sellReserve = float(0)
        
        checkLog.debug(str(pair)+" "+str(buyReserve))
        checkLog.debug(str(pair)+" "+str(sellReserve))
        
        divideBy = -1
        
        if data['sell'] >= sellPrice:
            divideBy = self.divideBy(pair, "sell")
            checkLog.debug(totalFunds({pair[4:]:round(float(sellReserve/divideBy) * float(data['sell']) + buyReserve, rounding[pair[4:]]), pair[:3]:round(float(sellReserve) - float(sellReserve/divideBy), rounding[pair[:3]])}))
            checkLog.debug("Sell %s" % pair)
            #if sellReserve > 0 and round(float(sellReserve/divideBy) * float(data['sell']), rounding[pair[4:]]) > 0.1 or (pair[4:] == "btc" and round(float(sellReserve/divideBy) * float(data['sell']), rounding[pair[4:]]) > 0.01):
            if (not options.btc_only and sellReserve > 0 and round(float(sellReserve/divideBy), rounding[pair[4:]]) > 0.1) or (pair[4:] == "btc" and round(float(sellReserve/divideBy), rounding[pair[4:]]) > 0.01):
                totalFund = totalFunds({pair[4:]:round(float(sellReserve/divideBy) * float(data['sell']) + buyReserve, rounding[pair[4:]]), pair[:3]:round(float(sellReserve) - float(sellReserve/divideBy), rounding[pair[:3]])})
                btcTotalFund = totalFunds(tradeData={pair[4:]:round(float(sellReserve/divideBy) * float(data['sell']) + buyReserve, rounding[pair[4:]]), pair[:3]:round(float(sellReserve) - float(sellReserve/divideBy), rounding[pair[:3]])}, returnBTC=True)
                if totalFund > maxFunds+0.5 or btcTotalFund > btcMaxFunds+0.01:
                    amount = round(float(sellReserve/divideBy), rounding[pair[4:]])
                    checkLog.debug("Selling")
                    x = o.trade(pair, "sell", data['sell'], amount)
                    if x != -1:
                        self.monitorLog.info("We sold "+str(amount)+" "+pair[:3]+" at "+float(data['sell']))
                        SMS().send(" We sold "+str(amount)+" "+pair[:3]+" at "+float(data['sell']))
                        totalFunds()
                    else:
                        self.monitorLog.error("We couldn't sell "+str(round(amount, rounding[pair[4:]]))+" "+pair[:3]+" at "+str(float(data['sell'])))
                else:
                    loss = round(maxFunds - totalFund, 2)
                    self.monitorLog.info("We tried selling "+pair[:3]+" from "+pair+" for a $"+str(loss)+" loss.")
            else:
                self.monitorLog.info("We wanted to sell some "+pair[:3]+" from "+pair+" but we either had no reserves, or it didn't amount to the minimum")
        elif data['buy'] <= buyPrice:
            divideBy = self.divideBy(pair, "buy")
            checkLog.debug(pair+" "+str(buyReserve)+" "+str(divideBy)+" "+ str(float(buyReserve/divideBy))+" "+str(float(data['buy']))+" "+str(float(buyReserve/divideBy) / float(data['buy'])))
            #if buyReserve > 0 and round(float(buyReserve/divideBy) / float(data['buy']), rounding[pair[:3]]) > 0.1 or (pair[4:] == "btc" and round(float(buyReserve/divideBy) / float(data['buy']), rounding[pair[:3]]) > 0.01):
            if buyReserve > 0 and round(float(buyReserve/divideBy), rounding[pair[:3]]) > 0.1 or (pair[4:] == "btc" and round(float(buyReserve/divideBy), rounding[pair[:3]]) > 0.01):
                checkLog.debug("Buying")
                x = o.trade(pair, "buy", data['buy'], round(float(buyReserve/divideBy) / float(data['buy']), rounding[pair[:3]]))
                if x != -1:
                    self.monitorLog.info("We bought "+str(round(float(buyReserve/divideBy) / float(data['buy']), rounding[pair[:3]]))+" "+pair[:3]+" at "+str(data['buy'])+" from "+pair)
                    SMS().send(" We bought "+str(round(float(buyReserve/divideBy) / float(data['buy']), rounding[pair[:3]]))+" "+pair[:3]+" at "+str(data['buy'])+" from "+pair)
                    totalFunds()
            else:
                self.monitorLog.info("We wanted to buy some "+pair[:3]+" from "+pair+" but we either had no reserves, or it didn't amount to the minimum")
        else:
            divideBy = self.divideBy(pair, "sell", save=False)
            if pair[4:] == "btc" or pair[4:] == "usd":
                #if sellReserve > 0 and round(float(sellReserve/divideBy) * float(data['sell']), rounding[pair[4:]]) > 0.1 or (pair[4:] == "btc" and round(float(sellReserve/divideBy) * float(data['sell']), rounding[pair[4:]]) > 0.01):
                if (not options.btc_only and sellReserve > 0 and round(float(sellReserve/divideBy), rounding[pair[4:]]) > 0.1) or (pair[4:] == "btc" and round(float(sellReserve/divideBy), rounding[pair[4:]]) > 0.01):
                    totalFund = totalFunds({pair[4:]:round(float(sellReserve/divideBy) * float(data['sell']) + buyReserve, rounding[pair[4:]]), pair[:3]:round(float(sellReserve) - float(sellReserve/divideBy), rounding[pair[:3]])})
                    btcTotalFund = totalFunds(tradeData={pair[4:]:round(float(sellReserve/divideBy) * float(data['sell']) + buyReserve, rounding[pair[4:]]), pair[:3]:round(float(sellReserve) - float(sellReserve/divideBy), rounding[pair[:3]])}, returnBTC=True)
                    if totalFund > maxFunds+0.5 or btcTotalFund > btcMaxFunds+btcMaxFunds*0.01:
                        divideBy = self.divideBy(pair, "sell")
                        checkLog.debug("Selling")
                        x = o.trade(pair, "sell", data['sell'], round(float(sellReserve/divideBy), rounding[pair[4:]]))
                        if x != -1:
                            self.monitorLog.info("We sold "+str(round(float(sellReserve/divideBy), rounding[pair[4:]]))+" "+pair[:3]+" at "+float(data['sell']))
                            SMS().send(" We sold "+str(round(float(sellReserve/divideBy), rounding[pair[4:]]))+" "+pair[:3]+" at "+float(data['sell']))
                            totalFunds()
                        else:
                            self.monitorLog.error("We couldn't sell "+str(round(float(sellReserve/divideBy), rounding[pair[4:]]))+" "+pair[:3]+" at "+float(data['sell']))
                    elif totalFund > maxFunds:
                        self.monitorLog.info("Right now, selling "+pair[:3]+" from "+pair+" would probably be a good idea, you'd net a profit of $"+str(totalFund-maxFunds)+" (without fees) at "+str(float(data['sell'])))
                        SMS().send(" Right now, selling "+pair[:3]+" would probably be a good idea, you'd net a profit of $"+str(maxFunds-totalFund)+" (without fees) at "+str(float(data['sell'])))
                    elif btcTotalFund > btcMaxFunds:
                        self.monitorLog.info("Right now, selling "+pair[:3]+" from "+pair+" would probably be a good idea, you'd net a profit of "+str(btcTotalFund-btcMaxFunds)+" BTC (without fees) at "+str(float(data['sell'])))
                        SMS().send(" Right now, selling "+pair[:3]+" would probably be a good idea, you'd net a profit of "+str(btcTotalFund-btcMaxFunds)+" BTC (without fees) at "+str(float(data['sell'])))
                    elif totalFund > maxFunds-(maxFunds*0.05) or btcTotalFund > btcMaxFunds*0.95:
                        self.monitorLog.info("We may be selling "+pair[:3]+" from "+pair+" soon, as of right now there would be a net loss of $"+str(round(maxFunds-totalFund, 2))+" or "+str(round(btcMaxFunds-btcTotalFund, 5))+" BTC")
                    else:
                        checkLog.debug("Did not meet price ranges: "+pair)
        checkLog.debug(divideBy)
                
    def checkTradeAbility(self):
        o = Order() 
        data = o.getinfo()
        try:
            if data['rights']['trade'] == 1:
                log.debug("We have ability to trade")
                return True
        except Exception, e:
            log.exception(e)
            pass
        return False
        
    def divideBy(self, pair, tradeType, save=True):
        conn = sqlite3.connect('trading.db', timeout=30)
        c = conn.cursor()
        
        fiveMinTime = int(time.time()) - 600
        trades = []
        ret = 16
        try:
            test = "SELECT * FROM %s WHERE (type=? AND time > ?)" % pair
            trades = c.execute(test, (str(tradeType), str(fiveMinTime))).fetchall()
            log.debug(trades)
        except Exception, e:
            log.exception(e)
        if len(trades) > 0:
            for i in range(len(trades)):
                if i % 2 == 0:
                    ret = ret/2
        if ret < 4:
            ret = 4
        
        if save == True:
            log.debug("INSERT INTO %s (type, time)VALUES(%s, %s)" % (pair, str(tradeType), str(int(time.time()))))
            test = "INSERT INTO %s (type, time)VALUES(?, ?)" % pair
            c.execute(test, (str(tradeType), str(int(time.time()))))
        conn.commit()
        return ret
            
if __name__ == '__main__':
    parser = OptionParser()

    parser.add_option("-V", "--total-funds", dest="calcFunds", action="store_true",
                        help="Recalculate total worth of funds (use after adding new funds)")
    parser.add_option("-d", "--debug", dest="debug", action="store_true",
                        help="Activates debug mode, get ready to be destroyed with messages c:")
    parser.add_option("--daemonize", dest="daemon", metavar="start|stop|restart",
                        help="Daemonize's the bot with output in ./logs/output.log")
    parser.add_option("--btc-only", dest="btc_only", action="store_true")
    (options, args) = parser.parse_args()

    if options.calcFunds == True:
        totalFunds()

    if options.debug == True:
        validityLogLvl = logging.DEBUG
        orderLogLvl = logging.DEBUG
        monitorLogLvl = logging.DEBUG
        checkLogLvl = logging.DEBUG
        log.setLevel(logging.DEBUG)
        log.debug(maxFunds)
        log.debug(btcMaxFunds)
        
    if options.calcFunds:
        totalFunds()
    try:
        maxFunds = float(config.get('FUNDS', 'worth'))
        btcMaxFunds = float(config.get('FUNDS', 'btc'))
    except Exception, e:
        log.exception(e)
        maxFunds = totalFunds()
        btcMaxFunds = totalFunds(returnBTC=True)
    if not os.path.isdir("./logs"):
        os.mkdirs("./logs")
    m = MonitorTicker()
    try:
        if options.daemon:
            context = daemon.DaemonContext(
                working_directory=os.getcwd(),
                pidfile=lockfile.FileLock(os.path.abspath('./logs/bot.pid'))
                )
            context.files_preserve = [handlerLogFile.stream]
            if options.daemon == "start":
                try:
                    with open('./logs/bot.pid.lock'): 
                        log.error("Bot already running!")
                        sys.exit(1)
                except IOError:
                    pass
                with context:
                    log.info("Daemon started at "+str(datetime.datetime.today()))
                    pid = str(os.getpid())
                    file("./logs/bot.pid",'w+').write("%s\n" % pid)
                    m.allcoins()
            elif options.daemon == "stop":
                context.close()
                try:
                    pf = file("./logs/bot.pid",'r')
                    pid = int(pf.read().strip())
                    pf.close()
                except IOError:
                    pid = None
                if not pid:
                    log.error("Bot not running.")
                    sys.exit(0)
                try:
                    while 1:
                        os.kill(pid, SIGTERM)
                        time.sleep(0.1)
                except OSError, err:
                    err = str(err)
                    if err.find("No such process") > 0:
                        if os.path.exists("./logs/bot.pid"):
                            os.remove("./logs/bot.pid")
                    else:
                        print str(err)
                        sys.exit(1)
                log.info("Daemon stopped")
        else:
            try:
                with open('./logs/bot.pid.lock'): 
                    log.error("Bot already running!")
                    sys.exit(1)
            except IOError:
                pass
            a = threading.Thread(target=m.allcoins())
            a.daemon = True
            a.start()
    except KeyboardInterrupt, e:
        log.info("\nUser abort, shutting down!")
    
