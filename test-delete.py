# import paramiko
################################################################################
#
# Title - Event Handler for Em7 Runbook
#
# Description - Used for em7 run book action for a given em7 org and open/update
# tickets in SNOW automatically
#
# Author - Marcus Mitchell
#
# Date - 10/7/2016
#
version = "1.015"
#
# Modifications -
# 10.18.2016 - modified SN update and new procedures to remove XML markers
# from event messages that were breaking the API calls.
#
# 10.24.2016 - added GetEventAction procedure
#              added IsEventNewTicketException procedure to allow for new tickets to be created for < minor tickets
#              modified open ticket process to include new tickets even if a ticket in restored status for a device
#              add SNSearchShortDescClose procedure to get previous closed/restored tickets
#              updated SetEm7Creds procedure to include icvue2 string to find
#              added UtcStringToLocal to allow for conversion of em7 event UTC timestamp to local string and remove millisecond component
# 11/7/2016 -  corrected issue of the proper SNOW ticket priorities being set by the event severity and when ticket updated upgrade priority
#              if severity warrants
# 12/12/2016 -  Modified to allow for all events try to be sent to list of EVA boxes first and if fails, send to SNOW directy
################################################################################
import sys
import requests
import StringIO
import re
import random
import json
import urllib
from requests.auth import HTTPBasicAuth
import xml.etree.ElementTree as ET
from requests.auth import HTTPBasicAuth
from collections import namedtuple
import calendar
from datetime import datetime, timedelta
import time

##############################################################################
# Global Values
debugLogging = True
em7Host = ""
em7Uname = ""
em7Passwd = ""

CEUname = "ceTest"
CEPasswd = "ceTest"

# define ticket specific information
custArr = {}
evaHosts = []

evaHosts.append("10.53.128.127")  # eva2
evaHosts.append("10.53.128.118")  # eva1
evaHosts.append("eva2.eloyalty.com")
evaHosts.append("eva1.eloyalty.com")
evaHosts.append("eva4.eloyalty.com")

##############################################################################
#        em7 org                automation status    SNOW Customer org for tickets
#          \/                             \/                      \/
custArr['eLoyalty Infrastructure'] = {"active": "True", "snowOrg": "eLoyalty CCMS Internal"}
# Set the logfile if you need debug logs
if debugLogging is True:
    mylog = em7_snippets.logger("/data/tmp/core_event_handler.log")
else:
    mylog = em7_snippets.logger("/dev/null")
##############################################################################
##############################################################################
# ServiceNow Globals
maxShtDescLen = 80  # max short description length for SNOW
snowOrgName = ""  # snow org to open tickets under
soap_user = 'eloymonitoring'
soap_pw = 'eloyb135nJv1p6'
snow_host = "eloyaltytest.service-now.com"
headers = {'Content-Type': 'text/xml;charset=UTF-8', 'Host': snow_host}
getHeaders = {'Accept': 'application/json', 'Content-Type': 'text/xml;charset=UTF-8', 'Host': snow_host}

u_company = ''
u_short_desc = ''
u_desc = ''
u_assignment_group = ''
u_ip = ''


##############################################################################
def UtcStringToLocal(str):
    dt_obj = datetime.strptime(str, "%Y-%m-%d %H:%M:%S")
    dt_obj = dt_obj - timedelta(hours=5)
    return dt_obj.strftime("%Y-%m-%d %H:%M:%S")


def UtcNow():
    ts = datetime.utcnow()
    ts = (ts - datetime(1970, 1, 1)).total_seconds()
    return ts - 604800


def UtcDaysAgo(numDays):
    numSeconds = numDays * 86400
    ts = datetime.utcnow()
    ts = (ts - datetime(1970, 1, 1)).total_seconds()
    return ts - numSeconds


def UtcHoursAgo(numHours):
    numSeconds = numHours * 3600
    ts = datetime.utcnow()
    ts = (ts - datetime(1970, 1, 1)).total_seconds()
    return ts - numSeconds


def UtcMinsAgo(numMins):
    numSeconds = numMins * 60
    ts = datetime.utcnow()
    ts = (ts - datetime(1970, 1, 1)).total_seconds()
    return ts - numSeconds


def is_dst():
    return bool(time.localtime().tm_isdst)


