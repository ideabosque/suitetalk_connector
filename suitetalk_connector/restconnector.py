#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "bibow"

import requests, time, warlock
from silvaengine_utility import Utility
from requests_oauthlib import OAuth1
from datetime import datetime, timedelta
from pytz import timezone
from .soapadaptor import SOAPAdaptor

datetime_format = "%Y-%m-%dT%H:%M:%S%z"


class RESTConnector(object):
    def __init__(self, logger, **setting):
        self.logger = logger
        self.setting = setting
        self.lookup_select_values = setting["NETSUITEMAPPINGSREST"][
            "lookup_select_values"
        ]
        self.lookup_record_fields = setting["NETSUITEMAPPINGSREST"][
            "lookup_record_fields"
        ]
        company_url = f"https://{self.setting['ACCOUNT'].lower().replace('_', '-')}.suitetalk.api.netsuite.com"
        self.rest_services = f"{company_url}/services/rest"
        self.transaction_update_statuses = setting["NETSUITEMAPPINGSREST"].get(
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

    def get_select_values(self, field, record_type, sublist=None):
        return self.soap_adaptor.get_select_values(field, record_type, sublist=sublist)

    def get_select_value_id(self, value, field, record_type, sublist=None):
        if self.lookup_select_values.get(field):
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

        select_values = self.get_select_values(field, record_type, sublist=sublist)
        id = select_values.get(value)
        if id:
            return id

        raise Exception(
            f"Cannot find the select value ({value}) with the field ({field}) and recordType ({record_type})."
        )

    @property
    def auth(self):
        return OAuth1(
            self.setting["CONSUMER_KEY"],
            self.setting["CONSUMER_SECRET"],
            self.setting["TOKEN_ID"],
            self.setting["TOKEN_SECRET"],
            realm=self.setting["ACCOUNT"],
            signature_method="HMAC-SHA256",
        )

    def get_schema(self, record_type):
        request_url = f"{self.rest_services}/record/v1/metadata-catalog/{record_type}"
        headers = {
            "Accept": "application/schema+json",
        }
        response = requests.get(request_url, auth=self.auth, headers=headers)

        if response.status_code == 200:
            return Utility.json_loads(response.text)

        self.logger.error(response.content)
        raise Exception(response.content)

    def get_model(self, record_type):
        schema = self.get_schema(record_type)
        return warlock.model_factory(schema)

    def get_record(
        self, record_type, id, use_external_id=False, expand_sub_resources=True
    ):
        request_url = f"{self.rest_services}/record/v1/{record_type}/{id}"
        if use_external_id:
            request_url = f"{self.rest_services}/record/v1/{record_type}/eid:{id}"
        params = {}
        if expand_sub_resources:
            params = {"expandSubResources": expand_sub_resources}
        response = requests.get(request_url, auth=self.auth, params=params)

        if response.status_code == 200:
            return Utility.json_loads(response.text)
        if response.status_code == 404:
            return None

        self.logger.error(response.content)
        raise Exception(response.content)

    def get_records_by_condition(self, record_type, condition, limit=None, offset=None):
        request_url = f"{self.rest_services}/record/v1/{record_type}"
        params = {}
        if condition:
            params = {"q": condition}

        if limit and offset:
            params.update(
                {
                    "limit": limit,
                    "offset": offset,
                }
            )
        response = requests.get(request_url, auth=self.auth, params=params)

        if response.status_code == 200:
            return Utility.json_loads(response.text)

        self.logger.error(response.content)
        raise Exception(response.content)

    def create_record(self, record_type, record, external_id=None):
        request_url = f"{self.rest_services}/record/v1/{record_type}"
        method = "POST"
        if external_id:
            request_url = (
                f"{self.rest_services}/record/v1/{record_type}/eid:{external_id}"
            )
            method = "PUT"

        response = requests.request(
            method, request_url, auth=self.auth, data=Utility.json_dumps(record)
        )

        if response.status_code == 204:
            return True

        self.logger.error(response.content)
        raise Exception(response.content)

    def update_record(
        self, record_type, id, record, params={}, use_external_id=False, method="PATCH"
    ):
        request_url = f"{self.rest_services}/record/v1/{record_type}/{id}"
        if use_external_id:
            request_url = f"{self.rest_services}/record/v1/{record_type}/eid:{id}"
        response = requests.request(
            method,
            request_url,
            auth=self.auth,
            data=Utility.json_dumps(record),
            params=params,
        )

        if response.status_code == 204:
            return True

        self.logger.error(response.content)
        raise Exception(response.content)

    def get_record_id(self, record_type, field, value):
        condition = f'{field} is "{value}"'
        result = self.get_records_by_condition(record_type, condition)
        if result["count"] == 0:
            return None

        return result["items"][0]["id"]

    def get_record_by_variables(self, record_type, **kwargs):
        if kwargs.get("id"):
            return self.get_record(record_type, kwargs.get("id"))
        if kwargs.get("externalId"):
            return self.get_record(record_type, kwargs.get("id"), use_external_id=True)

        record_lookup_field = self.lookup_record_fields.get(record_type)["field"]
        if kwargs.get(record_lookup_field):
            id = self.get_record_id(
                record_type, record_lookup_field, kwargs.get(record_lookup_field)
            )
            if id:
                return self.get_record(record_type, id)
            return None

        raise Exception("Miss required variables!!!")

    def get_custom_fields(self, record_type, custom_fields, sublist=None):
        for script_id, value in custom_fields.items():
            # Find the select value internal id by the value.
            if script_id in self.lookup_select_values.keys():
                if type(value) is list and len(value) > 0:
                    custom_fields.update(
                        {
                            script_id: [
                                {
                                    "id": self.get_select_value_id(
                                        i, script_id, record_type, sublist=sublist
                                    )
                                }
                                for i in value
                            ]
                        }
                    )
                else:
                    custom_fields.update(
                        {
                            script_id: {
                                "id": self.get_select_value_id(
                                    value, script_id, record_type, sublist=sublist
                                )
                            }
                        }
                    )

        return custom_fields

    def get_address(self, address, addresses=[], default=None):
        # Use default billing address or default shipping address in NetSuite if it is set.
        if default is not None:
            if default == "billing":
                _addresses = list(
                    filter(
                        lambda addr: addr.get("addressBookAddress") is not None
                        and addr["defaultBilling"] == True,
                        addresses,
                    )
                )
            elif default == "shipping":
                _addresses = list(
                    filter(
                        lambda addr: addr.get("addressBookAddress") is not None
                        and addr["defaultShipping"] == True,
                        addresses,
                    )
                )
            else:
                raise Exception(
                    f"The default address type ({default}) is not supported."
                )

            if len(_addresses) > 0:
                return {"id": str(_addresses[0]["id"])}

        if not (
            address.get("city")
            and address.get("state")
            and address.get("zip")
            and address.get("country")
        ):
            return None

        _address = self.get_addr(address, addresses)
        if _address is None:
            address.update({"country": {"id": address.pop("country")}})
            return {
                k: v
                for k, v in address.items()
                if k
                in (
                    "addressee",
                    "attention",
                    "addrPhone",
                    "addr1",
                    "addr2",
                    "addr3",
                    "city",
                    "state",
                    "zip",
                    "country",
                )
            }
        return {"id": str(_address["id"])}

    def get_addr(self, address, addresses):
        addresses = list(
            filter(lambda addr: addr.get("addressBookAddress") is not None, addresses)
        )

        # Find the address that is matched by city, state, zip, and country.
        _addresses = list(
            filter(
                lambda addr: (
                    addr["addressBookAddress"].get("city", "").upper()
                    == address["city"].strip().upper()
                    and addr["addressBookAddress"].get("state", "").upper()
                    == address["state"].strip().upper()
                    and addr["addressBookAddress"].get("zip", "").upper()
                    == address["zip"].strip().upper()
                    and addr["addressBookAddress"]
                    .get("country", {"id": ""})["id"]
                    .upper()
                    == address["country"].strip().upper()
                ),
                addresses,
            )
        )

        # Find the address that is matched by state, zip, and country.
        if len(_addresses) == 0:
            _addresses = list(
                filter(
                    lambda addr: (
                        addr["addressBookAddress"].get("state", "").upper()
                        == address["state"].strip().upper()
                        and addr["addressBookAddress"].get("zip", "").upper()
                        == address["zip"].strip().upper()
                        and addr["addressBookAddress"]
                        .get("country", {"id": ""})["id"]
                        .upper()
                        == address["country"].strip().upper()
                    ),
                    addresses,
                )
            )

        # Find the address that is matched by city, zip, and country.
        if len(_addresses) == 0:
            _addresses = list(
                filter(
                    lambda addr: (
                        addr["addressBookAddress"].get("city", "").upper()
                        == address["city"].strip().upper()
                        and addr["addressBookAddress"].get("zip", "").upper()
                        == address["zip"].strip().upper()
                        and addr["addressBookAddress"]
                        .get("country", {"id": ""})["id"]
                        .upper()
                        == address["country"].strip().upper()
                    ),
                    addresses,
                )
            )

        if len(_addresses) == 0:
            return None

        # If there are multiple addresses, use the full address to locate the address.
        return self.get_addr_by_full_addr(address, _addresses)

    def get_addr_by_full_addr(self, address, _addresses):
        full_addr = f"{address.get('addr1','').strip()} {address.get('addr2','').strip()} {address.get('addr3', '').strip()}"

        elements = [
            element
            for element in full_addr.replace("\n", " ").split(" ")
            if element != ""
        ]
        obj_list = [{"addr": addr, "match": 0} for addr in _addresses]
        for obj in obj_list:
            for element in elements:
                if (
                    obj["addr"]["addressBookAddress"]
                    .get("addr1", "")
                    .upper()
                    .find(element.upper())
                    != -1
                ):
                    obj["match"] += 1
                if (
                    obj["addr"]["addressBookAddress"]
                    .get("addr2", "")
                    .upper()
                    .find(element.upper())
                    != -1
                ):
                    obj["match"] += 1
                if (
                    obj["addr"]["addressBookAddress"]
                    .get("addr3", "")
                    .upper()
                    .find(element.upper())
                    != -1
                ):
                    obj["match"] += 1

        matched_obj = max(obj_list, key=lambda obj: obj["match"])
        if matched_obj["match"] > 0:
            return matched_obj["addr"]
        return None

    def get_customer(self, ext_customer_id, ns_customer_id):
        customer = self.get_record_by_variables(
            "customer",
            **{
                "externalId": ext_customer_id,
                self.lookup_record_fields["customer"]["field"]: ns_customer_id,
            },
        )

        if customer is None:
            if self.setting.get("CREATE_CUSTOMER", False):
                pass
                ## Create customer.
            else:
                raise Exception(
                    f"Cannot find the customer with entity_id ({ns_customer_id}), or ({ext_customer_id})."
                )

        self.logger.info(
            f"Customer: {customer['email']}/{customer['id']} by {ns_customer_id}/{ext_customer_id}."
        )

        return customer

    def get_transaction_items(self, record_type, _items, pricelevel=None, status=None):
        # Initialize variables
        message = None
        transaction_items = []

        for _item in _items:
            # Extract item attributes
            sku = _item.get("sku")
            qty = _item.get("qty")
            commit_inventory = _item.get("commitInventory")
            lot_no_locs = _item.get("lot_no_locs")
            item_record_type = _item.get("itemRecordType", "inventoryItem")

            # Retrieve item information
            item = self.get_record_by_variables(
                item_record_type,
                **{self.lookup_record_fields[item_record_type]["field"]: sku},
            )

            if item:
                transaction_item = {"item": {"id": item["id"]}}

                # Calculate item price level or customized price.
                difference = -1
                if pricelevel and item.get("price"):
                    _prices = list(
                        filter(
                            lambda p: p["priceLevelName"] == pricelevel,
                            item["price"]["items"],
                        )
                    )
                    if _prices:
                        _price = min(
                            filter(
                                lambda p: (
                                    p["quantity"] is None
                                    or float(p["quantity"]["value"]) <= float(qty)
                                ),
                                _prices,
                            ),
                            key=lambda p: p["price"],
                        )
                        difference = (
                            float(_price["price"]) - float(_item["price"])
                            if _item.get("price")
                            else 0
                        )

                        if difference == 0:
                            transaction_item.update(
                                {"price": {"id": str(_price["priceLevel"]["id"])}}
                            )

                if difference != 0 and _item.get("price"):
                    transaction_item.update(
                        {"price": {"id": "-1"}, "rate": float(_item.get("price"))}
                    )

                # Calculate the subtotal for each line item.
                if _item.get("price"):
                    transaction_item.update(
                        {"amount": float(qty) * float(_item["price"])}
                    )

                # Item Custom Fields
                item_custom_fields = self.get_custom_fields(
                    record_type, _item.pop("customFields"), sublist="itemList"
                )
                if item_custom_fields:
                    transaction_item.update(item_custom_fields)

                # Check if commit_inventory is None or not.
                if commit_inventory:
                    transaction_item.update(
                        {
                            "commitInventory": {
                                "id": self.get_select_value_id(
                                    commit_inventory,
                                    "commitInventory",
                                    "salesOrder",
                                    sublist="itemList",
                                )
                            }
                        }
                    )

                # Check if lotNoLocs is None or not.
                if lot_no_locs:
                    inventory_assignments = []
                    for lot_no_loc in lot_no_locs:
                        inventory_number_id = self.get_record_id(
                            "inventorynumber",
                            "inventoryNumber",
                            lot_no_loc["lot_no"],
                        )
                        if inventory_number_id is None:
                            continue

                        inventory_assignment = {
                            "issueInventoryNumber": {"id": inventory_number_id},
                            "quantity": float(lot_no_loc["deduct_qty"]),
                        }
                        inventory_assignments.append(inventory_assignment)

                    if inventory_assignments:
                        transaction_item.update(
                            {
                                "inventoryDetail": {
                                    "inventoryassignment": {
                                        "items": inventory_assignments
                                    },
                                    "quantity": float(qty),
                                },
                            }
                        )

                # Check status and record type
                if status == "Closed" and record_type == "salesOrder":
                    transaction_item.update({"isClosed": True})

                # Append the transaction item to the list
                transaction_items.append(transaction_item)
                self.logger.info(f"The item ({sku}/{item['id']}) is added.")
            else:
                # Item not found
                log = f"The item ({sku}) is removed since it cannot be found."
                message = message + "\n" + log if message else log
                self.logger.info(log)

        return transaction_items, message

    ## Insert a customer deposit.
    ##
    ## @param kwargs: The customer deposit.
    def insert_customer_deposit(self, **_customer_deposit):
        # Check if payment is zero, if so, return early
        if _customer_deposit["payment"] == 0:
            return

        # Create a dictionary for customer deposit data
        customer_deposit = {
            "salesOrder": {"id": _customer_deposit["sales_order_internal_id"]},
            "customer": {"id": _customer_deposit["customer_internal_id"]},
            "tranDate": _customer_deposit["tran_date"].strftime(datetime_format),
            "subsidiary": _customer_deposit["subsidiary"],
            "paymentMethod": _customer_deposit["payment_method"],
            "customForm": {
                "id": "67"
                # "id": self.get_select_value_id(
                #     _customer_deposit["custom_form"],
                #     "customForm",
                #     "customerDeposit",
                # )
            },
            "payment": _customer_deposit["payment"],
            "ccApproved": _customer_deposit["cc_approved"],
        }

        # Add the customer deposit to the system
        CustomerDeposit = self.get_model("customerDeposit")
        self.create_record("customerDeposit", CustomerDeposit(**customer_deposit))

    ## Insert transaction notes.
    ##
    ## @param notes: The transaction notes.
    def insert_transaction_notes(self, notes, id):
        if notes is None:
            return

        # Import necessary data models
        Note = self.get_model("Note")

        # Iterate through notes and insert them
        for note in notes:
            if note["memo"] is None or note["memo"] == "":
                continue

            self.create_record(
                "note",
                Note(
                    **{
                        "title": note["title"],
                        "note": note["memo"],
                        "transaction": {"id": id},
                    }
                ),
            )

    def insert_update_transaction(self, record_type, transaction):
        payment_method = transaction.get("paymentMethod")
        notes = transaction.get("notes")

        # Get/Create the customer.
        ext_customer_id = transaction.pop("extCustomerId", None)
        ns_customer_id = transaction.pop("nsCustomerId", None)
        customer = self.get_customer(ext_customer_id, ns_customer_id)
        transaction.update({"entity": {"id": customer["id"]}})

        # Lookup select values.
        for key, value in transaction.items():
            if (
                key
                in self.setting["NETSUITEMAPPINGSREST"]["lookup_select_values"].keys()
            ):
                transaction.update(
                    {key: {"id": self.get_select_value_id(value, key, record_type)}}
                )

        # Replace the term with the customer term.
        if (
            customer.get("terms")
            and transaction.get("terms") is None
            and record_type in ["salesOrder", "estimate"]
        ):
            transaction.update({"terms": {"id": customer["terms"]["id"]}})

        # Get tranaction items.
        transaction_items, message = self.get_transaction_items(
            record_type,
            transaction.pop("items"),
            pricelevel=transaction.get("priceLevel"),
            status=transaction.get("status"),
        )

        if message:
            transaction.update({"message": message})
        transaction.update({"item": {"items": transaction_items}})

        # Billing Address.
        billing_address = self.get_address(
            transaction.pop("billingAddress"),
            addresses=customer["addressBook"]["items"],
            default="billing"
            if self.setting.get("DEFAULT_TRANSACTION_BILLING", False)
            else None,
        )
        if billing_address:
            if billing_address.get("id"):
                transaction.update({"billAddressList": billing_address})
            else:
                transaction.update({"billingAddress": billing_address})

        # Shipping Address.
        shipping_address = self.get_address(
            transaction.pop("shippingAddress"),
            addresses=customer["addressBook"]["items"],
            default="shipping"
            if self.setting.get("DEFAULT_TRANSACTION_SHIPPING", False)
            else None,
        )
        if shipping_address:
            if shipping_address.get("id"):
                transaction.update({"shipAddressList": shipping_address})
            else:
                transaction.update({"shippingAddress": shipping_address})

        # Check if shipDate, tranData is None or not.
        current = datetime.now(tz=timezone(self.setting.get("TIMEZONE", "UTC")))
        if transaction.get("shipDate") is not None:
            transaction.update(
                {
                    "shipDate": (
                        current + timedelta(hours=transaction.get("shipDate"))
                    ).strftime(datetime_format)
                }
            )

        if transaction.get("tranDate") is not None:
            transaction.update(
                {
                    "tranDate": (
                        current + timedelta(hours=transaction.get("tranDate"))
                    ).strftime(datetime_format)
                }
            )

        # orderStatus.
        # It should be done in the lookup_select_values.

        # Created From.
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
                transaction.update({"createdFrom": {"id": created_from_record["id"]}})

        # Order Custom Fields
        custom_fields = self.get_custom_fields(
            record_type,
            transaction.pop("customFields"),
        )
        if len(custom_fields.keys()) != 0:
            transaction.update(custom_fields)

        self.logger.info(Utility.json_dumps(transaction))

        Transaction = self.get_model(record_type)

        record_lookup_field = self.lookup_record_fields.get(record_type)["field"]
        record = self.get_record_by_variables(
            record_type,
            **{record_lookup_field: transaction.get(record_lookup_field)},
        )
        if record:
            ## Only if the transaction status is in the update statuses list, then update the record.
            ## Or if the record type of the transaction is not in the transaction_update_statuses's key list then update the record.
            if (
                record_type not in self.transaction_update_statuses.keys()
                or transaction.get("status")
                in self.transaction_update_statuses[record_type]
            ):
                args = [record_type, record["id"], Transaction(**transaction)]
                if record_type == "salesOrder":
                    self.update_record(*args, params={"replace": "item"})
                else:
                    self.update_record(*args)

                ## Add notes
                self.insert_transaction_notes(notes, record["id"])
                return record["tranId"]

        # Create a transaction.
        self.create_record(record_type, Transaction(**transaction))
        record = self.get_record_by_variables(
            record_type,
            **{record_lookup_field: transaction.get(record_lookup_field)},
        )

        # Insert CustomerDeposit if record_type == "salesOrder" with the condition.
        if record_type == "salesOrder" and payment_method in self.setting.get(
            "CREATE_CUSTOMER_DEPOSIT", []
        ):
            customer_deposit = {
                "sales_order_internal_id": record["id"],
                "customer_internal_id": customer["id"],
                "tran_date": transaction["tranDate"]
                if transaction.get("tranDate")
                else current + timedelta(hours=24),
                "subsidiary": transaction["subsidiary"],
                "payment_method": transaction["paymentMethod"],
                "custom_form": "Standard Customer Deposit",
                "payment": (
                    sum([item["amount"] for item in record["item"]["items"]])
                    + record["shippingCost"]
                ),
                "cc_approved": True,
            }
            ## Insert CustomerDeposit.
            self.insert_customer_deposit(**customer_deposit)

        ## Add notes
        self.insert_transaction_notes(notes, record["id"])
        return record["tranId"]

    def execute_suiteql(self, suiteql, limit=None, offset=None):
        request_url = f"{self.rest_services}/query/v1/suiteql"

        params = {}
        if limit:
            params.update({"limit": limit})
        if offset:
            params.update({"offset": offset})

        response = requests.post(
            request_url,
            auth=self.auth,
            headers={
                "prefer": "transient",
            },
            data=Utility.json_dumps({"q": suiteql}),
            params=params,
        )

        if response.status_code == 200:
            return Utility.json_loads(response.text)
        if response.status_code == 404:
            return None

        self.logger.error(response.content)
        raise Exception(response.content)
