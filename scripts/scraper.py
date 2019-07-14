#!/usr/bin/python3
# -*- coding: utf-8 -*-
import datetime
import lxml.etree
import os
import requests
import sys

try:
    import logman
except ModuleNotFoundError:
    sys.path.append('.')
    sys.path.append('..')
    import logman
try:
    from scripts import globs
    from scripts import utils
except ModuleNotFoundError:
    import globs
    import utils


def get_individual_atlantsolia_prices():
    relation = globs.ATLANTSOLIA_LOCATION_RELATION
    url = 'https://www.atlantsolia.is/stodvaverd/'
    res = requests.get(url, headers=utils.headers())
    html_text = res.content
    html = lxml.etree.fromstring(html_text, lxml.etree.HTMLParser())
    div_prices = html.find('.//*[@id="content"]/div/div/div/div[2]/div/div/table/tbody')
    prices = {}
    for div_price in div_prices:
        key = relation[div_price[0][0].text]
        bensin95 = float(div_price[1][0].text.replace(',', '.'))
        diesel = float(div_price[2][0].text.replace(',', '.'))
        bensin95_discount = int(
            (bensin95 - globs.ATLANTSOLIA_MINIMUM_DISCOUNT) * 10
        ) / 10.0
        diesel_discount = int(
            (diesel - globs.ATLANTSOLIA_MINIMUM_DISCOUNT) * 10
        ) / 10.0
        if key in globs.ATLANTSOLIA_DISCOUNTLESS_STATIONS:
            bensin95_discount = None
            diesel_discount = None
        prices[key] = {
            'bensin95': bensin95,
            'diesel': diesel,
            'bensin95_discount': bensin95_discount,
            'diesel_discount': diesel_discount
        }
    return prices


def get_global_costco_prices():
    # Costco does not intend to show petrol price on their webpage according to
    # email reply I've received from them, so we have no choice but to hardcode
    # their prices if we wish to include their prices in Gasvaktin.
    # Instead of hardcoding prices in the repo itself like with Dælan last
    # summer I've created a personal Google Docs Spreadsheet to hold their
    # current petrol prices, Simplifies updating prices if away from
    # workstation.
    headers = {
        'Accept': (
            'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,'
            '*/*;q=0.8'
        ),
        'Accept-Encoding': 'gzip, deflate, sdch, br',
        'Accept-Language': 'en-US,en;q=0.8,is;q=0.6,da;q=0.4',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache',
        'User-Agent': utils.random_ua()
    }
    url = (
        'https://docs.google.com/spreadsheets/d/'
        '18xuZbhfInW_6Loua3_4LE7KxbGPsh-_3IFfLpf3uwYE/edit'
    )
    res = requests.get(url, headers=headers)
    res.raise_for_status()
    # <shameless-incredibly-naive-html-parsing>
    bensin = None
    diesel = None
    html_text = res.content.decode('utf-8')
    for line in html_text.split('\n'):
        if line.lstrip().startswith('Bensin,'):
            bensin = float(line.lstrip()[7:].replace(' ', ''))
        if line.lstrip().startswith('Diesel,'):
            diesel = float(line.lstrip()[7:].replace(' ', ''))
        if bensin is not None and diesel is not None:
            break
    if bensin is None or diesel is None:
        err_msg = 'Failed to read costco prices (%s, %s)\n%s ...' % (
            bensin,
            diesel,
            html_text[:10000]
        )
        raise Exception(err_msg)
    # </shameless-incredibly-naive-html-parsing>
    return {
        'bensin95': bensin,
        'diesel': diesel,
        # Costco has no discount program
        'bensin95_discount': None,
        'diesel_discount': None
    }