def utc_to_local(utc_dt):
    # get integer timestamp to avoid precision lost
    timestamp = calendar.timegm(utc_dt.timetuple())
    local_dt = datetime.fromtimestamp(timestamp)
    assert utc_dt.resolution >= timedelta(microseconds=1)
    return local_dt.replace(microsecond=utc_dt.microsecond)


def aslocaltimestr(utc_dt):
    return utc_to_local(utc_dt).strftime('%Y-%m-%d %H:%M:%S.%f %Z%z')


def strtoutc(utc_str):
    utcInt = float(utc_str)
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(utcInt))


def strfind(needle, haystack):
    if (haystack.find(needle) == -1):
        return False
    else:
        return True


######################################################################
## Function - snNewTicket
##
## Description - creates a new ticket in Service Now
##
## Author - jchen
##
## Parameters - company - company to create ticket for
##            - short description - short description line in ticket
##            - desc - detailed description
##            - assignment_group - snow group to receive ticket
##            - ip -
##            - severity
##
## Return Value - ticket # created if successful blank if failure
######################################################################
def snNewTicket(company, short_desc, desc, assignment_group, ip, severity):
    # define local varibles with default value
    global mylog
    returnval = {}

    try:

        impact = '2'  # Define SNOW priorities default for Ticket
        urgency = '2'  # Define SNOW priorities default for Ticket
        if (severity == '2'):  # Set snow priorities given alarm severity
            impact = '2'
            urgency = '2'
        elif (severity == '3'):  # Set snow priorities given alarm severity
            impact = '1'
            urgency = '2'
        elif (severity == '4'):  # Set snow priorities given alarm severity
            impact = '1'
            urgency = '1'

        desc = desc.replace("<", "[").replace(">", "]")

        # build XML for SNOW API call
        print
        "new ticket msg ", desc
        xml = """<?xml version="1.0" encoding="UTF-8"?><soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:inc="http://www.service-now.com/incident"><soapenv:Header/><soapenv:Body><inc:insert><inc:active>true</inc:active><inc:assignment_group>""" + assignment_group + """</inc:assignment_group><inc:caller_id>108680156f1412c03051f941be3ee492</inc:caller_id><inc:category>Software</inc:category><inc:company>""" + company + """</inc:company><inc:contact_type>Monitoring Event</inc:contact_type><inc:description>""" + desc + """</inc:description><inc:impact>""" + impact + """</inc:impact><inc:short_description>""" + short_desc + """</inc:short_description><inc:state>1</inc:state><inc:u_device_ip>""" + ip + """</inc:u_device_ip><inc:u_type>Incident</inc:u_type><inc:u_issue>TBD</inc:u_issue><inc:u_supported_product>UCCE</inc:u_supported_product><inc:u_service_category>Monitoring</inc:u_service_category><inc:urgency>""" + urgency + """</inc:urgency></inc:insert></soapenv:Body></soapenv:Envelope>"""
        print
        "SN New Ticket XML ", xml

        # send xml to SNOW and take response.
        ret = requests.post('https://' + snow_host + '/incident.do?SOAP', data=xml, headers=headers,
                            auth=HTTPBasicAuth(soap_user, soap_pw), verify=False).text
        print
        "SNow New repsonse ", str(ret)

        returnval['number'] = re.search('<number>(.*)</number>', str(ret)).group(1)  # grab ticket number from response
        returnval['sysId'] = re.search('<sys_id>(.*)</sys_id>', str(ret)).group(
            1)  # grab sysid for update from response

    except Exception, e:
        mylog.debug(str(e))
        return ""
    return returnval


