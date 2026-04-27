from genericpath import exists
import concurrent.futures
import time
import requests
from requests.exceptions import ProxyError, RequestException
import hashlib
from lxml import etree
import os
import random
from datetime import datetime
from datetime import timezone
from datetime import timedelta
import json
import pymysql
from copy import deepcopy
from func_timeout import func_set_timeout
import func_timeout
from dotenv import load_dotenv
import string
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
import threading
from rich.console import Console
from collections import OrderedDict
import traceback
import argparse
import sys

FORCE_AP = None
FORCE_CSC = None
FORCE_MODEM = None
FORCE_STARTBL = None
FORCE_ENDBL = None
FORCE_SUP = None
FORCE_EUP = None
FORCE_SY = None
FORCE_EY = None
parameters = "not none"

load_dotenv()
thread_local = threading.local()
isFirst = True
oldMD5Dict = {}
console = Console()
current_latest_version = "16"  # Current latest Android version number

def printStr(msg):
    console.log(msg)

def getModel():
    ModelDic = {}
    model = args.model
    name = args.model
    modelCode = args.model
    csc = args.csc
    countryCode = []
    for cc in csc.split("|"):
        countryCode.append(cc)
    ModelDic[modelCode] = {"CC": countryCode, "name": name}
    return ModelDic

def getCountryName(cc):
    """
    Get region name by device code
    """
    cc2Country = {
        "CHC": "China",
        "CHN": "China",
        "TGY": "Hong Kong",
        "KOO": "Korea",
        "EUX": "Europe",
        "INS": "India",
        "XAA": "USA",
        "ATT": "USA",
        "TPA": "Panama",
        "ZTO": "Brazil",
        "GTO": "Guatemala",
    }
    if cc in cc2Country.keys():
        return cc2Country[cc]
    else:
        return "Unknown Region"


def get_session():
    if not hasattr(thread_local, "session"):
        thread_local.session = requests.Session()
    return thread_local.session


def requestXML(url, max_retries=3, sleep_sec=1):
    """
    Request XML content
    """
    UA_list = [
        "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/68.0.3440.106 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36 Edg/107.0.0.0",
        "Mozilla/5.0 (Linux; Android 9; SAMSUNG SM-T825Y) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/15.0 Chrome/90.0.4430.210 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/64.0.3282.186 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/62.0.3202.62 Safari/537.36",
        "Mozilla/5.0 (Linux; U; Android 8.1.0; zh-cn; vivo X20A Build/OPM1.171019.011) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/77.0.3865.120 MQQBrowser/12.0 Mobile Safari/537.36 COVC/045730",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 11_0_3 like Mac OS X) AppleWebKit/604.3.5 (KHTML, like Gecko) Version/11.0 MQQBrowser/11.8.3 Mobile/15B87 Safari/604.1 QBWebViewUA/2 QBWebViewType/1 WKType/1",
        "Mozilla/5.0 (Macintosh; U; PPC Mac OS X 10.5; en-US; rv:1.9.2.15) Gecko/20110303 Firefox/3.6.15",
    ]
    headers = {"User-Agent": random.choice(UA_list), "Connection": "close"}
    for attempt in range(1, max_retries + 1):
        try:
            session = get_session()
            response = session.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            return response.content
        except ProxyError as e:
            printStr(f"ProxyError({attempt}/{max_retries}): {e}")
        except RequestException as e:
            printStr(f"RequestException({attempt}/{max_retries}): {e}")
        except Exception as e:
            printStr(f"Error occurred ({attempt}/{max_retries}): {e}")
        if attempt < max_retries:
            time.sleep(sleep_sec)
    return None


def readXML_worker(args):
    """XML read task for a single CC"""
    model, cc = args
    md5list = []
    url = f"https://fota-cloud-dn.ospserver.net/firmware/{cc}/{model}/version.test.xml"
    content = requestXML(url)
    if content is not None:
        xml = etree.fromstring(content)
        if len(xml.xpath("//value//text()")) == 0:
            printStr(f"<{model}> Region code <{cc}> input error!!!")
        else:
            for node in xml.xpath("//value//text()"):
                md5list.append(node)
    return cc, md5list


def readXML(model, modelDic):
    """
    Get MD5 values of official website version codes (multi-threaded version)
    """
    md5Dic = {}
    cc_list = modelDic[model]["CC"]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = pool.map(readXML_worker, [(model, cc) for cc in cc_list])
        for cc, md5list in results:
            if md5list:
                md5Dic[cc] = md5list
    return md5Dic


def char_to_number(char):
    """
    Convert character to corresponding number
    """
    if char.isdigit():
        return int(char)
    elif char.isalpha() and char.isupper():
        return ord(char) - ord("A") + 10
    else:
        raise ValueError("Input must be a character between 0-9 or A-Z")