def get_global_n1_prices():
    url_eldsneyti = 'https://www.n1.is/thjonusta/eldsneyti'
    url_eldsneyti_api = 'https://www.n1.is/umbraco/api/fuel/GetSingleFuelPrice'
    headers = utils.headers()
    session = requests.Session()
    session.get(url_eldsneyti, headers=headers)
    post_data_bensin = 'fuelType=95+Oktan'
    post_data_diesel = 'fuelType=D%C3%ADsel'
    headers_eldsneyti_api = {
        'Accept': '*/*',
        'Accept-Encoding': 'gzip, deflate',
        'Accept-Language': 'en-US,en;q=0.8,is;q=0.6',
        'Connection': 'keep-alive',
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'Host': 'www.n1.is',
        'Origin': 'https://www.n1.is',
        'Referer': 'https://www.n1.is/eldsneyti/',
        'User-Agent': headers['User-Agent'],
        'X-Requested-With': 'XMLHttpRequest'
    }
    headers_eldsneyti_api['Content-Length'] = str(len(post_data_bensin))
    res = session.post(url_eldsneyti_api, data=post_data_bensin, headers=headers_eldsneyti_api)
    bensin95_discount_text = res.content.decode('utf-8')
    headers_eldsneyti_api['Content-Length'] = str(len(post_data_diesel))
    res = session.post(url_eldsneyti_api, data=post_data_diesel, headers=headers_eldsneyti_api)
    diesel_discount_text = res.content.decode('utf-8')
    prices = {}
    prices['bensin95'] = float(bensin95_discount_text.replace('"', '').replace(',', '.'))
    prices['diesel'] = float(diesel_discount_text.replace('"', '').replace(',', '.'))
    prices['bensin95_discount'] = prices['bensin95'] - globs.N1_DISCOUNT
    prices['diesel_discount'] = prices['diesel'] - globs.N1_DISCOUNT
    return prices


def get_global_daelan_prices():
    headers = utils.headers()
    session = requests.Session()
    res = session.get('https://daelan.is/', headers=headers)
    html = lxml.etree.fromstring(res.content.decode('utf-8'), lxml.etree.HTMLParser())
    price_info_container = html.find('.//div[@id="gas-price-info-container"]')
    bensin95 = None
    diesel = None
    for column in price_info_container.findall('.//li'):
        if column.find('.//span').text == 'Dísel':
            diesel_text = column.find('.//em').text.strip()
            if diesel_text.endswith(' kr.'):
                diesel_text = diesel_text[:-4]
            diesel_text = diesel_text.replace(',', '.')
            diesel = float(diesel_text)
        elif column.find('.//span').text == 'Bensín':
            bensin95_text = column.find('.//em').text.strip()
            if bensin95_text.endswith(' kr.'):
                bensin95_text = bensin95_text[:-4]
            bensin95_text = bensin95_text.replace(',', '.')
            bensin95 = float(bensin95_text)
    assert(bensin95 is not None)
    assert(diesel is not None)
    return {
        'bensin95': bensin95,
        'diesel': diesel,
        # Dælan has no discount program
        'bensin95_discount': None,
        'diesel_discount': None
    }