######################################################################
## Function - snSearchShortDesc
##
## Description - Search for closed/resolved/restored service now tickets
## with a specific short description
##
## Author - mmitchell
##
## Parameters - msg - search text to find in short description,
##             daysAgo - how many days back to look
##
## Return Value - array of ticket numbers,sys_id pairs that match description
######################################################################
def snSearchShortDesc(msg):
    global mylog
    list_item = []

    try:

        msg = urllib.quote_plus(msg)
        query = "stateNOT%20IN15%2C6%2C7^short_descriptionLIKE" + msg + "^ORDERBYDESCnumber"
        print
        "QUERY ", query
        xml = """<?xml version="1.0" encoding="UTF-8"?><soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:inc="http://www.service-now.com/incident"><soapenv:Header/><soapenv:Body><inc:getRecords><inc:__encoded_query>""" + query + """</inc:__encoded_query></inc:getRecords></soapenv:Body></soapenv:Envelope>"""
        # build URL for SNOW API call
        url = 'https://' + snow_host + "/api/now/v1/table/incident?sysparm_query=" + query

        print
        "Tickets Open Search URL ", url
        ret = requests.get(url, headers=getHeaders, auth=HTTPBasicAuth(soap_user, soap_pw), verify=False).text
        val = ret.encode('utf8', 'ignore')  # encode response
        mylog.debug("SNOW response %s" % str(ret))
        obj = json.loads(val)

        for result in obj['result']:
            mylog.debug("Found open ticket for this message -> " + result['number'])
            item = (result['number'], result['sys_id'], result['impact'], result['urgency'])
            list_item.append(item)





    except Exception, e:
        mylog.debug("Exception snSearchShortDescClosed %s" % str(e))

    return list_item


######################################################################
## Function - snSearchShortDesc
##
## Description - Search for closed/resolved/restored service now tickets
## with a specific short description
##
## Author - mmitchell
##
## Parameters - msg - search text to find in short description,
##             daysAgo - how many days back to look
##
## Return Value - array of ticket numbers,sys_id pairs that match description
######################################################################
def snSearchShortDescClosed(msg, daysAgo):
    global mylog
    list_num = []  # Declares an empty list named list

    try:

        msg = urllib.quote_plus(msg)
        query = "stateIN15%2C6%2C7^short_descriptionLIKE" + msg + "^sys_created_on%3Ejavascript%3Ags.daysAgoStart(" + str(
            daysAgo) + ")^ORDERBYDESCnumber"
        print
        "QUERY ", query
        xml = """<?xml version="1.0" encoding="UTF-8"?><soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:inc="http://www.service-now.com/incident"><soapenv:Header/><soapenv:Body><inc:getRecords><inc:__encoded_query>""" + query + """</inc:__encoded_query></inc:getRecords></soapenv:Body></soapenv:Envelope>"""
        # build URL for SNOW API call
        url = 'https://' + snow_host + "/api/now/v1/table/incident?sysparm_query=" + query

        print
        "Closed Search URL ", url
        ret = requests.get(url, headers=getHeaders, auth=HTTPBasicAuth(soap_user, soap_pw), verify=False).text
        val = ret.encode('utf8', 'ignore')  # encode response
        mylog.debug("SNOW SearchClosed response %s" % str(ret))
        obj = json.loads(val)
        for result in obj['result']:
            mylog.debug("Found Closed/Resolved/Restored ticket for this message -> " + result['number'])
            list_num.append(result['number'])




    except Exception, e:
        mylog.debug("Exception snSearchShortDescClosed %s" % str(e))

    return list_num


######################################################################
## Function - snUpdateTicket
##
## Description - Update existing ticket in SNOW
##
## Author - jchen
##
## Parameters - sysid - sysid of existing ticket
##              note - update to add to notes
##
## Return Value - return ticket sys_id if updated successfully
######################################################################
def snUpdateTicket(sysid, note, severity, impact, urgency):
    global mylog
    try:
        note = note.replace("<", "[").replace(">", "]")
        list_num = []  # Declares an empty list named list
        newImpact = '0'
        newUrgency = '0'
        if (severity == '2'):  # Set snow priorities given alarm severity
            newImpact = '2'
            newUrgency = '2'
        elif (severity == '3'):  # Set snow priorities given alarm severity
            newImpact = '1'
            newUrgency = '2'
        elif (severity == '4'):  # Set snow priorities given alarm severity
            newImpact = '1'
            newUrgency = '1'

        print
        "new impact ", severity, newImpact, newUrgency
        if (newImpact < impact or newUrgency < urgency):  # don't downgrade ticket
            impact = newImpact
            urgency = newUrgency
            print
            "Ticket needs higher priority ", impact, urgency
        else:
            print
            "Ticket not downgraded", impact, urgency
        print
        "Update Everity ", severity, impact, urgency
        xml = """<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:inc="http://www.service-now.com/incident"><soapenv:Header/><soapenv:Body><inc:update><inc:sys_id>""" + sysid + """</inc:sys_id><inc:work_notes>""" + note + """</inc:work_notes><inc:impact>""" + impact + """</inc:impact><inc:urgency>""" + urgency + """</inc:urgency></inc:update></soapenv:Body></soapenv:Envelope>"""

        ret = requests.post('https://' + snow_host + '/incident.do?SOAP', data=xml, headers=headers,
                            auth=HTTPBasicAuth(soap_user, soap_pw), verify=False).text
        number = re.search('<sys_id>(.*)</sys_id>', str(ret)).group(1)
        return number
    except Exception, e:
        mylog.debug("Exception snUpdateTicket %s" % str(e))
        return ''