def get_letters_range(start: str, end: str) -> str:
    """Return string in given range (including end character)"""
    # Get all uppercase letters A-Z
    letters = "0123456789" + string.ascii_uppercase + string.ascii_lowercase
    start_index = letters.find(start)
    end_index = letters.find(end)
    if start_index == -1 or end_index == -1:
        raise ValueError(f"get_letters_range: '{start}' or '{end}' is not in valid character range")
    end_index += 1
    if letters[start_index:end_index] == "":
        raise Exception("String start and end error, please check")
    else:
        return letters[start_index:end_index].upper()


def getFirmwareAddAndRemoveInfo(oldJson: list, newJson: list) -> dict:
    """
    Get firmware version add/remove information
    Args:
        oldJson(dict): Dictionary containing old version MD5s
        newJson(dict): Dictionary containing new version MD5s
    Returns:
        dict: Get added firmware versions via key "added"; get removed firmware versions via key "removed"
    """
    oldSet = set(oldJson)
    newSet = set(newJson)
    info = {}
    info["added"] = newSet - oldSet
    info["removed"] = oldSet - newSet
    return info


def LoadOldMD5Firmware() -> dict:
    """
    Get previously saved firmware version MD5 information
    Returns:
        Historical MD5 encoded firmware information
    """
    MD5VerFilePath = "md5_encoded_firmware_versions.json"

    try:
        # Ensure file exists, create and write empty dict if not
        if not os.path.isfile(MD5VerFilePath):
            with open(MD5VerFilePath, "w", encoding="utf-8") as file:
                json.dump({}, file)
        # Load JSON data from file
        with open(MD5VerFilePath, "r", encoding="utf-8") as file:
            oldFirmwareJson = json.load(file)
    except json.JSONDecodeError as e:
        # If file content is not valid JSON, return empty dict
        printStr(f"JSON parsing error, error message: {e}")
        oldFirmwareJson = {}

    return oldFirmwareJson


def UpdateOldFirmware(newDict: dict):
    """
    Update historical firmware version MD5 information
    Args:
        newDict(dict): New MD5 encoded firmware version numbers
    """
    global oldMD5Dict
    MD5VerFilePath = "md5_encoded_firmware_versions.json"
    # First read historical data
    if os.path.exists(MD5VerFilePath):
        with open(MD5VerFilePath, "r", encoding="utf-8") as f:
            try:
                old_data = json.load(f)
            except Exception:
                old_data = {}
    else:
        old_data = {}

    # Update historical data
    for k, v in newDict.items():
        old_data[k] = v

    # Save
    with open(MD5VerFilePath, "w", encoding="utf-8") as f:
        f.write(json.dumps(old_data, indent=4, ensure_ascii=False))


def WriteInfo(model: str, cc: str, AddAndRemoveInfo: dict, modelDic: dict):
    """
    Record server firmware change information
    Args:
        model(str): Device model information
        cc(str): Device region code
        AddAndRemoveInfo(str): Contains add/remove firmware version information
    """
    global isFirst

def getNowTime() -> str:
    SHA_TZ = timezone(
        timedelta(hours=8),
        name="Asia/Shanghai",
    )
    now = (
        datetime.utcnow()
        .replace(tzinfo=timezone.utc)
        .astimezone(SHA_TZ)
        .strftime("%Y-%m-%d %H:%M")
    )
    return now


