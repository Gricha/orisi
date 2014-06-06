from settings_local import (
    BITCOIND_RPC_USERNAME,
    BITCOIND_RPC_PASSWORD,
    BITCOIND_RPC_HOST,
    BITCOIND_RPC_PORT)

import json
import jsonrpclib

class BitcoinClient:

  def __init__(self):
    self.connect()

  def connect(self):
    self.server = jsonrpclib.Server('http://{0}:{1}@{2}:{3}'.format(
        BITCOIND_RPC_USERNAME,
        BITCOIND_RPC_PASSWORD,
        BITCOIND_RPC_HOST,
        BITCOIND_RPC_PORT))

  def keep_alive(self, fun):
    def ping_and_reconnect(*args, **kwargs):
      try:
        self.server.ping()
      except:
        self.connect()
      return fun(*args, **kwargs)
    return ping_and_reconnect

  @keep_alive
  def sing_transaction(self, transaction):
    #TODO: SIGN_TRANSACTION RETURN: NEW SIGNED TRANSACTION
    return transaction

  @keep_alive
  def is_valid_transaction(self, transaction):
    #TODO: if transaction is valid (it is in fact a transaction and not a stupid string or so)
    # Especially: check wether current signatures on transaction are valid
    return True

  @keep_alive
  def get_inputs_outputs(self, transaction):
    #TODO: Assumes to get inputs and outputs for transaction
    #PLS GIMME JSON
    return json.dumps({"placeholder":"hehe"})

  @keep_alive
  def get_multisig_sender_address(self, transaction):
    #TODO: transaction as it's input should have multisig transaction,
    # This method should get it (i tried to figure it out and don't know how)
    # http://bitcoin.stackexchange.com/questions/7838/why-does-gettransaction-report-me-only-the-receiving-address
    return "3aabb"