# ---------------------------------------------------------
# function - em7GetAPI
#
# params - apiCall - text of the em7 API call to make
#
# description - function executes and returns an em7 GET API call
#
# date -
#
# author -
#
# return - string containing json formatted data from
#          em7 API call
# ---------------------------------------------------------
def em7GetAPI(apiCall):
    global em7Uname  # define global variables for local use
    global em7Passwd
    global em7Host
    global mylog
    try:
        url = em7Host + "/api/" + apiCall  # build API url
        mylog.debug("Sending URL => %s" % url)
        responseStr = ""
        headerInfo = {"Accept": "application/json", "Content-Type": "application/xml", "Origin": "http://" + em7Host}
        res = ""
        requests.packages.urllib3.disable_warnings()  # insall self-signed cert ignore package
        res = requests.get("https://" + url, auth=HTTPBasicAuth(em7Uname, em7Passwd), headers=headerInfo,
                           allow_redirects=False, verify=False)  # make URL request
        for line in res:  # iterate through the lines and create a single string
            responseStr += line
    except Exception, e:
        mylog.debug("Exception %s" % str(e))

    return responseStr  # send back to caller


# ---------------------------------------------------------
# function - em7PostAPI
#
# params - apiCall - text of the em7 API call to make
#
# description - function executes and returns an em7 GET API call
#
# date -
#
# author -
#
# return - string containing json formatted data from
#          em7 API call
# ---------------------------------------------------------
def em7PostAPI(apiCall, postData):
    global em7Uname  # define global variables for local use
    global em7Passwd
    global em7Host
    global mylog
    try:
        print
        "EM7 Post call ", postData
        url = em7Host + "/api/" + apiCall  # build API url
        mylog.debug("Sending URL => %s" % url)
        responseStr = ""

        headerInfo = {"Accept": "application/json", "Content-Type": "application/json", "Origin": "http://" + em7Host}
        res = ""
        requests.packages.urllib3.disable_warnings()  # insall self-signed cert ignore package
        res = requests.post("https://" + url, auth=HTTPBasicAuth(em7Uname, em7Passwd), headers=headerInfo,
                            allow_redirects=False, verify=False, data=postData, timeout=10)  # make URL request
        requests.close()
        print
        res
        for line in res:  # iterate through the lines and create a single string
            responseStr += line
    except Exception, e:
        mylog.debug("Exception %s" % str(e))

    return responseStr


def SetEm7Creds(eventArr):
    global em7Uname  # define global variables for local use
    global em7Passwd
    global em7Host
    global mylog
    if (strfind("hcs.int", eventArr["eventURL"])):
        em7Host = "10.38.235.4"
        em7Uname = "svc_adr"
        em7Passwd = "xFnB3LTZZLAfhTjFtYHb"
        mylog.debug("EM7 HOST for event is %s" % em7Host)
    elif (strfind("em7prem", eventArr["eventURL"])):
        em7Host = "10.53.3.150"
        em7Uname = "svc_adr"
        em7Passwd = "xFnB3LTZZLAfhTjFtYHb"
        mylog.debug("EM7 HOST for event is %s" % em7Host)
    elif (strfind("icvue2", eventArr["eventURL"])):
        em7Host = "10.53.3.150"
        em7Uname = "svc_adr"
        em7Passwd = "xFnB3LTZZLAfhTjFtYHb"
        mylog.debug("EM7 HOST for event is %s" % em7Host)


