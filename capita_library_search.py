# Copyright 2019-present, B. S. Chambers --- Distributed under GPL version 3

"""Get search information from capitadiscovery based library catalogue websites
by web-scraping with BeautifulSoup.

USAGE:

 $ python -i capita_library_search.py -t "diary of a nobody" -a grossmith -b islington

NOTE: Using -i option to enter into interactive python interpreter after running
the script. This way the search-results object can be queried interactively
after the search is done. If you want it to just print the results to the
terminal and then quit, leave out the -i option.

"""

from requests import get
from requests.exceptions import RequestException
from contextlib import closing
from bs4 import BeautifulSoup
from io import StringIO
import re
import sys
import argparse

def log_error(e):
    """
    It is always a good idea to log errors.
    This function just prints them, but you can
    make it do anything.
    """
    print(e)

def simple_get(url):
    """
    Attempts to get the content at `url` by making an HTTP GET request.
    If the content-type of response is some kind of HTML/XML, return the
    text content, otherwise return None.
    """
    try:
        with closing(get(url, stream=True)) as resp:
            if is_good_response(resp):
                return resp.content
            else:
                return None

    except RequestException as e:
        log_error('Error during requests to {0} : {1}'.format(url, str(e)))
        return None

def is_good_response(resp):
    """
    Returns True if the response seems to be HTML, False otherwise.
    """
    content_type = resp.headers['Content-Type'].lower()
    return (resp.status_code == 200
            and content_type is not None
            and content_type.find('html') > -1)

class CatalogueItem(object):
    """A library catalogue item."""

    def __init__(self):
        self.status = ''
        self.barcode = 0
        self.shelfmark = ''
        self.item_type = ''

    def is_available(self):
        return self.status.lower() == 'available'

    def to_string(self):
        return 'status={} | barcode={} | shelfmark={} | type={}'.format(self.status,
                                                                        self.barcode,
                                                                        self.shelfmark,
                                                                        self.item_type)

class BranchResultItem(object):
    """A search results item's library branch detail."""

    def __init__(self):
        self.name = ''
        self.items = []

    def add_item(self, cat_item):
        "cat_item = a CatalogueItem"
        self.items.append(cat_item)

    def is_available(self):
        for i in self.items:
            if i.is_available():
                return True
        return False

    def to_string(self):
        available = ' (AVAILABLE)' if self.is_available() else ''
        s = StringIO()
        s.write('BRANCH: {}{}\n'.format(self.name, available))
        for i in self.items:
            s.write('... {}\n'.format(i.to_string()))
        return s.getvalue()

class SearchResultItem(object):
    """A search results item."""

    def __init__(self):
        self.item_id = 'default'
        self.title = 'default'
        self.publisher = 'default'
        self.link = 'default'
        self.summary = 'default'
        self.available = 'default'
        self.branches = []

    def add_branch_result(self, bri):
        "bri = a BranchResultItem"
        self.branches.append(bri)

    def to_string(self):
        s = StringIO()
        s.write('ID:        {}\n'.format(self.item_id))
        s.write('TITLE:     {}\n'.format(self.title))
        s.write('PUBLISHER: {}\n'.format(self.publisher))
        s.write('LINK:      {}\n'.format(self.link))
        s.write('SUMMARY:   {}\n'.format(self.summary))
        s.write('AVAILABLE: {}\n'.format(self.available))
        for b in self.branches:
            s.write(b.to_string())
        return s.getvalue()