def get_next_char(char, alphabet="0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
    """
    Return next character, return None if does not exist
    """
    index = alphabet.find(char)
    if index == -1:
        return None
    # If not the last character, return next character, otherwise return first character
    return alphabet[(index + 1) % len(alphabet)]


def get_pre_char(char, alphabet="0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
    """
    Return previous character, return None if does not exist
    """
    index = alphabet.find(char)
    if index == -1:
        return None
    # If not the first character, return previous character, otherwise return last character
    return alphabet[(index - 1) % len(alphabet)]


# @func_set_timeout(2000)
def DecryptionFirmware(
    model: str, md5Dic: dict, cc: str, modelDic: dict, oldJson
) -> dict:
    printStr(
        f"Starting decryption of <{model} {getCountryName(cc)} version> test firmware",
    )
    md5list = md5Dic[cc]
    url = f"https://fota-cloud-dn.ospserver.net/firmware/{cc}/{model}/version.xml"
    content = requestXML(url)
    if content == None:
        return None

    ccList = {
        "CHC": ["ZC", "CHC", "ZC"],
        "CHN": ["ZC", "CHC", ""],
        "TGY": ["ZH", "OZS", "ZC"],
        "XAA": ["UE", "OYM", "UE"],
        "KOO": ["KS", "OKR", "KS"],
        "TPA": ["PA", "TPA", "PA"],
        "CPW": ["UB", "OWO", "UB"],
        "BVO": ["UB", "OWO", "UB"],
    }

    try:
        xml = etree.fromstring(content)
        if len(xml.xpath("//latest//text()")) == 0:
            # Initialize version number for new device (sem version.xml)
            if cc in ccList.keys():
                latestVer = ""
                latestVerStr = "No official version yet"
                currentOS = "Unknown"
                FirstCode = model.replace("SM-", "") + ccList[cc][0]
                SecondCode = model.replace("SM-", "") + ccList[cc][1]
                ThirdCode = model.replace("SM-", "") + ccList[cc][2]
                startYear = chr(datetime.now().year - 2001 - 5 + ord("A"))
                endYear = "Z"
            else:
                printStr(f"Warning: CSC <{cc}> not found. Trying without them).")
                latestVer = ""
                latestVerStr = "No official version yet"

                if FORCE_AP is not None:
                    FirstCode = model.replace("SM-", "") + FORCE_AP
                if FORCE_CSC is not None:
                    SecondCode = model.replace("SM-", "") + FORCE_CSC
                if FORCE_MODEM is not None:
                    ThirdCode = model.replace("SM-", "") + FORCE_MODEM
                    parameters = None
                currentOS = "Unknown"
        else:
            # Directly get current latest version number information from server
            latestVerStr = xml.xpath("//latest//text()")[0]
            latestVer = latestVerStr.split("/")
            currentOS = xml.xpath("//latest//@o")[0]

            FirstCode = latestVer[0][:-6]
            SecondCode = latestVer[1][:-5]
            ThirdCode = latestVer[2][:-6]

            if FORCE_AP is not None:
                FirstCode = model.replace("SM-", "") + FORCE_AP
            if FORCE_CSC is not None:
                SecondCode = model.replace("SM-", "") + FORCE_CSC
            if FORCE_MODEM is not None:
                ThirdCode = model.replace("SM-", "") + FORCE_MODEM
                parameters = None

            if cc in ccList and parameters is not None:
                FirstCode = model.replace("SM-", "") + ccList[cc][0]
                SecondCode = model.replace("SM-", "") + ccList[cc][1]
                ThirdCode = model.replace("SM-", "") + ccList[cc][2]
                printStr(f"Using custom cclist prefixes: {cc}: {FirstCode}, {SecondCode}, {ThirdCode}")

            startYear = chr(
                datetime.now().year - 2001 - 4 + ord("A")
            )

        Dicts = {model: {cc: {"versions": {}, "latest_test_upload_time": ""}}}
        DecDicts = {}
        oldDicts = {model: {cc: {}}}
        CpVersions = []

        lastVersion1 = ""
        lastVersion2 = ""

        if (
            model in oldJson
            and cc in oldJson[model]
            and "regular_update_test" in oldJson[model][cc]
        ):
            if "None" in oldJson[model][cc]["major_version_test"].split("/")[0]:
                lastVersion1 = oldJson[model][cc]["regular_update_test"].split("/")[0]
            else:
                lastVersion1 = oldJson[model][cc]["regular_update_test"].split("/")[0]
                lastVersion2 = oldJson[model][cc]["major_version_test"].split("/")[0]
            oldDicts[model][cc] = deepcopy(oldJson[model][cc]["versions"])
            seen = set()
            modelVersion = [
                x.split("/")[-1] for x in oldJson[model][cc]["versions"].values()
            ]
            newMV = [x for x in modelVersion if not (x in seen or seen.add(x))][-12:]
            CpVersions = newMV

        startUpdateCount = "A"
        endUpdateCount = "B"
        startBLVersion = "0"
        endBLVersion = "2"

        if lastVersion1:
            startBLVersion = lastVersion1[-5]
            if latestVer:
                startUpdateCount = latestVer[0][-4]
            startYear = lastVersion1[-3]

        if latestVer:
            endBLVersion = get_next_char(latestVer[0][-5])
            endUpdateCount = get_next_char(latestVer[0][-4])
            if latestVer[0][-2] in "JKL":
                endYear = get_next_char(latestVer[0][-3])
            else:
                endYear = latestVer[0][-3]

        alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

        def ensure_char(c, default):
            if c is None or len(c) != 1 or c not in alphabet:
                return default
            return c

        if FORCE_AP is not None and FORCE_MODEM is not None and FORCE_STARTBL is not None and FORCE_ENDBL is not None and FORCE_SUP is not None and FORCE_EUP is not None and FORCE_SY is not None and FORCE_EY is not None and args.output is not None and args.model is not None and args.csc is not None:
            startBLVersion = FORCE_STARTBL
            endBLVersion = FORCE_ENDBL
            startUpdateCount = FORCE_SUP
            endUpdateCount = FORCE_EUP
            startYear = FORCE_SY
            endYear = FORCE_EY
        else:
            print("")
            print("           Some parameters are missing! Running in simple mode.")
            print("")
            
        startBLVersion = ensure_char(startBLVersion, "0")
        endBLVersion = ensure_char(endBLVersion, "2")
        startUpdateCount = ensure_char(startUpdateCount, "A")
        endUpdateCount = ensure_char(endUpdateCount, "B")
        startYear = ensure_char(startYear, chr(datetime.now().year - 2001 - 1 + ord('A')))
        endYear = ensure_char(endYear, get_next_char(startYear) or startYear)
        
        def fix_order(a, b):
            if alphabet.index(a) > alphabet.index(b):
                return b, a
            return a, b

        startBLVersion, endBLVersion = fix_order(startBLVersion, endBLVersion)
        startUpdateCount, endUpdateCount = fix_order(startUpdateCount, endUpdateCount)
        startYear, endYear = fix_order(startYear, endYear)

        updateLst = get_letters_range(startUpdateCount, endUpdateCount)
        updateLst += "Z"

        starttime = time.perf_counter()
        first_run = True
        for i1 in "US":
            for bl_version in get_letters_range(startBLVersion, endBLVersion):
                for update_version in updateLst:
                    for yearStr in get_letters_range(startYear, endYear):
                        for monthStr in get_letters_range("A", "L"):
                            tempCP = CpVersions[-12:].copy()
                            if ThirdCode:
                                for i in range(1, 3):
                                    initCP = ThirdCode + i1 + bl_version + update_version + yearStr + monthStr + str(i)
                                    tempCP.append(initCP)
                            for serialStr in "".join(string.digits[1:] + string.ascii_uppercase):
                                initCP1 = ThirdCode + i1 + bl_version + update_version + yearStr + monthStr + get_pre_char(serialStr)
                                initCP2 = ThirdCode + i1 + bl_version + update_version + yearStr + monthStr + get_pre_char(get_pre_char(serialStr))
                                if initCP1 not in tempCP:
                                    tempCP.append(initCP1)
                                if initCP2 not in tempCP:
                                    tempCP.append(initCP2)
                                randomVersion = bl_version + update_version + yearStr + monthStr + serialStr
                                tempCode = "" if not ThirdCode else ThirdCode + i1 + randomVersion
                                version1 = FirstCode + i1 + randomVersion + "/" + SecondCode + randomVersion + "/" + tempCode

                                if first_run and len(md5list) > 0:
                                    printStr(f"From prefixes generation example: {version1}")
                                    printStr(f"First MD5 found: {md5list[0]}")
                                    test_md5 = hashlib.md5(version1.encode()).hexdigest()
                                    printStr(f"Calculated MD5 example: {test_md5}")
                                    first_run = False

                                md5 = hashlib.md5()
                                md5.update(version1.encode())
                                if md5.hexdigest() in md5list:
                                    DecDicts[md5.hexdigest()] = version1
                                    printStr(f"Added <{model} {getCountryName(cc)}> test firmware: {version1}")
                                    if version1.split("/")[2] and version1.split("/")[2] not in CpVersions and version1.split("/")[2] not in tempCP:
                                        CpVersions.append(version1.split("/")[2])
                                        tempCP.append(version1.split("/")[2])

                                if CpVersions:
                                    for tempCpVersion in tempCP:
                                        version2 = FirstCode + i1 + randomVersion + "/" + SecondCode + randomVersion + "/" + tempCpVersion
                                        if version1 == version2:
                                            continue
                                        if (
                                            model in oldJson
                                            and cc in oldJson[model]
                                            and "versions" in oldJson[model][cc]
                                            and version2 in oldJson[model][cc]["versions"].values()
                                        ):
                                            continue
                                        md5 = hashlib.md5()
                                        md5.update(version2.encode())
                                        if md5.hexdigest() in md5list:
                                            DecDicts[md5.hexdigest()] = version2
                                            printStr(f"<Baseband> Added <{model} {getCountryName(cc)}> test firmware: {version2}")
                                            if version2.split("/")[2] and version2.split("/")[2] not in CpVersions and version2.split("/")[2] not in tempCP:
                                                CpVersions.append(version2.split("/")[2])
                                                tempCP.append(version2.split("/")[2])

                                vc2 = bl_version + "Z" + yearStr + monthStr + serialStr
                                tempCode = "" if not ThirdCode else ThirdCode + i1 + randomVersion
                                version3 = FirstCode + i1 + vc2 + "/" + SecondCode + vc2 + "/" + tempCode
                                if (
                                    model in oldJson
                                    and cc in oldJson[model]
                                    and "versions" in oldJson[model][cc]
                                    and version3 in oldJson[model][cc]["versions"].values()
                                ):
                                    continue
                                md5 = hashlib.md5()
                                md5.update(version3.encode())
                                if md5.hexdigest() in md5list:
                                    DecDicts[md5.hexdigest()] = version3
                                    if version3.split("/")[2] and version3.split("/")[2] not in CpVersions and version3.split("/")[2] not in tempCP:
                                        CpVersions.append(version3.split("/")[2])
                                        tempCP.append(version3.split("/")[2])

                                if CpVersions:
                                    for tempCpVersion in tempCP:
                                        version4 = FirstCode + i1 + vc2 + "/" + SecondCode + vc2 + "/" + tempCpVersion
                                        if version1 == version4:
                                            continue
                                        if (
                                            model in oldJson
                                            and cc in oldJson[model]
                                            and "versions" in oldJson[model][cc]
                                            and version4 in oldJson[model][cc]["versions"].values()
                                        ):
                                            continue
                                        md5 = hashlib.md5()
                                        md5.update(version4.encode())
                                        if md5.hexdigest() in md5list:
                                            DecDicts[md5.hexdigest()] = version4
                                            printStr(f"<Z> Added <{model} {getCountryName(cc)}> test firmware: {version4}")
                                            if version4.split("/")[2] and version4.split("/")[2] not in CpVersions and version4.split("/")[2] not in tempCP:
                                                CpVersions.append(version4.split("/")[2])
                                                tempCP.append(version4.split("/")[2])

        oldDicts[model][cc].update(DecDicts)
        key_func = make_sort_key(oldDicts[model][cc].values())
        sortedList = sorted(oldDicts[model][cc].values(), key=key_func)

        if latestVerStr != "No official version yet" and latestVerStr:
            stableVersion = latestVerStr.split("/")[0]
            currentChar = stableVersion[-4]
            majorChar = get_next_char(stableVersion[-4])
            minorVersion = getLatestVersion(sortedList, currentChar)
            if minorVersion is None:
                minorVersion = "No test firmware found"
            majorVerison = getLatestVersion(sortedList, majorChar)
            if majorVerison is None:
                majorVerison = "No major version test yet"
            else:
                majorChar = get_next_char(stableVersion[-4]) + "Z"
                majorVerison = getLatestVersion(sortedList, majorChar)
            Dicts[model][cc]["regular_update_test"] = minorVersion
            Dicts[model][cc]["major_version_test"] = majorVerison
        else:
            if sortedList:
                Dicts[model][cc]["regular_update_test"] = sortedList[-1]
            else:
                Dicts[model][cc]["regular_update_test"] = "No test firmware found"
            Dicts[model][cc]["major_version_test"] = "No major version test yet"

        Dicts[model][cc]["versions"] = DecDicts
        Dicts[model][cc]["latest_test_upload_time"] = ""
        if DecDicts:
            new_latest1 = Dicts[model][cc]["regular_update_test"].split("/")[0]
            new_latest2 = Dicts[model][cc]["major_version_test"].split("/")[0]
            if new_latest1 != lastVersion1 or new_latest2 != lastVersion2:
                Dicts[model][cc]["latest_test_upload_time"] = getNowTime()
        Dicts[model][cc]["latest_official"] = latestVerStr
        Dicts[model][cc]["official_android_version"] = currentOS

        if currentOS != "Unknown":
            if Dicts[model][cc]["major_version_test"].split("/")[0][-4] == "Z":
                Dicts[model][cc]["test_android_version"] = str(int(currentOS) + 1)
            else:
                if 'None' in Dicts[model][cc]["major_version_test"].split("/")[0]:
                    Dicts[model][cc]["test_android_version"] = str(
                        int(currentOS)
                        + ord(Dicts[model][cc]["regular_update_test"].split("/")[0][-4])
                        - ord(Dicts[model][cc]["latest_official"].split("/")[0][-4])
                    )
                else:
                    Dicts[model][cc]["test_android_version"] = str(
                        int(currentOS)
                        + ord(Dicts[model][cc]["major_version_test"].split("/")[0][-4])
                        - ord(Dicts[model][cc]["latest_official"].split("/")[0][-4])
                    )
        else:
            Dicts[model][cc]["official_android_version"] = current_latest_version
            Dicts[model][cc]["test_android_version"] = current_latest_version

        endtime = time.perf_counter()
        if (
            model in oldJson
            and cc in oldJson[model]
            and "versions" in oldJson[model][cc]
            and oldJson[model][cc]["versions"]
        ):
            sumCount = len(Dicts[model][cc]["versions"]) + len(oldJson[model][cc]["versions"])
            rateOfSuccess = round(sumCount / len(md5list) * 100, 2)
        else:
            rateOfSuccess = round(len(Dicts[model][cc]["versions"]) / len(md5list) * 100, 2)
        Dicts[model][cc]["decryption_percentage"] = f"{rateOfSuccess}%"
        printStr(
            f"<{modelDic[model]['name']} {getCountryName(cc)} version> decryption completed, time: {round(endtime - starttime, 2)}s, success: {rateOfSuccess}%"
        )
        if DecDicts:
            printStr(f"Added {len(DecDicts)} test firmware(s).")
        return Dicts
    except Exception as e:
        printStr(f"Error occurred: {e}")
        traceback.print_exc()
        return None

def make_sort_key(strings):
    order = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    order_map = {c: i for i, c in enumerate(order)}

    def get_tail4(s):
        first_part = s.split("/")[0]
        return first_part[-4:] if len(first_part) >= 4 else first_part

    def key_func(s):
        tail4 = get_tail4(s)
        if len(tail4) < 4:
            return (-1, -1, -1, -1)
        last3 = tail4[-3:]
        fourth = tail4[-4]
        z_priority = 0 if fourth == "Z" else 1
        return tuple(order_map.get(c, 98) for c in last3) + (
            z_priority,
            order_map.get(fourth, 98),
        )

    return key_func


def getLatestVersion(version_list, chars):
    """
    Filter version numbers where the 4th character from the end is in the specified character set, sort by last 3 characters in ascending order, and return the maximum version number.
    :param version_list: List of version number strings
    :param chars: Specified character set for the 4th character from the end (e.g. "ZAB")
    :return: Maximum version number string (None if not found)
    """
    order = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    order_map = {c: i for i, c in enumerate(order)}

    def get_tail4(s):
        first_part = s.split("/")[0]
        return first_part[-4:] if len(first_part) >= 4 else first_part

    # Support filtering by multiple characters
    filtered = [
        s for s in version_list if len(get_tail4(s)) == 4 and get_tail4(s)[0] in chars
    ]
    if not filtered:
        return None

    def last3_key(s):
        tail4 = get_tail4(s)
        return tuple(order_map.get(c, -1) for c in tail4[1:])

    return max(filtered, key=last3_key)

def run():
    # Get related parameter variable data
    global args
    global modelDic, oldMD5Dict, isFirst
    jsonStr = ""
    decDicts = {"last_update_time": getNowTime()}
    if args.output:
        VerFilePath = f"{args.output}.json"
        Ver_mini_FilePath = f"{args.output}_mini.json"
    else:
        VerFilePath = "firmware.json"
        Ver_mini_FilePath = "firmware_mini.json"
    startTime = time.perf_counter()
    if not os.path.exists(VerFilePath):
        with open(VerFilePath, "w") as file:
            file.write("{}")

    with open(VerFilePath, "r", encoding="utf-8") as f:
        jsonStr = f.read()
        oldJson = {}
        if jsonStr != "":
            oldJson = json.loads(jsonStr)
        hasNewVersion = False
        with ProcessPoolExecutor(max_workers=4) as pool:
            future_to_model = {
                pool.submit(getNewVersions, oldJson, model, modelDic, oldMD5Dict): model
                for model in modelDic
            }
            for future in concurrent.futures.as_completed(future_to_model):
                model = future_to_model[future]
                result = future.result()
                if result is not None:
                    hasNew, newMDic = result
                    if hasNew:
                        hasNewVersion = True
                    for m, cc_dict in newMDic.items():
                        if m not in decDicts:
                            decDicts[m] = {}
                        for cc, cc_data in cc_dict.items():
                            decDicts[m][cc] = cc_data
        if hasNewVersion:
            # Firmware update log
            with open(AddTxtPath, "a+", encoding="utf-8") as file:
                for model in modelDic:
                    if (model in decDicts) and (model in oldJson):
                        for cc in modelDic[model]["CC"]:
                            if not cc in oldJson[model] or not cc in decDicts[model]:
                                continue
                            md5Keys = (
                                decDicts[model][cc]["versions"].keys()
                                - oldJson[model][cc]["versions"].keys()
                            )
                            if len(md5Keys) > 0:
                                if isFirst:
                                    file.write(f"***** Record time: {getNowTime()} *****\n")
                                    isFirst = False
                                Str = ""
                                newVersions = {}
                                for md5key in md5Keys:
                                    newVersions[md5key] = decDicts[model][cc]["versions"][
                                        md5key
                                    ]
                                newVersions = dict(
                                    sorted(newVersions.items(), key=lambda x: x[1])
                                )
                                for key, value in newVersions.items():
                                    textStr = "\n" + value
                                    Str += f"{modelDic[model]['name']}-{getCountryName(cc)} version added test firmware version: {value}, corresponding MD5 value: {key}\n"
                                file.write(Str)
            # Update latest version for all models
            with open("latest_versions_by_model.md", "w", encoding="utf-8") as f:
                textStr = ""
                for model in sorted(modelDic.keys()):
                    if (model not in decDicts) or (model not in oldJson):
                        continue
                    for cc in modelDic[model]["CC"]:
                        if not cc in decDicts[model].keys():
                            continue
                        textStr += f"#### {modelDic[model]['name']} {getCountryName(cc)} version: \nOfficial: {decDicts[model][cc]['latest_official']}  \nRegular update test: {decDicts[model][cc]['regular_update_test']}  \nMajor version test: {decDicts[model][cc]['major_version_test']} \n"
                f.write(textStr)
    endTime = time.perf_counter()
    printStr(f"Total time: {round(endTime - startTime, 2)}s")
    # Create deep copy to avoid destroying original data
    firmware_info_mini = deepcopy(decDicts)
    for model_data in firmware_info_mini.values():
        if isinstance(model_data, dict):
            for region_data in model_data.values():
                if isinstance(region_data, dict):
                    region_data.pop("versions", None)
    sorted_firmware_info_mini = OrderedDict()
    for model in sorted(firmware_info_mini.keys()):
        sorted_firmware_info_mini[model] = firmware_info_mini[model]
    with open(Ver_mini_FilePath, "w", encoding="utf-8") as f:
        f.write(json.dumps(sorted_firmware_info_mini, indent=4, ensure_ascii=False))
    # Before writing firmware.json, sort version numbers for each model/region
    for model in decDicts:
        if model == "last_update_time":
            continue
        for region in decDicts[model]:
            if "versions" in decDicts[model][region]:
                ver_dict = decDicts[model][region]["versions"]
                # Get all values
                values = list(ver_dict.values())
                # Generate sort key
                key_func = make_sort_key(values)
                # Sort by value and rebuild dictionary
                sorted_items = sorted(
                    ver_dict.items(), key=lambda item: key_func(item[1])
                )
                decDicts[model][region]["versions"] = dict(sorted_items)
    sorted_decDicts = OrderedDict()
    for model in sorted(decDicts.keys()):
        sorted_decDicts[model] = decDicts[model]
    with open(VerFilePath, "w", encoding="utf-8") as f:
        f.write(json.dumps(sorted_decDicts, indent=4, ensure_ascii=False))


def process_cc(cc, modelDic, oldMD5Dict, md5Dic, oldJson, model):
    newMDic = {model: {}}
    newMD5Dict = {model: {}}
    hasNewVersion = False
    if model in oldJson.keys() and cc in oldJson[model].keys():
        # Copy existing device firmware version content
        newMDic[model][cc] = deepcopy(oldJson[model][cc])
        # Initialize if following keys don't exist
        newMDic[model][cc].setdefault("latest_test_upload_time", "None")
        newMDic[model][cc].setdefault("official_android_version", "")
        newMDic[model][cc].setdefault("test_android_version", "")
    else:
        # Initialize content for new device
        newMDic[model][cc] = {
            "versions": {},
            "major_version_test": "",
            "latest_official": "",
            "latest_version_description": "",
            "decryption_percentage": "",
            "latest_test_upload_time": "None",
            "official_android_version": "",
            "test_android_version": "",
            "region": "",
            "model": "",
            "decryption_count": 0,
        }
    if model in oldMD5Dict and cc in oldMD5Dict[model]:
        # Get add/remove information of MD5 encoded firmware version numbers
        newMD5Dict[model][cc] = deepcopy(oldMD5Dict[model][cc])
        oldMD5Vers = oldMD5Dict[model][cc]["versions"]
        newMD5Vers = md5Dic[cc]
        addAndRemoveInfo = getFirmwareAddAndRemoveInfo(
            oldJson=oldMD5Vers, newJson=newMD5Vers
        )
        WriteInfo(
            model=model, cc=cc, AddAndRemoveInfo=addAndRemoveInfo, modelDic=modelDic
        )
    else:
        # Initialize content for new device
        newMD5Dict[model][cc] = {"versions": {}, "firmware_count": 0}
    newMD5Dict[model][cc]["versions"] = md5Dic[cc]
    newMD5Dict[model][cc]["firmware_count"] = len(md5Dic[cc])

    verDic = DecryptionFirmware(model, md5Dic, cc, modelDic, oldJson)  # Decrypt to get new data
    if verDic is None or model not in verDic or cc not in verDic[model] or "versions" not in verDic[model][cc]:
        return False, {}, {}
    newMDic[model][cc]["latest_official"] = verDic[model][cc]["latest_official"]

    newMDic[model][cc]["region"] = getCountryName(cc)
    newMDic[model][cc]["model"] = modelDic[model]["name"]
    if verDic[model][cc]["major_version_test"] != "":
        newMDic[model][cc]["major_version_test"] = verDic[model][cc]["major_version_test"]
    if verDic[model][cc]["regular_update_test"] != "":
        newMDic[model][cc]["regular_update_test"] = verDic[model][cc]["regular_update_test"]
    if verDic[model][cc]["latest_official"] != "":
        newMDic[model][cc]["latest_official"] = verDic[model][cc]["latest_official"]
    if verDic[model][cc]["latest_test_upload_time"] != "":
        newMDic[model][cc]["latest_test_upload_time"] = verDic[model][cc][
            "latest_test_upload_time"
        ]
    newMDic[model][cc]["official_android_version"] = verDic[model][cc]["official_android_version"]
    newMDic[model][cc]["test_android_version"] = verDic[model][cc]["test_android_version"]

    # Version number description
    ver = newMDic[model][cc]["major_version_test"].split("/")[0]
    ver2 = newMDic[model][cc]["regular_update_test"].split("/")[0]
    
    def is_valid_version_string(s):
        return s and len(s) >= 4 and all(c in "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ" for c in s[-4:])
    
    if is_valid_version_string(ver):
        yearStr = ord(ver[-3]) - 65 + 2001
        monthStr = ord(ver[-2]) - 64
        countStr = char_to_number(ver[-1])
        definitionStr = f"Year {yearStr} Month {monthStr} #{countStr} major version test"
        newMDic[model][cc]["latest_version_description"] = definitionStr
    elif is_valid_version_string(ver2):
        yearStr = ord(ver2[-3]) - 65 + 2001
        monthStr = ord(ver2[-2]) - 64
        countStr = char_to_number(ver2[-1])
        definitionStr = f"Year {yearStr} Month {monthStr} #{countStr} regular update test"
        newMDic[model][cc]["latest_version_description"] = definitionStr
    else:
        newMDic[model][cc]["latest_version_description"] = "None"
    
    if verDic[model][cc]["decryption_percentage"] != "":
        newMDic[model][cc]["decryption_percentage"] = verDic[model][cc]["decryption_percentage"]
    
    if len(verDic[model][cc]["versions"]) == 0:
        return False, newMDic, newMD5Dict
    
    diffModel = set(verDic[model][cc]["versions"].keys()) - set(
        newMDic[model][cc]["versions"].keys()
    )
    if diffModel:
        hasNewVersion = True
        for key in diffModel:
            newMDic[model][cc]["versions"][key] = verDic[model][cc]["versions"][key]
    
    newMDic[model][cc]["versions"] = dict(
        sorted(
            newMDic[model][cc]["versions"].items(), key=lambda x: x[1].split("/")[0][-3:]
        )
    )
    newMDic[model][cc]["decryption_count"] = len(newMDic[model][cc]["versions"])
    return hasNewVersion, newMDic, newMD5Dict


def getNewVersions(oldJson, model, modelDic, oldMD5Dict):
    md5Dic = readXML(model, modelDic)  # Return md5 dictionary containing multiple regional versions
    if len(md5Dic) == 0:
        return
    newMDic = {model: {}}
    md5Dicts_list = []  # Used to collect newMD5Dict from each thread
    hasNewVersion = False
    with ThreadPoolExecutor(max_workers=4) as pool:
        future_to_cc = {
            pool.submit(
                process_cc, cc, modelDic, oldMD5Dict, md5Dic, oldJson, model
            ): cc
            for cc in md5Dic.keys()
        }
        for future in as_completed(future_to_cc):
            result = future.result()
            if result is None:
                continue
            hasNew, newMDic_part, newMD5Dict_part = result
            if hasNew:
                hasNewVersion = True
            for m, cc_dict in newMDic_part.items():
                if m not in newMDic:
                    newMDic[m] = {}
                for cc, cc_data in cc_dict.items():
                    newMDic[m][cc] = cc_data
            md5Dicts_list.append(newMD5Dict_part)
    # Merge newMD5Dict
    mergedMD5Dict = {"last_update_time": getNowTime()}
    mergedMD5Dict[model] = {}
    for md5Dict in md5Dicts_list:
        if model in md5Dict:
            mergedMD5Dict[model].update(md5Dict[model])
    UpdateOldFirmware(mergedMD5Dict)  # Update historical firmware Json information
    return hasNewVersion, newMDic


def init_globals(q):
    global log_queue
    log_queue = q


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Decrypt Samsung firmware test versions.')
    parser.add_argument('--ap', help='Force AP prefix (e.g., UB)')
    parser.add_argument('--cscp', help='Force CSC prefix (e.g., OWO)')
    parser.add_argument('--modem', help='Force modem prefix (e.g., UB)')
    parser.add_argument('--bls', help='Bootloader SW Rev Bit start (e.g., 7)')
    parser.add_argument('--ble', help='Bootloader SW Rev Bit end (e.g., 9)')
    parser.add_argument('--sup', help='Major update version start (e.g., A)')
    parser.add_argument('--eup', help='Major update version end (e.g., E)')
    parser.add_argument('--sy', help='Scan start year (e.g., W)')
    parser.add_argument('--ey', help='Scan end year (e.g., Y)')
    parser.add_argument('--output', help='Base name for output files (without extension)')
    parser.add_argument('--model', help='Model name (e.g., SM-A156M)')
    parser.add_argument('--csc', help='Country Service Code (e.g, ZTO)')
    args = parser.parse_args()
    
    if not args.model and not args.csc:
        if args.ap:
            FORCE_AP = args.ap
        if args.csc:
            FORCE_CSC = args.cscp
        if args.modem:
            FORCE_MODEM = args.modem
        if args.bls:
            FORCE_STARTBL = args.bls
        if args.ble:
            FORCE_ENDBL = args.ble
        if args.sup:
            FORCE_SUP = args.sup
        if args.eup:
            FORCE_EUP = args.eup        # Major version from A to Z
        if args.sy:
            FORCE_SY = args.sy
        if args.ey:
            FORCE_EY = args.ey  


    try:
        oldMD5Dict = LoadOldMD5Firmware()  # Get last MD5 encoded version number data
        try:
            modelDic = getModel()  # Get model information from database
        except Exception as db_error:
            sys.exit("Error: Something went wrong.")
        run()
    except func_timeout.exceptions.FunctionTimedOut:
        printStr("Task timeout, execution exited!")
    except Exception as e:
        printStr(f"Error occurred: {e}")