def IsPinging(eventArr):
    returnval = {}
    returnval['RESULT'] = False
    global mylog
    try:
        SetEm7Creds(eventArr)
        apiResp = em7GetAPI("device/" + str(eventArr['device_id']) + "/vitals/latency/data?duration=30m")
        mylog.debug("API Response %s" % apiResp)
        obj = json.loads(apiResp)  # load into JSON object
        objStr = str(obj['data']['d_latency'])
        mylog.debug("Latency values %s " % objStr)
        totalPings = 0
        for time, value in obj['data']['d_latency'].iteritems():
            mylog.debug("ping latency %s " % value)
            value = float(value)
            if (value > 0) and (value <= 1000):
                mylog.debug("Ping Alive at %s " % strtoutc(time))
                totalPings = totalPings + 1

        returnval['totalPings'] = totalPings
        mylog.debug("Total Pings %s" % totalPings)
        if totalPings >= 4:
            mylog.debug("Device is pingable")
            returnval['RESULT'] = True
        else:
            mylog.debug("Device not pingable")
    except Exception, e:
        exceptionStr = e
        mylog.debug("Exception IsPinging %s" % str(e))
    return returnval


def GetEventDetail(eventArr):
    returnval = {}
    returnval['RESULT'] = False
    global mylog
    try:
        SetEm7Creds(eventArr)

        ts = str(UtcDaysAgo(30))
        apiResp = em7GetAPI("device/" + str(eventArr['device_id']) + "/log?limit=10&filter.event_policy=" + eventArr[
            'event_policy_num'] + "&filter.date.min=" + ts)
        mylog.debug("API Response %s" % apiResp)
        obj = json.loads(apiResp)  # load into JSON object
        returnval['total30Days'] = obj['total_matched']

        ts = str(UtcDaysAgo(7))
        apiResp = em7GetAPI("device/" + str(eventArr['device_id']) + "/log?limit=10&filter.event_policy=" + eventArr[
            'event_policy_num'] + "&filter.date.min=" + ts)
        mylog.debug("API Response %s" % apiResp)
        obj = json.loads(apiResp)  # load into JSON object
        returnval['total7Days'] = obj['total_matched']

        ts = str(UtcDaysAgo(1))
        apiResp = em7GetAPI("device/" + str(eventArr['device_id']) + "/log?limit=10&filter.event_policy=" + eventArr[
            'event_policy_num'] + "&filter.date.min=" + ts)
        mylog.debug("API Response %s" % apiResp)
        obj = json.loads(apiResp)  # load into JSON object
        returnval['total1Day'] = obj['total_matched']

        ts = str(UtcHoursAgo(1))
        apiResp = em7GetAPI("device/" + str(eventArr['device_id']) + "/log?limit=10&filter.event_policy=" + eventArr[
            'event_policy_num'] + "&filter.date.min=" + ts)
        mylog.debug("API Response %s" % apiResp)
        obj = json.loads(apiResp)  # load into JSON object
        returnval['total1hour'] = obj['total_matched']

        ts = str(UtcHoursAgo(24))
        apiResp = em7GetAPI("device/" + str(
            eventArr['device_id']) + "/log?limit=25&extended_fetch=true&order.date=desc&filter.date.min=" + ts)
        mylog.debug("API Response %s" % apiResp)
        obj = json.loads(apiResp)  # load into JSON object
        returnval['logs'] = []
        for key, value in iter(sorted(obj['result_set'].iteritems(), reverse=True)):

            if (value['severity'] == "0"):
                value['severity'] = "Healthy"
            elif (value['severity'] == "1"):
                value['severity'] = "Notice"
            elif (value['severity'] == "2"):
                value['severity'] = "Minor"
            elif (value['severity'] == "3"):
                value['severity'] = "Major"
            elif (value['severity'] == "4"):
                value['severity'] = "Critical"
            else:
                value['severity'] = "unk"
            logMsg = value['severity'] + " | " + strtoutc(value['date']) + " | " + value['message']
            item = (key, logMsg)
            returnval['logs'].append(item)

        apiResp = em7GetAPI(
            "event?limit=100&extended_fetch=true&&order.date_last=desc&filter.aligned_resource/device=" + str(
                eventArr['device_id']))
        mylog.debug("API Response %s" % apiResp)
        obj = json.loads(apiResp)  # load into JSON object
        returnval['events'] = []
        for key, value in iter(sorted(obj['result_set'].iteritems(), reverse=True)):

            if (value['severity'] == "0"):
                value['severity'] = "Healthy"
            elif (value['severity'] == "1"):
                value['severity'] = "Notice"
            elif (value['severity'] == "2"):
                value['severity'] = "Minor"
            elif (value['severity'] == "3"):
                value['severity'] = "Major"
            elif (value['severity'] == "4"):
                value['severity'] = "Critical"
            else:
                value['severity'] = "unk"
            eventMsg = value['severity'] + " | " + strtoutc(value['date_last']) + " | " + value['message']
            item = (key, eventMsg)
            returnval['events'].append(item)

        returnval['RESULT'] = True
    except Exception, e:
        exceptionStr = e
        mylog.debug("Exception GetEventDetail %s" % str(e))
    return returnval


