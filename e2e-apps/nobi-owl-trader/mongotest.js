var MongoClient = require('mongodb').MongoClient

var url = 'mongodb://localhost/<DB>'

//basic connection test
MongoClient.connect(url, function(err, db) {
    console.log("connected");

        db.close();

});

//querying

MongoClient.connect(url, function(err, db) {
    const algo = db.collection("Algo")

    //fetch latest data for BTC/USDT on binace:
    const binBTC = await algo.find({exchange: "binance", symbol: "BTC/USDT"});
    await binBTC.forEach(console.dir)

})