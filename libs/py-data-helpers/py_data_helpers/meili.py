import meilisearch

class MeiliHelper:
    def __init__(self, url, api_key, index=None):
        self.url = url
        self.api_key = api_key
        self.client = meilisearch.Client(url, api_key)
        self.index = index

    def set_index(self, index):
        self.index = index
        return self