def ProcessDeviceAvailability(eventArr):
    try:
        eventArr['searchMsg'] = "Device Failed Availability Check"
    except Exception, e:
        mylog.debug("Exception ProcessDeviceAvailability %s" % str(e))

    return eventArr


def GetEventAction(eventArr):
    returnval = ""
    try:

        if (eventArr['message'].find("reported a collection problem (Explanation: Timeout)") >= 0):
            returnval = "Possible Device Unable to be monitored due to timeouts, validate monitoring connectivity. If still failing, assign to montioring team "
        elif (eventArr['message'].find(
                "reported a collection problem (Explanation: (genError) A general failure occured)") >= 0):
            returnval = "Possible Device Unable to be monitored due to application errors - assign to montioring team"
    except Exception, e:
        mylog.debug("Exception GetEventAction %s" % str(e))

    return returnval;


def ProcessEvent(eventArr):
    returnval = {}
    returnval['RESULT'] = False
    try:
        ####Get basic information
        mylog.debug("Processing Event Message %s" % eventArr['messageFormatted'])
        returnval['snowQueue'] = "snow_gsc"

        if (strfind("DeviceFailedAvailabilityCheck", eventArr['messageFormatted'])):
            eventArr = ProcessDeviceAvailability(eventArr)
            returnval['snowQueue'] = "snow_gsc"

        returnval['pingResults'] = IsPinging(eventArr)  # Get ping information from em7 latency metrics
        if (returnval['pingResults']['RESULT'] == False):
            eventArr['action'] = "Device may be down or network lost"
        else:
            eventArr['action'] = GetEventAction(eventArr)

        returnval['eventDetail'] = GetEventDetail(eventArr)  # Get Event Log metrics from em7 log for device
        returnval['RESULT'] = True
    except Exception, e:
        mylog.debug("Exception ProcessEvent %s" % str(e))

    return returnval


def SendReportPeg(resp, event, ticket, ticketAction):
    global mylog
    try:
        mylog.debug("Sending Report Peg")
        headerInfo = {"Accept": "application/json", "Origin": "http://ausl3adrv2.eloyalty.com"}
        url = "ausl3adrv2.eloyalty.com/adrapi/api/v1/api_monitoring.php?queryType=SnowReportPeg"
        postData = {'snow_ticket': ticket, 'em7org': event['organization'], 'device_name': event['device_name'],
                    'event_msg': event['message'], "ticket_action": ticketAction, "severity": event['severity'],
                    "snow_org": event['snowOrg'], "event_id": event['event_policy_num']}
        requests.packages.urllib3.disable_warnings()  # insall self-signed cert ignore package
        res = requests.post("https://" + url, headers=headerInfo, allow_redirects=False, verify=False, data=postData)
        print
        res
        # need to add new or update to peg
        # need to add event severity to peg
    except Exception, e:
        mylog.debug("Exception SendReportPeg %s" % str(e))


def IsEventNewTicketException(event):
    returnval = False
    if (event['message'].find("reported a collection problem (Explanation: Timeout)") >= 0):
        returnval = True
    elif (event['message'].find(
            "reported a collection problem (Explanation: (genError) A general failure occured)") >= 0):
        returnval = True

    return returnval


