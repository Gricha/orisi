from basehandler import BaseHandler
from password_db import LockedPasswordTransaction

from shared.liburl_wrapper import safe_read
from decimal import Decimal

import json
import logging
import datetime


class PricecheckCreateHandler(BaseHandler):
  def __init__(self, oracle):
    self.oracle = oracle
    self.btc = oracle.btc


  def handle_request(self, request):
    message = request.message

    if not self.try_prepare_raw_transaction(message):
      logging.debug('transaction looks invalid, ignoring')
      return

    pwtxid = self.oracle.btc.add_multisig_address(message['req_sigs'], message['pubkey_list'])

    if LockedPasswordTransaction(self.oracle.db).get_by_pwtxid(pwtxid):
      logging.debug('pwtxid/multisig address already in use. did you resend the same request?')
      return

    reply_msg = { 'operation' : 'pricecheck_created',
        'pwtxid' : pwtxid,
        'in_reply_to' : message['message_id'] }

    logging.debug('broadcasting reply')
    self.oracle.communication.broadcast("pricecheck created for %s" % pwtxid, json.dumps(reply_msg))

    LockedPasswordTransaction(self.oracle.db).save({'pwtxid':pwtxid, 'json_data':json.dumps(message)})

    locktime = int(message['locktime'])

    logging.debug("awaiting %r" % datetime.datetime.fromtimestamp(locktime).strftime('%Y-%m-%d %H:%M:%S'))

    message['pwtxid'] = pwtxid

    self.oracle.task_queue.save({
        "operation": 'pricecheck_create',
        "json_data": json.dumps(message),
        "done": 0,
        "next_check": int(locktime)
    })


  def handle_task(self, task):
    message = json.loads(task['json_data'])

    response = safe_read("https://www.bitstamp.net/api/ticker/", 10)
    if not response:
      if not 'retries_number' in message:
        message['retries_number'] = 0

      if message['retries_number'] > 10:
        return

      message['retries_number'] += 1
      self.oracle.task_queue.save({
          "operation": 'pricecheck_create',
          "json_data": json.dumps(message),
          "done": 0,
          "next_check": int(task['locktime']) + 600
      })

    response_dict = json.loads(response)

    price = Decimal(response_dict['last'])
    expected_price = Decimal(message['price'])

    if price > expected_price:
      return_address = message['return_if_greater']
    else:
      return_address = message['return_if_lesser']

    message['return_address'] = return_address

    future_transaction = self.try_prepare_raw_transaction(message)
    assert(future_transaction is not None) # should've been verified gracefully in handle_request

    logging.debug('transaction ready to be signed')

    self.oracle.signer.sign(future_transaction, message['pwtxid'], message['prevtxs'], message['req_sigs'])
