#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "bibow"

import re
from datetime import datetime, timedelta
from pytz import timezone
from .soapadaptor import SOAPAdaptor
from functools import reduce

datetime_format = "%m/%d/%Y %H:%M:%S"
datetime_format_regex = re.compile(r"^\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}$")


class SOAPConnector(object):
    def __init__(self, logger, **setting):
        self.logger = logger
        self.setting = setting
        self.transaction_update_restrict_attributes = setting["NETSUITEMAPPINGS"][
            "transaction_update_restrict_attributes"
        ]
        self.transaction_data_type = setting["NETSUITEMAPPINGS"][
            "transaction_data_type"
        ]
        self.transaction_item_data_type = setting["NETSUITEMAPPINGS"][
            "transaction_item_data_type"
        ]
        self.transaction_item_list_data_type = setting["NETSUITEMAPPINGS"][
            "transaction_item_list_data_type"
        ]
        self.person_update_restrict_attributes = setting["NETSUITEMAPPINGS"][
            "person_update_restrict_attributes"
        ]
        self.person_data_type = setting["NETSUITEMAPPINGS"]["person_data_type"]
        self.person_addressbook_list_data_type = setting["NETSUITEMAPPINGS"][
            "person_addressbook_list_data_type"
        ]
        self.person_addressbook_data_type = setting["NETSUITEMAPPINGS"][
            "person_addressbook_data_type"
        ]
        self.item_data_type = setting["NETSUITEMAPPINGS"]["item_data_type"]
        self.lookup_select_values = setting["NETSUITEMAPPINGS"]["lookup_select_values"]
        self.lookup_record_fields = setting["NETSUITEMAPPINGS"]["lookup_record_fields"]
        self.lookup_join_fields = setting["NETSUITEMAPPINGS"]["lookup_join_fields"]
        self.custom_records = setting["NETSUITEMAPPINGS"]["custom_records"]
        self.item_detail_record_types = setting["NETSUITEMAPPINGS"][
            "item_detail_record_types"
        ]
        self.inventory_detail_record_types = setting["NETSUITEMAPPINGS"][
            "inventory_detail_record_types"
        ]
        self.transaction_update_statuses = setting["NETSUITEMAPPINGS"].get(
            "transaction_update_statuses", {}
        )
        self._soap_adaptor = None

    @property
    def soap_adaptor(self):
        if self._soap_adaptor is None:
            self._soap_adaptor = SOAPAdaptor(self.logger, **self.setting)
        return self._soap_adaptor

    @soap_adaptor.setter
    def soap_adaptor(self, soap_adaptor):
        self._soap_adaptor = soap_adaptor

    @soap_adaptor.deleter
    def soap_adaptor(self):
        del self._soap_adaptor

    def get_data_type(self, data_type):
        return self.soap_adaptor.get_data_type(data_type)

    def search(self, search_record, search_preferences=None, advance=False):
        return self.soap_adaptor.search(
            search_record, search_preferences=search_preferences, advance=advance
        )

    def add(self, record):
        return self.soap_adaptor.add(record)

    def update(self, record, record_type=None):
        return self.soap_adaptor.update(record)

    def get_select_values(self, record_type, field, sublist=None):
        return self.soap_adaptor.get_select_values(record_type, field, sublist=sublist)

    def get_deleted(self, get_deleted_filter=None, page_index=0, preferences=None):
        return self.soap_adaptor.get_deleted(
            get_deleted_filter=get_deleted_filter,
            page_index=page_index,
            preferences=preferences,
        )

    def get_select_value_id(self, value, field, record_type=None, sublist=None):
        try:
            if self.lookup_select_values[field].get(
                "values"
            ) and self.lookup_select_values[field]["values"].get(value):
                return self.lookup_select_values[field]["values"].get(value)

            if self.lookup_select_values[field].get("record_type"):
                return self.get_record_id(
                    self.lookup_select_values[field]["record_type"],
                    self.lookup_select_values[field]["field"],
                    value,
                )

            select_values = self.get_select_values(record_type, field, sublist=sublist)
            id = select_values.get(value)
            assert (
                id is not None
            ), f"Cannot find the select value ({value}) with the field ({field}) and record type ({record_type})."

            return id
        except:
            raise Exception(
                f"Cannot find the field ({field}) and record type ({record_type}) in the configuration."
            )

    def get_record(self, record_type, id, use_external_id=False):
        RecordRef = self.get_data_type("ns0:RecordRef")
        kwargs = {"internalId": id, "type": record_type}
        if use_external_id:
            kwargs = {"externalId": id, "type": record_type}

        recordRef = RecordRef(**kwargs)
        return self.soap_adaptor.get(baseRef=recordRef)

    def get_record_id(self, record_type, field, value):
        if record_type.find("customlist") == 0:
            record = self.get_custom_list(record_type)
            if record:
                return {
                    element.value: element.valueId
                    for element in record.customValueList.customValue
                }.get(value)
            return None

        if record_type.find("customrecord") == 0:
            rec_type_id = self.custom_records.get(record_type)
            record = self.get_custom_record(rec_type_id, field, value)
            if record:
                return record.internalId
            return None

        if record_type in self.lookup_record_fields.keys():
            record_lookup = self.lookup_record_fields.get(record_type)
            if field == record_lookup["field"]:
                record = self.get_record_by_lookup(
                    record_type, record_lookup["search_data_type"], field, value
                )
                if record:
                    return record.internalId
                return None
            raise Exception(
                f"{field} is not match with the configuration ({record_lookup['field']}) of the record_look!!!"
            )

        raise Exception("Miss variables to look up record_id!!!")

    def get_custom_list(self, script_id):
        SearchPreferences = self.get_data_type("ns4:SearchPreferences")
        CustomListSearchBasic = self.get_data_type("ns5:CustomListSearchBasic")
        SearchStringField = self.get_data_type("ns0:SearchStringField")

        search_preferences = SearchPreferences(bodyFieldsOnly=False)
        search_record = CustomListSearchBasic(
            **{
                "scriptId": SearchStringField(searchValue=script_id, operator="is"),
            }
        )
        records = self.search(search_record, search_preferences=search_preferences)
        if records is not None:
            return records[-1]
        return None

    def get_custom_record(self, rec_type_id, field, value):
        RecordRef = self.get_data_type("ns0:RecordRef")
        SearchPreferences = self.get_data_type("ns4:SearchPreferences")
        CustomRecordSearchBasic = self.get_data_type("ns5:CustomRecordSearchBasic")
        SearchStringField = self.get_data_type("ns0:SearchStringField")
        SearchMultiSelectField = self.get_data_type("ns0:SearchMultiSelectField")

        search_preferences = SearchPreferences(bodyFieldsOnly=False)
        record_ref = RecordRef(internalId=rec_type_id)
        if field == "internalId":
            search_record = CustomRecordSearchBasic(
                **{
                    "recType": record_ref,
                    field: SearchMultiSelectField(
                        searchValue=[RecordRef(internalId=value)],
                        operator="anyOf",
                    ),
                }
            )
        else:
            search_record = CustomRecordSearchBasic(
                **{
                    "recType": record_ref,
                    field: SearchStringField(searchValue=value, operator="is"),
                }
            )
        records = self.search(search_record, search_preferences=search_preferences)
        if records is not None:
            return records[-1]
        return None

    def get_custom_records(self, rec_type_id, **kwargs):
        SearchPreferences = self.get_data_type("ns4:SearchPreferences")
        CustomRecordSearchBasic = self.get_data_type("ns5:CustomRecordSearchBasic")
        RecordRef = self.get_data_type("ns0:RecordRef")
        SearchDateField = self.get_data_type("ns0:SearchDateField")

        cut_date = kwargs.get("cut_date")
        end_date = kwargs.get("end_date")
        limit = int(kwargs.get("limit", 100))
        hours = float(kwargs.get("hours", 0))

        search_preferences = SearchPreferences(bodyFieldsOnly=False)

        begin = datetime.strptime(cut_date, "%Y-%m-%dT%H:%M:%S%z")
        if hours == 0:
            end = datetime.strptime(end_date, "%Y-%m-%dT%H:%M:%S%z")
        else:
            end = begin + timedelta(hours=hours)

        record_ref = RecordRef(internalId=rec_type_id)
        search_record = CustomRecordSearchBasic(
            recType=record_ref,
            lastModified=SearchDateField(
                searchValue=begin, searchValue2=end, operator="within"
            ),
        )
        records = []
        _records = self.search(search_record, search_preferences=search_preferences)

        if _records is None:
            return records

        _records = sorted(_records, key=lambda x: x["lastModified"], reverse=True)
        while len(_records):
            if (
                len(records) >= limit
                and records[len(records) - 1]["lastModified"]
                != _records[len(_records) - 1]["lastModified"]
            ):
                break
            _record = _records.pop()
            records.append(_record)
        return records

    def get_records_by_lookup(
        self, record_type, search_data_type, field, value, operator="contains"
    ):
        SearchPreferences = self.get_data_type("ns4:SearchPreferences")
        RecordSearchBasic = self.get_data_type(search_data_type)
        SearchStringField = self.get_data_type("ns0:SearchStringField")
        SearchEnumMultiSelectField = self.get_data_type(
            "ns0:SearchEnumMultiSelectField"
        )
        SearchStringCustomField = self.get_data_type("ns0:SearchStringCustomField")
        SearchCustomFieldList = self.get_data_type("ns0:SearchCustomFieldList")
        SearchMultiSelectField = self.get_data_type("ns0:SearchMultiSelectField")
        SearchTextNumberField = self.get_data_type("ns0:SearchTextNumberField")

        search_preferences = SearchPreferences(bodyFieldsOnly=False)
        if field is None and value is None and operator is None:
            params = {}
        elif field.find("cust") == 0:
            custom_fields = [
                SearchStringCustomField(
                    scriptId=field, searchValue=value, operator="is"
                )
            ]
            params = {
                "customFieldList": SearchCustomFieldList(customField=custom_fields)
            }
        elif field == "otherRefNum":
            params = {
                field: SearchTextNumberField(searchValue=value, operator="equalTo")
            }
        elif isinstance(value, list):
            params = {
                field: SearchMultiSelectField(searchValue=value, operator=operator)
            }
        else:
            params = {
                field: SearchStringField(searchValue=value.strip(), operator=operator),
            }
        if search_data_type.find("TransactionSearchBasic") != -1:
            params.update(
                {
                    "type": SearchEnumMultiSelectField(
                        searchValue=[record_type], operator="anyOf"
                    ),
                }
            )

        search_record = RecordSearchBasic(**params)
        records = self.search(search_record, search_preferences=search_preferences)
        if records:
            return records
        return None

    def get_record_by_lookup(
        self, record_type, search_data_type, field, value, operator="contains"
    ):
        records = self.get_records_by_lookup(
            record_type, search_data_type, field, value, operator=operator
        )
        if records:
            return records[0]
        return None

    def get_record_by_variables(self, record_type, **kwargs):
        RecordRef = self.get_data_type("ns0:RecordRef")
        record_lookup = self.lookup_record_fields.get(record_type)

        ## Lookup the record by internalId if the internalId is provided.
        if kwargs.get("id"):
            return self.get_record(record_type, kwargs.get("id"))

        ## Lookup the record by externalId if the externalId is provided.
        if kwargs.get("externalId"):
            variables = {
                "record_type": record_type,
                "search_data_type": record_lookup["search_data_type"],
                "field": "externalId",
                "value": [RecordRef(externalId=kwargs.get("externalId"))],
                "operator": "anyOf",
            }
            return self.get_record_by_lookup(**variables)

        ## Lookup the record by custom field if the custom field is provided.
        value = kwargs.get(record_lookup["field"])
        if value is not None:
            field = record_lookup["field"]
        else:
            keys = list(
                filter(
                    lambda x: x not in ["id", "externalId", "operator"], kwargs.keys()
                )
            )
            assert len(keys) > 0, "Miss required variables!!!"
            field = keys[0]
            value = kwargs.get(field)

        variables = {
            "record_type": record_type,
            "search_data_type": record_lookup["search_data_type"],
            "field": field,
            "value": kwargs.get(field),
        }
        if kwargs.get("operator"):
            variables.update(
                {
                    "operator": kwargs.get("operator"),
                }
            )
        return self.get_record_by_lookup(**variables)

    def get_custom_fields(self, record_type, _custom_fields, sublist=None):
        StringCustomFieldRef = self.get_data_type("ns0:StringCustomFieldRef")
        BooleanCustomFieldRef = self.get_data_type("ns0:BooleanCustomFieldRef")
        DateCustomFieldRef = self.get_data_type("ns0:DateCustomFieldRef")
        SelectCustomFieldRef = self.get_data_type("ns0:SelectCustomFieldRef")
        MultiSelectCustomFieldRef = self.get_data_type("ns0:MultiSelectCustomFieldRef")
        ListOrRecordRef = self.get_data_type("ns0:ListOrRecordRef")

        custom_fields = []
        if _custom_fields is None:
            return custom_fields

        for script_id, value in _custom_fields.items():
            # Find the select value internal id by the value.
            if script_id in self.lookup_select_values.keys():
                if type(value) is list and len(value) > 0:
                    custom_fields.append(
                        MultiSelectCustomFieldRef(
                            scriptId=script_id,
                            value=[
                                ListOrRecordRef(
                                    internalId=self.get_select_value_id(
                                        i,
                                        script_id,
                                        record_type=record_type,
                                        sublist=sublist,
                                    )
                                )
                                for i in value
                            ],
                        )
                    )
                else:
                    custom_fields.append(
                        SelectCustomFieldRef(
                            scriptId=script_id,
                            value=ListOrRecordRef(
                                internalId=self.get_select_value_id(
                                    value,
                                    script_id,
                                    record_type=record_type,
                                    sublist=sublist,
                                )
                            ),
                        )
                    )
            else:
                if type(value) == bool:
                    custom_fields.append(
                        BooleanCustomFieldRef(scriptId=script_id, value=value)
                    )
                elif type(value) == datetime:
                    custom_fields.append(
                        DateCustomFieldRef(scriptId=script_id, value=value)
                    )
                else:
                    value = str(value)

                    if datetime_format_regex.match(value):
                        custom_fields.append(
                            DateCustomFieldRef(
                                scriptId=script_id,
                                value=datetime.strptime(value, datetime_format),
                            )
                        )
                    else:
                        custom_fields.append(
                            StringCustomFieldRef(scriptId=script_id, value=value[:4000])
                        )
        return custom_fields

    def get_search_custom_fields(self, custom_fields, record_type):
        SearchStringCustomField = self.get_data_type("ns0:SearchStringCustomField")
        SearchBooleanCustomField = self.get_data_type("ns0:SearchBooleanCustomField")
        SearchDateCustomField = self.get_data_type("ns0:SearchDateCustomField")
        SearchMultiSelectCustomField = self.get_data_type(
            "ns0:SearchMultiSelectCustomField"
        )
        ListOrRecordRef = self.get_data_type("ns0:ListOrRecordRef")
        search_custom_fields = []
        if custom_fields is None:
            return search_custom_fields

        for script_id, value in custom_fields.items():
            if script_id in self.lookup_select_values.keys():
                search_custom_fields.append(
                    SearchMultiSelectCustomField(
                        scriptId=script_id,
                        searchValue=[
                            ListOrRecordRef(
                                internalId=self.get_select_value_id(
                                    i,
                                    script_id,
                                    record_type=record_type,
                                )
                            )
                            for i in value
                        ],
                        operator="anyOf",
                    )
                )
            else:
                if type(value) == bool:
                    search_custom_fields.append(
                        SearchBooleanCustomField(scriptId=script_id, searchValue=value)
                    )
                elif (
                    type(value) is list
                    and type(value[0])
                    and type(value[1]) == datetime
                ):
                    search_custom_fields.append(
                        SearchDateCustomField(
                            scriptId=script_id,
                            searchValue=value[0],
                            searchValue2=value[1],
                            operator="within",
                        )
                    )
                else:
                    if (
                        type(value) is list
                        and datetime_format_regex.match(value[0])
                        and datetime_format_regex.match(value[1])
                    ):
                        search_custom_fields.append(
                            SearchDateCustomField(
                                scriptId=script_id,
                                searchValue=datetime.strptime(
                                    value[0], datetime_format
                                ),
                                searchValue2=datetime.strptime(
                                    value[1], datetime_format
                                ),
                                operator="within",
                            )
                        )
                    else:
                        search_custom_fields.append(
                            SearchStringCustomField(
                                scriptId=script_id, searchValue=value, operator="is"
                            )
                        )
        return search_custom_fields

    def get_address(self, address, addresses=[]):
        Address = self.get_data_type("ns5:Address")
        if not (
            address.get("city")
            and address.get("state")
            and address.get("zip")
            and address.get("country")
        ):
            return None

        _address = self.get_addr(address, addresses)
        if _address is None:
            return Address(
                country=address.get("country"),
                attention=address.get("attention"),
                addressee=address.get("addressee"),
                addrPhone=address.get("addrPhone"),
                addr1=address.get("addr1"),
                addr2=address.get("addr2"),
                addr3=address.get("addr3"),
                city=address.get("city"),
                state=address.get("state"),
                zip=address.get("zip"),
            )
        return Address(
            country=_address.addressbookAddress.country,
            attention=_address.addressbookAddress.attention,
            addressee=_address.addressbookAddress.addressee,
            addrPhone=_address.addressbookAddress.addrPhone,
            addr1=_address.addressbookAddress.addr1,
            addr2=_address.addressbookAddress.addr2,
            addr3=_address.addressbookAddress.addr3,
            city=_address.addressbookAddress.city,
            state=_address.addressbookAddress.state,
            zip=_address.addressbookAddress.zip,
        )

    def get_addr(self, address, addresses):
        addresses = list(
            filter(lambda addr: addr.addressbookAddress is not None, addresses)
        )

        # Find the address that is matched by city, state, zip, and country.
        _addresses = list(
            filter(
                lambda addr: (
                    (
                        addr.addressbookAddress.city is not None
                        and addr.addressbookAddress.city.upper()
                        == address["city"].strip().upper()
                    )
                    and (
                        addr.addressbookAddress.state is not None
                        and addr.addressbookAddress.state.upper()
                        == address["state"].strip().upper()
                    )
                    and (
                        addr.addressbookAddress.zip is not None
                        and addr.addressbookAddress.zip.upper()
                        == address["zip"].strip().upper()
                    )
                    and (
                        addr.addressbookAddress.country is not None
                        and addr.addressbookAddress.country.upper()
                        == address["country"].strip().upper()
                    )
                ),
                addresses,
            )
        )

        # Find the address that is matched by state, zip, and country.
        if len(_addresses) == 0:
            _addresses = list(
                filter(
                    lambda addr: (
                        (
                            addr.addressbookAddress.state is not None
                            and addr.addressbookAddress.state.upper()
                            == address["state"].strip().upper()
                        )
                        and (
                            addr.addressbookAddress.zip is not None
                            and addr.addressbookAddress.zip.upper()
                            == address["zip"].strip().upper()
                        )
                        and (
                            addr.addressbookAddress.country is not None
                            and addr.addressbookAddress.country.upper()
                            == address["country"].strip().upper()
                        )
                    ),
                    addresses,
                )
            )

        # Find the address that is matched by city, zip, and country.
        if len(_addresses) == 0:
            _addresses = list(
                filter(
                    lambda addr: (
                        (
                            addr.addressbookAddress.city is not None
                            and addr.addressbookAddress.city.upper()
                            == address["city"].strip().upper()
                        )
                        and (
                            addr.addressbookAddress.zip is not None
                            and addr.addressbookAddress.zip.upper()
                            == address["zip"].strip().upper()
                        )
                        and (
                            addr.addressbookAddress.country is not None
                            and addr.addressbookAddress.country.upper()
                            == address["country"].strip().upper()
                        )
                    ),
                    addresses,
                )
            )

        if len(_addresses) == 0:
            return None

        # If there are multiple addresses, use the full address to locate the address.
        return self.get_addr_by_full_addr(address, _addresses)

    def get_addr_by_full_addr(self, address, _addresses):
        full_addr = "{addr1} {addr2} {addr3}".format(
            addr1=address.get("addr1").strip()
            if address.get("addr1") is not None
            else "",
            addr2=address.get("addr2").strip()
            if address.get("addr2") is not None
            else "",
            addr3=address.get("addr3").strip()
            if address.get("addr3") is not None
            else "",
        ).strip()

        elements = [
            element
            for element in full_addr.replace("\n", " ").split(" ")
            if element != ""
        ]
        obj_list = [{"addr": addr, "match": 0} for addr in _addresses]
        for obj in obj_list:
            for element in elements:
                if (
                    obj["addr"].addressbookAddress.addr1 is not None
                    and obj["addr"]
                    .addressbookAddress.addr1.upper()
                    .find(element.upper())
                    != -1
                ):
                    obj["match"] += 1
                if (
                    obj["addr"].addressbookAddress.addr2 is not None
                    and obj["addr"]
                    .addressbookAddress.addr2.upper()
                    .find(element.upper())
                    != -1
                ):
                    obj["match"] += 1
                if (
                    obj["addr"].addressbookAddress.addr3 is not None
                    and obj["addr"]
                    .addressbookAddress.addr3.upper()
                    .find(element.upper())
                    != -1
                ):
                    obj["match"] += 1

        matched_obj = max(obj_list, key=lambda obj: obj["match"])
        if matched_obj["match"] > 0:
            return matched_obj["addr"]
        return None

    def get_customer(self, ext_customer_id, ns_customer_id, entity):
        customer = self.get_record_by_variables(
            "customer",
            **{
                "externalId": ext_customer_id,
                self.lookup_record_fields["customer"]["field"]: ns_customer_id,
            },
        )
        if customer is not None:
            self.logger.info(
                f"Customer: {customer.email}/{customer.internalId} by {ns_customer_id}/{ext_customer_id}."
            )
            return customer

        ## Create customer if CREATE_CUSTOMER is True.
        if self.setting.get("CREATE_CUSTOMER", False):
            _customer = {
                {
                    "email": entity.get("email"),
                    "addresses": [entity.get("billingAddress")],
                    "externalId": ext_customer_id,
                    "subsidiary": entity.get("subsidiary"),
                    "entityStatus": entity.get("entityStatus"),
                }
            }
            if entity.get("firstName") and entity.get("lastName"):
                _customer.update(
                    {
                        "isPerson": True,
                        "firstName": entity.get("firstName"),
                        "lastName": entity.get("lastName"),
                    }
                )
            elif entity.get("companyName"):
                _customer.update(
                    {
                        "isPerson": False,
                        "companyName": entity.get("companyName"),
                    }
                )
            else:
                raise Exception("Miss variables to create a customer!!!")

            _customer = _customer.update(
                {
                    "entityId": ns_customer_id,
                    "externalId": ext_customer_id,
                }
            )
            customer = self.get_record(
                "customer", self.insert_update_person("customer", _customer)
            )

            self.logger.info(
                f"Customer: {customer.email}/{customer.internalId} by {ns_customer_id}/{ext_customer_id}."
            )
            return customer

        raise Exception(
            f"Cannot find the customer with entity_id ({ns_customer_id}), or external_id ({ext_customer_id})."
        )

    ## GET lookup select values for the entity.
    ##
    ## @param entity: The entity.
    ## @return: The entity with the lookup select values.
    def get_lookup_select_values(self, entity, record_type=None):
        RecordRef = self.get_data_type("ns0:RecordRef")
        entity = list(
            map(
                lambda key: {
                    key: RecordRef(
                        internalId=self.get_select_value_id(
                            entity[key], key, record_type=record_type
                        )
                    ),
                }
                if key
                in self.setting["NETSUITEMAPPINGS"]["lookup_select_values"].keys()
                else {key: entity[key]},
                entity.keys(),
            )
        )
        entity = reduce(lambda x, y: dict(x, **y), entity)
        return entity

    ## Insert/Update a task.
    ##
    ## @param record_type: The record type.
    ## @param task: The task.
    def insert_update_task(self, transaction_record_type, task):
        RecordRef = self.get_data_type("ns0:RecordRef")
        CustomFieldList = self.get_data_type("ns0:CustomFieldList")
        TaskContactList = self.get_data_type("ns7:TaskContactList")
        TaskContact = self.get_data_type("ns7:TaskContact")
        Task = self.get_data_type("ns7:Task")

        # Get/Create the customer for the company.
        ext_customer_id = task.pop("extCustomerId", None)
        ns_customer_id = task.pop("nsCustomerId", None)
        customer = self.get_customer(ext_customer_id, ns_customer_id, task)
        task.update({"company": RecordRef(internalId=customer.internalId)})

        # Get lookup select values.
        task = self.get_lookup_select_values(task, record_type="task")

        # Lookup contact list.
        if task.get("contacts"):
            contact_customers = [
                self.get_customer(
                    contact.pop("extCustomerId", None),
                    contact.pop("nsCustomerId", None),
                    contact,
                )
                for contact in task.pop("contacts", [])
            ]

            task_contacts = list(
                map(
                    lambda contact_customer: TaskContact(
                        **{"company": RecordRef(internalId=contact_customer.internalId)}
                    )
                    if contact_customer.isPerson == False
                    else TaskContact(
                        **{"contact": RecordRef(internalId=contact_customer.internalId)}
                    ),
                    contact_customers,
                )
            )

            task.update(
                {"contactList": TaskContactList(contact=task_contacts, replaceAll=True)}
            )

        # Task Custom Fields
        _custom_fields = task.pop("customFields", {})
        custom_fields = self.get_custom_fields("task", _custom_fields)
        if len(custom_fields) != 0:
            task.update({"customFieldList": CustomFieldList(customField=custom_fields)})

        # Lookup transaction.
        record_lookup = self.lookup_record_fields.get(transaction_record_type)
        record_lookup_value = task.get(record_lookup["field"])
        if record_lookup_value is None:
            record_lookup_value = _custom_fields.get(record_lookup["field"])
        record = self.get_record_by_variables(
            transaction_record_type,
            **{record_lookup["field"]: record_lookup_value},
        )
        task.update(
            {
                "transaction": RecordRef(
                    internalId=record.internalId,
                    type=transaction_record_type,
                )
            }
        )

        self.logger.info(task)

        record_lookup = self.lookup_record_fields.get("task")
        record_lookup_value = task.get(record_lookup["field"])
        if record_lookup_value is None:
            record_lookup_value = _custom_fields.get(record_lookup["field"])
        record = self.get_record_by_variables(
            "task",
            **{record_lookup["field"]: record_lookup_value},
        )

        if record:
            task.update({"internalId": record.internalId})
            self.update(Task(**task))
        else:
            record = self.add(Task(**task))
            record = self.get_record("task", record.internalId)

        return record.internalId

    ## Get transaction items.
    ##
    ## @param record_type: The record type.
    ## @param items: The items.
    ## @param pricelevel: The price level.
    ## @return: The transaction items and message.
    def get_transaction_items(self, record_type, _items, pricelevel=None, status=None):
        RecordRef = self.get_data_type("ns0:RecordRef")
        CustomFieldList = self.get_data_type("ns0:CustomFieldList")
        TransactionItem = self.get_data_type(
            self.transaction_item_data_type.get(record_type)
        )
        SalesOrderItemCommitInventory = self.get_data_type(
            "ns20:SalesOrderItemCommitInventory"
        )
        InventoryDetail = self.get_data_type("ns5:InventoryDetail")
        InventoryAssignmentList = self.get_data_type("ns5:InventoryAssignmentList")
        InventoryAssignment = self.get_data_type("ns5:InventoryAssignment")

        # Items
        message = None
        transaction_items = []

        pricelevel = None
        if pricelevel:
            pricelevel = self.get_record_by_variables(
                "priceLevel", **{"name": pricelevel}
            )
        for _item in _items:
            sku = _item.get("sku")
            qty = _item.get("qty")
            commit_inventory = _item.get("commitInventory")
            lot_no_locs = _item.get("lot_no_locs")
            item = self.get_record_by_variables(
                "inventoryItem", **{"itemId": sku, "operator": "is"}
            )
            if item is not None:
                transaction_item = TransactionItem(
                    item=RecordRef(internalId=item.internalId),
                    quantity=qty,
                )

                if _item.get("location"):
                    location = self.get_record_by_variables(
                        "location", **{"name": _item.get("location")}
                    )
                    transaction_item.location = RecordRef(
                        internalId=location.internalId
                    )

                # Calculate item price level or customized price.
                difference = -1
                if pricelevel is not None and item.pricingMatrix is not None:
                    _prices = list(
                        filter(
                            lambda p: (
                                p["priceLevel"]["internalId"] == pricelevel.internalId
                            ),
                            item.pricingMatrix.pricing,
                        )
                    )
                    if len(_prices) > 0:
                        _price = min(
                            list(
                                filter(
                                    lambda p: p["quantity"] is None
                                    or (p["quantity"] <= qty),
                                    _prices[0]["priceList"]["price"],
                                )
                            ),
                            key=lambda p: p["value"],
                        )
                        difference = (
                            float(_price["value"]) - float(_item["price"])
                            if _item.get("price") is not None
                            else 0
                        )  # If there is no price in the line item of the order, the price of the product will be used.

                    if difference == 0:
                        transaction_item.price = RecordRef(
                            internalId=pricelevel.internalId
                        )

                if difference != 0 and _item.get("price") is not None:
                    transaction_item.price = RecordRef(internalId=-1)
                    transaction_item.rate = _item["price"]

                # Calculate the subtotal for each line item.
                if _item.get("price") is not None:
                    transaction_item.amount = float(qty) * float(_item["price"])

                # Item Custom Fields
                item_custom_fields = self.get_custom_fields(
                    record_type, _item.pop("customFields", {}), sublist="itemList"
                )
                if len(item_custom_fields) != 0:
                    transaction_item.customFieldList = CustomFieldList(
                        customField=item_custom_fields
                    )

                # Check if commitInventory is None or not.
                if commit_inventory:
                    transaction_item.commitInventory = SalesOrderItemCommitInventory(
                        commit_inventory
                    )

                # Check if lot_no_locs is None or not.
                if lot_no_locs:
                    inventory_assignments = []
                    for lot_no_loc in lot_no_locs:
                        records = self.get_inventory_numbers(
                            **{"item_internal_id": item.internalId}
                        )
                        if records is None:
                            continue

                        _records = list(
                            filter(
                                lambda x: x["status"] == "Available"
                                and x["inventoryNumber"] == lot_no_loc["lot_no"],
                                records,
                            )
                        )
                        if len(_records) == 0:
                            continue

                        inventory_number = _records[-1]
                        inventory_assignment = InventoryAssignment(
                            issueInventoryNumber=RecordRef(
                                internalId=inventory_number.internalId
                            ),
                            quantity=lot_no_loc["deduct_qty"],
                        )
                        inventory_assignments.append(inventory_assignment)

                    if len(inventory_assignments) > 0:
                        transaction_item.inventoryDetail = InventoryDetail(
                            inventoryAssignmentList=InventoryAssignmentList(
                                inventoryAssignment=inventory_assignments,
                                replaceAll=True,
                            )
                        )

                if status == "Cancelled" and record_type in ["salesOrder"]:
                    transaction_item.isClosed = True

                transaction_items.append(transaction_item)
                self.logger.info(f"The item ({sku}/{item.internalId}) is added.")
            else:
                log = f"The item ({sku}) is removed since it cannot be found."
                message = message + "\n" + log if message else log
                self.logger.info(log)

        return transaction_items, message

    ## Insert a customer deposit.
    ##
    ## @param kwargs: The customer deposit.
    def insert_customer_deposit(self, **kwargs):
        RecordRef = self.get_data_type("ns0:RecordRef")
        CustomerDeposit = self.get_data_type("ns23:CustomerDeposit")

        if kwargs["payment"] == 0:
            return

        customer_deposit = {
            "salesOrder": RecordRef(internalId=kwargs["sales_order_internal_id"]),
            "customer": RecordRef(internalId=kwargs["customer_internal_id"]),
            "tranDate": kwargs["tran_date"],
            "subsidiary": kwargs["subsidiary"],
            "paymentMethod": kwargs["payment_method"],
            "customForm": RecordRef(
                internalId=self.get_select_value_id(
                    kwargs["custom_form"],
                    "customForm",
                    record_type="customerDeposit",
                )
            ),
            "payment": kwargs["payment"],
            "status": kwargs["status"],
            "ccApproved": kwargs["cc_approved"],
        }
        self.add(CustomerDeposit(**customer_deposit))

    ## Insert transaction notes.
    ##
    ## @param notes: The transaction notes.
    def insert_transaction_notes(self, notes):
        RecordRef = self.get_data_type("ns0:RecordRef")
        Note = self.get_data_type("ns9:Note")
        for note in notes:
            self.add(
                Note(
                    title=note["title"],
                    note=note["note"],
                    transaction=RecordRef(internalId=note["transaction_internal_id"]),
                )
            )

    ## Insert/Update a transaction.
    ##
    ## @param record_type: The record type.
    ## @param transaction: The transaction.
    def insert_update_transaction(self, record_type, transaction):
        RecordRef = self.get_data_type("ns0:RecordRef")
        CustomFieldList = self.get_data_type("ns0:CustomFieldList")
        TransactionItemList = self.get_data_type(
            self.transaction_item_list_data_type.get(record_type)
        )
        SalesOrderOrderStatus = self.get_data_type("ns20:SalesOrderOrderStatus")
        Transaction = self.get_data_type(self.transaction_data_type.get(record_type))
        # Access the attributes of the type
        transaction_attributes = [element_name for element_name, _ in Transaction.elements]

        self.logger.info(transaction)
        payment_method = transaction.get("paymentMethod")
        notes = transaction.get("notes")

        # Get/Create the customer.
        ext_customer_id = transaction.pop("extCustomerId", None)
        ns_customer_id = transaction.pop("nsCustomerId", None)
        customer = self.get_customer(ext_customer_id, ns_customer_id, transaction)
        transaction.update({"entity": RecordRef(internalId=customer.internalId)})

        # Get lookup select values.
        transaction = dict(
            transaction,
            **self.get_lookup_select_values(
                {
                    key: value
                    for key, value in transaction.items()
                    if key in transaction_attributes
                },
                record_type=record_type,
            ),
        )

        # Replace the term with the customer term.
        if (
            customer.terms
            and transaction.get("terms") is None
            and record_type in ["salesOrder", "estimate"]
        ):
            transaction.update({"terms": customer.terms})

        # Items
        transaction_items, message = self.get_transaction_items(
            record_type,
            transaction.pop("items"),
            pricelevel=transaction.pop("priceLevel", None),
            status=transaction.get("status"),
        )

        if message:
            transaction.update({"message": message})
        transaction.update(
            {"itemList": TransactionItemList(item=transaction_items, replaceAll=True)}
        )

        # Billing Address
        if transaction.get("billingAddress"):
            billingAddress = self.get_address(
                transaction.get("billingAddress"),
                addresses=customer.addressbookList.addressbook,
            )
            transaction.update({"billingAddress": billingAddress})

        # Shipping Address
        if transaction.get("shippingAddress"):
            shippingAddress = self.get_address(
                transaction.get("shippingAddress"),
                addresses=customer.addressbookList.addressbook,
            )
            transaction.update({"shippingAddress": shippingAddress})

        # Check if shipDate, tranData is None or not.
        current = datetime.now(tz=timezone(self.setting.get("TIMEZONE", "UTC")))
        if transaction.get("shipDate") is not None:
            transaction.update(
                {
                    "shipDate": current
                    + timedelta(hours=float(transaction.get("shipDate")))
                }
            )

        if transaction.get("tranDate") is not None:
            transaction.update(
                {
                    "tranDate": current
                    + timedelta(hours=float(transaction.get("tranDate", 24)))
                }
            )

        if transaction.get("orderStatus"):
            transaction.update(
                {"orderStatus": SalesOrderOrderStatus(transaction.get("orderStatus"))}
            )

        # Created From
        if transaction.get("createdFrom"):
            lookup_join_fields = self.lookup_join_fields.get(record_type)
            created_from_record_lookup = self.lookup_record_fields.get(
                lookup_join_fields["created_from_lookup_type"]
            )
            created_from_record = self.get_record_by_variables(
                lookup_join_fields["created_from_lookup_type"],
                **{created_from_record_lookup["field"]: transaction["createdFrom"]},
            )
            if created_from_record:
                transaction.update(
                    {
                        "createdFrom": RecordRef(
                            internalId=created_from_record.internalId,
                            type=lookup_join_fields["created_from_lookup_type"],
                        )
                    }
                )

        # Order Custom Fields
        _custom_fields = transaction.pop("customFields")
        custom_fields = self.get_custom_fields(record_type, _custom_fields)
        if len(custom_fields) != 0:
            transaction.update(
                {"customFieldList": CustomFieldList(customField=custom_fields)}
            )

        transaction = {
            k: v
            for k, v in transaction.items()
            if k in transaction_attributes
        }
        self.logger.info(transaction)

        record_lookup = self.lookup_record_fields.get(record_type)
        record_lookup_value = transaction.get(record_lookup["field"])
        if record_lookup_value is None:
            record_lookup_value = _custom_fields.get(record_lookup["field"])
        record = self.get_record_by_variables(
            record_type,
            **{record_lookup["field"]: record_lookup_value},
        )

        if record:
            ## Only if the transaction status is in the update statuses list, then update the record.
            ## Or if the record type of the transaction is not in the transaction_update_statuses's key list then update the record.
            if (
                record_type not in self.transaction_update_statuses.keys()
                or transaction.get("status")
                in self.transaction_update_statuses[record_type]
            ):
                for attribute in self.transaction_update_restrict_attributes:
                    transaction.pop(attribute, None)

                ## If the record_type is salesOrder, then remove the status attribute from the transaction.
                if record_type in ["salesOrder"]:
                    transaction.pop("status", None)

                transaction.update({"internalId": record.internalId})
                self.update(Transaction(**transaction), record_type=record_type)
        else:
            record = self.add(Transaction(**transaction))
            record = self.get_record(record_type, record.internalId)

            # Insert CustomerDeposit if record_type == "salesOrder" with the condition.
            if record_type == "salesOrder" and payment_method in self.setting.get(
                "CREATE_CUSTOMER_DEPOSIT", []
            ):
                customer_deposit = {
                    "sales_order_internal_id": record.internalId,
                    "customer_internal_id": customer.internalId,
                    "tran_date": transaction["tranDate"]
                    if transaction.get("tranDate")
                    else current + timedelta(hours=24),
                    "subsidiary": transaction["subsidiary"],
                    "payment_method": transaction["paymentMethod"],
                    "custom_form": "Standard Customer Deposit",
                    "payment": (
                        sum([item.amount for item in record.itemList.item])
                        + record.shippingCost
                    ),
                    "status": "Fully Applied",
                    "cc_approved": True,
                }
                self.insert_customer_deposit(**customer_deposit)

        # Add notes.
        if notes:
            notes = [
                {
                    "title": note["title"],
                    "note": note["memo"],
                    "transaction_internal_id": record.internalId,
                }
                for note in notes
                if note["memo"] is not None and note["memo"] != ""
            ]
            self.insert_transaction_notes(notes)

        return record.tranId

    def get_contact_roles_list(self, contacts, company_internal_id=None):
        RecordRef = self.get_data_type("ns0:RecordRef")
        ContactAccessRoles = self.get_data_type("ns13:ContactAccessRoles")
        ContactAccessRolesList = self.get_data_type("ns13:ContactAccessRolesList")
        contact_roles = []
        for contact in contacts:
            records = self.get_records_by_lookup(
                "contact",
                "ns5:ContactSearchBasic",
                "company",
                [RecordRef(internalId=company_internal_id)],
                operator="anyOf",
            )

            _records = list(filter(lambda x: x.email == contact.get("email"), records))
            if len(_records) > 0:
                contact_role = {
                    "contact": RecordRef(internalId=_records[0].internalId),
                    "email": contact.get("email"),
                }
                contact_roles.append(ContactAccessRoles(**contact_role))
                continue

            contact.update(
                {
                    "companyInternalId": company_internal_id,
                }
            )
            internal_id = self.insert_update_person("contact", contact)
            contact_role = {
                "contact": RecordRef(internalId=internal_id),
                "email": contact.get("email"),
            }
            contact_roles.append(ContactAccessRoles(**contact_role))

        contact_roles_list = ContactAccessRolesList(
            contactRoles=contact_roles,
            replaceAll=True,
        )
        return contact_roles_list

    def get_person(self, person, contacts, internal_id):
        for attribute in self.person_update_restrict_attributes:
            person.pop(attribute, None)

        if len(contacts) > 0:
            contact_roles_list = self.get_contact_roles_list(
                contacts,
                company_internal_id=internal_id,
            )
            person.update({"contactRolesList": contact_roles_list})

        person.update({"internalId": internal_id})
        return person

    def insert_update_person(self, record_type, person):
        RecordRef = self.get_data_type("ns0:RecordRef")
        PersonAddressbookList = self.get_data_type(
            self.person_addressbook_list_data_type.get(record_type)
        )
        PersonAddressbook = self.get_data_type(
            self.person_addressbook_data_type.get(record_type)
        )
        Address = self.get_data_type("ns5:Address")
        CustomFieldList = self.get_data_type("ns0:CustomFieldList")
        CategoryList = self.get_data_type("ns13:CategoryList")

        self.logger.info(person)

        # Get lookup select values.
        person = self.get_lookup_select_values(person, record_type=record_type)

        if record_type in ["customer", "vendor"]:
            person.update({"isPerson": person.get("isPerson", True)})

        # Lookup addressbook.
        addressbook = []
        for address in person.pop("addresses"):
            personAddressbook = PersonAddressbook(
                **{
                    "defaultShipping": address.pop("defaultShipping", False),
                    "defaultBilling": address.pop("defaultBilling", False),
                    "label": address.get("addr1"),
                }
            )
            if record_type == "customer":
                personAddressbook.isResidential = address.pop("isResidential", True)
            personAddressbook.addressbookAddress = Address(
                **dict(
                    address,
                    **{
                        "customFieldList": CustomFieldList(
                            customField=self.get_custom_fields(
                                record_type,
                                address.pop("customFields", {}),
                                sublist="itemList",
                            )
                        )
                    },
                )
            )
            addressbook.append(personAddressbook)

        person.update(
            {"addressbookList": PersonAddressbookList(**{"addressbook": addressbook})}
        )

        # Lookup compamy.
        if person.get("companyInternalId"):
            record = self.get_record_by_variables(
                "customer",
                **{"id": person.pop("companyInternalId")},
            )
            person.update({"company": RecordRef(internalId=record.internalId)})

        # Lookup categories.
        if person.get("categories"):
            categories = []
            for category in person.pop("categories"):
                internal_id = self.get_select_value_id(
                    category, "category", record_type=record_type
                )
                categories.append(RecordRef(internalId=internal_id))
            person.update({"categoryList": CategoryList(category=categories)})

        # Lookup contacts.
        contacts = person.pop("contacts", [])

        # person Custom Fields
        custom_fields = self.get_custom_fields(
            record_type, person.pop("customFields", {})
        )
        if len(custom_fields) != 0:
            person.update(
                {"customFieldList": CustomFieldList(customField=custom_fields)}
            )

        self.logger.info(person)

        Person = self.get_data_type(self.person_data_type.get(record_type))
        record_lookup = self.lookup_record_fields.get(record_type)
        if person.get(record_lookup["field"]):
            record = self.get_record_by_variables(
                record_type,
                **{record_lookup["field"]: person.get(record_lookup["field"])},
            )

            if record:
                person = self.get_person(person, contacts, record.internalId)
                self.update(Person(**person), record_type=record_type)
                return record.internalId

        record = self.add(Person(**person))

        person = self.get_person(person, contacts, record.internalId)
        self.update(Person(**person), record_type=record_type)

        return record.internalId

    def insert_update_item(self, record_type, item):
        RecordRef = self.get_data_type("ns0:RecordRef")
        RecordRefList = self.get_data_type("ns0:RecordRefList")
        CustomFieldList = self.get_data_type("ns0:CustomFieldList")
        ItemVendor = self.get_data_type("ns17:ItemVendor")
        ItemVendorList = self.get_data_type("ns17:ItemVendorList")

        self.logger.info(item)

        # Setup the default values.
        item = dict(
            item,
            **{
                "itemId": item.pop("itemId"),
                "upcCode": "{:12}".format(int(eval(item.get("upcCode"))))
                if item.get("upcCode")
                else None,
                "mpn": item.get("mpn", ""),
                "weight": item.get("weight", 0.1),
                "weightUnit": item.get("weightUnit", "lb"),
                "salesDescription": item.pop("salesDescription", "")[:4000],
                "cost": item.get("cost", "0"),
            },
        )

        # Get lookup select values.
        item = self.get_lookup_select_values(item, record_type=record_type)

        # Lookup Subsidiaries.
        if item.get("subsidiaries"):
            subsidiaries = [
                self.get_record_by_variables(
                    "subsidiary",
                    **{
                        self.lookup_record_fields["subsidiary"]["field"]: subsidiary,
                    },
                )
                for subsidiary in item.pop("subsidiaries")
            ]
            if len(subsidiaries) > 0:
                item.update(
                    {
                        "subsidiaryList": RecordRefList(
                            recordRef=[
                                RecordRef(internalId=subsidiary.internalId)
                                for subsidiary in subsidiaries
                            ]
                        )
                    }
                )

        # Lookup vendor_entity_id
        if item.get("vendorEntityIds"):
            vendors = [
                self.get_record_by_variables(
                    "vendor",
                    **{
                        self.lookup_record_fields["vendor"]["field"]: vendor_entity_id,
                    },
                )
                for vendor_entity_id in item.pop("vendorEntityIds")
            ]
            if len(vendors) > 0:
                item.update(
                    {
                        "itemVendorList": ItemVendorList(
                            itemVendor=[
                                ItemVendor(
                                    vendor=RecordRef(
                                        internalId=vendor.internalId,
                                    )
                                )
                                for vendor in vendors
                            ]
                        )
                    }
                )

        # Item Custom Fields
        custom_fields = self.get_custom_fields(
            record_type, item.pop("customFields", {})
        )
        if len(custom_fields) != 0:
            item.update({"customFieldList": CustomFieldList(customField=custom_fields)})

        # Item MSRP Price.
        if item.get("msrp") and item.get("msrpPriceLevel"):
            PricingMatrix = self.get_data_type("ns17:PricingMatrix")
            Pricing = self.get_data_type("ns17:Pricing")
            PriceList = self.get_data_type("ns17:PriceList")
            Price = self.get_data_type("ns17:Price")

            msrpPriceLevel = self.get_record_by_variables(
                "priceLevel", **{"name": item.pop("msrpPriceLevel")}
            )

            pricing = Pricing(
                currency=None,
                priceLevel=RecordRef(internalId=msrpPriceLevel.internalId),
                discount=None,
                priceList=PriceList(
                    price=[Price(value=item.pop("msrp"), quantity=None)]
                ),
            )

            item.update({"pricingMatrix": PricingMatrix(pricing=[pricing])})

        self.logger.info(item)

        record_lookup = self.lookup_record_fields.get(record_type)
        record = self.get_record_by_variables(
            record_type,
            **{record_lookup["field"]: item.get(record_lookup["field"])},
        )

        Item = self.get_data_type(self.item_data_type.get(record_type))
        if record:
            item = {
                k: v
                for k, v in item.items()
                if k not in self.setting["NETSUITEMAPPINGS"].get("PRESERVEDFIELDS", [])
            }
            item["customFieldList"].customField = [
                custom_field
                for custom_field in custom_fields
                if custom_field.scriptId
                not in self.setting["NETSUITEMAPPINGS"].get("PRESERVEDFIELDS", [])
            ]
            item.update({"internalId": record.internalId})
            self.update(Item(**item), record_type=record_type)
            return record.internalId

        record = self.add(Item(**item))
        return record.internalId

    def get_persons(self, record_type, **kwargs):
        SearchPreferences = self.get_data_type("ns4:SearchPreferences")
        SearchBooleanField = self.get_data_type("ns0:SearchBooleanField")
        SearchDateField = self.get_data_type("ns0:SearchDateField")
        record_lookup = self.lookup_record_fields.get(record_type)
        RecordSearchBasic = self.get_data_type(record_lookup["search_data_type"])
        RecordRef = self.get_data_type("ns0:RecordRef")
        SearchMultiSelectField = self.get_data_type("ns0:SearchMultiSelectField")

        cut_date = kwargs.get("cut_date")
        end_date = kwargs.get("end_date")
        limit = int(kwargs.get("limit", 100))
        hours = float(kwargs.get("hours", 0))
        subsidiary = kwargs.get("subsidiary")

        search_preferences = SearchPreferences(bodyFieldsOnly=False)
        if kwargs.get("internal_ids"):
            search_record = RecordSearchBasic(
                # isInactive=SearchBooleanField(searchValue=False),
                internalId=SearchMultiSelectField(
                    searchValue=[
                        RecordRef(internalId=internal_id)
                        for internal_id in kwargs.get("internal_ids")[:limit]
                    ],
                    operator="anyOf",
                ),
            )
        else:
            begin = datetime.strptime(cut_date, "%Y-%m-%dT%H:%M:%S%z")
            if hours == 0:
                end = datetime.strptime(end_date, "%Y-%m-%dT%H:%M:%S%z")
            else:
                end = begin + timedelta(hours=hours)

            search_record = RecordSearchBasic(
                # isInactive=SearchBooleanField(searchValue=False),
                lastModifiedDate=SearchDateField(
                    searchValue=begin, searchValue2=end, operator="within"
                ),
            )

            self.logger.info(
                f"Begin: {begin.astimezone(timezone('UTC')).strftime('%Y-%m-%dT%H:%M:%S%z')}"
            )
            self.logger.info(
                f"End: {end.astimezone(timezone('UTC')).strftime('%Y-%m-%dT%H:%M:%S%z')}"
            )

        if subsidiary:
            record = self.get_record_by_variables(
                "subsidiary",
                **{
                    self.lookup_record_fields["subsidiary"]["field"]: subsidiary,
                },
            )
            record_ref = RecordRef(internalId=record.internalId)
            search_record.subsidiary = SearchMultiSelectField(
                searchValue=[record_ref], operator="anyOf"
            )

        persons = []
        records = self.search(search_record, search_preferences=search_preferences)
        if records:
            for record in sorted(
                records, key=lambda x: x["lastModifiedDate"], reverse=False
            )[:limit]:
                if record_type == "customer" and record.salesRep:
                    record.salesRep = self.get_record(
                        "employee", record.salesRep.internalId
                    )
                persons.append(record)
        return persons

    def get_inventory_numbers(self, **kwargs):
        RecordRef = self.get_data_type("ns0:RecordRef")

        record_type = "inventoryNumber"
        search_data_type = "ns5:InventoryNumberSearchBasic"
        if kwargs.get("item_internal_id"):
            value = [RecordRef(internalId=kwargs.get("item_internal_id"))]
            records = self.get_records_by_lookup(
                record_type, search_data_type, "item", value, operator="anyOf"
            )

        elif kwargs.get("inventory_number"):
            records = self.get_records_by_lookup(
                record_type,
                search_data_type,
                "inventoryNumber",
                kwargs.get("inventory_number"),
                operator="is",
            )
        elif kwargs.get("internal_ids"):
            value = [
                RecordRef(internalId=internal_id)
                for internal_id in kwargs.get("internal_ids")
            ]
            records = self.get_records_by_lookup(
                record_type, search_data_type, "internalId", value, operator="anyOf"
            )
        else:
            raise Exception("Miss variables!!!")

        if records is not None:
            return records
        else:
            self.logger.error(
                f"The inventory numbers search by ({kwargs}) are not found."
            )
            return None

    def get_last_qty_available_change_for_items(self, records):
        RecordRef = self.get_data_type("ns0:RecordRef")
        ItemSearchAdvanced = self.get_data_type("ns17:ItemSearchAdvanced")
        ItemSearchRow = self.get_data_type("ns17:ItemSearchRow")
        ItemSearchRowBasic = self.get_data_type("ns5:ItemSearchRowBasic")
        ItemSearch = self.get_data_type("ns17:ItemSearch")
        ItemSearchBasic = self.get_data_type("ns5:ItemSearchBasic")
        SearchColumnStringField = self.get_data_type("ns0:SearchColumnStringField")
        SearchColumnDateField = self.get_data_type("ns0:SearchColumnDateField")
        SearchMultiSelectField = self.get_data_type("ns0:SearchMultiSelectField")

        search_record = ItemSearchAdvanced(
            columns=ItemSearchRow(
                basic=ItemSearchRowBasic(
                    itemId=SearchColumnStringField(),
                    lastQuantityAvailableChange=SearchColumnDateField(),
                )
            ),
            criteria=ItemSearch(
                basic=ItemSearchBasic(
                    internalId=SearchMultiSelectField(
                        searchValue=[
                            RecordRef(internalId=record.internalId)
                            for record in records
                        ],
                        operator="anyOf",
                    )
                )
            ),
        )
        rows = self.search(search_record, advance=True)
        for record in records:
            _rows = list(
                filter(
                    lambda row: (row.basic.itemId[0].searchValue == record.itemId), rows
                )
            )
            if len(_rows) > 0:
                record.lastModifiedDate = (
                    _rows[0].basic.lastQuantityAvailableChange[0].searchValue
                )

    def get_last_qty_available_change(self, item_id):
        ItemSearchAdvanced = self.get_data_type("ns17:ItemSearchAdvanced")
        ItemSearchRow = self.get_data_type("ns17:ItemSearchRow")
        ItemSearchRowBasic = self.get_data_type("ns5:ItemSearchRowBasic")
        ItemSearch = self.get_data_type("ns17:ItemSearch")
        ItemSearchBasic = self.get_data_type("ns5:ItemSearchBasic")
        SearchColumnStringField = self.get_data_type("ns0:SearchColumnStringField")
        SearchColumnDateField = self.get_data_type("ns0:SearchColumnDateField")
        SearchStringField = self.get_data_type("ns0:SearchStringField")

        search_record = ItemSearchAdvanced(
            columns=ItemSearchRow(
                basic=ItemSearchRowBasic(
                    itemId=SearchColumnStringField(),
                    lastQuantityAvailableChange=SearchColumnDateField(),
                )
            ),
            criteria=ItemSearch(
                basic=ItemSearchBasic(
                    itemId=SearchStringField(searchValue=item_id, operator="is")
                )
            ),
        )
        rows = self.search(search_record, advance=True)
        if rows and len(rows) > 0:
            return rows[0].basic.lastQuantityAvailableChange[0].searchValue
        return None

    def get_inventory_detail_by_transaction(self, record_type, internal_id):
        RecordRef = self.get_data_type("ns0:RecordRef")
        TransactionSearchAdvanced = self.get_data_type("ns19:TransactionSearchAdvanced")
        TransactionSearchRow = self.get_data_type("ns19:TransactionSearchRow")
        InventoryDetailSearchRowBasic = self.get_data_type(
            "ns5:InventoryDetailSearchRowBasic"
        )
        TransactionSearch = self.get_data_type("ns19:TransactionSearch")
        TransactionSearchBasic = self.get_data_type("ns5:TransactionSearchBasic")
        SearchColumnSelectField = self.get_data_type("ns0:SearchColumnSelectField")
        SearchColumnDoubleField = self.get_data_type("ns0:SearchColumnDoubleField")
        SearchMultiSelectField = self.get_data_type("ns0:SearchMultiSelectField")
        SearchStringField = self.get_data_type("ns0:SearchStringField")

        search_record = TransactionSearchAdvanced(
            columns=TransactionSearchRow(
                inventoryDetailJoin=InventoryDetailSearchRowBasic(
                    binNumber=SearchColumnSelectField(customLabel="Bin Number"),
                    inventoryNumber=SearchColumnSelectField(
                        customLabel="Inventory Number ID"
                    ),
                    quantity=SearchColumnDoubleField(customLabel="Quantity"),
                    status=SearchColumnSelectField(customLabel="Status"),
                )
            ),
            criteria=TransactionSearch(
                TransactionSearchBasic(
                    internalId=SearchMultiSelectField(
                        searchValue=[RecordRef(internalId=internal_id)],
                        operator="anyOf",
                    ),
                    recordType=SearchStringField(
                        searchValue=record_type, operator="is"
                    ),
                )
            ),
        )
        rows = self.search(search_record, advance=True)
        return self.get_values_for_inventory_detail(rows)

    def get_inventory_detail(self, internal_id, use_bin_number=False):
        RecordRef = self.get_data_type("ns0:RecordRef")
        ItemSearchAdvanced = self.get_data_type("ns17:ItemSearchAdvanced")
        ItemSearchRow = self.get_data_type("ns17:ItemSearchRow")
        InventoryDetailSearchRowBasic = self.get_data_type(
            "ns5:InventoryDetailSearchRowBasic"
        )
        ItemSearch = self.get_data_type("ns17:ItemSearch")
        InventoryDetailSearchBasic = self.get_data_type(
            "ns5:InventoryDetailSearchBasic"
        )
        SearchColumnSelectField = self.get_data_type("ns0:SearchColumnSelectField")
        SearchColumnDoubleField = self.get_data_type("ns0:SearchColumnDoubleField")
        SearchMultiSelectField = self.get_data_type("ns0:SearchMultiSelectField")

        if use_bin_number:
            item_search = ItemSearch(
                inventoryDetailJoin=InventoryDetailSearchBasic(
                    binNumber=SearchMultiSelectField(
                        searchValue=[RecordRef(internalId=internal_id)],
                        operator="anyOf",
                    ),
                )
            )
        else:
            item_search = ItemSearch(
                inventoryDetailJoin=InventoryDetailSearchBasic(
                    inventoryNumber=SearchMultiSelectField(
                        searchValue=[RecordRef(internalId=internal_id)],
                        operator="anyOf",
                    ),
                )
            )

        search_record = ItemSearchAdvanced(
            columns=ItemSearchRow(
                inventoryDetailJoin=InventoryDetailSearchRowBasic(
                    binNumber=SearchColumnSelectField(customLabel="Bin Number"),
                    inventoryNumber=SearchColumnSelectField(
                        customLabel="Inventory Number ID"
                    ),
                    quantity=SearchColumnDoubleField(customLabel="Quantity"),
                    status=SearchColumnSelectField(customLabel="Status"),
                )
            ),
            criteria=item_search,
        )
        rows = self.search(search_record, advance=True)
        return self.get_values_for_inventory_detail(rows)

    def get_values_for_inventory_detail(self, rows):
        entities = []
        for row in rows:
            entity = {}
            for key in row["inventoryDetailJoin"]:
                entity[key] = None
                if len(row["inventoryDetailJoin"][key]) != 0:
                    entity[key] = row["inventoryDetailJoin"][key][0]["searchValue"]
                    if key == "binNumber":
                        entity[key] = self.get_record(
                            "bin",
                            entity[key]["internalId"],
                        )
                    if key == "inventoryNumber":
                        entity[key] = self.get_record(
                            "inventoryNumber",
                            entity[key]["internalId"],
                        )
                    if key == "status":
                        entity[key] = self.get_select_value_id(
                            entity[key]["internalId"], "inventoryStatus"
                        )
            entities.append(entity)
        return entities

    def get_items(self, record_type, **kwargs):
        SearchPreferences = self.get_data_type("ns4:SearchPreferences")
        ItemSearchBasic = self.get_data_type("ns5:ItemSearchBasic")
        SearchEnumMultiSelectField = self.get_data_type(
            "ns0:SearchEnumMultiSelectField"
        )
        SearchDateField = self.get_data_type("ns0:SearchDateField")
        SearchStringField = self.get_data_type("ns0:SearchStringField")
        SearchBooleanField = self.get_data_type("ns0:SearchBooleanField")
        RecordRef = self.get_data_type("ns0:RecordRef")
        SearchMultiSelectField = self.get_data_type("ns0:SearchMultiSelectField")
        SearchCustomFieldList = self.get_data_type("ns0:SearchCustomFieldList")

        cut_date = kwargs.get("cut_date")
        end_date = kwargs.get("end_date")
        limit = int(kwargs.get("limit", 100))
        hours = float(kwargs.get("hours", 0))
        item_types = kwargs.get(
            "item_types",
            [
                "inventoryItem",
                "lotNumberedInventoryItem",
                "nonInventoryItem",
                "nonInventoryResaleItem",
            ],
        )
        vendor_name = kwargs.get("vendor_name")
        subsidiary = kwargs.get("subsidiary")
        active_only = kwargs.get("active_only", False)
        last_qty_available_change = kwargs.get("last_qty_available_change", True)
        custom_fields = kwargs.get("custom_fields")

        search_preferences = SearchPreferences(bodyFieldsOnly=False)

        if kwargs.get("internal_ids"):
            search_record = ItemSearchBasic(
                type=SearchEnumMultiSelectField(
                    searchValue=item_types, operator="anyOf"
                ),
                internalId=SearchMultiSelectField(
                    searchValue=[
                        RecordRef(internalId=internal_id)
                        for internal_id in kwargs.get("internal_ids")[:limit]
                    ],
                    operator="anyOf",
                ),
            )
        else:
            begin = datetime.strptime(cut_date, "%Y-%m-%dT%H:%M:%S%z")
            if hours == 0:
                end = datetime.strptime(end_date, "%Y-%m-%dT%H:%M:%S%z")
            else:
                end = begin + timedelta(hours=hours)

            search_date_field = SearchDateField(
                searchValue=begin, searchValue2=end, operator="within"
            )

            search_record = ItemSearchBasic(
                type=SearchEnumMultiSelectField(
                    searchValue=item_types, operator="anyOf"
                ),
            )
            if (
                record_type in ["inventory", "inventoryLot"]
                and last_qty_available_change
            ):
                search_record.lastQuantityAvailableChange = search_date_field
            else:
                search_record.lastModifiedDate = search_date_field

            self.logger.info(
                f"Begin: {begin.astimezone(timezone('UTC')).strftime('%Y-%m-%dT%H:%M:%S%z')}"
            )
            self.logger.info(
                f"End: {end.astimezone(timezone('UTC')).strftime('%Y-%m-%dT%H:%M:%S%z')}"
            )

        if vendor_name:
            search_record.vendorName = SearchStringField(
                searchValue=vendor_name, operator="is"
            )
        if subsidiary:
            record = self.get_record_by_variables(
                "subsidiary",
                **{
                    self.lookup_record_fields["subsidiary"]["field"]: subsidiary,
                },
            )
            record_ref = RecordRef(internalId=record.internalId)
            search_record.subsidiary = SearchMultiSelectField(
                searchValue=[record_ref], operator="anyOf"
            )
        if active_only:
            search_record.isInactive = SearchBooleanField(searchValue=False)

        if custom_fields:
            search_custom_fields = self.get_search_custom_fields(
                custom_fields, item_types[0]
            )
            search_record.customFieldList = SearchCustomFieldList(
                customField=search_custom_fields
            )

        items = []
        records = self.search(search_record, search_preferences=search_preferences)
        if records:
            if (
                record_type in ["inventory", "inventoryLot"]
                and last_qty_available_change
            ):
                self.get_last_qty_available_change_for_items(records)
            records = sorted(records, key=lambda x: x["lastModifiedDate"], reverse=True)
            while len(records) > 0:
                if (
                    len(items) >= limit
                    and items[len(items) - 1]["lastModifiedDate"]
                    != records[len(records) - 1]["lastModifiedDate"]
                ):
                    break
                record = records.pop()
                if record_type == "inventoryLot":
                    record["inventoryNumbers"] = self.get_inventory_numbers(
                        **{"item_internal_id": record.internalId}
                    )
                items.append(record)

        return items

    def get_transactions_by_created_from(self, record_type, **kwargs):
        SearchPreferences = self.get_data_type("ns4:SearchPreferences")
        RecordRef = self.get_data_type("ns0:RecordRef")
        TransactionSearchBasic = self.get_data_type("ns5:TransactionSearchBasic")
        SearchEnumMultiSelectField = self.get_data_type(
            "ns0:SearchEnumMultiSelectField"
        )
        SearchMultiSelectField = self.get_data_type("ns0:SearchMultiSelectField")

        search_preferences = SearchPreferences(bodyFieldsOnly=False)
        record_ref = RecordRef(
            internalId=kwargs.get("created_from_internal_id"),
            type=kwargs.get("created_from_type"),
        )
        search_record = TransactionSearchBasic(
            type=SearchEnumMultiSelectField(
                searchValue=[record_type], operator="anyOf"
            ),
            createdFrom=SearchMultiSelectField(
                searchValue=[record_ref], operator="anyOf"
            ),
        )

        records = self.search(search_record, search_preferences=search_preferences)
        if records:
            return records
        return []

    def join_entity(self, entity_type, record, value, entities):
        record[entity_type] = []
        for entity in entities:
            line = {"customFieldList": {"customField": []}}
            for field in value["base"]:
                cols = field.split("|")
                # Retrieve a custom field from the base level.
                if cols[0] == "@":
                    custom_fields = list(
                        filter(
                            lambda i: i["scriptId"] == cols[1],
                            entity["customFieldList"]["customField"],
                        )
                    )
                    line["customFieldList"]["customField"].extend(custom_fields)
                    continue
                line[cols[0]] = entity[cols[1]]
            record[entity_type].append(line)

        for item in record.itemList.item:
            for entity in entities:
                x = list(
                    filter(
                        lambda t: (t.item.internalId == item.item.internalId),
                        entity.itemList.item,
                    )
                )
                if len(x) > 0:
                    for field in value["lines"]:
                        cols = field.split("|")
                        # Retrieve a custom field from the line level.
                        if cols[0] == "@":
                            customFields = list(
                                filter(
                                    lambda i: i["scriptId"] == cols[1],
                                    x[0]["customFieldList"]["customField"],
                                )
                            )
                            item["customFieldList"]["customField"].extend(customFields)
                            continue
                        item[cols[0]] = x[0][cols[1]]

    def get_line_items(self, internal_ids):
        SearchPreferences = self.get_data_type("ns4:SearchPreferences")
        search_preferences = SearchPreferences(bodyFieldsOnly=False)
        ## The limitation for multiselect search is 1000.
        records = []
        for i in range(0, len(internal_ids), 500):
            ItemSearchBasic = self.get_data_type("ns5:ItemSearchBasic")
            SearchMultiSelectField = self.get_data_type("ns0:SearchMultiSelectField")
            search_record = ItemSearchBasic(
                internalId=SearchMultiSelectField(
                    searchValue=internal_ids[i : i + 500], operator="anyOf"
                )
            )
            records.extend(
                self.search(search_record, search_preferences=search_preferences)
            )

        return {record.internalId: record for record in records}

    def update_line_items(self, record):
        RecordRef = self.get_data_type("ns0:RecordRef")
        internal_ids = []
        for i in range(0, len(record["itemList"]["item"])):
            internal_id = record["itemList"]["item"][i]["item"]["internalId"]
            internal_ids.append(RecordRef(internalId=internal_id))

        line_items = self.get_line_items(internal_ids)
        for i in range(0, len(record["itemList"]["item"])):
            internal_id = record["itemList"]["item"][i]["item"]["internalId"]
            if internal_id not in line_items.keys():
                continue

            if "locationsList" in line_items[internal_id].__dict__["__values__"].keys():
                record["itemList"]["item"][i]["item"]["locationsList"] = line_items[
                    internal_id
                ]["locationsList"]
            if (
                "itemVendorList"
                in line_items[internal_id].__dict__["__values__"].keys()
            ):
                record["itemList"]["item"][i]["item"]["itemVendorList"] = line_items[
                    internal_id
                ]["itemVendorList"]
            if "pricingMatrix" in line_items[internal_id].__dict__["__values__"].keys():
                record["itemList"]["item"][i]["item"]["pricingMatrix"] = line_items[
                    internal_id
                ]["pricingMatrix"]

    def get_transactions(self, record_type, **kwargs):
        SearchPreferences = self.get_data_type("ns4:SearchPreferences")
        TransactionSearchBasic = self.get_data_type("ns5:TransactionSearchBasic")
        SearchEnumMultiSelectField = self.get_data_type(
            "ns0:SearchEnumMultiSelectField"
        )
        SearchDateField = self.get_data_type("ns0:SearchDateField")
        RecordRef = self.get_data_type("ns0:RecordRef")
        SearchMultiSelectField = self.get_data_type("ns0:SearchMultiSelectField")

        cut_date = kwargs.get("cut_date")
        end_date = kwargs.get("end_date")
        limit = int(kwargs.get("limit", 100))
        hours = float(kwargs.get("hours", 0))
        vendor_id = kwargs.get("vendor_id")
        subsidiary = kwargs.get("subsidiary")
        item_detail = kwargs.get("item_detail", False)
        inventory_detail = kwargs.get("inventory_detail", False)

        search_preferences = SearchPreferences(bodyFieldsOnly=False)
        if kwargs.get("internal_ids"):
            search_record = TransactionSearchBasic(
                type=SearchEnumMultiSelectField(
                    searchValue=[record_type], operator="anyOf"
                ),
                internalId=SearchMultiSelectField(
                    searchValue=[
                        RecordRef(internalId=internal_id)
                        for internal_id in kwargs.get("internal_ids")[:limit]
                    ],
                    operator="anyOf",
                ),
            )
        else:
            begin = datetime.strptime(cut_date, "%Y-%m-%dT%H:%M:%S%z")
            if hours == 0:
                end = datetime.strptime(end_date, "%Y-%m-%dT%H:%M:%S%z")
            else:
                end = begin + timedelta(hours=hours)

            search_date_field = SearchDateField(
                searchValue=begin, searchValue2=end, operator="within"
            )

            search_record = TransactionSearchBasic(
                type=SearchEnumMultiSelectField(
                    searchValue=[record_type], operator="anyOf"
                ),
                lastModifiedDate=search_date_field,
            )
            self.logger.info(
                f"Begin: {begin.astimezone(timezone('UTC')).strftime('%Y-%m-%dT%H:%M:%S%z')}"
            )
            self.logger.info(
                f"End: {end.astimezone(timezone('UTC')).strftime('%Y-%m-%dT%H:%M:%S%z')}"
            )

        if vendor_id:
            record_ref = RecordRef(internalId=vendor_id)
            search_record.entity = SearchMultiSelectField(
                searchValue=[record_ref], operator="anyOf"
            )

        if subsidiary:
            record = self.get_record_by_variables(
                "subsidiary",
                **{
                    self.lookup_record_fields["subsidiary"]["field"]: subsidiary,
                },
            )
            record_ref = RecordRef(internalId=record.internalId)
            search_record.subsidiary = SearchMultiSelectField(
                searchValue=[record_ref], operator="anyOf"
            )

        transactions = []
        records = self.search(search_record, search_preferences=search_preferences)
        if records:
            records = sorted(records, key=lambda x: x["lastModifiedDate"], reverse=True)
            while len(records):
                if (
                    len(transactions) >= limit
                    and transactions[len(transactions) - 1]["lastModifiedDate"]
                    != records[len(records) - 1]["lastModifiedDate"]
                ):
                    break
                record = records.pop()

                if (
                    inventory_detail
                    and record_type in self.inventory_detail_record_types
                ):
                    if record_type in ["inventoryTransfer", "inventoryAdjustment"]:
                        record.inventoryList = self.get_record(
                            record_type, record.internalId
                        ).inventoryList
                    else:
                        record.itemList = self.get_record(
                            record_type, record.internalId
                        ).itemList

                if item_detail and record_type in self.item_detail_record_types:
                    self.update_line_items(record)

                for entity_type, value in self.lookup_join_fields.items():
                    if record_type in value.get("created_from_types", []):
                        entities = self.get_transactions_by_created_from(
                            entity_type,
                            **{
                                "created_from_internal_id": record.internalId,
                                "created_from_type": record_type,
                            },
                        )
                        if entities:
                            self.join_entity(entity_type, record, value, entities)

                transactions.append(record)

        return transactions

    def get_files(self, internal_ids):
        SearchPreferences = self.get_data_type("ns4:SearchPreferences")
        RecordRef = self.get_data_type("ns0:RecordRef")
        FileSearchBasic = self.get_data_type("ns5:FileSearchBasic")
        SearchMultiSelectField = self.get_data_type("ns0:SearchMultiSelectField")
        recordRefs = [RecordRef(internalId=internalId) for internalId in internal_ids]
        search_record = FileSearchBasic(
            internalId=SearchMultiSelectField(searchValue=recordRefs, operator="anyOf")
        )

        search_preferences = SearchPreferences(bodyFieldsOnly=False)
        records = self.search(search_record, search_preferences=search_preferences)
        if records is not None:
            return records
        else:
            return None

    def advance_search(self, entity_type, saved_search_id, **kwargs):
        SearchDateField = self.get_data_type("ns0:SearchDateField")
        SearchEnumMultiSelectField = self.get_data_type(
            "ns0:SearchEnumMultiSelectField"
        )
        if entity_type == "transaction":
            SearchAdvanced = self.get_data_type("ns19:TransactionSearchAdvanced")
            Search = self.get_data_type("ns19:TransactionSearch")
            SearchBasic = self.get_data_type("ns5:TransactionSearchBasic")
        elif entity_type == "customer":
            SearchAdvanced = self.get_data_type("ns13:CustomerSearchAdvanced")
            Search = self.get_data_type("ns13:CustomerSearch")
            SearchBasic = self.get_data_type("ns5:CustomerSearchBasic")
        elif entity_type == "item":
            SearchAdvanced = self.get_data_type("ns17:ItemSearchAdvanced")
            Search = self.get_data_type("ns17:ItemSearch")
            SearchBasic = self.get_data_type("ns5:ItemSearchBasic")
        else:
            raise Exception(f"entity_type ({entity_type}) is not supported!!!")

        search_basic = None
        if kwargs.get("cut_date") and kwargs.get("hours"):
            begin = datetime.strptime(kwargs.get("cut_date"), "%Y-%m-%dT%H:%M:%S%z")
            if kwargs.get("hours") == 0:
                end = (
                    datetime.now(
                        tz=timezone(self.setting.get("TIMEZONE", "UTC"))
                    ).strftime("%Y-%m-%dT%H:%M:%S%z"),
                )
            else:
                end = begin + timedelta(hours=kwargs.get("hours"))

            last_modified_date = SearchDateField(
                searchValue=begin, searchValue2=end, operator="within"
            )
            search_basic = SearchBasic(lastModifiedDate=last_modified_date)

        if kwargs.get("data_type"):
            data_type = SearchEnumMultiSelectField(
                searchValue=[kwargs.get("data_type")], operator="anyOf"
            )
            if search_basic:
                search_basic.type = data_type
            else:
                search_basic = SearchBasic(type=data_type)

        criteria = None
        if search_basic:
            criteria = Search(basic=search_basic)

        search_record = SearchAdvanced(savedSearchId=saved_search_id)

        if criteria:
            search_record.criteria = criteria

        rows = self.search(search_record, advance=True)
        return rows

    def get_deleted_records(self, record_type, **kwargs):
        GetDeletedFilter = self.get_data_type("ns0:GetDeletedFilter")
        SearchEnumMultiSelectField = self.get_data_type(
            "ns0:SearchEnumMultiSelectField"
        )
        SearchDateField = self.get_data_type("ns0:SearchDateField")
        SearchStringField = self.get_data_type("ns0:SearchStringField")

        script_id = kwargs.get("script_id")
        page_index = int(kwargs.get("page_index", 1))
        cut_date = kwargs.get("cut_date")
        end_date = kwargs.get("end_date")
        hours = float(kwargs.get("hours", 0))

        begin = datetime.strptime(cut_date, "%Y-%m-%dT%H:%M:%S%z")
        if hours == 0:
            end = datetime.strptime(end_date, "%Y-%m-%dT%H:%M:%S%z")
        else:
            end = begin + timedelta(hours=hours)

        search_date_field = SearchDateField(
            searchValue=begin, searchValue2=end, operator="within"
        )

        get_deleted_filter = GetDeletedFilter(
            deletedDate=search_date_field,
            type=SearchEnumMultiSelectField(
                searchValue=[record_type], operator="anyOf"
            ),
        )

        if script_id:
            get_deleted_filter.scriptId = SearchStringField(
                searchValue=script_id, operator="is"
            )

        return self.soap_adaptor.get_deleted(
            get_deleted_filter=get_deleted_filter,
            page_index=page_index,
        )
