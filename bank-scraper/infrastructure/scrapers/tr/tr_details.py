class TRDetails:
    DATA_TYPES = [
        "stockDetails",
        "neonNews",
        "ticker",
        "performance",
        "instrument",
        "instrumentSuitability",
    ]

    def __init__(self, tr, isin):
        self.instrument_suitability = None
        self.instrument = None
        self.performance = None
        self.ticker = None
        self.neon_news = None
        self.stock_details = None

        self._tr = tr
        self._isin = isin

    async def fetch(self, data: list = DATA_TYPES):
        recv = 0
        if "stockDetails" in data:
            await self._tr.stock_details(self._isin)
        if "neonNews" in data:
            await self._tr.news(self._isin)
        # await self.tr.subscribe_news(self.isin)
        if "ticker" in data:
            await self._tr.ticker(self._isin, exchange="LSX")
        if "performance" in data:
            await self._tr.performance(self._isin, exchange="LSX")
        if "instrument" in data:
            await self._tr.instrument_details(self._isin)
        if "instrumentSuitability" in data:
            await self._tr.instrument_suitability(self._isin)

        # await self.tr.add_watchlist(self.isin)
        # await self.tr.remove_watchlist(self.isin)
        # await self.tr.savings_plan_parameters(self.isin)
        # await self.tr.unsubscribe_news(self.isin)

        while True:
            _subscription_id, subscription, response = await self._tr.recv()

            if "stockDetails" in data and subscription["type"] == "stockDetails":
                recv += 1
                self.stock_details = response
            elif "neonNews" in data and subscription["type"] == "neonNews":
                recv += 1
                self.neon_news = response
            elif "ticker" in data and subscription["type"] == "ticker":
                recv += 1
                self.ticker = response
            elif "performance" in data and subscription["type"] == "performance":
                recv += 1
                self.performance = response
            elif "instrument" in data and subscription["type"] == "instrument":
                recv += 1
                self.instrument = response
            elif (
                    "instrumentSuitability" in data
                    and subscription["type"] == "instrumentSuitability"
            ):
                recv += 1
                self.instrument_suitability = response

            if recv == len(data):
                return
