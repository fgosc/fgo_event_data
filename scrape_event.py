#!/usr/bin/env python3
import argparse
import logging
import re
from datetime import datetime as dt
import dataclasses
import json
import unicodedata
from typing import List

import requests
from bs4 import BeautifulSoup

ID_GEM_MIN = 6001
ID_HOLYGRAIL = 7999

logger = logging.getLogger(__name__)
quests = []

url_ce = "https://api.atlasacademy.io/export/JP/nice_equip.json"
url_item = "https://api.atlasacademy.io/export/JP/nice_item.json"
url_item_na = "https://api.atlasacademy.io/export/NA/nice_item.json"
OUTPUT_FILE = "fgo_event.json"

exclude_item = ["Eリアクター", "予備リアクター", "日輪扇子"]
r_get = requests.get(url_item)
item_list = r_get.json()
id2name = {item["id"]: unicodedata.normalize('NFKC', item["name"])
           for item in item_list}
name2id = {unicodedata.normalize('NFKC', item["name"]): item["id"]
           for item in reversed(item_list)}
name2id_rev = {unicodedata.normalize('NFKC', item["name"]): item["id"]
               for item in item_list}
id2type = {item["id"]: item["type"] for item in item_list}
r_get2 = requests.get(url_ce)
ce_list = r_get2.json()
id2name_ce = {item["id"]: unicodedata.normalize('NFKC', item["name"])
              for item in ce_list}
r_get3 = requests.get(url_item_na)
item_eng_list = r_get3.json()
id2name_eng = {item["id"]: item["name"] for item in item_eng_list}


@dataclasses.dataclass
class Item:
    id: int
    name: str
    name_eng: str
    type: str


@dataclasses.dataclass
class Quest:
    name: str
    page_title: str
    url: str
    revival: bool
    openedAt: int
    closedAt: int
    item: List


def parse_date(soup, load_url):
    if load_url == "https://news.fate-go.jp/2015/1731/":
        # can't scrape because the grammar is wrong.
        openedAt = 1445418000
        closedAt = 1446699599
        return openedAt, closedAt
    elif load_url == "https://news.fate-go.jp/2016/np9qnk/":
        # The date data is missing from the site.
        openedAt = 1465977600
        closedAt = 1467176399
        return openedAt, closedAt

    tag_item = soup.select_one('span:contains("イベント開催期間")')
    if tag_item is None:
        tag_item = soup.select_one('span:contains("開催期間")')
    if tag_item is None:
        tag_item = soup.select_one('span.strong:contains("イベント開催")')
    if tag_item is None:
        tag_item = soup.select_one('p:contains("◆イベント開催期間◆")')

    if tag_item is not None:
        tag_item = tag_item.find_next()
        if tag_item.get_text().strip() == "" \
           or tag_item.get_text().strip() == "◆":
            tag_item = tag_item.find_next()
        if tag_item.get_text().strip() == "":
            tag_item = tag_item.find_next()

    if tag_item is not None:
        date_str = tag_item.get_text(strip=True)
        date_str = date_str.replace("）", ")")
        date_str = date_str.replace("（", "(")
        date_str = date_str.replace("：", ":")
        pattern = r"(?P<year>20\d\d)年(?P<open>.+)～(?P<close>.+)まで"
        m = re.search(pattern, date_str)
        if m:
            logger.debug("find")
            year = re.sub(pattern, r"\g<year>", m.group())
            t_open = re.sub(pattern, r"\g<open>", m.group())
            t_open = t_open.replace(" ", "")
            t_open = t_open.replace(")9:", ")09:")
            t_open = re.sub(r"\([^\(\)]*\)", "", t_open)
            close = re.sub(pattern, r"\g<close>", m.group())
            close = close.replace(" ", "")
            close = re.sub(r"\([^\(\)]*\)", "", close)
            # UNIX TIMEに変換
            open_str = year + '年' + t_open + ':00'
            open_str = open_str.replace("AM", "0")
            open_str = open_str.replace(" ", "")
            close_str = year + '年' + close + ':59'
            close_str = close_str.replace("AM", "0")
            time_format = '%Y年%m月%d日%H:%M:%S'
            open_dt = dt.strptime(open_str, time_format)
            close_dt = dt.strptime(close_str, time_format)
            logger.debug(open_dt.timestamp())
            logger.debug(close_dt.timestamp())
            openedAt = int(open_dt.timestamp())
            closedAt = int(close_dt.timestamp())
            logger.debug(openedAt)
            logger.debug(closedAt)
        else:
            logger.debug("not find")
            openedAt = 0
            closedAt = 0
    else:
        openedAt = 0
        closedAt = 0

    return openedAt, closedAt


