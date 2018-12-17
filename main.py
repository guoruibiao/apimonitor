#!/usr/bin python
#coding:utf8
import sys
reload(sys)
sys.setdefaultencoding("utf8")
###############################################
# File Name: main.py
# Author: 郭 璞
# mail: marksinoberg@gmail.com
# Created Time: 四 11/ 1 17:43:26 2018
# Description: Nginx error log monitor.
#              捕捉config配置好的错误日志，解析并整理后，发送到钉钉群组,让开发及时发现并进行bug修复。
###############################################
import re
import os
import json
import time
import hashlib
import urllib2
import commands
import argparse
from collections import defaultdict

msg_template = """
{
    "msgtype": "text",
    "text": {
        "content": "我就是我, 是不一样的烟火"
    },
    "at": {
        "atMobiles": [
            "156xxxx8827",
            "189xxxx8325"
        ],
        "isAtAll": 0
    }
}
"""

def svn_blame(username, passwd, repopath, filepath, linenum):
    """
    使用SVN命令blame出错误代码对应的作者
    """
    cmd = "cd {0} && svn blame {1} --username={2} --password={3} | head -{4} | tail -1 ".format(repopath, filepath, username, passwd, linenum)
    status, output = commands.getstatusoutput(cmd)
    msgarray = output.split("\n")
    msg = msgarray[0]
    # 顶多两行，找出linenum对应的那一行就行
    for item in msgarray:
        if "svn:" in item:
            continue
        else:
            msg = item
    splits = msg.split(" ")
    # 部分日志格式有问题，有的是第二个有的是第5个，干脆都拿了呗
    return str(str(splits[1]) + str(splits[4])).strip("  ")

def extract_line(line=""):
    regpattern = r'.*?PHP message: (.*?) in (.*?) on line (\d*)'
    result = re.findall(re.compile(regpattern), line)
    if result:
        return tuple(result)[0]
    else:
        return tuple()


def read_configs(configpath=""):
    """
    根据给定的配置文件的路径读取配置内容到一个公共的对象中
    """
    configs = None
    if os.path.exists(configpath) == False or str(configpath).endswith(".json") == False:
        print("{0} 文件不存在或者文件名非.json结尾".format(configpath))
    else:
        with open(configpath, "r") as file:
            configs = json.load(file)
            file.close()
    return configs


def tail_logs(logpath, tailnumber):
    """
    每次获取logpath文件的后tailnumber行数据，先进行\r\n等特殊字符的替换
    """
    status, output = commands.getstatusoutput("tail -{0} {1}".format(int(tailnumber), logpath))
    ret = []
    if status == 0:
        output = str(output).replace("\r\n", "").split("[error]")
        if len(output) >= 1:
            ret = output[1:]
    return ret

def md5(*args):
    """
    单纯根据可变参数来计算出对应的md5值
    """
    raw = ",".join([str(item) for item in args])
    m = hashlib.md5()
    m.update(raw)
    hashcode = m.hexdigest()
    return hashcode


def is_error_need_record(configs, md5value, errortuple):
    """
    将计算到的错误信息持久化
    TODO 写到内存中，最后再持久化
    返回值为True则说明未记录过此错误信息
    """
    ret = False
    folder = str(configs['output']['folder'])
    if os.path.exists(folder) == False:
        os.makedirs(folder)
    if str(folder).endswith("/") == False:
        folder = folder + str("/")
    filename = time.strftime(configs['output']['fileformat'], time.localtime()) + str(".json")
    filepath = folder + filename
    if os.path.exists(filepath) == False:
        os.system("touch {0}".format(filepath))
    # 拿到当天的统计，没有则需要更新
    with open(filepath, "r") as readfile:
        content = readfile.read()
        readfile.close()
        # 空文件不能load为json对象
        if content == "":
            content = "{}";
        errors = json.loads(content)
        if md5value not in errors.keys() or errors is {}:
            ret = True
            errors[md5value] = {
                    "description": str(errortuple[0]),
                    "filepath": str(errortuple[1]),
                    "line": str(errortuple[2])
                    }
            # 更新错误到文件中
            with open(filepath, "w") as writefile:
                # json.dump(fp) 会因为errors not JSON serializable 出错
                writefile.write(json.dumps(errors))
                writefile.close()
    return ret


def send_dingtalk(configs, errortuple):
    """
    把抓取到的错误信息整理好之后发送到钉钉群组
    """
    global msg_template
    msg = json.loads(msg_template)
    author = svn_blame(configs['svninfo']['username'], configs['svninfo']['password'], configs['monitor']['repopath'], errortuple[1], errortuple[2])
    maintainer = configs['phones'].get(author, "")
    phone = -1
    name = author
    if maintainer:
        name = maintainer['name']
        phone = maintainer['phone']
    msg['text']['content'] = "检测到NGINX错误\n错误信息为:{0}\n文件全路径:{1}\n出错代码行数:{2}\n代码作者:{3}\n".format(errortuple[0], errortuple[1], errortuple[2], name)
    if phone != -1:
        msg['at']['atMobiles'] = [phone]
    else:
        msg['at']['isAtAll'] = True
    payload = json.dumps(msg)
    url = str(configs['dingtalk_hook'])
    req = urllib2.Request(url, payload, {"Content-Type": "application/json"})
    res = urllib2.urlopen(req)
    res = res.read()

def main(configpath=""):
    configs = read_configs(configpath)
    if configs:
        # 读取一段日志,进行解析处理
        logs = tail_logs(configs['monitor']['filepath'], configs['monitor']['taillines'])
        for line in logs:
            errortuple = extract_line(line)
            md5value = md5(errortuple[0], errortuple[1])
            if is_error_need_record(configs, md5value, errortuple) == True:
                # 需要发送出去的错误信息
                send_dingtalk(configs, errortuple)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='a tool for monitoring nginx error log')
    parser.add_argument("-c", "--config", help="the configuration file patha", required=True)
    args = parser.parse_args()
    main(args.config)