class CapitaSearch(object):
    """Get search results from CapitaDiscovery Library Catalogue website."""

    capita_url = 'https://capitadiscovery.co.uk/'
    default_borough = 'islington'

    def __init__(self, title='', author='', borough=''):

        self.borough_url = ''
        self.search_url = ''
        self.items_found = []
        self.error_message = ''

        if not (title or author):
            log_error('IslingtonSearch: must supply title and/or author\n')
            return

        self.borough_url = self.capita_url + (borough if borough else self.default_borough) + '/'

        # build search url
        self.search_url = self.borough_url + 'items?query='
        if title:
            self.search_url += '+title%3A%28' + title + '%29'
        if author:
            if title:
                self.search_url += '+AND'
                self.search_url += '+author%3A%28' + author + '%29'
                self.search_url += '#availability'

        # get website
        raw_html = simple_get(self.search_url)
        if not raw_html:
            self.error_message = "could not get web page"
            return

        html = BeautifulSoup(raw_html, 'html.parser')

        # extract info

        for search_results in html.select('div#searchResults'):

            for div in search_results.select('div.summary'):
                new_item = SearchResultItem()

                h2 = div.select('h2.title')
                if h2:
                    a = h2[0].select('a')
                    if a:
                        new_item.title = a[0].get('title', 'NOT FOUND')
                        temp_link = a[0].get('href', 'NOT FOUND')
                        match_obj = re.search(r'items/([0-9]+)\?', temp_link)
                        if match_obj:
                            new_item.item_id = match_obj.group(1)
                            new_item.link = self.borough_url + 'items/' + new_item.item_id

                div_pub = div.select('div.publisher')
                if div_pub:
                    span = div_pub[0].select('span.publisher')
                    if span:
                        new_item.publisher = span[0].text

                div_summ = div.select('div.summarydetail')
                if div_summ:
                    span = div_summ[0].select('span.summarydetail')
                    if span:
                        new_item.summary = span[0].text

                # availability
                html = BeautifulSoup(simple_get(new_item.link), 'html.parser')
                div_avail = html.select('div#availability')
                if div_avail:

                    avail_status = div_avail[0].select('div.status')
                    if avail_status:
                        p_branches = avail_status[0].select('p.branches')
                        if p_branches:
                            new_item.available = p_branches[0].text

                    ul_options = div_avail[0].select('ul.options')
                    if ul_options:
                        li_branches = ul_options[0].select('li')

                        # print('\nLI_BRANCHES: {}\n'.format(li_branches))
                        for li_branch in li_branches:
                            bri = self.getBranchResultItem(li_branch)
                            new_item.add_branch_result(bri)

                self.items_found.append(new_item)

    def getBranchResultItem(self, branch):

        bri = BranchResultItem()

        # <span itemprop="name">
        name_span = branch.findAll('span', {"itemprop" : "name"})
        if name_span:
            bri.name = name_span[0].text

            # <tbody> - table body contains the items
            tbody = branch.select('tbody')
            if tbody:
                # each <tr> is a CatalogueItem
                for row in tbody[0].select('tr'):
                    citem = CatalogueItem()

                    prop = row.findAll('span', {'itemprop' : 'serialNumber'})
                    if prop:
                        citem.barcode = prop[0].text

                    prop = row.findAll('span', {'itemprop' : 'sku'})
                    if prop:
                        citem.shelfmark = prop[0].text

                    prop = row.findAll('td', {'class' : 'loan'})
                    if prop:
                        citem.item_type = prop[0].text

                    prop = row.findAll('td', {'class' : re.compile(r'item-status .*')})
                    if prop:
                        citem.status = prop[0].text
                        citem.status = citem.status.strip()

                    bri.add_item(citem)

        return bri

def show_search(search):
    """Prints summary of a search to standard output.

Arguments:
    search -- a CapitaSearch object
    """
    count = 0
    for item in search.items_found:
        count += 1
        print('ITEM {}:\n{}\n'.format(count, item.to_string()))

    print('{} ITEMS FOUND'.format(len(search.items_found)))
    print('\nUSING SEARCH URL: {}\n'.format(search.search_url))
    print('title = {}'.format(title))
    print('author = {}'.format(author))
    print('borough = {}\n'.format(borough))

    if search.error_message:
        print('ERROR: {}\n'.format(search.error_message))

def do_search(title, author, borough):
    print('\nSEARCHING: title="{}", author="{}", borough="{}"\n'.format(title,
                                                                        author,
                                                                        borough))
    search = CapitaSearch(title, author, borough)
    show_search(search)
    return search

def do_search_from_file(filename):
    print('\nDO SEARCH FROM FILE: \n'.format(filename))
    borough = ""
    author = ""
    title = ""
    search_results = []
    # open the file and process it line by line
    # using 'with' means that the file is properly closed, even if an exception is raised
    with open(filename, 'r') as f:
        for line in f:
            # each line should consist of two parts:
            # 1: a directive specifier (-b, -a or -t)
            # 2: the content
            parts = line.split()
            if len(parts) > 1:

                # get first word of line (it should be a directive specifier)
                parts = line.split()
                directive = parts[0]
                # rest of line is the content
                content = " ".join(parts[1:])

                if directive == '-b':
                    borough = content
                    print("borough set to \"" + borough + '"')

                elif directive == '-a':
                    author = content
                    print("author set to \"" + author + '"')

                elif directive == '-t':
                    title = content
                    print("title set to \"" + title + '"')
                    search = CapitaSearch(title, author, borough)
                    search_results = search_results + [search]
                    show_search(search)

    return search_results

if __name__ == '__main__':
    # using argparse to get the command line args
    parser = argparse.ArgumentParser(description='Search Islington Library Catalogue')
    parser.add_argument('--title', '-t', metavar='T', type=str, nargs=1)
    parser.add_argument('--author', '-a', metavar='A', type=str, nargs=1)
    parser.add_argument('--borough', '-b', metavar='B', type=str, nargs=1)
    parser.add_argument('--filename', '-f', metavar='F', type=str, nargs=1)
    args = parser.parse_args()
    title = args.title
    author = args.author
    borough = args.borough
    filename = args.filename
    # argparse gets the args as lists - let's just take the first elements
    if isinstance(title, list): title = title[0]
    if isinstance(author, list): author = author[0]
    if isinstance(borough, list): borough = borough[0]
    if isinstance(filename, list): filename = filename[0]

    results = []

    if filename:
        results = do_search_from_file(filename)
    else:
        search = do_search(title, author, borough)
        results = [search]
