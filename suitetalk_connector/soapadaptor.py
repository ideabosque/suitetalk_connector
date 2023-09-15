#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "bibow"

import base64, hmac, hashlib, random, time
from tenacity import retry, wait_exponential, stop_after_attempt

from zeep import Client
from zeep.transports import Transport
from zeep.settings import Settings


class SOAPAdaptor(object):
    """Adaptor connects with SuiteTask SOAP API."""

    version = "2021_2_0"
    wsdl_url_tmpl = "https://{account_id}.suitetalk.api.netsuite.com/wsdl/v{underscored_version}/netsuite.wsdl"

    def __init__(self, logger, **setting):
        self.setting = setting
        self.logger = logger
        self.client = Client(
            self.wsdl_url_tmpl.format(
                underscored_version=self.setting.get("VERSION", self.version),
                account_id=self.setting["ACCOUNT"].lower().replace("_", "-"),
            ),
            transport=Transport(timeout=1000),
            settings=Settings(strict=False, xml_huge_tree=True),
        )

    def generate_timestamp(self):
        return str(int(time.time()))

    def generate_nonce(self, length=20):
        """Generate pseudorandom number"""
        return "".join([str(random.randint(0, 9)) for i in range(length)])

    def get_signature_key(self):
        return "&".join((self.setting["CONSUMER_SECRET"], self.setting["TOKEN_SECRET"]))

    def get_signature_message(self, nonce, timestamp):
        return "&".join(
            (
                self.setting["ACCOUNT"],
                self.setting["CONSUMER_KEY"],
                self.setting["TOKEN_ID"],
                nonce,
                timestamp,
            )
        )

    def get_signature_value(self, nonce, timestamp):
        key = self.get_signature_key()
        message = self.get_signature_message(nonce, timestamp)
        hashed = hmac.new(
            key=key.encode("utf-8"),
            msg=message.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        return base64.b64encode(hashed).decode()

    @property
    def client(self):
        return self._client

    @client.setter
    def client(self, client):
        self._client = client

    @property
    def token_passport(self):
        TokenPassport = self.get_data_type("ns0:TokenPassport")
        TokenPassportSignature = self.get_data_type("ns0:TokenPassportSignature")

        nonce = self.generate_nonce()
        timestamp = self.generate_timestamp()
        token_passport_signature = TokenPassportSignature(
            self.get_signature_value(nonce, timestamp), algorithm="HMAC-SHA256"
        )

        return TokenPassport(
            account=self.setting["ACCOUNT"],
            consumerKey=self.setting["CONSUMER_KEY"],
            token=self.setting["TOKEN_ID"],
            nonce=nonce,
            timestamp=timestamp,
            signature=token_passport_signature,
        )

    @property
    def application_info(self):
        ApplicationInfo = self.get_data_type("ns4:ApplicationInfo")
        application_info = ApplicationInfo(applicationId="")
        return application_info

    def get_data_type(self, data_type):
        return self.client.get_type(data_type)

    @retry(
        reraise=True,
        wait=wait_exponential(multiplier=1, max=60),
        stop=stop_after_attempt(5),
    )
    def get(self, baseRef=None):
        soapheaders = {
            "tokenPassport": self.token_passport,
            "applicationInfo": self.application_info,
        }
        response = self.service.get(baseRef=baseRef, _soapheaders=soapheaders)
        if response["body"]["readResponse"]["status"]["isSuccess"] == True:
            return response["body"]["readResponse"]["record"]
        else:
            statusDetail = response["body"]["readResponse"]["status"]["statusDetail"]
            raise Exception(statusDetail)

    @retry(
        reraise=True,
        wait=wait_exponential(multiplier=1, max=60),
        stop=stop_after_attempt(5),
    )
    def delete(self, baseRef=None):
        soapheaders = {
            "tokenPassport": self.token_passport,
            "applicationInfo": self.application_info,
        }
        response = self.service.delete(baseRef=baseRef, _soapheaders=soapheaders)
        if response["body"]["writeResponse"]["status"]["isSuccess"] == True:
            return True
        else:
            statusDetail = response["body"]["writeResponse"]["status"]["statusDetail"]
            raise Exception(statusDetail)

    @retry(
        reraise=True,
        wait=wait_exponential(multiplier=1, max=60),
        stop=stop_after_attempt(5),
    )
    def add(self, record=None):
        soapheaders = {
            "tokenPassport": self.token_passport,
            "applicationInfo": self.application_info,
        }
        response = self.service.add(record=record, _soapheaders=soapheaders)
        write_response = response["body"]["writeResponse"]
        is_success = write_response["status"]["isSuccess"]

        if not is_success:
            raise Exception(write_response["status"]["statusDetail"])

        updated_record = write_response["baseRef"]
        return updated_record

    @retry(
        reraise=True,
        wait=wait_exponential(multiplier=1, max=60),
        stop=stop_after_attempt(5),
    )
    def update(self, record=None):
        soapheaders = {
            "tokenPassport": self.token_passport,
            "applicationInfo": self.application_info,
        }

        response = self.service.update(record=record, _soapheaders=soapheaders)
        write_response = response["body"]["writeResponse"]
        is_success = write_response["status"]["isSuccess"]

        if not is_success:
            raise Exception(write_response["status"]["statusDetail"])

        updated_record = write_response["baseRef"]
        return updated_record

    @retry(
        reraise=True,
        wait=wait_exponential(multiplier=1, max=60),
        stop=stop_after_attempt(5),
    )
    def upsert(self, record=None):
        soapheaders = {
            "tokenPassport": self.token_passport,
            "applicationInfo": self.application_info,
        }

        response = self.service.upsert(record=record, _soapheaders=soapheaders)
        write_response = response["body"]["writeResponse"]
        is_success = write_response["status"]["isSuccess"]

        if not is_success:
            raise Exception(write_response["status"]["statusDetail"])

        updated_record = write_response["baseRef"]
        return updated_record

    def process_search_result(self, search_result, advance=False):
        is_success = search_result["status"]["isSuccess"]
        total_records = search_result["totalRecords"]
        total_pages = search_result["totalPages"]
        page_index = search_result["pageIndex"]
        search_id = search_result["searchId"]

        if not is_success:
            status_detail = search_result["status"]["statusDetail"]
            raise Exception(status_detail)

        return {
            "search_id": search_id,
            "total_records": total_records,
            "total_pages": total_pages,
            "page_index": page_index,
            "records": (
                search_result["searchRowList"]["searchRow"]
                if search_result["searchRowList"]
                else []
            )
            if advance
            else (
                search_result["recordList"]["record"]
                if search_result["recordList"]
                else []
            ),
        }

    @retry(
        reraise=True,
        wait=wait_exponential(multiplier=1, max=60),
        stop=stop_after_attempt(5),
    )
    def search(self, search_record, search_preferences=None, advance=False):
        soapheaders = {
            "tokenPassport": self.token_passport,
            "applicationInfo": self.application_info,
        }

        if search_preferences:
            soapheaders["searchPreferences"] = search_preferences

        response = self.service.search(
            searchRecord=search_record, _soapheaders=soapheaders
        )
        return self.process_search_result(
            response["body"]["searchResult"], advance=advance
        )

    @retry(
        reraise=True,
        wait=wait_exponential(multiplier=1, max=60),
        stop=stop_after_attempt(5),
    )
    def search_more_with_id(self, search_id, page_index, advance=False):
        soapheaders = {
            "tokenPassport": self.token_passport,
            "applicationInfo": self.application_info,
        }

        response = self.service.searchMoreWithId(
            searchId=search_id, pageIndex=page_index, _soapheaders=soapheaders
        )
        return self.process_search_result(
            response["body"]["searchResult"], advance=advance
        )

    @retry(
        reraise=True,
        wait=wait_exponential(multiplier=1, max=60),
        stop=stop_after_attempt(5),
    )
    def async_search(self, search_record, search_preferences=None, advance=False):
        soapheaders = {
            "tokenPassport": self.token_passport,
            "applicationInfo": self.application_info,
        }

        if search_preferences:
            soapheaders["searchPreferences"] = search_preferences

        response = self.service.asyncSearch(
            searchRecord=search_record, _soapheaders=soapheaders
        )

        async_status_result = response["body"]["asyncStatusResult"]

        return {
            "job_id": async_status_result["jobId"],
            "status": async_status_result["status"],
            "percent_completed": async_status_result["percentCompleted"],
            "est_remaining_duration": async_status_result["estRemainingDuration"],
        }

    @retry(
        reraise=True,
        wait=wait_exponential(multiplier=1, max=60),
        stop=stop_after_attempt(5),
    )
    def check_async_status(self, job_id):
        soapheaders = {
            "tokenPassport": self.token_passport,
            "applicationInfo": self.application_info,
        }

        response = self.service.checkAsyncStatus(jobId=job_id, _soapheaders=soapheaders)
        async_status_result = response["body"]["asyncStatusResult"]

        return {
            "job_id": async_status_result["jobId"],
            "status": async_status_result["status"],
            "percent_completed": async_status_result["percentCompleted"],
            "est_remaining_duration": async_status_result["estRemainingDuration"],
        }

    @retry(
        reraise=True,
        wait=wait_exponential(multiplier=1, max=60),
        stop=stop_after_attempt(5),
    )
    def get_async_result(self, job_id, page_index, advance=False):
        soapheaders = {
            "tokenPassport": self.token_passport,
            "applicationInfo": self.application_info,
        }

        response = self.service.getAsyncResult(
            jobId=job_id, pageIndex=page_index, _soapheaders=soapheaders
        )

        return self.process_search_result(
            response["body"]["asyncResult"]["searchResult"], advance=advance
        )

    @retry(
        reraise=True,
        wait=wait_exponential(multiplier=1, max=60),
        stop=stop_after_attempt(5),
    )
    def get_select_value(self, get_select_value_field_description=None):
        soapheaders = {
            "tokenPassport": self.token_passport,
            "applicationInfo": self.application_info,
        }

        response = self.service.getSelectValue(
            fieldDescription=get_select_value_field_description,
            pageIndex=0,
            _soapheaders=soapheaders,
        )

        select_value_result = response.body.getSelectValueResult
        base_ref_list = select_value_result.baseRefList

        if base_ref_list and base_ref_list.baseRef:
            return base_ref_list.baseRef

        return None

    def get_select_values(self, record_type, field, sublist=None):
        # Create GetSelectValueFieldDescription object
        get_select_value_field_description = self.create_select_value_field_description(
            record_type, field, sublist
        )

        # Get select values
        select_values = self.get_select_value(get_select_value_field_description)

        # Convert select values to a dictionary
        if select_values:
            return {
                select_value.name: select_value.internalId
                for select_value in select_values
            }
        return {}

    def create_select_value_field_description(self, record_type, field, sublist=None):
        GetSelectValueFieldDescription = self.get_data_type(
            "ns0:GetSelectValueFieldDescription"
        )
        get_select_value_field_description = GetSelectValueFieldDescription(
            recordType=record_type, field=field
        )
        if sublist:
            get_select_value_field_description.sublist = sublist
        return get_select_value_field_description

    @retry(
        reraise=True,
        wait=wait_exponential(multiplier=1, max=60),
        stop=stop_after_attempt(5),
    )
    def get_data_center_urls(self):
        soapheaders = {
            "tokenPassport": self.token_passport,
            "applicationInfo": self.application_info,
        }
        response = self.service.getDataCenterUrls(
            account=self.setting["ACCOUNT"], _soapheaders=soapheaders
        )
        return response.body.getDataCenterUrlsResult.dataCenterUrls

    @retry(
        reraise=True,
        wait=wait_exponential(multiplier=1, max=60),
        stop=stop_after_attempt(5),
    )
    def get_deleted(self, get_deleted_filter=None, page_index=1, preferences=None):
        soapheaders = {
            "tokenPassport": self.token_passport,
            "applicationInfo": self.application_info,
        }

        if preferences:
            soapheaders["preferences"] = preferences

        response = self.service.getDeleted(
            getDeletedFilter=get_deleted_filter,
            pageIndex=page_index,
            _soapheaders=soapheaders,
        )

        get_deleted_result = response["body"]["getDeletedResult"]
        is_success = get_deleted_result["status"]["isSuccess"]

        if not is_success:
            raise Exception(get_deleted_result["status"]["statusDetail"])

        total_records = get_deleted_result["totalRecords"]
        total_pages = get_deleted_result["totalPages"]
        page_size = get_deleted_result["pageSize"]

        if total_records > 0:
            records = get_deleted_result["deletedRecordList"]["deletedRecord"]
            self.logger.info(
                f"Total_records/Total_pages {total_records}/{total_pages}: {len(records)} records at page {page_index}."
            )
            return {
                "total_records": total_records,
                "total_pages": total_pages,
                "page_index": page_index,
                "page_size": page_size,
                "records": records,
            }
        else:
            return None

    @property
    def service(self):
        """SOAP Service."""
        version = self.setting.get("VERSION", self.version).replace("_0", "")
        return self.client.create_service(
            "{urn:platform_" + version + ".webservices.netsuite.com}NetSuiteBinding",
            "https://{account_id}.suitetalk.api.netsuite.com/services/NetSuitePort_{version}".format(
                account_id=self.setting["ACCOUNT"].lower().replace("_", "-"),
                version=version,
            ),
        )
