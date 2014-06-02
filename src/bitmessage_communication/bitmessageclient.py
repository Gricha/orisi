from bitmessageaddress import BitmessageAddress
from bitmessageserver import BitmessageServer
from settings_local import DEFAULT_ADDRESS_LABEL

import xmlrpclib
import json
import base64
import re

class BitmessageClient:

  def __init__(self):
    self.connect()
    self.get_addresses()
    self.update_address_if_empty()

  def connect(self):
    self.api = BitmessageServer()

  def create_random_address(self, label="main"):
    label_base64 = base64.encodestring(label)
    self.api.createRandomAddress(label_base64)

  def get_addresses(self):
    addresses_json = self.api.listAddresses2()
    address_list = json.loads(addresses_json)['addresses']

    self.addresses = \
        [BitmessageAddress(address_dict) for address_dict in address_list]

    if len(self.addresses) > 0:
      self.default_address = self.addresses[0]

    for address in self.addresses:
      if address.label == DEFAULT_ADDRESS_LABEL:
        self.default_address = address
        break

  def update_address_if_empty(self):
    if len(self.addresses) > 0:
      return
    self.create_random_address()
    self.get_addresses()

  def send_message(self, address, subject, message):
    ack_data = self.api.sendMessage(
                  address, 
                  self.default_address.address, 
                  base64.encodestring(subject),
                  base64.encodestring(message))
    return ack_data

  def send_broadcast(self, subject, message):
    ack_data = self.api.sendBroadcast(
                  self.default_address.address,
                  base64.encodestring(subject),
                  base64.encodestring(message))
    return ack_data

  def delete_address(self, address):
    self.api.deleteAddress(address)