def parse_discribe_item(soup):
    discribe_item_list = []
    tag_items = [n.get_text() for n in soup.select('.em01')]

    for tag in tag_items:
        if "を装備することで、イベント" in tag \
           or "を装備することでイベント" in tag \
           or "ピックアップされる期間限定概念礼装" in tag:
            # 後者はアイアイアイエー
            pattern = r"(聖晶石召喚|ピックアップ).+を装備することで(|、)(|本)イベント(|収集|専用)アイテム(?P<items>.+)(|それぞれ)の(|ドロップ)獲得数が(増加|アップ)します。"
            i = re.search(pattern, tag)
            if i:
                logger.debug("find item")
                items = re.sub(pattern, r"\g<items>", i.group())
                items = items.replace("｢", "「")
                items = items.replace("｣", "」")
                discribe_item_list += re.findall("(?<=「).+?(?=」)", items)
                logger.debug(discribe_item_list)
            else:
                pattern = r"(|本)イベント(|収集|専用)アイテム(?P<items>.+)(|それぞれ)の(|ドロップ)獲得数が(増加|アップ)します。"
                i = re.search(pattern, tag)
                if i:
                    logger.debug("find item")
                    items = re.sub(pattern, r"\g<items>", i.group())
                    items = items.replace("｢", "「")
                    items = items.replace("｣", "」")
                    discribe_item_list += re.findall("(?<=「).+?(?=」)", items)
                    logger.debug(discribe_item_list)
                else:
                    logger.debug("not find item")
    new_list = []
    for item in discribe_item_list:
        new_list.append(unicodedata.normalize('NFKC', item))
    return new_list


def parse_exchange_item(soup, url):
    if url == "https://news.fate-go.jp/2015/mxxr3e/":
        ex_item_list = ["ネロメダル〔銅〕", "ネロメダル〔銀〕", "ネロメダル〔金〕"]
        return ex_item_list
    elif url == "https://news.fate-go.jp/2015/1967/":
        ex_item_list = ["特選団子", "月見団子"]
        return ex_item_list
    elif url == "https://news.fate-go.jp/2015/1621/":
        ex_item_list = ["平蜘蛛", "曜変天目茶碗", "九十九髪茄子", "本能寺ポイント"]
        return ex_item_list
    elif url == "https://news.fate-go.jp/2016/agtjcj/":
        ex_item_list = ["アルトリウム", "シンクウカーン", "トランGスター", "バンノウレンズ"]
        return ex_item_list
    elif url == "https://news.fate-go.jp/2016/2opbte/" \
            or url == "https://news.fate-go.jp/2017/xjuyrr/":
        ex_item_list = ["材料チョコ", "剣のコインチョコ",  "弓のコインチョコ",
                        "槍のコインチョコ", "騎のコインチョコ", "術のコインチョコ",
                        "殺のコインチョコ", "狂のコインチョコ", "全のコインチョコ",
                        "剣のチョコ型", "弓のチョコ型", "槍のチョコ型",
                        "騎のチョコ型", "術のチョコ型", "殺のチョコ型",
                        "狂のチョコ型"]
        return ex_item_list

    ex_item_list = []
    tag_items = [n.get_text() for n in soup.select('span.strong')]
    if len(tag_items) == 0:
        tag_items = [n.get_text() for n in soup.select('strong')]

    for tag in tag_items:
        if "で交換可能なアイテム" in tag or "で獲得可能なアイテム" in tag:
            item = tag.replace("で交換可能なアイテム", "")
            item = item.replace("で獲得可能なアイテム", "")
            # 安易にsplitするのはまずい
            # items = re.split("[･、]", tag)
            if item == "ダメージポイント":
                continue
            item = unicodedata.normalize('NFKC', item)
            item = item.replace("◆", "")
            if "、" in item:
                tmp = item.split("、")
                for t in tmp:
                    if item not in id2name.values():
                        item = re.sub(r"\([^\(\)]*\)", "", item)
                    ex_item_list.append(t)
            elif "・" in item or "･" in item:
                # アイテム名が存在するかチェックする
                if item in id2name.values():
                    ex_item_list.append(item)
                else:
                    tmp = item.split("・")
                    for t in tmp:
                        ex_item_list.append(t)
            else:
                if item not in id2name.values():
                    item = re.sub(r"\([^\(\)]*\)", "", item)
                ex_item_list.append(item)

    return ex_item_list