def get_individual_olis_prices():
    url = 'https://www.olis.is/solustadir/thjonustustodvar/eldsneytisverd/'
    res = requests.get(url, headers=utils.headers())
    html = lxml.etree.fromstring(res.content.decode('utf-8'), lxml.etree.HTMLParser())
    data = {
        'stations': {},
        'highest': {'bensin95': None, 'diesel': None}
    }
    price_table = html.find('.//table')  # theres just one table element, let's use that ofc
    for row in price_table.findall('.//tr'):
        if len(row.findall('.//td')) < 3:
            continue
        if row.findall('.//td')[0].text.strip() == '':
            continue
        name = row.findall('.//td')[0].text.strip()
        station_key = globs.OLIS_LOCATION_RELATION[name]
        bensin = None
        if row.findall('.//td')[1].text.strip() != '':
            bensin = float(row.findall('.//td')[1].text.strip().replace(',', '.'))
        diesel = None
        if row.findall('.//td')[2].text.strip() != '':
            diesel = float(row.findall('.//td')[2].text.strip().replace(',', '.'))
        data['stations'][station_key] = {'bensin95': bensin, 'diesel': diesel}
        if data['highest']['bensin95'] is None or data['highest']['bensin95'] < bensin:
            data['highest']['bensin95'] = bensin
        if data['highest']['diesel'] is None or data['highest']['diesel'] < diesel:
            data['highest']['diesel'] = diesel
    assert(data['highest']['bensin95'] is not None)
    assert(data['highest']['diesel'] is not None)
    for name in data['stations']:
        # fallback to highest provided price if for some reason it's not provided ._.
        if data['stations'][name]['bensin95'] is None:
            data['stations'][name]['bensin95'] = data['highest']['bensin95']
        if data['stations'][name]['diesel'] is None:
            data['stations'][name]['diesel'] = data['highest']['diesel']
    prices = {}
    olis_stations = utils.load_json(
        os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            '../stations/olis.json'
        )
    )
    for key in olis_stations:
        if key in data['stations']:
            bensin95 = data['stations'][key]['bensin95']
            diesel = data['stations'][key]['diesel']
        else:
            bensin95 = data['highest']['bensin95']
            diesel = data['highest']['diesel']
        bensin95_discount = int((bensin95 - globs.OLIS_MINIMUM_DISCOUNT) * 10) / 10.0
        diesel_discount = int((diesel - globs.OLIS_MINIMUM_DISCOUNT) * 10) / 10.0
        prices[key] = {
            'bensin95': bensin95,
            'diesel': diesel,
            'bensin95_discount': bensin95_discount,
            'diesel_discount': diesel_discount
        }
    return prices


def get_individual_ob_prices():
    url = 'https://www.ob.is/eldsneytisverd/'
    res = requests.get(url, headers=utils.headers())
    html = lxml.etree.fromstring(res.content.decode('utf-8'), lxml.etree.HTMLParser())
    data = {
        'stations': {},
        'highest': {'bensin95': None, 'diesel': None}
    }
    price_table = html.find('.//table[@id="gas-prices"]')
    for row in price_table.findall('.//tr'):
        if len(row.findall('.//td')) == 0:
            continue
        if row.findall('.//td')[0].get('style') == 'border:0px;':
            continue
        name = row.findall('.//td')[0].text.strip()
        station_key = globs.OB_LOCATION_RELATION[name]
        bensin = float(row.findall('.//td')[1].text.strip().replace(',', '.'))
        diesel = float(row.findall('.//td')[2].text.strip().replace(',', '.'))
        data['stations'][station_key] = {'bensin95': bensin, 'diesel': diesel}
        if data['highest']['bensin95'] is None or data['highest']['bensin95'] < bensin:
            data['highest']['bensin95'] = bensin
        if data['highest']['diesel'] is None or data['highest']['diesel'] < diesel:
            data['highest']['diesel'] = diesel
    prices = {}
    ob_stations = utils.load_json(
        os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            '../stations/ob.json'
        )
    )
    now = datetime.datetime.now()
    end = datetime.datetime.strptime(globs.OB_EXTRA_DISCOUNT_UNTIL, '%Y-%m-%dT%H:%M')
    for key in ob_stations:
        if key in data['stations']:
            bensin95 = data['stations'][key]['bensin95']
            diesel = data['stations'][key]['diesel']
        else:
            bensin95 = data['highest']['bensin95']
            diesel = data['highest']['diesel']
        bensin95_discount = int((bensin95 - globs.OB_MINIMUM_DISCOUNT) * 10) / 10.0
        diesel_discount = int((diesel - globs.OB_MINIMUM_DISCOUNT) * 10) / 10.0
        if key in globs.OB_DISCOUNTLESS_STATIONS:
            bensin95_discount = None
            diesel_discount = None
        if key in globs.OB_EXTRA_DISCOUNT_STATIONS and now < end:
            if bensin95_discount is not None:
                bensin95_discount = int((bensin95 - globs.OB_EXTRA_DISCOUNT_AMOUNT) * 10) / 10.0
            if diesel_discount is not None:
                diesel_discount = int((diesel - globs.OB_EXTRA_DISCOUNT_AMOUNT) * 10) / 10.0
        prices[key] = {
            'bensin95': bensin95,
            'diesel': diesel,
            'bensin95_discount': bensin95_discount,
            'diesel_discount': diesel_discount
        }
    return prices