def ProcessTicket(resp, event):
    global mylog
    global maxShtDescLen
    mylog.debug("Processing Event %s" % event['event_id'])
    try:
        idMsg = ""
        if event['device_id'] == "0":
            appID = event['appId']
            mylog.debug("appID = " + appID)
            idMsg = "APP ID " + appID
        else:
            devID = event['ipAddr']
            mylog.debug("devId = " + str(devID))
            idMsg = "IP=" + str(devID)

        # desc = "EVT [" + str(event['organization']) + "]|" + idMsg + "|" + str(event['device_id'])
        desc = "EVT|" + str(event['device_name']) + "|" + str(event['device_id']) + "|" + str(event['organization'])
        if len(desc) > maxShtDescLen:
            desc = desc[0:maxShtDescLen - 3]
            desc = desc + "..."

        mylog.debug("DESC MSG -> %s" % desc)
        msg = "-------------------------------------------------\n"
        msg += "Event fired @ " + event['localTimeLastOccur'] + " CST\n"
        msg += "Event Message - " + event['message'] + "\n"
        msg += "Device Address - " + event['ipAddr'] + "\n"

        msg += "Recommended Action:  " + event['action'] + "\n"
        msg += "-----------------------------------------------\n"
        msg += "Ping Data --- \n"
        if (resp['pingResults']['RESULT'] == False):
            msg += "WARNING - Device not Pingable" + "\n"
        elif (resp['pingResults']['RESULT'] == True):
            msg += "Device is Pingable in " + str(
                resp['pingResults']['totalPings']) + " intervals in last 30 minutes" + "\n"
        else:
            msg += "Ping Result Failed / Unknown Results" + "\n"
        msg += "-----------------------------------------------\n"

        addlData = "###Event Occurence Counters##################\n"
        addlData += "30 Day Event Occurence -  " + str(resp['eventDetail']['total30Days']) + "\n"
        addlData += "1 Week Event Occurence -  " + str(resp['eventDetail']['total7Days']) + "\n"
        addlData += "1 Day Event Occurence -  " + str(resp['eventDetail']['total1Day']) + "\n"
        addlData += "##Current Active Events#######################\n"
        for key, value in resp['eventDetail']['events']:
            addlData += value + "\n" + "----------------" + "\n"
        addlData += "#############################################\n"
        addlData += "Recent Monitoring Log Activity ----\n"
        for key, value in resp['eventDetail']['logs']:
            addlData += value + "\n" + "----------------" + "\n"

        mylog.debug("Alert Severity = %s" % event['severity'])
        tickets = snSearchShortDesc(desc)
        mylog.debug("Ticket Search Response - %s" % str(tickets))

        if len(tickets) > 0:
            for ticket in tickets:
                mylog.debug("Ticket updated sys id -> %s" % snUpdateTicket(ticket[1], msg + addlData, event['severity'],
                                                                           ticket[2], ticket[3]))
                postData = '{"ext_ticket_ref":"' + ticket[0] + '"}'
                em7PostAPI("event/" + event['event_id'], postData)
                # SendReportPeg(resp,event,ticket[0],"Update")
        else:
            severity = int(event['severity'])
            if (severity >= 2) or IsEventNewTicketException(event):
                mylog.debug("Creating new ticket")
                mylog.debug("Checking for previous tickets")
                prevTickets = snSearchShortDescClosed(desc, 30)
                if (len(prevTickets) > 0):
                    addlData += "####Previous Tickets for this device#####################\n"
                    for ticket in prevTickets:
                        addlData += ticket + "\n"
                    addlData += "#####################################################\n"

                ticketInfo = snNewTicket(event['snowOrg'], desc, msg, resp['snowQueue'], '', event['severity'])
                mylog.debug("Ticket created ticket# -> %s" % ticketInfo['number'])
                mylog.debug(
                    "Ticket updated sys id -> %s" % snUpdateTicket(ticketInfo['sysId'], addlData, event['severity'],
                                                                   "0", "0"))
                postData = '{"ext_ticket_ref":"' + ticketInfo['number'] + '"}'
                em7PostAPI("event/" + event['event_id'], postData)
                SendReportPeg(resp, event, ticketInfo['number'], "New")
            else:
                if (event['message'].find("reported a collection problem (Explanation: Timeout)") >= 0):
                    print
                    "Found snippet timeout error"
                else:
                    mylog.debug("Alert < Minor no new ticket needed")

    except Exception, e:
        mylog.debug("Exception ProcessTicket %s" % str(e))
        return ''