def parse_point_item(soup):
    #################################
    # ポイント
    #################################
    point_list = []
    tag_items = [n.get_text() for n in soup.select('.em01')]
    for tag in tag_items:
        if "装備することで" in tag:
            # 閻魔亭
            pattern = r"イベント限定概念礼装.+イベント収集アイテム「(?P<points>.+)」(|それぞれ)の(|ドロップ)獲得(量|数)が(増加|アップ)します。"
            i = re.search(pattern, tag)
            if i:
                logger.debug("find point")
                points = re.sub(pattern, r"\g<points>", i.group())
                points = points.replace("｢", "「")
                points = points.replace("｣", "」")
                points = "「" + points + "」"
                point_list = re.findall("(?<=「).+?(?=」)", points)
                logger.debug(point_list)
            else:
                logger.debug("not find point")

    tag_items = [n.get_text() for n in soup.select('.em01')]
    for tag in tag_items:
        lines = tag.split("\n")
        pattern = r"^(?P<points>.+)の(|総)獲得量が一定量に到達する(と|ごとに)、(|獲得量に応じた)達成報酬を獲得できます。"
        for line in lines:
            i = re.search(pattern, line)
            if i:
                points = re.sub(pattern, r"\g<points>", i.group())
                points = points.replace("｢", "「")
                points = points.replace("｣", "」")
                if not points.startswith("「"):
                    points = "「" + points
                if not points.endswith("」"):
                    points = points + "」"
                point_list = re.findall("(?<=「).+?(?=」)", points)
                logger.debug(point_list)
    if "イベントポイント" in point_list:
        point_list.remove("イベントポイント")
    return point_list


def parse_ticket_item(soup):
    #################################
    # exchange ticket 交換券
    #################################
    ticket_list = []
    tag_items = [n.get_text() for n in soup.select('.em01')]
    for tag in tag_items:
        pattern = r"との交換は(|、)抽選で(おこな|行)われます。"
        p = re.search(pattern, tag)
        if p:
            logger.debug("find ticket")
            pattern = r"イベントクエストで(?P<items>.+)を集め、.+と交換しましょう！"
            t = re.search(pattern, tag)
            if t:
                logger.debug("find")
            else:
                logger.debug("not find")
            tickets = re.sub(pattern, r"\g<items>", t.group())
            tickets = tickets.replace("｢", "「")
            tickets = tickets.replace("｣", "」")
            if not tickets.startswith("「"):
                tickets = "「" + tickets
            if not tickets.endswith("」"):
                tickets = tickets + "」"
            ticket_list = re.findall("(?<=「).+?(?=」)", tickets)
            logger.debug(ticket_list)
    tag_items = [n.get_text() for n in soup.select('p')]
    for tag in tag_items:
        pattern = r"イベントクエストで(?P<items>.+)を集め(|て)、.+からプレゼントを(もら|貰)いましょう！"
        t = re.search(pattern, tag)
        if t:
            tickets = re.sub(pattern, r"\g<items>", t.group())
            tickets = tickets.replace("｢", "「")
            tickets = tickets.replace("｣", "」")
            if not tickets.startswith("「"):
                tickets = "「" + tickets
            if not tickets.endswith("」"):
                tickets = tickets + "」"
            ticket_list += re.findall("(?<=「).+?(?=」)", tickets)
            logger.debug(ticket_list)

    return ticket_list


def parse_dice_item(soup):
    dice_list = []
    tbodys = soup.select('table tbody')
    find_dice = False
    for tbody in tbodys:
        trs = tbody.select("tr")
        for i, tr in enumerate(trs):
            th = tr.select_one("th")
            if i == 0 and th is not None:
                if th.get_text() == "ダイスの種類":
                    find_dice = True
                    continue
                else:
                    break
            if find_dice:
                tds = tr.select_one("td:nth-child(2)")
                dice_list.append(tds.get_text())
                logger.debug(tds.get_text())
        if find_dice:
            break
    return dice_list


