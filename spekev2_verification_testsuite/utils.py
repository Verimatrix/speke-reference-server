import re
import base64
from urllib.parse import urlparse
import xml.etree.ElementTree as ET
from io import StringIO
from collections import Counter
import m3u8
import requests
import pytest

from aws_requests_auth.aws_auth import AWSRequestsAuth
from aws_requests_auth import boto_utils

# FILES USED FOR TESTS
# SpekeV2 test requests for Preset Video 1 and Preset Audio 1 with no Key rotation
GENERIC_WIDEVINE_TEST_FILE = "1_generic_spekev2_dash_widevine_preset_video_1_audio_1_no_rotation.xml"
GENERIC_PLAYREADY_TEST_FILE = "2_spekev2_dash_playready_preset_video_1_audio_1_no_rotation.xml"
WIDEVINE_PLAYREADY_TEST_FILE = "3_spekev2_dash_widevine_playready_preset_video_1_audio_1_no_rotation.xml"
WIDEVINE_PSSH_CPD_TEST_FILE = "7_spekev2_dash_widevine_preset_video_1_audio_1_no_rotation_pssh_cpd.xml"
PLAYREADY_PSSH_CPD_TEST_FILE = "8_spekev2_dash_playready_preset_video_1_audio_1_no_rotation_pssh_cpd.xml"
PLAYREADY_PSSH_HLSSIGNALINGDATA_TEST_FILE = "9_spekev2_dash_playready_preset_video_1_audio_1_no_rotation_pssh_signallingdata.xml"
WRONG_VERSION_TEST_FILE = "4_negative_wrong_version_spekev2_dash_widevine.xml" # Wrong CPIX version in request

SPEKE_V2_REQUEST_HEADERS = {"x-speke-version": "2.0", 'Content-type': 'application/xml'}
SPEKE_V2_MANDATORY_NAMESPACES = {
    "cpix" : "urn:dashif:org:cpix", 
    "pskc": "urn:ietf:params:xml:ns:keyprov:pskc"
}

SPEKE_V2_CONTENTKEY_COMMONENCRYPTIONSCHEME_ALLOWED_VALUES = ["cenc", "cbc1", "cens", "cbcs"]

SPEKE_V2_SUPPORTED_INTENDED_TRACK_TYPES = ['VIDEO', 'AUDIO']

SPEKE_V2_MANDATORY_ELEMENTS_LIST = [
    './{urn:dashif:org:cpix}ContentKeyList',
    './{urn:dashif:org:cpix}DRMSystemList',
    './{urn:dashif:org:cpix}ContentKeyUsageRuleList',
    './{urn:dashif:org:cpix}ContentKey',
    './{urn:dashif:org:cpix}DRMSystem',
    './{urn:dashif:org:cpix}ContentKeyUsageRule'
]

SPEKE_V2_MANDATORY_FILTER_ELEMENTS_LIST = [
    './{urn:dashif:org:cpix}VideoFilter',
    './{urn:dashif:org:cpix}AudioFilter'
]

SPEKE_V2_MANDATORY_ATTRIBUTES_LIST = [
    ['./{urn:dashif:org:cpix}ContentKey', ['kid', 'commonEncryptionScheme']],
    ['./{urn:dashif:org:cpix}DRMSystem', ['kid', 'systemId']],
    ['./{urn:dashif:org:cpix}ContentKeyUsageRule', ['kid', 'intendedTrackType']],
]

SPEKE_V2_GENERIC_RESPONSE_ELEMENT_LIST = [
    '{urn:ietf:params:xml:ns:keyprov:pskc}PlainValue',
    '{urn:ietf:params:xml:ns:keyprov:pskc}Secret',
    '{urn:dashif:org:cpix}Data',
    '{urn:dashif:org:cpix}ContentKey',
    '{urn:dashif:org:cpix}ContentKeyList',
    '{urn:dashif:org:cpix}PSSH',
    '{urn:dashif:org:cpix}DRMSystem',
    '{urn:dashif:org:cpix}DRMSystemList',
    '{urn:dashif:org:cpix}VideoFilter',
    '{urn:dashif:org:cpix}ContentKeyUsageRule',
    '{urn:dashif:org:cpix}AudioFilter',
    '{urn:dashif:org:cpix}ContentKeyUsageRuleList',
    '{urn:dashif:org:cpix}CPIX'
]

SPEKE_V2_GENERIC_RESPONSE_ATTRIBS_DICT = { 
                                            'CPIX': ['contentId', 'version'],
                                            'ContentKey': ['kid', 'commonEncryptionScheme'],
                                            'DRMSystem': ['kid', 'systemId'],
                                            'ContentKeyUsageRule': ['kid', 'intendedTrackType']
                                     }

SPEKE_V2_HLS_SIGNALING_DATA_PLAYLIST_MANDATORY_ATTRIBS = ['media', 'master']

## DRM SYSTEM ID LIST
WIDEVINE_SYSTEM_ID = 'edef8ba9-79d6-4ace-a3c8-27dcd51d21ed'
PLAYREADY_SYSTEM_ID = '9a04f079-9840-4286-ab92-e65be0885f95'

def read_xml_file_contents(filename):
    with open(f"./spekev2_requests/{filename.strip()}", "r") as f:
        return f.read().encode('utf-8')

def speke_v2_request(speke_url, request_data):
    return requests.post(
        url=speke_url,
        auth=get_aws_auth(speke_url),
        data=request_data,
        headers=SPEKE_V2_REQUEST_HEADERS
    )

def get_aws_auth(url):
    api_gateway_netloc = urlparse(url).netloc
    api_gateway_region = re.match(
        r"[a-z0-9]+\.execute-api\.(.+)\.amazonaws\.com",
        api_gateway_netloc
    ).group(1)

    return AWSRequestsAuth(
        aws_host=api_gateway_netloc,
        aws_region=api_gateway_region,
        aws_service='execute-api',
        **boto_utils.get_credentials()
    )

def count_tags(xml_content):
    xml_tags = []
    for element in ET.iterparse(StringIO(xml_content)):
        if type(element) is tuple:
            pos, ele = element
            xml_tags.append(ele.tag)
        else:
            xml_tags.append(element.tag)
    xml_keys = Counter(xml_tags).keys()
    xml_values = Counter(xml_tags).values()
    xml_dict = dict(zip(xml_keys, xml_values))
    return xml_dict

def count_child_element_tags_for_element(parent_element):
    xml_tags = [element.tag for element in parent_element]
    xml_keys = Counter(xml_tags).keys()
    xml_values = Counter(xml_tags).values()
    xml_dict = dict(zip(xml_keys, xml_values))
    return xml_dict

def parse_ext_x_key_contents(text_in_bytes):
    decoded_text = decode_b64_bytes(text_in_bytes)
    return m3u8.loads(decoded_text)

def parse_ext_x_session_key_contents(text_in_bytes):
    decoded_text = decode_b64_bytes(text_in_bytes).replace("#EXT-X-SESSION-KEY:METHOD", "#EXT-X-KEY:METHOD")
    return m3u8.loads(decoded_text)

def decode_b64_bytes(text_in_bytes):
    return base64.b64decode(text_in_bytes).decode('utf-8')