def FallBack():
    # parse event data in readable dictionary
    eventArr = {}
    eventArr['event_id'] = EM7_VALUES['%e']
    eventArr['device_id'] = EM7_VALUES['%x']
    eventArr['organization'] = EM7_VALUES['%O']
    eventArr['severity'] = EM7_VALUES['%s']
    eventArr['message'] = EM7_VALUES['%M']
    eventArr['messageFormatted'] = eventArr['message'].replace(" ", "")
    eventArr['computer'] = EM7_VALUES['%X']
    eventArr['ipAddr'] = EM7_VALUES['%a']
    eventArr['utcLastOccur'] = EM7_VALUES['%d']
    eventArr['appId'] = EM7_VALUES['%y']
    eventArr['eventURL'] = EM7_VALUES['%H']
    eventArr['event_policy_name'] = EM7_VALUES['%_event_policy_name']
    eventArr['event_policy_num'] = EM7_VALUES['%3']
    eventArr['device_name'] = EM7_VALUES['%X']
    eventArr['localTimeLastOccur'] = UtcStringToLocal(eventArr['utcLastOccur'])
    mylog.debug("###Event Data: %s ####" % (str(eventArr)))
    mylog.debug("Process event for organization %s " % eventArr['organization'])
    eventArr['snowOrg'] = "eLoyalty CCMS Internal"
    mylog.debug("Setting SNOW org to  %s" % eventArr['snowOrg'])
    resp = ProcessEvent(eventArr)
    ProcessTicket(resp, eventArr)


def EVA_PostAPI(CEHost, apiCall, postData):
    global CEUname  # define global variables for local use
    global CEPasswd

    returnval = {}
    returnval['httpCode'] = "-1"
    returnval['response'] = ""

    try:
        mylog.debug("CE Post call %s" % postData)
        url = CEHost + apiCall  # build API url
        mylog.debug("Sending URL => %s" % url)
        responseStr = ""

        headerInfo = {"Connection": "Close", "Accept": "application/json", "Origin": "http://" + CEHost}
        res = ""
        requests.packages.urllib3.disable_warnings()  # insall self-signed cert ignore package
        res = requests.post("https://" + url, auth=HTTPBasicAuth(CEUname, CEPasswd), headers=headerInfo,
                            allow_redirects=False, verify=False, data=postData)
        returnval['httpCode'] = res
        for line in res:  # iterate through the lines and create a single string
            responseStr += line
    except Exception, e:
        mylog.debug("Exception %s" % str(e))
        returnval['excMsg'] = "ERROR - Exception ", str(e)
        returnval['httpCode'] = "-2"
    returnval['response'] = responseStr
    return returnval


#######################################
#
# Main Section
#
#######################################

mylog.debug("##########################################")
mylog.debug("Version %s" % version)
mylog.debug("##########################################")
mylog.debug("Starting SNIPPET ")
# ScienceLogic Event Data
mylog.debug("Event Data: %s" % (str(EM7_VALUES)))

successFlag = False
for host in evaHosts:
    try:
        mylog.debug("Trying EVA HOST %s" % host)
        resp = EVA_PostAPI(host, "/eva/api/events.php?cmd=addEvent", EM7_VALUES)
        mylog.debug("EVA Return")
        print
        resp
        httpCode = str(resp['httpCode'])

        if (httpCode.find("200") >= 0):
            resultStr = str(resp['response'])
            if (resultStr.find("SUCCESS") >= 0):
                mylog.debug("Version %s" % version)
                mylog.debug("SUCCESS - Event Added via host %s" % host)
                successFlag = True
                break
    except Exception, e:
        mylog.debug("Exception ProcessTicket %s" % str(e))

# resp = EVA_PostAPI("eva.eloyalty.com","/eva2.0/api/events.php?cmd=addEvent",EM7_VALUES)
# resp = EVA_PostAPI("10.53.128.143","/eva/api/events.php?cmd=addEvent",EM7_VALUES)
if (successFlag == False):
    mylog.debug("ERROR - EVA Routes failed sending to SNOW direct -> %s" % snow_host)
    FallBack()