def parse_page(load_url):
    html = requests.get(load_url)
    soup = BeautifulSoup(html.content, "html.parser")
    page_title = soup.find(
                    'title'
                    ).text.replace(
                    "  |  Fate/Grand Order 公式サイト", ""
                    )
    revival = False
    if "復刻" in page_title or "ライト版" in page_title:
        revival = True

    for word in ["召喚", "TIPS", "キャンペーン",
                 "重要", "交換可能なアイテムについて",
                 "サーヴァント強化クエスト", "【カルデア広報局より】",
                 "プレゼント", "ログインボーナス", "ミステリーフェア",
                 "【ご報告】", "につきまして", "について", "アンケート",
                 "カルデアボーイズコレクション", "メンテナンス",
                 "お知らせ", "出展情報", "お願い", "公開", "開幕", "端末",
                 "対応", "ぐだテク", "マチ★アソビ", "Anniversary",
                 "サウンドトラック", "開放", "記念", "ぐだぐだお得テクニック",
                 "絆レベル上限開放", "投票", "発売中", "監獄塔", "曜日クエスト",
                 "クラス別サーヴァント戦"]:
        if word in page_title:
            return None
    openedAt, closedAt = parse_date(soup, load_url)
    tag_item = soup.select_one('div.title')
    title_pattern = r"(｢|「)(?P<title>.+)(｣|」)"
    t = re.search(title_pattern, tag_item.get_text())
    if t:
        logger.debug("find title")
        name = re.sub(title_pattern, r"\g<title>", t.group())
    else:
        logger.debug("not find title")
        name = ""

    discribe_items = parse_discribe_item(soup)
    exchange_items = parse_exchange_item(soup, load_url)
    point_items = parse_point_item(soup)
    ticket_items = parse_ticket_item(soup)
    dice_items = parse_dice_item(soup)
    i_list = list(set(discribe_items) | set(exchange_items)
                  | set(point_items) | set(ticket_items)
                  | set(dice_items))
    new_list = []
    for item in i_list:
        if item not in id2name_ce.values() and item not in exclude_item:
            item = item.replace("力のおにぎり", "ちからのおにぎり")
            if revival:
                itemid = name2id_rev[unicodedata.normalize('NFKC', item)]
            else:
                itemid = name2id[unicodedata.normalize('NFKC', item)]
            itemname = id2name[itemid]
            if itemid in id2name_eng.keys():
                itemname_eng = id2name_eng[itemid]
            else:
                itemname_eng = ""
            category = id2type[itemid]
            questitem = Item(itemid, itemname, itemname_eng, category)
            new_list.append(dataclasses.asdict(questitem))

    new_list = sorted(new_list, key=lambda x: x['id'])
    quest = Quest(name, page_title, load_url, revival,
                  openedAt, closedAt, new_list)
    i_list = []
    return quest


def get_pages(url):
    base_url = "https://news.fate-go.jp"
    html = requests.get(url)
    soup = BeautifulSoup(html.content, "html.parser")
    tag_item = soup.select('ul.list_news li a')

    for tag in tag_item:
        load_url = base_url + tag.get("href")
        logger.debug(load_url)
        quest = parse_page(load_url)
        if quest is not None:
            quests.append(dataclasses.asdict(quest))

    tag_pager = soup.select_one('div.pager p.prev a')
    if tag_pager is not None:
        prev_url = base_url + tag_pager.get("href")
        get_pages(prev_url)


def main():
    # Webページを取得して解析する
    news_url = "https://news.fate-go.jp"
    get_pages(news_url)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(quests, f, indent=2, ensure_ascii=False)


if __name__ == '__main__':
    # オプションの解析
    parser = argparse.ArgumentParser(
                description='Image Parse for FGO Battle Results'
                )
    # 3. parser.add_argumentで受け取る引数を追加していく
    parser.add_argument('-l', '--loglevel',
                        choices=('debug', 'info'), default='info')

    args = parser.parse_args()    # 引数を解析
    logging.basicConfig(
        level=logging.INFO,
        format='%(name)s <%(filename)s-L%(lineno)s> [%(levelname)s] %(message)s',
    )
    logger.setLevel(args.loglevel.upper())

    main()
