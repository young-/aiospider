#!/usr/bin/python3
#-*- coding:utf-8 -*-
'''
main part
'''
import asyncio
import logging
import sys
from functools import partial
from urllib.parse import urljoin
from itertools import zip_longest
from collections import namedtuple

import aiohttp

DEFAULT_HEADER = {'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/56.0.2924.87 Safari/537.36',
                        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
                        }

_Request = namedtuple("Request",["method","url","callback","header","data"])
def Request(method,url,callback,header=DEFAULT_HEADER,data=None):
    return _Request(method,url,callback,header,data)

class Spider:
    '''
    spider class
    '''

    default_config = {
        # How many requests can be run in parallel
        "concurrent": 10,
        # How long to wait after each request
        "delay": 0,
        # A stream to where internal logs are sent, optional
        "logs": sys.stdout,
        # Re - visit visited URLs, false by default
        "allowDuplicates": False,
    }

    def __init__(self, **kwargs):
        self.config = Spider.default_config.copy()

        self.config.update(kwargs.get("config", {}))

        self.loop = kwargs.get("loop", None)
        if self.loop is None or not isinstance(self.loop, asyncio.BaseEventLoop):
            self.loop = asyncio.get_event_loop()
        self.session = kwargs.get("session", None)
        if self.session is None or not isinstance(self.session, aiohttp.ClientSession):
            self.session = aiohttp.ClientSession(loop=self.loop)

        self.logger = logging.getLogger(self.__class__.__name__)
        self.pending = asyncio.Queue()
        self.active = []
        self.visited = set()
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self.session.closed:
            self.session.close()
        if not self.loop.is_closed():
            self.loop.close()

    def log(self, status, url):
        self.logger.warning(status + " " + url)

    def add_request(self, url, callback, method="GET", **kwargs):
        if url in self.visited:
            return
        if not self.config["allowDuplicates"]:
            self.visited.add(url)
        request = Request(method, url, callback)
        self.pending.put_nowait(request)
        self.log("ADD", url)

    async def load(self):
        try:
            while True:
                request = await self.pending.get()
                self.log("Loading", request.url)
                await self.__request(request)
                self.pending.task_done()
        except asyncio.CancelledError:
            pass

    async def __request(self, request: _Request):
        #print("request url: %s"%request.url)
        async with self.session.request(request.method, request.url) as resp:
            # self.log("Parse",resp.url)
            if callable(request.callback) and asyncio.iscoroutinefunction(request.callback):
                await request.callback(resp)

    async def download(self, src, dst):
        self.log("DOWNLOADING", src + dst)
        async with self.session.request("get", src) as resp:
            with open(dst, "wb") as fd:
                # while True:
                chunk = await resp.content.read()
                #   if not chunk:
                #       break
                # print(len(chunk))
                fd.write(chunk)

    async def __start(self):
        workers = [asyncio.Task(self.load(), loop=self.loop)
                   for _ in range(self.config["concurrent"])]

        await self.pending.join()
        for w in workers:
            w.cancel()

    def start(self, urls, callbacks):
        for url, callback in zip_longest(urls, callbacks, fillvalue=callbacks[len(callbacks) - 1]):
            self.add_request(url, callback)
        self.loop.run_until_complete(self.__start())