def get_individual_orkan_prices():
    # Read prices for Orkan and Orkan X stations because they're both on the
    # same webpage.
    url = 'https://www.orkan.is/orkan/orkustodvar/'
    res = requests.get(url, headers=utils.headers())
    html = lxml.etree.fromstring(res.content.decode('utf-8'), lxml.etree.HTMLParser())
    div_element = html.find('.//div[@class="accordion__container"]')
    territories = div_element.findall('.//div[@class="accordion__child"]')
    prices = {}
    key = None
    for territory in territories:
        for station in territory:
            station_name = station[0][0].text.strip()
            bensin95 = float(station[1].text.replace(',', '.'))
            diesel = float(station[2].text.replace(',', '.'))
            if station_name in globs.ORKAN_LOCATION_RELATION:
                key = globs.ORKAN_LOCATION_RELATION[station_name]
            elif station_name in globs.ORKAN_X_LOCATION_RELATION:
                key = globs.ORKAN_X_LOCATION_RELATION[station_name]
            else:
                continue
            # Orkan X stations have key starting with "ox", while ordinary
            # Orkan statins have keys starting with "or"
            bensin95_discount = None
            diesel_discount = None
            if key.startswith('or'):
                # Orkan has a 3-step discount system controlled by your
                # spendings on gas from them the month before
                # See more info here: https://www.orkan.is/Afslattarthrep
                # For consistency we just use the minimum default discount
                bensin95_discount = bensin95 - globs.ORKAN_MINIMUM_DISCOUNT
                diesel_discount = diesel - globs.ORKAN_MINIMUM_DISCOUNT
            if key in globs.ORKAN_DISCOUNTLESS_STATIONS:
                bensin95_discount = None
                diesel_discount = None
            prices[key] = {
                'bensin95': bensin95,
                'diesel': diesel,
                'bensin95_discount': bensin95_discount,
                'diesel_discount': diesel_discount
            }
    # TEMPORARY_FIX while three former Skeljungur stations are missing from the
    # list of stations on Orkan webpage
    for key in ['or_053', 'or_054', 'or_055']:
        if key not in prices:
            prices[key] = prices['or_000'].copy()
            if key in ['or_054', 'or_055']:
                # diesel currently 1 ISK more expensive on these two stations
                prices[key]['diesel'] += 1
                prices[key]['diesel_discount'] += 1
    # /TEMPORARY_FIX
    return prices


def testrun(selection):
    if logman.Logger is None:
        logman.init(role='cli', log_to_file=False)
    run_all = ('all' in selection)
    if run_all or 'ao' in selection:
        logman.info('Atlantsolía')
        logman.info(get_individual_atlantsolia_prices())
    if run_all or 'co' in selection:
        logman.info('Costco')
        logman.info(get_global_costco_prices())
    if run_all or 'dn' in selection:
        logman.info('Dælan')
        logman.info(get_global_daelan_prices())
    if run_all or 'n1' in selection:
        logman.info('N1')
        logman.info(get_global_n1_prices())
    if run_all or 'ol' in selection:
        logman.info('Olís')
        logman.info(get_individual_olis_prices())
    if run_all or 'ob' in selection:
        logman.info('ÓB')
        logman.info(get_individual_ob_prices())
    if run_all or 'or' in selection or 'ox' in selection:
        logman.info('Orkan (including Orkan X)')
        logman.info(get_individual_orkan_prices())


if __name__ == '__main__':
    testrun(['all'])
